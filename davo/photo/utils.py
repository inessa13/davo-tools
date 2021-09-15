import datetime
import os
import re

from . import errors, replace_classes


def iter_files(path, recursive=False):
    if os.path.isdir(path):
        if recursive:
            for dir_path, __, file_names in os.walk(path):
                for file_ in file_names:
                    yield os.path.join(dir_path, file_)
        else:
            for file_ in os.listdir(path):
                yield os.path.join(path, file_)

    elif os.path.isfile(path):
        yield path

    else:
        raise errors.UserError('Invalid path {}'.format(path))


def date_as_path(path):
    st_ctime = datetime.datetime.fromtimestamp(os.path.getmtime(path))
    sub_root = os.path.join(
        st_ctime.strftime('%Y'),
        st_ctime.strftime('%m'),
        st_ctime.strftime('%d'),
    )
    root, base = os.path.split(path)
    return os.path.join(root, sub_root), sub_root, base


def date_as_name(path, index, prefix='IMG_'):
    st_ctime = datetime.datetime.fromtimestamp(os.path.getmtime(path))
    if '.' in path:
        ext = '.' + path.rsplit('.', 1)[1]
    else:
        ext = ''

    return '{}{}_{:03d}{}'.format(
        prefix, st_ctime.strftime('%Y%m%d'), index, ext)


def split_ext(basename):
    if '.' in basename:
        basename, ext = basename.rsplit('.', 1)
        ext = '.' + ext
    else:
        ext = ''

    return basename, ext


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

    basename = re.sub(pattern, replace, basename)
    return basename


def get_known_pattern(pattern):
    if not replace_classes.PATTERNS.get(pattern):
        return None
    options = replace_classes.PATTERNS[pattern]
    return options['pattern'], options['replace']
