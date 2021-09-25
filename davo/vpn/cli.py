import logging
import os
import sys

import davo.common

from . import handlers, utils

logger = logging.getLogger(__name__)


@davo.common.utils.cli.run
def main():
    config_root = '/home/davo/Dropbox/etc/'
    account_name = sys.argv[1] if len(sys.argv) > 1 else None

    conf = davo.common.utils.conf.load_yaml_config(
        os.path.join(config_root, 'vpn.yaml'))

    conf = davo.common.utils.conf.fix_config_paths(conf)

    kp = davo.common.utils.conf.load_kp(conf['keepass_db_path'])
    conf = davo.common.utils.conf.fix_config_secrets(kp, conf)

    account = utils.get_account(conf, account_name)
    if account.get('handler') == 'openvpn':
        handlers.connect_openvpn(account)

    elif account.get('handler') == 'openconnect':
        handlers.connect_openconnect(account)

    else:
        raise davo.common.errors.Error(
            'Unknown handler: {}'.format(account.get('handler')))


if __name__ == '__main__':
    main()
