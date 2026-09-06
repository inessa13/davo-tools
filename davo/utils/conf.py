import logging
import os
import re
from copy import deepcopy
from pathlib import Path

import keyring
import keyring.errors
import yaml

from davo import errors, settings

logger = logging.getLogger(__name__)


def find_project_config(start=None):
    """Return the nearest project davo-tools configuration, if any."""
    current = Path(start or os.getcwd()).expanduser().resolve()
    if current.is_file():
        current = current.parent
    for directory in (current, *current.parents):
        candidate = directory / settings.PROJECT_CONFIG_NAME
        if candidate.is_file():
            return candidate
    return None


def _load_yaml_mapping(path, optional=False):
    """Load *path* as a YAML mapping, retaining the configuration root."""
    if path is None:
        return None
    path = Path(path).expanduser()
    if not path.exists():
        if optional:
            return None
        raise errors.UserError("Missing config: {}".format(path))
    try:
        contents = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise errors.UserError(
            "Invalid config {}: {}".format(path, exc)
        ) from exc
    if not isinstance(contents, dict):
        raise errors.UserError(
            "Invalid config {}: expected a mapping".format(path)
        )
    return fix_config_paths(contents, root={"root": str(path.parent)})


def deep_merge(base, override):
    """Merge mappings recursively; override scalars and lists wholesale."""
    result = deepcopy(base)
    for key, value in override.items():
        if isinstance(result.get(key), dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def load_davo_config(start=None, user_path=None):
    """Load the effective user and nearest-project davo-tools config.

    Each layer has its own path root: relative paths are expanded before the
    project layer is merged over the user layer.
    """
    user_path = Path(user_path or settings.CONFIG_PATH_DAVO_TOOLS).expanduser()
    project_path = find_project_config(start)
    user = _load_yaml_mapping(user_path, optional=True) or {}
    project = _load_yaml_mapping(project_path, optional=True) or {}
    return deep_merge(user, project), user_path, project_path

_P_KP_STR = r"kp:(?P<key>.*):(?P<attr>username|password|url)$"
_P_KR_STR = r"kr:((?P<service>.+):)?(?P<key>.+)$"


def load_yaml_config(conf_path):
    """
    Load yaml config to dict.

    :param str conf_path:

    :rtype: dict
    """
    if "~" in conf_path:
        conf_path = os.path.expanduser(conf_path)

    conf_root = os.path.dirname(conf_path)

    if not conf_path or not os.path.exists(conf_path):
        raise errors.Error("Missing config: {}".format(conf_path))

    with open(conf_path, "rt") as file:
        conf = yaml.safe_load(file)

    conf["root"] = conf_root
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
        if conf.startswith("./"):
            return os.path.join(root["root"], conf[2:])

    return conf


def mask_config_secrets(conf, key=None):
    if isinstance(conf, dict):
        return {
            key_: mask_config_secrets(value, key=key_)
            for key_, value in conf.items()
        }

    if isinstance(conf, list):
        return [mask_config_secrets(value, key=key) for value in conf]

    if isinstance(conf, str):
        if key in ("ACCESS_KEY", "SECRET_KEY"):
            return "{}***{}".format(conf[0], conf[-1])

    return conf


def fix_config_secrets(kp, conf, mask=True):
    """
    Fix/load secret values.
        kp:<keepass key>:<keepass entry attribute>
        kr:<keyring key>
        kr:<keyring service>:<keyring key>

    :param pykeepass.PyKeePass kp:
    :param dict conf:
    :param bool mask:

    :rtype: dict
    """
    if isinstance(conf, dict):
        return {
            key: fix_config_secrets(kp, value, mask=mask)
            for key, value in conf.items()
        }

    if isinstance(conf, list):
        return [fix_config_secrets(kp, value, mask=mask) for value in conf]

    if isinstance(conf, str):
        # load data from keepass
        if m := re.match(_P_KP_STR, conf):
            return _get_kp_value(
                kp, m.group("key"), m.group("attr"), mask=mask
            )

        # load data from keyring
        if m := re.match(_P_KR_STR, conf):
            return _get_kr_value(m.group("service"), m.group("key"), mask=mask)

    return conf


def load_kr_kp_pass():
    """
    Load keepass password from keyring.

    :raises errors.Error:

    :rtype: str
    """
    try:
        password = keyring.get_password(
            settings.KEYRING_SERVICE, settings.KEYRING_USER_KEEPASS
        )
    except keyring.errors.InitError:
        raise errors.Error("Keyring not inited")
    return password


def load_kp(path=None, password=None):
    """
    Load Keepass DB.

    :param str path:
    :param str password:

    :rtype: pykeepass.PyKeePass
    """
    try:
        import pykeepass  # noqa pylint: disable=C0415
        import pykeepass.exceptions  # noqa pylint: disable=C0415
    except ImportError:
        raise errors.Error(
            "Missing `pykeepass` package, please install it using "
            "`pip install pykeepass` or pip install davo-tools[keepass]`"
        )

    if path is None:
        path = settings.KEEPASS_PATH_DEFAULT

    if password is None:
        password = load_kr_kp_pass()
        if not password:
            raise errors.UserError(
                "Missing Keepass password in keyring, please init it using "
                "`davo-tools keyring keepass -p`"
            )

    try:
        return pykeepass.PyKeePass(path, password=password)
    except pykeepass.exceptions.CredentialsError:
        raise errors.UserError("Invalid credentials")


def load_kp_entry(kp, path, throw=False):
    """
    Load entry from Keepass DB.

    :param pykeepass.PyKeePass kp:
    :param str path:
    :param bool throw:

    :rtype: pykeepass.Entry
    """
    path = path.strip("/").split("/")
    if len(path) > 1:
        entry = kp.find_entries(path=path[:])
    else:
        entry = kp.find_entries(title=path[0], first=True)

    if throw and not entry:
        raise RuntimeError("Missing kp key: `{}`".format(path))

    return entry


def _get_kp_value(kp, kp_key, kp_attr, mask=True):
    """
    Get Keepass entry attribute value.

    :param pykeepass.PyKeePass kp:
    :param str kp_key:
    :param str kp_attr:
    :param bool mask:

    :rtype: str
    """
    entry = load_kp_entry(kp, kp_key)
    if not entry:
        logger.warning("Missing kp key: `{}`".format(kp_key))
        value = ""

    elif kp_attr == "username":
        value = entry.username

    elif kp_attr == "password":
        value = entry.password

    elif kp_attr == "url":
        value = entry.url

    else:
        value = entry.title

    if mask and value:
        value = "{}***{}".format(value[0], value[-1])

    return value


def _get_kr_value(kr_service, kr_key, mask=True):
    """
    Get value from keyring.

    :param str kr_service:
    :param str kr_key:
    :param bool mask:
    :rtype: str
    """
    if not kr_service:
        kr_service = settings.KEYRING_SERVICE

    value = keyring.get_password(kr_service, kr_key)

    if mask and value:
        value = "{}***{}".format(value[0], value[-1])

    return value
