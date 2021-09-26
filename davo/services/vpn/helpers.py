import os

import davo.utils

from . import handlers, utils


def connect(config_root, account_name=None):
    conf = davo.utils.conf.load_yaml_config(
        os.path.join(config_root, 'vpn.yaml'))

    conf = davo.utils.conf.fix_config_paths(conf)

    kp = davo.utils.conf.load_kp(conf['keepass_db_path'])
    conf = davo.utils.conf.fix_config_secrets(kp, conf, mask=False)

    account = utils.get_account(conf, account_name)
    if account.get('handler') == 'openvpn':
        handlers.connect_openvpn(account)

    elif account.get('handler') == 'openconnect':
        handlers.connect_openconnect(account)

    else:
        raise davo.errors.Error(
            'Unknown handler: {}'.format(account.get('handler')))
