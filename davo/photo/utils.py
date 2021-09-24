import datetime
import hashlib
import logging
import os
import re

from PIL import Image

from . import const, errors, replace_classes

logger = logging.getLogger(__name__)


def iter_files(roo_path, recursive=False):
    if os.path.isdir(roo_path):
        if recursive:
            for dir_path, __, file_names in os.walk(roo_path):
                for file in file_names:
                    path = os.path.join(dir_path, file)
                    if not os.path.isfile(path):
                        continue
                    yield path
        else:
            for file in os.listdir(roo_path):
                path = os.path.join(roo_path, file)
                if not os.path.isfile(path):
                    continue
                yield path

    elif os.path.isfile(roo_path):
        yield roo_path

    else:
        raise errors.UserError('Invalid path {}'.format(roo_path))


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

    if '[' in replace:
        for code, method in replace_classes.CLASSES.items():
            if code in replace:
                replace = replace.replace(code, method(basename, context))

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


def file_hash(f_path):
    file_ = open(f_path, 'rb')
    hash_ = hashlib.md5()
    while True:
        block = file_.read(128)
        if not block:
            break
        hash_.update(block)
    file_.close()
    return hash_


def ensure_path(path, output=None, commit=False):
    if '/' not in path:
        return

    root, basename = os.path.split(path)
    if os.path.exists(root):
        return

    if output == const.OUTPUT_COMMAND:
        logger.info('mkdir -p %s', root)
    elif output == const.OUTPUT_TABLE:
        logger.info('%s', root)

    if commit:
        os.makedirs(root)


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
