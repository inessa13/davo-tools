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

    p_recursive = argparse.ArgumentParser(add_help=False)
    p_recursive.add_argument(
        '-r', '--recursive', action='store_true', help='recursive scan')

    p_dry = argparse.ArgumentParser(add_help=False)
    p_dry.add_argument(
        '-d', '--dry', action='store_true', help='no-commit mode')

    p_root = argparse.ArgumentParser(add_help=False)
    p_root.add_argument('path', nargs='?', default=os.getcwd())

    p_common = [p_root, p_recursive, p_dry]

    subparsers = parser.add_subparsers(title='list of commands')

    cmd = subparsers.add_parser(
        'tree', parents=[p_root, p_dry], help='move files into tree struct')
    cmd.add_argument(
        '-R', '--reverse', action='store_true', help='reverse tree to flat')
    cmd.set_defaults(func=lambda namespace: helpers.command_tree(
        root=namespace.path,
        reverse=namespace.reverse,
        commit=not namespace.dry,
    ))

    choices_output = ('-', 'C', 'T')
    cmd = subparsers.add_parser(
        'rename', parents=[p_root, p_dry], help='rename files by regexp')
    cmd.add_argument(
        '-p', '--pattern', action='store', default='.*', help='search pattern')
    cmd.add_argument('-R', '--replace', action='store', help='replace pattern')
    cmd.add_argument(
        '-o', '--output', action='store', choices=choices_output, default='T',
        help='replace pattern')
    cmd.add_argument('-c', '--copy', action='store_true')
    cmd.set_defaults(func=lambda namespace: helpers.command_regexp(
        root=namespace.path,
        pattern=namespace.pattern,
        replace=namespace.replace,
        output=namespace.output,
        copy=namespace.copy,
        commit=not namespace.dry,
    ))

    cmd = subparsers.add_parser(
        'thumbnail', parents=p_common, help='prepare thumbnails')
    cmd.add_argument(
        '-s', '--size', action='store', type=int, default=120, help='max size')
    cmd.add_argument('-t', '--type', help='convert type')
    cmd.set_defaults(func=lambda namespace: helpers.command_thumbnail(
        root=namespace.path,
        size=namespace.size,
        type_=namespace.type,
        recursive=namespace.recursive,
        commit=not namespace.dry,
    ))

    cmd = subparsers.add_parser('convert', parents=p_common)
    cmd.add_argument('-R', '--replace-pattern', default='[source].[ext]')
    cmd.add_argument('-D', '--delete-source', action='store_true')
    cmd.add_argument('-c', '--copy', action='store_true')
    cmd.add_argument('-t', '--thumbnail', type=int)
    cmd.set_defaults(func=lambda namespace: helpers.command_convert(
        root=namespace.path,
        replace=namespace.replace_pattern,
        recursive=namespace.recursive,
        copy=namespace.copy,
        delete=namespace.delete_source,
        thumbnail=namespace.thumbnail,
        commit=not namespace.dry,
    ))

    cmd = subparsers.add_parser(
        'iphone-clean-live', parents=p_common,
        help='clean iphone live photo .mov files')
    cmd.set_defaults(func=lambda namespace: helpers.command_live(
        root=namespace.path,
        recursive=namespace.recursive,
        commit=not namespace.dry,
    ))

    cmd = subparsers.add_parser(
        'search-copies', parents=p_common, help='search file copies')
    cmd.add_argument('file')
    cmd.set_defaults(func=lambda namespace: helpers.command_search_copy(
        root=namespace.path,
        source_file=namespace.file,
        recursive=namespace.recursive,
    ))

    cmd = subparsers.add_parser(
        'search-duplicates', parents=[p_root, p_recursive],
        help='search duplicates')
    cmd.add_argument('-m', '--md5', action='store_true', help='check md5 hash')
    cmd.set_defaults(func=lambda namespace: helpers.command_search_duplicates(
        root=namespace.path,
        md5=namespace.md5,
        recursive=namespace.recursive,
    ))

    return parser


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
