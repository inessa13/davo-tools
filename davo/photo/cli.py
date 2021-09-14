import argparse
import logging
import logging.config
import os

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

    cmd = subparsers.add_parser('move', help='move files')
    cmd.set_defaults(func=_command_move)
    cmd.add_argument('path', nargs='?', default=os.getcwd())
    cmd.add_argument('-d', '--dry', action='store_true', help='no-commit mode')

    return parser


def _command_move(namespace):
    helpers.command_move(
        root=namespace.path,
        commit=not namespace.dry,
    )


def main():
    if settings.LOGGING:
        logging.config.dictConfig(settings.LOGGING)

    parser = init_parser()
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
