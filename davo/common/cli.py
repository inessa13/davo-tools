# PYTHON_ARGCOMPLETE_OK
import argparse
import logging
import logging.config


from . import __version__, helpers, settings, utils

logger = logging.getLogger(__name__)


def init_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '-V', '--version',
        action='version',
        version='%(prog)s ' + __version__,
        help='show version and exit')

    subparsers = parser.add_subparsers(title='list of commands')

    cmd = subparsers.add_parser('config')
    cmd.add_argument('key', action='store')
    cmd.add_argument('value', nargs='?', action='store')
    cmd.add_argument('-p', '--enter-pass', action='store_true')
    cmd.set_defaults(func=lambda namespace: helpers.command_config(
        key=namespace.key,
        value=namespace.value,
        enter_pass=namespace.enter_pass,
        commit=True,
    ))

    return parser


def main():
    logging.config.dictConfig(settings.LOGGING)
    parser = init_parser()
    utils.cli.run_parser(parser)


if __name__ == '__main__':
    main()
