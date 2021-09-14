import datetime
import os

from . import errors


def iter_files(path):
    if os.path.isdir(path):
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
    return os.path.join(root, sub_root), base
