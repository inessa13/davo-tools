# PYTHON_ARGCOMPLETE_OK
import argparse
import logging.config
import os

import davo.utils.cli
from davo import constants, utils, version

from . import conf, const, handlers, utils

logger = logging.getLogger(__name__)


def _command(command_name, commands):
    if isinstance(commands, dict):
        return commands.get(command_name, command_name)

    return command_name


def init_parser(parser=None, subparsers=None, commands=()):
    if parser is None:
        parser = argparse.ArgumentParser()

    parser.add_argument(
        '-V', '--version',
        action='version',
        version='%(prog)s ' + version.__version__,
        help='show version and exit')

    p_recursive = argparse.ArgumentParser(add_help=False)
    p_recursive.add_argument(
        '-r', '--recursive', action='store_true', help='recursive scan')

    p_root = argparse.ArgumentParser(add_help=False)
    p_root.add_argument('path', nargs='?', default=os.getcwd())

    if subparsers is None:
        subparsers = parser.add_subparsers(title='list of commands')

    if not commands or 'config' in commands:
        name = _command('config', commands)
        cmd = subparsers.add_parser(name, help='show/edit config')
        cmd.set_defaults(func=handlers.on_config)
        cmd.add_argument(
            '--local',
            action='store_true',
            help='show/edit local config; by default global')

    if not commands or 'info' in commands:
        name = _command('info', commands)
        cmd = subparsers.add_parser(name, help='show additional info')
        cmd.set_defaults(func=handlers.on_info)
        cmd.add_argument(
            'topic',
            nargs='?',
            choices=('topics',) + tuple(const.TOPICS),
            default='topics',
            action='store',
            help='topic')

    if not commands or 'init' in commands:
        name = _command('init', commands)
        cmd = subparsers.add_parser(name, help='init project')
        cmd.set_defaults(func=handlers.on_init)
        cmd.add_argument(
            'bucket', action='store', help='bucket for sync')

    if not commands or 'buckets' in commands:
        name = _command('buckets', commands)
        cmd = subparsers.add_parser(name, help='list buckets')
        cmd.set_defaults(func=handlers.on_list_buckets)

    if not commands or 'list' in commands:
        name = _command('list', commands)
        cmd = subparsers.add_parser(
            name,
            parents=[p_recursive],
            formatter_class=utils.Formatter,
            help='list files')
        cmd.set_defaults(func=handlers.on_list)
        cmd.add_argument(
            '-b', '--bucket', action='store', help='bucket')
        cmd.add_argument(
            '-p', '--path',
            action='store', type=str, help='path to compare')
        cmd.add_argument(
            '-R', '--region', action='store', help='s3 region')
        cmd.add_argument(
            '-l', '--limit',
            action='store', default=10, type=int, help='output limit')

    common_diff = argparse.ArgumentParser(
        add_help=False, parents=[p_root, p_recursive])
    common_diff.add_argument(
        '-a', '--all',
        action='store_true', help='use all modes. ignores -m')
    common_diff.add_argument(
        '-b', '--brief', action='store_true', help='brief diff')
    common_diff.add_argument(
        '-i', '--ignore-case',
        action='store_true', help='ignore file path case')
    common_diff.add_argument(
        '-5', '--md5', action='store_true', help='compare file content')

    common_diff.add_argument(
        '--force-upload',
        action='store_true',
        help='data transfer direction force change to upload')
    common_diff.add_argument(
        '--force-download',
        action='store_true',
        help='data transfer direction force change to download')

    common_diff.add_argument(
        '-m', '--modes',
        action='store', default=constants.STATES_DIFF_ALL,
        help='modes of comparing (by default all diff states)')
    common_diff.add_argument(
        '-f', '--file-types',
        action='store',
        metavar='TYPES',
        help='file types (extension) for compare')
    common_diff.add_argument('--no-cache', action='store_true')
    common_diff.add_argument('-v', '--verbose', action='store_true')

    if not commands or 'diff' in commands:
        name = _command('diff', commands)
        cmd = subparsers.add_parser(
            name,
            parents=[common_diff],
            formatter_class=utils.Formatter,
            help='diff local and remote')
        cmd.set_defaults(func=handlers.on_diff)

    if not commands or 'upload' in commands:
        name = _command('upload', commands)
        cmd = subparsers.add_parser(name, help='upload file')
        cmd.set_defaults(func=handlers.on_upload)
        cmd.add_argument('path', action='store', help='path to upload')
        cmd.add_argument(
            '-f', '--force', action='store_true', help='force upload')
        cmd.add_argument(
            '-r', '--recursive', action='store_true', help='list recursive')

    if not commands or 'update' in commands:
        name = _command('update', commands)
        cmd = subparsers.add_parser(
            name,
            parents=[common_diff],
            formatter_class=utils.Formatter,
            help='update local or remote')
        cmd.set_defaults(func=handlers.on_update)
        cmd.add_argument(
            '-l', '--limit',
            action='store',
            default=0,
            metavar='L',
            type=int,
            help='process limit')
        cmd.add_argument(
            '-t', '--threads',
            action='store',
            default=0,
            type=int,
            help='threads count')
        cmd.add_argument(
            '-q', '--quiet',
            action='store_true', help='quiet (no interactive)')
        cmd.add_argument(
            '-U', '--upload',
            action='store_true', help='confirm upload action')
        cmd.add_argument(
            '-D', '--download',
            action='store_true', help='confirm download action')
        cmd.add_argument(
            '-R', '--rename-remote',
            action='store_true', help='confirm rename remote file')
        cmd.add_argument(
            '-L', '--rename-local',
            action='store_true', help='confirm rename local file')
        cmd.add_argument(
            '--replace-upload',
            action='store_true', help='confirm replace on upload')
        cmd.add_argument(
            '--replace-download',
            action='store_true', help='confirm replace on download')
        cmd.add_argument(
            '--delete-local',
            action='store_true', help='confirm delete local file')
        cmd.add_argument(
            '--delete-remote',
            action='store_true', help='confirm delete remote file')

    if not commands or 'cache-clean' in commands:
        name = _command('cache-clean', commands)
        cmd = subparsers.add_parser(name, help='clean cache')
        cmd.set_defaults(func=handlers.on_cache_clean)

    if not commands or 'cache-update' in commands:
        name = _command('cache-update', commands)
        cmd = subparsers.add_parser(name, help='update cache')
        cmd.set_defaults(func=handlers.on_cache_update)

    return parser


def main():
    logging.config.dictConfig(davo.settings.LOGGING)
    conf.init()
    parser = init_parser()
    davo.utils.cli.run_parser(parser, use_completion=True)


if __name__ == '__main__':
    main()
