import getpass
import glob
import os
import random

import pykeepass
import pykeepass.exceptions
import pyotp
import yaml

from . import errors


def load_config(conf_path):
    if '~' in conf_path:
        conf_path = os.path.expanduser(conf_path)

    conf_root = os.path.dirname(conf_path)

    if not conf_path or not os.path.exists(conf_path):
        raise RuntimeError('Missing vpn config: {}'.format(conf_path))

    with open(conf_path, 'rt') as file:
        conf = yaml.safe_load(file)

    conf['root'] = conf_root
    return conf


def _expand_path(path, conf):
    if not isinstance(path, str) or '%etc%' not in path:
        return path

    return path.replace('%etc%', conf['root'])


def get_account(conf, account_name=None):
    if not account_name:
        account_name = conf.get('default', 'default')

    if account_name not in conf.get('accounts', {}):
        raise RuntimeError('Unknown account: `{}`'.format(account_name))

    account = conf['accounts'][account_name]

    # validate and clean
    if not account.get('handler'):
        raise RuntimeError(
            'Unknown handler: {}'.format(account.get('handler')))
    account = {
        key: _expand_path(value, conf)
        for key, value in account.items()
    }

    return account


def load_account_secrets(account, storage_password=None):
    if storage_password is None:
        storage_password = getpass.getpass('storage password: ')

    try:
        kp = pykeepass.PyKeePass(
            account['keepass_db_path'], password=storage_password)
    except pykeepass.exceptions.CredentialsError:
        raise errors.UserError('Invalid credentials')

    entry = load_kp_entry(kp, account['keepass_key_pass'], throw=True)
    user = entry.username
    password = entry.password
    entry = load_kp_entry(kp, account['keepass_key_otp'], throw=True)
    otp_secret = entry.password
    otp = pyotp.TOTP(otp_secret).now()
    return user, password, otp


def load_kp_entry(kp, path, throw=False):
    path = path.strip('/').split('/')
    if len(path) > 1:
        entry = kp.find_entries(path=path[:])
    else:
        entry = kp.find_entries(title=path[0], first=True)

    if throw and not entry:
        raise RuntimeError('Missing vpn key: `{}`'.format(path))

    return entry


def create_temp_file(content, prefix='pf'):
    path = '/tmp/{}{}'.format(prefix, int(random.random() * 10 ** 6))
    os.system('echo "%s" > %s' % (content, path))
    return path


def remove_temp_file():
    for f in glob.glob('/tmp/tmp_pf*'):
        os.remove(f)
