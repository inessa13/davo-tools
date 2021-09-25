import os

KEYRING_SERVICE = 'davo-tools'
KEYRING_USER_KEEPASS = 'keepass'
KEEPASS_PATH_DEFAULT = os.path.expanduser('~/Dropbox/etc/pwd.kdbx')

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'stdout': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'stream': 'ext://sys.stdout'
        },
    },
    'loggers': {
        '': {
            'handlers': ['stdout'],
            'propagate': False,
            'level': 'INFO',
        },
    }
}
