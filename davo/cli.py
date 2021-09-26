# PYTHON_ARGCOMPLETE_OK
import argparse
import logging
import logging.config

from . import services, settings, utils, version

logger = logging.getLogger(__name__)


def init_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '-V', '--version',
        action='version',
        version='%(prog)s ' + version.__version__,
        help='show version and exit')

    subparsers = parser.add_subparsers(title='list of commands')

    cmd = subparsers.add_parser('keyring', help='get/set keyring records')
    cmd.add_argument('key', action='store')
    cmd.add_argument('value', nargs='?', action='store')
    cmd.add_argument('-p', '--enter-pass', action='store_true')
    cmd.set_defaults(func=lambda namespace: services.common.command_keyring(
        key=namespace.key,
        value=namespace.value,
        enter_pass=namespace.enter_pass,
        commit=True,
    ))

    cmd = subparsers.add_parser('file', help='file tools')
    services.photo.cli.init_parser(cmd, commands=(
        'convert',
        'rename',
        'iphone-clean-live',
        'search-duplicates',
    ))

    cmd = subparsers.add_parser('vpn', help='connect vpn')
    cmd.add_argument('account', nargs='?', action='store')
    cmd.set_defaults(func=lambda namespace: services.vpn.helpers.connect(
        config_root=settings.CONFIG_PATH,
        account_name=namespace.account,
    ))

    cmd = subparsers.add_parser(
        'cit', help='run git commands on multiple repos')
    services.git_tools.init_parser(cmd)

    cmd = subparsers.add_parser('s3', help='s3 tools')
    services.s3sync.cli.init_parser(cmd, commands=(
        'config',
        'buckets',
        'list',
        'diff',
        'update',
    ))

    return parser


def main():
    logging.config.dictConfig(settings.LOGGING)
    parser = init_parser()
    utils.cli.run_parser(parser, use_completion=True)


if __name__ == '__main__':
    main()
