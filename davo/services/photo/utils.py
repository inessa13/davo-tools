import datetime
import functools
import logging
import os
import re
import time

import exif
import pymediainfo
import reprint
from PIL import Image

import davo.utils

from . import replace_classes

logger = logging.getLogger(__name__)


def iter_files(root_path, recursive=False, sort=False):
    it = davo.utils.path.iter_files(root_path, recursive=recursive)

    if sort:
        return sorted(it)

    return it


def date_as_path(path):
    st_ctime = datetime.datetime.fromtimestamp(os.path.getmtime(path))
    sub_root = os.path.join(
        st_ctime.strftime('%Y'),
        st_ctime.strftime('%m'),
        st_ctime.strftime('%d'),
    )
    root, base = os.path.split(path)
    return os.path.join(root, sub_root), sub_root, base


def is_ext_same(path1, path2):
    return davo.utils.path.get_extension(
        path1, lower=True) == davo.utils.path.get_extension(path2, lower=True)


def replace_file_params(filename, pattern, replace, **context):
    root, basename = os.path.split(filename)
    if not (m := re.match(pattern, basename)):
        return

    match_dict = m.groupdict()
    if match_dict.get('source'):
        context['source'] = match_dict['source']
    context['source_match_groups'] = m.groups()
    context['source_match_group_dict'] = match_dict

    if '[' in replace:
        for code, method in replace_classes.CLASSES.items():
            if code in replace:
                replace = replace.replace(code, method(basename, context))
        for pattern_, method in replace_classes.CLASSES_RE.items():
            while m := re.search(pattern_, replace):
                replace = replace.replace(
                    m.group(0), method(basename, context, m))

    for index in range(1, 5):
        if f'\\{index}' in replace:
            replace = replace.replace(f'\\{index}', m.group(index))

    if pattern == '.*':
        basename = replace
    else:
        basename = re.sub(pattern, replace, basename)
    return basename


def get_known_pattern(pattern):
    if not replace_classes.PATTERNS.get(pattern):
        return None
    options = replace_classes.PATTERNS[pattern]
    return options['pattern'], options['replace']


def image_load_pil(path):
    try:
        return Image.open(path)
    except (IOError, ValueError) as exc:
        logger.warning('image load error: %s', exc)
        return None


def get_exif_with_details(filename, verbose=False):
    ext = davo.utils.path.get_extension(filename, lower=True)
    if ext not in {'jpg', 'jpeg'}:
        return None, 'extension'

    with open(filename, 'rb') as file:
        try:
            image = exif.Image(file)
        except Exception as exc:
            if verbose:
                logger.warning('exif parse error: %s', exc)
            return None, 'failed'

    if not image.has_exif:
        return None, 'missing'

    data = exif_get_all_tags(image, verbose=verbose)
    data = {
        key: value if type(value) in (str, float, int) else str(value)
        for key, value in data.items()
    }
    return data, 'ok'


def get_exif(filename):
    return get_exif_with_details(filename, verbose=False)[0]


def exif_get_all_tags(exif_image, verbose=False):
    """
    Fixed exif_image.get_all. Correctly handles ValueError.
    :param exif_image:
    :param bool verbose:
    :rtype: dict
    """
    data = {}
    for tag_name in exif_image.list_all():
        try:
            # with warnings.catch_warnings(action="ignore"):
            tag_value = exif_image.__getattr__(tag_name)
        except Exception as exc:
            if verbose:
                logger.warning(
                    'exif tag lad failed: %s, %s', tag_name,
                    str(exc).split('\n')[0],
                )
            continue

        data[tag_name] = tag_value
    return data


def get_media_info(path):
    data = pymediainfo.MediaInfo.parse(path).to_data()['tracks'][0]
    data = {key: value for key, value in data.items() if key not in {
        'count',
        'file_name',
        # 'file_size',
        'track_type',
        'folder_name',
        # 'stream_size',
        'complete_name',
        'file_extension',
        'kind_of_stream',
        'other_file_name',
        'other_file_size',
        'other_stream_size',
        'stream_identifier',
        'other_kind_of_stream',
        'proportion_of_this_stream',
        'count_of_stream_of_this_kind',
    }}
    return data


def image_convert(
    path_source, path_dest, thumbnail=None, save_exif=False, save_mtime=False,
    drop_alpha=False, commit=False,
):
    """
    Convert image with options (using PIL/pillow).

    :param str path_source:
    :param str path_dest:
    :param int thumbnail:
    :param bool save_exif:
    :param bool save_mtime:
    :param bool drop_alpha:
    :param bool commit:
    """
    image = image_load_pil(path_source)
    if not image:
        return

    if thumbnail:
        image.thumbnail((thumbnail, thumbnail))

    save_options = {}

    if save_exif and (exif_ := image.info.get('exif')):
        save_options['exif'] = exif_

    if drop_alpha:
        image = image.convert('RGB')

    if commit:
        image.save(path_dest, **save_options)
        if save_mtime:
            os.utime(path_dest, (
                os.path.getatime(path_source), os.path.getmtime(path_source)))


def int2frac(value):
    if not isinstance(value, (int, float)):
        return 0
    return max(1, min(100, value)) / 100


def each_file(elt=False, cycled=10):
    def deco(func):
        @functools.wraps(func)
        def wrap(root, recursive=False, silent=False, **kwargs):
            it = iter_files(root, recursive=recursive, sort=True)
            size = len(it)
            _t = time.time()
            use_elt = elt
            with reprint.output(initial_len=1) as output:
                if silent:
                    output = None
                    use_elt = False
                kwargs.update(
                    elt=use_elt,
                    cycled=cycled,
                    root=root,
                    silent=silent,
                )

                for i, inf in enumerate(it):
                    if output is not None:
                        output[0] = davo.utils.prnt.progress_bar(i, size, elt=_t)

                    ef_log_task_start(output, inf, **kwargs)

                    _t2 = time.time()
                    status = func(inf, output, **kwargs)
                    if status is None:
                        continue

                    ef_log_task_end(output, inf, status, _t2, **kwargs)

                if output is not None:
                    output[0] = davo.utils.prnt.progress_bar(size, size, elt=_t)
        return wrap
    return deco


def ef_log_task_start(output, inf, root='', cycled=10, elt=False, **_kwargs):
    if elt:
        davo.utils.prnt.rp_cycled(
            '{}:'.format(inf.replace(root, '.')),
            output,
            max_lines=cycled,
        )


def ef_log_task_end(output, inf, status, ts_start, root='', cycled=10, elt=False, **_kwargs):
    if elt:
        davo.utils.prnt.rp_cycled(
            '    {} {:.2f}s'.format(status, time.time() - ts_start),
            output,
            max_lines=cycled,
        )
    else:
        davo.utils.prnt.rp_cycled(
            '{}: {}'.format(inf.replace(root, '.'), status),
            output,
            max_lines=cycled,
        )


def ef_stop(status, verbose):
    """
    Used in pair with each_file().

    :param str status:
    :param bool verbose:
    :return:
    """
    # return status for output
    if verbose:
        return status
    # skip output if no-verbose mode
    return None


def ef_status(status, output, elt=False, root='', cycled=10, verbose=False, commit=False, **_kwargs):
    """
    Used in pair with each_file().

    :param bool|str status:
    :param dict output:
    :param bool elt:
    :param str root:
    :param int cycled:
    :param bool verbose:
    :param bool commit:
    :rtype: str
    """
    if commit:
        if isinstance(status, bool):
            status = 'succeed' if status else 'failed'
    else:
        if isinstance(status, str):
            command = status
        else:
            command = str(status)
        if root:
            command = command.replace(root, '')
        if elt:
            command = ' ' * 4 + command
        if verbose:
            davo.utils.prnt.rp_cycled(command, output, max_lines=cycled)
        status = 'dry-run'
    return status
