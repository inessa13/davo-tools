import collections
import datetime
import logging
import os
import pprint
import time

import boto.s3
import boto.s3.connection
import boto.s3.key
import reprint
import yaml

import davo.utils
from davo import errors, settings

from . import conf, const, workers, tasks, utils

logger = logging.getLogger(__name__)

_CONFIRM_PERMANENT = {}


def on_config(namespace):
    if namespace.local:
        local_root = utils.find_project_root()
        if not local_root:
            raise errors.UserError('Local config not found')
        config_path = os.path.join(
            local_root, settings.CONFIG_PATH_S3SYNC_LOCAL)
    else:
        config_path = settings.CONFIG_PATH_S3SYNC

    print('{}:'.format(config_path))
    config = conf.load_config(config_path, load_secrets=True, mask=True)
    if config:
        pprint.pprint(config)

    else:
        print('Config is empty')


def on_init(namespace):
    config_path = os.path.join(os.getcwd(), settings.CONFIG_PATH_S3SYNC_LOCAL)
    with open(config_path, 'w') as config_file:
        config = {'BUCKET': namespace.bucket}
        yaml.dump(config, config_file, default_flow_style=False)


def on_list_buckets(_namespace):
    conf.init()

    conn = utils.connect_host()
    for bucket in conn.get_all_buckets():
        logger.info(bucket.name)


def on_list(namespace):
    conf.init()

    bucket = utils.iter_remote_path(
        utils.connect_bucket(namespace.bucket, namespace.region),
        namespace.path,
        recursive=namespace.recursive)

    if not bucket:
        raise errors.UserError('Missing bucket')

    for index, key in enumerate(bucket):
        if index >= namespace.limit > 0:
            logger.info('list limit reached!')
            break
        _print_key(key)


def on_diff(namespace, print_details=True):
    conf.init()

    bucket = utils.connect_bucket()
    if not bucket:
        raise errors.UserError('missing bucket')

    if namespace.all:
        modes = '=+-<>r'
    else:
        modes = namespace.modes

    path = os.path.abspath(namespace.path)

    src_files = []
    for file_path in utils.iter_local_path(
            path, namespace.recursive):
        if not os.path.isfile(file_path):
            continue

        if not utils.check_file_type(file_path, namespace.file_types):
            continue

        key = utils.file_key(file_path)
        if namespace.ignore_case:
            key = key.lower()
        src_files.append((key, file_path))

    logger.info('%d local objects', len(src_files))

    remote_files = dict()

    ls_remote = utils.iter_remote_path(
        bucket, path, recursive=namespace.recursive)

    for file_ in ls_remote:
        if not isinstance(file_, boto.s3.key.Key) or file_.name[-1] == '/':
            continue
        if not utils.check_file_type(file_.name, namespace.file_types):
            continue

        key = file_.name
        if namespace.ignore_case:
            key = key.lower()

        remote_files[key] = dict(
            key=file_,
            name=file_.name,
            size=file_.size,
            modified=file_.last_modified,
            md5=file_.etag[1:-1],
            state='-',
            comment=[],
            local_path=utils.file_path(file_.name),
        )

    logger.info('%d remote objects', len(remote_files.keys()))

    if not src_files and not remote_files:
        return None

    logger.info('comparing...')
    for key, f_path in src_files:
        stat = os.stat(f_path)

        if key in remote_files:
            equal = True
            remote = remote_files[key]
            remote['local_path'] = f_path

            if stat.st_size != remote['size']:
                equal = False
                if remote['size']:
                    diff = stat.st_size * 100 / float(remote['size'])
                else:
                    diff = 0
                remote['comment'].append('size: {:.2f}%'.format(diff))

            elif namespace.md5:
                if davo.utils.path.file_hash(f_path) != remote['md5']:
                    equal = False
                    remote['comment'].append('md5: different')

            if equal:
                remote.update(state='=', comment=[])
            else:
                remote['local_size'] = stat.st_size
                local_modified = datetime.datetime.fromtimestamp(
                    stat.st_ctime).replace(microsecond=0)
                remote_modified = datetime.datetime.strptime(
                    remote['modified'], '%Y-%m-%dT%H:%M:%S.000Z')
                remote_modified += datetime.timedelta(hours=4)

                delta = local_modified - remote_modified
                if delta.days > 1:
                    remote['comment'].append(
                        'modified: remote {0} days older'.format(
                            delta.days))
                else:
                    remote['comment'].append('modified: {0}'.format(delta))

                if namespace.force_upload:
                    remote['state'] = '>'
                elif namespace.force_download:
                    remote['state'] = '<'
                elif local_modified > remote_modified:
                    remote['state'] = '>'
                else:
                    remote['state'] = '<'

            if remote['state'] not in modes:
                del remote_files[key]

        else:
            if '+' not in modes and 'r' not in modes:
                continue

            remote_files[key] = dict(
                local_size=stat.st_size,
                local_path=f_path,
                modified=stat.st_mtime,
                md5=None,
                state='+',
                comment=[],
            )
            if namespace.md5:
                remote_files[key]['md5'] = davo.utils.path.file_hash(
                    f_path)

    # find renames
    if 'r' in modes:
        to_del = []
        for key, new_data in remote_files.items():
            if new_data['state'] != '+':
                continue
            for name, data in remote_files.items():
                if data['state'] != '-':
                    continue
                if data['size'] != new_data['local_size']:
                    continue
                if namespace.md5 and data['md5'] != new_data['md5']:
                    continue
                remote_files[name].update(
                    state='r',
                    local_name=key,
                    local_size=new_data['local_size']
                )
                remote_files[name]['comment'].append(
                    'new: {0}'.format(key))
                to_del.append(key)
                break

        for key in to_del:
            del remote_files[key]

    remote_files = {
        k: v for k, v in remote_files.items() if v['state'] in modes
    }

    if print_details and not namespace.brief:
        keys = remote_files.keys()
        for key in keys:
            data = remote_files[key]
            print('{} {} {}'.format(
                data['state'],
                key,
                ', '.join(data.get('comment', []))))

    davo.utils.path.count_diff(remote_files, verbose=True)

    return bucket, remote_files


def on_upload(namespace):
    conf.init()

    bucket = utils.connect_bucket()
    if not bucket:
        raise errors.UserError('missing bucket')

    path = os.path.abspath(namespace.path)

    files = {}
    for local_path in utils.iter_local_path(
            path, namespace.recursive):
        if not os.path.isfile(local_path):
            continue

        key = utils.file_key(local_path)
        files[key] = {
            'local_size': os.stat(local_path).st_size,
            'local_path': local_path,
        }

    for remote in utils.iter_remote_path(
            bucket, path, namespace.recursive):
        if remote.name in files:
            files[remote.name]['key'] = remote

    conflicts = 0
    pool = workers.ThreadPool(conf.get('THREAD_MAX_COUNT'), auto_start=False)

    for key, data in files.items():
        if 'key' in data and namespace.force:
            task = tasks.ReplaceUpload()
        elif 'key' not in data:
            data['key'] = boto.s3.key.Key(bucket=bucket, name=key)
            task = tasks.Upload()
        else:
            conflicts += 1
            continue

        pool.add_task(task, bucket, key, data)

    if conflicts:
        print('{} remote paths exists, use force flag'.format(conflicts))

    with reprint.output(initial_len=conf.get('THREAD_MAX_COUNT')) as output:
        pool.start(output)
        pool.join()


def on_update(namespace):
    conf.init()
    if namespace.threads:
        conf.option('THREAD_MAX_COUNT', value=namespace.threads)

    bucket, files = on_diff(namespace, print_details=False)
    if not files:
        logger.error('no changes')
        return

    logger.info('processing...')

    _t = time.time()
    processed, size = 0, 0

    try:
        processed, size = _update(bucket, files, namespace)
    finally:
        delta = time.time() - _t
        if delta:
            speed = utils.humanize_size(size / delta)
            logger.info('average speed: %s', speed)

        logger.info(
            '%d actions processed, %d skipped',
            processed, len(files.keys()) - processed
        )


def _update(bucket, files, namespace):
    processed = 0
    size = 0

    pool = workers.ThreadPool(conf.get('THREAD_MAX_COUNT'))

    for name, data in files.items():
        action = None

        if data['state'] == '=':
            processed += 1
            continue

        elif data['state'] == '+':
            if namespace.upload:
                action = tasks.Upload()
            elif namespace.delete_local:
                action = tasks.DeleteLocal()
            elif namespace.quiet:
                continue
            else:
                act = _confirm_update(
                    name, data,
                    tasks.Upload(), tasks.DeleteLocal())
                if act == 'n':
                    continue
                else:
                    action = act

        elif data['state'] == '-':
            if namespace.download:
                action = tasks.Download()
            elif namespace.delete_remote:
                action = tasks.DeleteRemote()
            elif namespace.quiet:
                continue
            else:
                act = _confirm_update(
                    name, data,
                    tasks.Download(), tasks.DeleteRemote())

                if act == 'n':
                    continue
                action = act

        elif data['state'] == 'r':
            if _check(
                    name, data, namespace.quiet,
                    namespace.rename_remote):
                action = tasks.RenameRemote()
            elif _check(
                    name, data, namespace.quiet,
                    namespace.rename_local):
                action = tasks.RenameLocal()
            else:
                continue

        elif data['state'] == '>':
            if _check(
                    name, data, namespace.quiet,
                    namespace.replace_upload):
                action = tasks.ReplaceUpload()
            else:
                continue

        elif data['state'] == '<':
            if _check(
                    name, data, namespace.quiet,
                    namespace.replace_download):
                action = tasks.Download()
            else:
                continue

        if not action:
            logging.error('Unknown action')
            continue
        pool.add_task(action.init(bucket, name, data))
        processed += 1

        if isinstance(action, tasks.Download):
            size += data.get('size') or 0
        elif isinstance(action, (tasks.Upload, tasks.ReplaceUpload)):
            size += data.get('local_size') or 0

        if processed >= namespace.limit > 0:
            logger.info('list limit reached!')
            break

    with reprint.output(initial_len=conf.get('THREAD_MAX_COUNT')) as output:
        pool.start(output)
        pool.join()

    return processed, size


def _check(name, data, quiet, confirm):
    if confirm:
        return True
    if quiet:
        return False

    return _confirm_update(name, data, 'y') == 'y'


def _confirm_update(name, data, *values):
    assert values

    code = data['state']
    if code in _CONFIRM_PERMANENT:
        return _CONFIRM_PERMANENT[code]

    values_map = {str(value): value for value in values}

    if 'n' not in values_map:
        values_map['n'] = 'n'

    prompt_str = '{} {} {} ({} [all])? '.format(
        code, name,
        ', '.join(data.get('comment', [])),
        '/'.join(values_map.keys()),
    )

    input_data = []
    while not input_data or input_data[0] not in values_map:
        input_data = input(prompt_str)
        input_data = input_data.split(' ', 1)

    if len(input_data) > 1 and input_data[1] == 'all':
        _CONFIRM_PERMANENT[code] = values_map[input_data[0]]

    return values_map[input_data[0]]


def _print_key(key):
    name_len = conf.get('KEY_PATTERN_NAME_LEN')

    if len(key.name) < name_len:
        name = key.name.ljust(name_len, ' ')
    else:
        name = key.name[:name_len - 3] + '...'

    if isinstance(key, boto.s3.key.Key):
        params = {
            'name': name,
            'size': str(key.size).ljust(10, ' '),
            'owner': key.owner.display_name,
            'modified': key.last_modified,
            'storage': const.STORAGE_ALIASES.get(
                key.storage_class, '?'),
            'md5': key.etag[1:-1],
        }
    else:
        params = {
            'name': name,
            'size': '<DIR>'.ljust(10, ' '),
            'owner': '',
            'modified': '',
            'storage': '?',
            'md5': ''
        }

    pattern = conf.get('KEY_PATTERN')
    print(pattern.format(**params))
