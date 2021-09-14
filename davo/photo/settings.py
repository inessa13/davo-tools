LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'console': {
            'format': '[%(asctime)s] %(levelname).1s %(message)s',
            'datefmt': '%Y%m%d %H%M%S',
        },
        'stream': {
            'format': '%(message)s',
            'datefmt': '%Y%m%d %H%M%S',
        },
    },
    'handlers': {
        'stream': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'stream',
        },
    },
    'loggers': {
        '': {
            'handlers': ['stream'],
            'propagate': False,
            'level': 'INFO',
        },
    }
}
