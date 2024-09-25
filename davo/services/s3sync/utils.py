import argparse
import dataclasses
import logging
import os
import re

import boto.s3
import boto.s3.bucket
import boto.s3.connection
import boto.s3.key

import davo.errors
from davo import settings, utils

from . import cache, conf

logger = logging.getLogger(__name__)


def file_path_info(path, project_root=None, current_root=None):
    if project_root is None:
        project_root = find_project_root() or get_cwd()
    if current_root is None:
        current_root = get_cwd()

    if not path or path == '.':
        path = current_root

    if os.path.isabs(path):
        if path == project_root:
            key = ''
            path = project_root.replace('\\', '/')
        else:
            path = path.replace('\\', '/')
            key = re.sub(
                '^{}/'.format(project_root.replace('\\', '/')), '', path)

    elif project_root == current_root:
        key = path.replace('\\', '/')
        path = os.path.join(project_root, path).replace('\\', '/')

    else:
        if current_root.startswith(project_root):
            current_root = current_root[len(project_root):].lstrip('\\/')
            if not path.startswith(current_root):
                path = os.path.join(current_root, path).replace('\\', '/')
            path = os.path.join(project_root, path)

        key = re.sub(
            '^{}/'.format(project_root.replace('\\', '/')), '', path)

    # TODO: fix for windows
    path = '/' + os.path.join(*path.split('/'))
    return path, key


def file_key(path):
    return file_path_info(path)[1]


def file_path(path):
    return file_path_info(path)[0]


def iter_local_path(path, recursive=False):
    yield from utils.path.iter_files(path, recursive=recursive)


def iter_remote_path(
    bucket, path, current_root=None, recursive=False, cached=False,
):
    local_path, key = file_path_info(
        path,
        project_root=conf.get('PROJECT_ROOT'),
        current_root=current_root,
    )
    if key and os.path.isdir(local_path) and key[-1] != '/':
        key += '/'

    params = {}
    if not recursive:
        params['delimiter'] = '/'

    if key:
        params['prefix'] = key.replace('\\', '/')

    if cached:
        return _iter_remote_cache(bucket, **params)

    return _iter_remote(bucket, **params)


@dataclasses.dataclass
class S3KeyCached:
    bucket: boto.s3.bucket.Bucket
    name: str
    size: int
    last_modified: str
    etag: str

    def _key(self):
        return self.bucket.get_key(self.name)

    def delete(self):
        self._key().delete()
        cache.cache.delete(self.name)
        cache.cache.flush()

    def copy(self, bucket, local_name, **kwargs):
        new_key = self._key().copy(bucket, local_name, **kwargs)
        if new_key:
            cache.cache.update(local_name, {
                'name': local_name,
                'size': self.size,
                'last_modified': self.last_modified,
                'etag': self.etag,
            })
            cache.cache.flush()
        return new_key

    def get_contents_to_filename(self, *args, **kwargs):
        return self._key().get_contents_to_filename(*args, **kwargs)

    def set_contents_from_file(self, *args, **kwargs):
        return self._key().set_contents_from_file(*args, **kwargs)


def _iter_remote_cache(bucket, prefix=None, delimiter=None):
    for data in cache.cache.select(prefix=prefix, delimiter=delimiter):
        yield S3KeyCached(bucket=bucket, **data)


def _iter_remote(bucket, **params):
    for key in bucket.list(**params):
        if (not isinstance(key, boto.s3.key.Key)
                or key.name[-1] == '/'):
            continue
        yield key


def update_cache(bucket, reprint=None):
    if cache.cache.total():
        cache.cache.clear()

    if reprint:
        reprint[0] = 'connecting...'

    it = iter_remote_path(
        bucket, path='', current_root='', recursive=True, cached=False)
    for index, s3key in enumerate(it):
        if reprint and index % 100 == 0:
            reprint[0] = 'loading... ({})'.format(index)
        cache.cache.update(s3key.name, {
            'name': s3key.name,
            'size': s3key.size,
            'last_modified': s3key.last_modified,
            'etag': s3key.etag,
        })

    if reprint:
        reprint[0] = 'saving...'

    cache.cache.flush()

    if reprint:
        reprint[0] = 'saved successfully'


def check_file_type(filename, types):
    if not types:
        return True

    filename = filename.lower()

    file_types = types.lower().split(',')
    if file_types[0][0] == '^':
        exclude = True
        file_types[0] = file_types[0][1:]
    else:
        exclude = False
    if exclude and filename.split('.')[-1] in file_types:
        return False
    if not exclude and filename.split('.')[-1] not in file_types:
        return False
    return True


def memoize(func):
    memo = {}

    def wrapper(*args, **kwargs):
        memo_key = ''

        if args:
            memo_key += ','.join(map(str, args))
        if kwargs:
            memo_key += ','.join(
                '{}:{}'.format(k, v) for k, v in kwargs.items())

        if memo_key not in memo:
            memo[memo_key] = func(*args, **kwargs)

        return memo[memo_key]

    return wrapper


@memoize
def find_project_root():
    return davo.utils.path.find_config_root(
        get_cwd(), settings.CONFIG_PATH_S3SYNC_LOCAL)


@memoize
def get_cwd():
    return os.getcwd()


class Formatter(argparse.HelpFormatter):
    def __init__(
            self, prog, indent_increment=2, max_help_position=30, width=None):
        super(Formatter, self).__init__(
            prog, indent_increment, max_help_position, width)

    def _format_action_invocation(self, action):
        if not action.option_strings:
            metavar, = self._metavar_formatter(action, action.dest)(1)
            return metavar

        parts = []
        # if the Optional doesn't take a value, format is:
        #    -s, --long
        if action.nargs == 0:
            parts.extend(action.option_strings)

        # if the Optional takes a value, format is:
        #    -s, --long ARGS
        else:
            default = action.dest.upper()
            args_string = self._format_args(action, default)
            for option_string in action.option_strings:
                parts.append(option_string)
            parts[-1] += ' %s' % args_string

        return ', '.join(parts)


def connect_host(region=boto.s3.connection.NoHostProvided):
    """
    Connect s3 host by region.

    :param str region:

    :rtype: boto.s3.connection.S3Connection
    """
    return boto.s3.connection.S3Connection(
        conf.get('ACCESS_KEY'),
        conf.get('SECRET_KEY'),
        host=region,
    )


def connect_bucket(name=None, regions=None):
    if name is None:
        name = conf.get('BUCKET')
        # регион грузим из настроек, только если сам бакет оттуда, если бакет
        #  это параметр из консоли, то регион не грузим.
        if regions is None:
            regions = conf.get('ALLOWED_REGIONS')

    if not name:
        raise davo.errors.UserError('Specify bucket or use valid root!')

    if regions and isinstance(regions, str):
        regions = regions.replace(' ', '').strip(',')
        if not regions:
            regions = []
        else:
            regions = regions.split(',')
    elif not regions:
        regions = []

    if len(regions) == 1:
        return _connect_bucket(name, regions[0])

    if not regions:
        logger.warning('Bucket `%s` region not set, using full lookup', name)

    for region in boto.s3.regions():
        logger.info('region %s...', region.endpoint)
        if (regions
                and region.name not in regions
                and region.endpoint not in regions):
            continue
        if (bucket := _connect_bucket(name, region.endpoint)) is not None:
            return bucket

    raise davo.errors.Error('Bucket not found')


def _connect_bucket(name, region_host):
    conn = connect_host(region_host)
    if conn is None:
        return None

    return conn.lookup(name, validate=True)


def output_finish(output, string):
    prefix = conf.get('THREAD_MAX_COUNT')
    total = prefix + conf.get('ENDED_OUTPUT_MAX_COUNT')
    if len(output) >= total:
        output[prefix:total] = output[prefix + 1:total] + [string]
    else:
        output.append(string)
