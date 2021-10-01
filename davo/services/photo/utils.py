import datetime
import logging
import os
import re

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


def _get_ext(basename):
    if '.' in basename:
        return basename.rsplit('.', 1)[1]
    return ''


def is_ext_same(path1, path2):
    return _get_ext(path1).lower() == _get_ext(path2).lower()


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
    except IOError as exc:
        logger.warning('image load error: %s', exc)
        return None


def image_convert(
    path_source, path_dest, thumbnail=None, save_exif=False, save_mtime=False,
    commit=False,
):
    """
    Convert image with options.

    :param str path_source:
    :param str path_dest:
    :param int thumbnail:
    :param bool save_exif:
    :param bool save_mtime:
    :param bool commit:
    """
    image = image_load_pil(path_source)
    if not image:
        return

    if thumbnail:
        image.thumbnail((thumbnail, thumbnail))

    save_options = {}

    if save_exif and (exif := image.info.get('exif')):
        save_options['exif'] = exif

    if commit:
        image.save(path_dest, **save_options)
        if save_mtime:
            os.utime(path_dest, (
                os.path.getatime(path_source), os.path.getmtime(path_source)))
