import argparse
import getpass
import logging
import os

import keyring

import davo.utils
from davo import constants, settings, version

logger = logging.getLogger(__name__)


def command_keyring(key, value=None, enter_pass=False, commit=False):
    if not value and enter_pass:
        value = getpass.getpass('Enter value: ')

    if value is None:
        value = keyring.get_password(settings.KEYRING_SERVICE, key)
        if isinstance(value, str):
            value = '{}***{}'.format(value[0], value[-1])

        logger.info('keyring: password value for: `%s`: `%s`', key, value)
        return

    if commit:
        keyring.set_password(settings.KEYRING_SERVICE, key, value)

    logger.info('keyring: password set for: `%s`', key)


def command_compare_dirs(
    root1, root2, states='-+~<>r', show_all=False, show_equals=False,
    ignore_case=False, check_md5=False,
    recursive=False, exclude=(), verbose=True, sync_in=False, sync_out=False,
    force=False, commit=False,
):
    if sync_in and sync_out:
        raise davo.errors.UserError(
            'sync_in and sync_out are mutually exclusive')

    root = davo.utils.path.find_config_root(
        os.getcwd(), constants.LOCAL_CONF_PATH)
    if not root:
        raise davo.errors.UserError('No config root found')
    root = os.path.join(root, '')
    config = davo.utils.conf.load_yaml_config(
        os.path.join(root, constants.LOCAL_CONF_PATH))
    if verbose:
        print('config root: {}'.format(root))

    if root1 == '.':
        root1 = os.getcwd()

    root1 = os.path.join(root1, '')
    sub_path = root1.replace(root, '').lstrip('/')

    if root2:
        root2 = os.path.join(root2, '')
    else:
        root2 = config.get('dest_path')
        if '~' in root2:
            root2 = os.path.expanduser(root2)
        root2 = os.path.join(root2, sub_path, '')

    if not exclude:
        exclude = [constants.LOCAL_CONF_PATH]
    if config.get('ignore'):
        exclude += config['ignore']

    if show_all:
        states = '-+~<>r=?'
    else:
        if show_equals and '=' not in states:
            states += '='

    try:
        files = davo.utils.path.compare_dirs(
            root1, root2,
            states=states,
            ignore_case=ignore_case,
            check_size=True,
            check_md5=check_md5,
            recursive=recursive,
            exclude=exclude,
            verbose=True,
        )
    except KeyboardInterrupt:
        raise davo.errors.UserError('KeyboardInterrupt')

    if sync_in or sync_out:
        _make_dirs_sync(
            files,
            root1,
            root2,
            sync_in=sync_in,
            safe=not force,
            commit=commit,
        )

    else:
        if verbose:
            for key, data in files.items():
                print('{} {}\t{}'.format(
                    data.get('state', '?'),
                    key,
                    data.get('comment', ''),
                ))
        davo.utils.path.count_diff(files, verbose=True)


def _make_dirs_sync(files, root1, root2, sync_in=False, safe=True, commit=False):
    processed = 0
    for file, data in files.items():
        if sync_in:
            if data['state'] in ('+', '=', '?'):
                continue

            elif data['state'] == 'r':
                processed += davo.utils.path.sync_file_rename(
                    data['path'],
                    data['path_source'],
                    root2,
                    root1,
                    commit=commit,
                )

            elif data['state'] == '-':
                processed += davo.utils.path.sync_file(
                    data['path'], root1, root2, safe=safe, commit=commit)

        else:
            if data['state'] in ('-', '=', '?'):
                continue

            elif data['state'] == 'r':
                processed += davo.utils.path.sync_file_rename(
                    data['path_source'],
                    data['path'],
                    root1,
                    root2,
                    commit=commit,
                )

            elif data['state'] == '+':
                processed += davo.utils.path.sync_file(
                    data['path_source'],
                    root2,
                    root1,
                    safe=safe,
                    commit=commit,
                )

    if commit:
        print('processed {}/{}'.format(processed, len(files)))
    else:
        print('processed (dry-run) {}/{}'.format(processed, len(files)))


def init_parser(parser=None, subparsers=None, commands=()):
    if not parser:
        parser = argparse.ArgumentParser()
        parser.add_argument(
            '-V', '--version',
            action='version',
            version='%(prog)s ' + version.__version__,
            help='show version and exit')

    if subparsers is None:
        subparsers = parser.add_subparsers(title='list of commands')

    if 'keyring' in commands:
        cmd = subparsers.add_parser('keyring', help='get/set keyring records')
        cmd.add_argument('key', action='store')
        cmd.add_argument('value', nargs='?', action='store')
        cmd.add_argument('-p', '--enter-pass', action='store_true')
        cmd.set_defaults(func=lambda namespace: command_keyring(
            key=namespace.key,
            value=namespace.value,
            enter_pass=namespace.enter_pass,
            commit=True,
        ))

    if 'compare' in commands:
        cmd = subparsers.add_parser('compare', help='compare dirs')
        cmd.add_argument('root1', nargs='?', default=os.getcwd())
        cmd.add_argument('root2', nargs='?', default='')
        cmd.add_argument(
            '-t', '--states', action='store', default='-+~<>r')
        cmd.add_argument('-i', '--ignore-case', action='store_true')
        cmd.add_argument('-5', '--check-md5', action='store_true')
        cmd.add_argument('-r', '--recursive', action='store_true')
        cmd.add_argument('-v', '--verbose', action='store_true')
        cmd.add_argument('-a', '--show-all-states', action='store_true')
        cmd.add_argument('-e', '--show-equals', action='store_true')
        cmd.add_argument('-x', '--exclude', action='append')
        cmd.add_argument('--sync-in', action='store_true')
        cmd.add_argument('--sync-out', action='store_true')
        cmd.add_argument(
            '--force',
            action='store_true',
            help='force non-safe action like remove files',
        )
        cmd.add_argument('--commit', action='store_true')
        cmd.set_defaults(func=lambda namespace: command_compare_dirs(
            root1=namespace.root1,
            root2=namespace.root2,
            states=namespace.states,
            show_all=namespace.show_all_states,
            show_equals=namespace.show_equals,
            ignore_case=namespace.ignore_case,
            check_md5=namespace.check_md5,
            recursive=namespace.recursive,
            exclude=namespace.exclude,
            verbose=namespace.verbose,
            sync_in=namespace.sync_in,
            sync_out=namespace.sync_out,
            force=namespace.force,
            commit=namespace.commit,
        ))
