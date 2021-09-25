import logging
import sys

from . import errors, handlers, utils

logger = logging.getLogger(__name__)


def main():
    account_name = sys.argv[1] if len(sys.argv) > 1 else None
    try:
        conf = utils.load_config('/home/davo/Dropbox/etc/vpn.yaml')
        account = utils.get_account(conf, account_name)
        if account.get('handler') == 'openvpn':
            handlers.connect_openvpn(account)
        else:
            handlers.connect_openconnect(account)

    except KeyboardInterrupt:
        logger.warning('Interrupted')

    except errors.UserError as exc:
        logger.warning(exc.args[0])

    except errors.BaseError as exc:
        logger.error(exc.args[0])


if __name__ == '__main__':
    main()
