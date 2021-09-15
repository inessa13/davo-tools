import datetime
import os

from . import errors


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
