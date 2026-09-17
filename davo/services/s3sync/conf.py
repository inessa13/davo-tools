import logging
import os

import davo.errors
import davo.utils

from . import utils

logger = logging.getLogger(__name__)

_CONFIG = {
    "KEY_PATTERN": "{name} {storage} {size} {modified} {owner} {md5}",
    "KEY_PATTERN_NAME_LEN": 60,
    "THREAD_MAX_COUNT": 16,
    "ENDED_OUTPUT_MAX_COUNT": 4,
    "UPLOAD_CB_NUM": 10,
    "UPLOAD_FORMAT": "[{progress}>{left}]"
    "\t{progress_percent:3.0f}%"
    "\t{speed}\t{estimate}\t{elapsed}\t{info}",
    "BUCKET": None,
    "ALLOWED_REGIONS": None,
    "ACCESS_KEY": None,
    "SECRET_KEY": None,
    "PROJECT_ROOT": None,
    "LOCAL_CONFIG": None,
    "ALLOWED_EXTENSIONS": (),
    "CACHE_FILE_NAME": ".s3cache.db",
    "IGNORE": (),
    "LOAD_SECRETS": None,
}


def update(options):
    _CONFIG.update(options)


def is_init():
    return _CONFIG.get("_init", False)


def mark_init():
    _CONFIG["_init"] = True


def option(key, default=None, value=None):
    if value is not None:
        _CONFIG[key] = value
        return None
    return _CONFIG.get(key, default)


def get(key, default=None):
    return _CONFIG.get(key, default)


def load_config(
    start=None,
    load_secrets=None,
    mask=True,
    keepass_path=None,
    keepass_pwd=None,
):
    """Return the effective ``s3`` block from davo-tools configuration."""
    config, _user_path, project_path = davo.utils.conf.load_davo_config(start)
    config = config.get("s3", {})
    if not isinstance(config, dict):
        raise davo.errors.UserError("Invalid s3: expected a mapping")
    config = {key: value for key, value in config.items() if key in _CONFIG}
    if load_secrets is None:
        load_secrets = config.get("LOAD_SECRETS", True)
    if load_secrets and config:
        kp = davo.utils.conf.load_kp(path=keepass_path, password=keepass_pwd)
        config = davo.utils.conf.fix_config_secrets(kp, config, mask=mask)
    elif mask:
        config = davo.utils.conf.mask_config_secrets(config)
    if project_path:
        config["PROJECT_ROOT"] = str(project_path.parent)
        config["LOCAL_CONFIG"] = str(project_path)
    else:
        config["PROJECT_ROOT"] = os.getcwd()
    return config


def init(local_root=None, keepass_path=None, keepass_pwd=None):
    if is_init():
        return
    mark_init()
    update(
        load_config(
            local_root or utils.get_cwd(),
            mask=False,
            keepass_path=keepass_path,
            keepass_pwd=keepass_pwd,
        )
    )
