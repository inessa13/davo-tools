import datetime
import hashlib
import os
import re

from . import errors, replace_classes


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
