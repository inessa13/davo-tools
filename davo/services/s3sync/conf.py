import logging
import os

import davo.utils
from davo import settings

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
    "\t{speed}"
    "\t{estimate}"
    "\t{elapsed}"
    "\t{info}",
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
    "GLOBAL_CONFIG": "~/Dropbox/etc/s3sync.yaml",
}


def update(options):
    _CONFIG.update(options)


def is_init():
    return _CONFIG.get("_init", False)


def mark_init():
    _CONFIG["_init"] = True


def init(
    global_root=settings.CONFIG_PATH_S3SYNC,
    local_root=None,
    keepass_path=None,
    keepass_pwd=None,
):
    if is_init():
        return

    mark_init()

    if local_root or (local_root := utils.find_project_root()):
        config = load_config_tree(
            local_root,
            global_root,
            mask=False,
            keepass_path=keepass_path,
            keepass_pwd=keepass_pwd,
        )
        update(config)


def option(key, default=None, value=None):
    if value is not None:
        _CONFIG[key] = value
        return

    return _CONFIG.get(key, default=default)


def get(key, default=None):
    return _CONFIG.get(key, default)


def load_config(
    conf_path,
    load_secrets=None,
    mask=True,
    keepass_path=None,
    keepass_pwd=None,
):
    config = davo.utils.conf.load_yaml_config(conf_path)
    config = {key: value for key, value in config.items() if key in _CONFIG}
    if load_secrets is None:
        load_secrets = config.get("LOAD_SECRETS", True)
    if load_secrets:
        kp = davo.utils.conf.load_kp(path=keepass_path, password=keepass_pwd)
        config = davo.utils.conf.fix_config_secrets(kp, config, mask=mask)
    elif mask:
        config = davo.utils.conf.mask_config_secrets(config)
    return config


def load_config_tree(local_root, global_root, **kwargs):
    config = {
        "PROJECT_ROOT": local_root,
        "LOCAL_CONFIG": os.path.join(
            local_root, settings.CONFIG_PATH_S3SYNC_LOCAL
        ),
    }

    config_l = load_config(config["LOCAL_CONFIG"], load_secrets=None, **kwargs)
    global_root = config_l.get("GLOBAL_CONFIG", global_root)
    if "~" in global_root:
        global_root = os.path.expanduser(global_root)
    if os.path.exists(global_root):
        config_g = load_config(
            global_root,
            load_secrets=config_l.get("LOAD_SECRETS", True),
            **kwargs,
        )
        config.update(config_g)
    else:
        logger.warning("Global config `%s` is missing", global_root)

    config.update(config_l)
    return config
