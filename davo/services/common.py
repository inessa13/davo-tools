import argparse
import collections
import getpass
import logging
import os

import keyring

import davo.utils
from davo import settings, version

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
    root1, root2, states='-+~<>', show_all=False, show_equals=False,
    show_renames=False, ignore_case=False, check_size=False, check_md5=False,
    recursive=False, exclude=(), verbose=True,
):
    if show_all:
        states = '-+~<>r='
    else:
        if show_renames and 'r' not in states:
            states += 'r'
        if show_equals and '=' not in states:
            states += '='

    if 'r' in states and not check_size:
        raise davo.errors.UserError(
            'Can\t search renames without check_size option')

    files = davo.utils.path.compare_dirs(
        root1, root2,
        states=states,
        ignore_case=ignore_case,
        check_size=check_size,
        check_md5=check_md5,
        recursive=recursive,
        exclude=exclude,
        verbose=True,
    )

    if verbose:
        for key, data in files.items():
            print('{} {}'.format(data['state'], key))

    if files:
        counter = collections.Counter()
        for data in files.values():
            counter.update(data['state'])
        info = ', '.join(
            '{}: {}'.format(k, v) for k, v in counter.most_common())
        logger.info('%d differences (%s)', len(files), info)

    else:
        logger.info('%d differences', len(files))


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
        cmd.add_argument('root1')
        cmd.add_argument('root2', nargs='?', default=os.getcwd())
        cmd.add_argument(
            '-t', '--states', action='store', default='-+~<>')
        cmd.add_argument('-i', '--ignore-case', action='store_true')
        cmd.add_argument('-s', '--check-size', action='store_true')
        cmd.add_argument('-5', '--check-md5', action='store_true')
        cmd.add_argument('-r', '--recursive', action='store_true')
        cmd.add_argument('-v', '--verbose', action='store_true')
        cmd.add_argument('-a', '--show-all-states', action='store_true')
        cmd.add_argument('-e', '--show-equals', action='store_true')
        cmd.add_argument('-R', '--show-renames', action='store_true')
        cmd.add_argument('-x', '--exclude', action='append')
        cmd.set_defaults(func=lambda namespace: command_compare_dirs(
            root1=namespace.root1,
            root2=namespace.root2,
            states=namespace.states,
            show_all=namespace.show_all_states,
            show_equals=namespace.show_equals,
            show_renames=namespace.show_renames,
            ignore_case=namespace.ignore_case,
            check_size=namespace.check_size,
            check_md5=namespace.check_md5,
            recursive=namespace.recursive,
            exclude=namespace.exclude,
            verbose=namespace.verbose,
        ))
