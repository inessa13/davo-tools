import logging
import os
import re

import keyring
import keyring.errors
import pykeepass
import pykeepass.exceptions
import yaml

from davo import errors, settings

logger = logging.getLogger(__name__)

_P_KP_STR = r'kp:(?P<key>[0-9a-zA-Z /]+)(:(?P<attr>username|password|url))?'


def load_yaml_config(conf_path):
    """
    Load yaml config to dict.

    :param str conf_path:

    :rtype: dict
    """
    if '~' in conf_path:
        conf_path = os.path.expanduser(conf_path)

    conf_root = os.path.dirname(conf_path)

    if not conf_path or not os.path.exists(conf_path):
        raise errors.Error('Missing vpn config: {}'.format(conf_path))

    with open(conf_path, 'rt') as file:
        conf = yaml.safe_load(file)

    conf['root'] = conf_root
    return conf


def fix_config_paths(conf, root=None):
    """
    Fix paths in config.
        ./ -> <base_dir>/

    :param dict conf:
    :param dict root:

    :rtype dict:
    """
    if root is None:
        root = conf

    if isinstance(conf, dict):
        return {
            key: fix_config_paths(value, root=root)
            for key, value in conf.items()
        }

    if isinstance(conf, list):
        return [fix_config_paths(value, root=root) for value in conf]

    if isinstance(conf, str):
        if conf.startswith('./'):
            return os.path.join(root['root'], conf[2:])

    return conf


# TODO: add keyring support "kr:"
def fix_config_secrets(kp, conf):
    """
    Fix/load secret values.
        kp:<keepass key>:<keepass entry attribute>

    :param pykeepass.PyKeePass kp:
    :param dict conf:

    :rtype: dict
    """
    if isinstance(conf, dict):
        return {
            key: fix_config_secrets(kp, value)
            for key, value in conf.items()
        }

    if isinstance(conf, list):
        return [fix_config_secrets(kp, value) for value in conf]

    if isinstance(conf, str):
        if m := re.match(_P_KP_STR, conf):
            return _get_kp_value(kp, m.group('key'), m.group('attr'))

    return conf


def load_kr_kp_pass():
    """
    Load keepass password from keyring.

    :raises errors.Error:

    :rtype: str
    """
    try:
        password = keyring.get_password(
            settings.KEYRING_SERVICE, settings.KEYRING_USER_KEEPASS)
    except keyring.errors.InitError:
        raise errors.Error('Keyring not inited')
    return password


def load_kp(path, password=None):
    """
    Load Keepass DB.

    :param str path:
    :param str password:

    :rtype: pykeepass.PyKeePass
    """
    if not path:
        path = settings.KEEPASS_PATH_DEFAULT

    if password is None:
        password = load_kr_kp_pass()
        if not password:
            raise errors.UserError(
                'Missing Keepass password in keyring, please init it using '
                '`davo-tools keyring keepass -p`'
            )

    try:
        return pykeepass.PyKeePass(path, password=password)
    except pykeepass.exceptions.CredentialsError:
        raise errors.UserError('Invalid credentials')


def load_kp_entry(kp, path, throw=False):
    """
    Load entry from Keepass DB.

    :param pykeepass.PyKeePass kp:
    :param str path:
    :param bool throw:

    :rtype: pykeepass.Entry
    """
    path = path.strip('/').split('/')
    if len(path) > 1:
        entry = kp.find_entries(path=path[:])
    else:
        entry = kp.find_entries(title=path[0], first=True)

    if throw and not entry:
        raise RuntimeError('Missing kp key: `{}`'.format(path))

    return entry


def _get_kp_value(kp, kp_key, kp_attr):
    """
    Get Keepass entry attribute value.

    :param pykeepass.PyKeePass kp:
    :param str kp_key:
    :param str kp_attr:

    :rtype: str
    """
    entry = load_kp_entry(kp, kp_key)
    if not entry:
        logger.warning('Missing kp key: `{}`'.format(kp_key))
        return ''

    if kp_attr == 'username':
        return entry.username

    elif kp_attr == 'password':
        return entry.password

    elif kp_attr == 'url':
        return entry.url

    return entry.title
