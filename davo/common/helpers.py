import getpass
import logging

import keyring

from . import settings

logger = logging.getLogger(__name__)


def command_config(key, value=None, enter_pass=False, commit=False):
    if not value and enter_pass:
        value = getpass.getpass('Enter value: ')

    if value is None:
        value = keyring.get_password(settings.KEYRING_SERVICE, key)
        if isinstance(value, str):
            value = '{}***{}'.format(value[0], value[-1])

        logger.info('keyring: password value for: `%s`: `%s`', key, value)
        return

    if commit:
        keyring.set_password(settings.KEYRING_SERVICE, key, value)

    logger.info('keyring: password set for: `%s`', key)
