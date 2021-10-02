import os

import davo.utils
from davo import settings

from . import utils

_CONFIG = {
    'KEY_PATTERN': '{name} {storage} {size} {modified} {owner} {md5}',
    'KEY_PATTERN_NAME_LEN': 60,
    'THREAD_MAX_COUNT': 16,
    'ENDED_OUTPUT_MAX_COUNT': 4,
    'UPLOAD_CB_NUM': 10,
    'UPLOAD_FORMAT':
        '[{progress}>{left}]'
        '\t{progress_percent:3.0f}%'
        '\t{speed}'
        '\t{estimate}'
        '\t{elapsed}'
        '\t{info}',
    'BUCKET': None,
    'ALLOWED_REGIONS': None,
    'ACCESS_KEY': None,
    'SECRET_KEY': None,
    'PROJECT_ROOT': None,
    'LOCAL_CONFIG': None,
    'ALLOWED_EXTENSIONS': (),
    'CACHE_FILE_NAME': '.s3cache.db',
}


def update(options):
    _CONFIG.update(options)


def is_init():
    return _CONFIG.get('_init', False)


def mark_init():
    _CONFIG['_init'] = True


def init(
    global_root=settings.CONFIG_PATH_S3SYNC, local_root=None,
    keepass_path=None, keepass_pwd=None,
):
    if is_init():
        return

    mark_init()

    config = load_config(
        global_root,
        load_secrets=True,
        mask=False,
        keepass_path=keepass_path,
        keepass_pwd=keepass_pwd,
    )
    update(config)

    if local_root or (local_root := utils.find_project_root()):
        _CONFIG['PROJECT_ROOT'] = local_root
        _CONFIG['LOCAL_CONFIG'] = os.path.join(
            _CONFIG['PROJECT_ROOT'], settings.CONFIG_PATH_S3SYNC_LOCAL)
        config = load_config(
            _CONFIG['LOCAL_CONFIG'],
            load_secrets=True,
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
    conf_path, load_secrets=False, mask=True, keepass_path=None,
    keepass_pwd=None,
):
    config = davo.utils.conf.load_yaml_config(conf_path)
    config = {key: value for key, value in config.items() if key in _CONFIG}
    if load_secrets:
        kp = davo.utils.conf.load_kp(path=keepass_path, password=keepass_pwd)
        config = davo.utils.conf.fix_config_secrets(kp, config, mask=mask)
    return config
