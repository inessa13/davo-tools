# PYTHON_ARGCOMPLETE_OK
import argparse
import logging
import logging.config
import os

import argcomplete

from . import __version__, errors, helpers, settings

logger = logging.getLogger(__name__)


def init_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '-V', '--version',
        action='version',
        version='%(prog)s ' + __version__,
        help='show version and exit')

    subparsers = parser.add_subparsers(title='list of commands')

    cmd = subparsers.add_parser('tree', help='move files into tree struct')
    cmd.set_defaults(func=_command_tree)
    cmd.add_argument('path', nargs='?', default=os.getcwd())
    cmd.add_argument(
        '-r', '--reverse', action='store_true', help='reverse tree to flat')
    cmd.add_argument('-d', '--dry', action='store_true', help='no-commit mode')

    choices_output = ('-', 'C', 'T')
    cmd = subparsers.add_parser('rename', help='rename files by regexp')
    cmd.set_defaults(func=_command_regexp)
    cmd.add_argument('path', nargs='?', default=os.getcwd())
    cmd.add_argument(
        '-p', '--pattern', action='store', default='.*', help='search pattern')
    cmd.add_argument('-r', '--replace', action='store', help='replace pattern')
    cmd.add_argument(
        '-o', '--output', action='store', choices=choices_output, default='T',
        help='replace pattern')
    cmd.add_argument('-d', '--dry', action='store_true', help='no-commit mode')

    cmd = subparsers.add_parser('thumbnail', help='prepare thumbnails')
    cmd.set_defaults(func=_command_thumbnail)
    cmd.add_argument('path', nargs='?', default=os.getcwd())
    cmd.add_argument('-d', '--dry', action='store_true', help='no-commit mode')
    cmd.add_argument(
        '-s', '--size', action='store', type=int, default=120, help='max size')
    cmd.add_argument('-r', '--recursive', action='store_true', help='max size')

    cmd = subparsers.add_parser(
        'iphone-clean-live', help='clean iphone live photo .mov files')
    cmd.set_defaults(func=_command_clean_live)
    cmd.add_argument('path', nargs='?', default=os.getcwd())
    cmd.add_argument('-d', '--dry', action='store_true', help='no-commit mode')
    cmd.add_argument('-r', '--recursive', action='store_true', help='max size')

    cmd = subparsers.add_parser('search-copies', help='search file copies')
    cmd.set_defaults(func=_command_search_copy)
    cmd.add_argument('file')
    cmd.add_argument('path', nargs='?', default=os.getcwd())
    cmd.add_argument('-r', '--recursive', action='store_true', help='max size')

    return parser


def _command_tree(namespace):
    if namespace.reverse:
        helpers.command_tree_reverse(
            root=namespace.path,
            commit=not namespace.dry,
        )
    else:
        helpers.command_tree(
            root=namespace.path,
            commit=not namespace.dry,
        )


def _command_regexp(namespace):
    helpers.command_regexp(
        root=namespace.path,
        pattern=namespace.pattern,
        replace=namespace.replace,
        output=namespace.output,
        commit=not namespace.dry,
    )


def _command_clean_live(namespace):
    helpers.command_live(
        root=namespace.path,
        recursive=namespace.recursive,
        commit=not namespace.dry,
    )


def _command_thumbnail(namespace):
    helpers.command_thumbnail(
        root=namespace.path,
        size=namespace.size,
        recursive=namespace.recursive,
        commit=not namespace.dry,
    )


def _command_search_copy(namespace):
    helpers.command_search_copy(
        root=namespace.path,
        source_file=namespace.file,
        recursive=namespace.recursive,
    )


def main():
    logging.config.dictConfig(settings.LOGGING)

    parser = init_parser()
    argcomplete.autocomplete(parser)
    namespace = parser.parse_args()

    try:
        if getattr(namespace, 'func', None):
            namespace.func(namespace)
        else:
            parser.print_help()

    except KeyboardInterrupt:
        logger.warning('interrupted')

    except errors.UserError as exc:
        logger.warning(exc.args[0])


if __name__ == '__main__':
    main()
