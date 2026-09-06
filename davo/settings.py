import os

__all__ = (
    "KEYRING_SERVICE",
    "KEYRING_USER_KEEPASS",
    "CONFIG_PATH",
    "CONFIG_PATH_DAVO_TOOLS",
    "PROJECT_CONFIG_NAME",
    "KEEPASS_PATH_DEFAULT",
    "LOGGING",
)

KEYRING_SERVICE = "davo-tools"
KEYRING_USER_KEEPASS = "keepass"
CONFIG_PATH = os.path.expanduser("~/Dropbox/etc/")
CONFIG_PATH_DAVO_TOOLS = os.path.join(CONFIG_PATH, "davo-tools.yaml")
PROJECT_CONFIG_NAME = ".davo-tools.yaml"
KEEPASS_PATH_DEFAULT = os.path.join(CONFIG_PATH, "pwd.kdbx")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "stdout": {
            "level": "INFO",
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout",
        },
    },
    "loggers": {
        "": {
            "handlers": ["stdout"],
            "propagate": False,
            "level": "INFO",
        },
    },
}
