import hashlib
import os

from davo import errors


def iter_files(root_path, recursive=False):
    """
    Iterate file in path.

    :param str root_path:
    :param bool recursive:

    :rtype: Iterator
    """
    if os.path.isdir(root_path):
        if recursive:
            for dir_path, __, file_names in os.walk(root_path):
                for file in file_names:
                    path = os.path.join(dir_path, file)
                    if not os.path.isfile(path):
                        continue
                    yield path
        else:
            for file in os.listdir(root_path):
                path = os.path.join(root_path, file)
                if not os.path.isfile(path):
                    continue
                yield path

    elif os.path.isfile(root_path):
        yield root_path

    else:
        raise errors.UserError('Invalid path {}'.format(root_path))


def ensure(path, commit=False):
    """
    Ensure path exists.

    :param str path:
    :param bool commit:
    """
    if '/' not in path:
        return

    root, basename = os.path.split(path)
    if os.path.exists(root):
        return

    if commit:
        os.makedirs(root)


def file_hash(f_path):
    """
    Calculate file md5 hash.

    :param str f_path:
    :rtype: hashlib.md5
    """
    file_ = open(f_path, 'rb')
    hash_value = hashlib.md5()
    while True:
        block = file_.read(128)
        if not block:
            break
        hash_value.update(block)
    file_.close()
    return hash_value
