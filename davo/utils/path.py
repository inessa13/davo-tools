import collections
import hashlib
import logging
import os
import re

from davo import constants, errors

logger = logging.getLogger(__name__)


def iter_files(root_path, recursive=False, exclude=()):
    """
    Iterate file in path.

    :param str root_path:
    :param bool recursive:
    :param tuple exclude:

    :rtype: Iterator
    """
    def _check(dir_, file_):
        path_ = os.path.join(dir_, file_)
        if not os.path.isfile(path_):
            return None
        if exclude:
            for excl in exclude:
                if excl.startswith('^'):
                    if re.match(excl, path_):
                        return None
                elif excl in path_:
                    return None
        return path_

    if os.path.isdir(root_path):
        if recursive:
            for dir_path, __, file_names in os.walk(root_path):
                for file in file_names:
                    path = _check(dir_path, file)
                    if path is None:
                        continue
                    yield path
        else:
            for file in os.listdir(root_path):
                path = _check(root_path, file)
                if path is None:
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


def _get_rel_path(root, path):
    return re.sub('^{}'.format(root), '', path).strip('/')


def _iter_file_options(
    root, recursive=False, ignore_case=False, check_size=False, exclude=(),
):
    for file_path in iter_files(root, recursive, exclude=exclude):
        # TODO: filters
        if not os.path.isfile(file_path):
            continue

        file_key = _get_rel_path(root, file_path)
        if ignore_case:
            file_key = file_key.lower()

        options = {
            'key': file_key,
            'path': file_path,
        }

        if check_size:
            stat = os.stat(file_path)
            options['size'] = stat.st_size
            options['modified'] = stat.st_mtime

        yield options


def _ensure_md5(file_options):
    if file_options.get('md5'):
        return
    # if not file_options.get('path'):
    #     return
    file_options['md5'] = file_hash(file_options['path'])


def compare_dirs(
    root1, root2, states=None, ignore_case=False, check_size=False,
    check_md5=False, recursive=False, exclude=(), verbose=False,
):
    if states is None:
        states = constants.STATES_DIFF_VALID

    files_src = []
    root1 = os.path.abspath(root1)
    for options in _iter_file_options(
            root1, recursive, ignore_case, check_size, exclude):
        files_src.append(options)

    if verbose:
        logger.info('%d files in %s', len(files_src), root1)

    files_dest = dict()
    for options in _iter_file_options(
            root2, recursive, ignore_case, check_size):
        options['state'] = constants.STATE_LOCAL_MISSING
        files_dest[options['key']] = options

    if verbose:
        logger.info('%d files in %s', len(files_dest), root2)

    if not files_src and not files_dest:
        return

    if verbose:
        logger.info('comparing...')

    for source in files_src:
        key_src = source['key']
        if key_src in files_dest:
            equal = True
            dest = files_dest[key_src]

            if check_size:
                if source['size'] != dest['size']:
                    equal = False

            if equal and check_md5:
                _ensure_md5(source)
                _ensure_md5(dest)
                if source['md5'] != dest['md5']:
                    equal = False

            if equal:
                dest['state'] = constants.STATE_EQUAL

            elif check_size:
                if source['modified'] > dest['modified']:
                    dest['state'] = constants.STATE_LOCAL_NEWER
                else:
                    dest['state'] = constants.STATE_LOCAL_OLDER
            else:
                dest['state'] = constants.STATE_DIFFERENT

        elif constants.STATE_LOCAL_NEW in states or constants.STATE_RENAMED in states:
            files_dest[key_src] = {
                'path': source['path'],
                'size': source.get('size'),
                'state': constants.STATE_LOCAL_NEW,
            }

    # find renames
    if constants.STATE_RENAMED in states:
        for key_new, data_new in files_dest.items():
            if data_new['state'] != constants.STATE_LOCAL_NEW:
                continue

            for key_missing, data_missing in files_dest.items():
                if data_missing['state'] != constants.STATE_LOCAL_MISSING:
                    continue

                if data_missing['size'] != data_new['size']:
                    continue

                if check_md5:
                    _ensure_md5(data_missing)
                    _ensure_md5(data_new)
                    if data_missing['md5'] != data_new['md5']:
                        continue

                data_missing.update({
                    'state': constants.STATE_RENAMED,
                    'path_new': data_new['path'],
                })
                # mark for remove from result
                data_new['state'] = constants.STATE_MARK_DELETE
                break

    return {
        key: options
        for key, options in files_dest.items()
        if options['state'] in states
    }


def count_diff(files, verbose=False):
    """
    Count files diff states. Compatible with .compare_dirs func result.

    :param dict files:
    :param bool verbose:

    :return: info
    :rtype: str
    """
    if not files:
        if verbose:
            logger.info('%d differences', len(files))
        return ''

    counter = collections.Counter()
    for data in files.values():
        counter.update(data['state'])
    info = ', '.join(
        '{}: {}'.format(k, v) for k, v in counter.most_common())

    if verbose:
        logger.info('%d differences (%s)', len(files), info)

    return info


def split3(filename):
    """
    Split file name into 3 item tuple.

    :param str filename:

    :return: root, name, extension
    :rtype: tuple
    """
    root, basename = os.path.split(filename)

    if '.' not in basename:
        return '', basename

    return root, *basename.rsplit('.', 1)


def get_extension(basename, lower=False):
    if '.' not in basename:
        return ''

    _root, _name, value = split3(basename)

    if lower:
        value = value.lower()

    return value


def get_filename_no_extension(filename, lower=False):
    _root, value, _ext = split3(filename)

    if lower:
        value = value.lower()

    return value
