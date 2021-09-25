import getpass
import logging

import keyring

from davo import settings

logger = logging.getLogger(__name__)


def command_keyring(key, value=None, enter_pass=False, commit=False):
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


# TODO: cmd: compare 2 dirs
# #!/usr/bin/env bash
#
# findex() {
#     find "$1" -type f -exec du {} + | awk -F '\t' '{print $2, "_ZDZ_", $1}'
# }
#
# dir1f=$(realpath "$1")
# dir2f=$(realpath "$2")
# dir1=$(dirname "$dir1f")
# dir2=$(dirname "$dir2f")
#
# #echo "$dir1f $dir1"
# #findex "$dir1f" | sed -e "s|$dir1f||g" | sort | head
# #echo "$dir2f $dir2"
# #findex "$dir2f" | sed -e "s|$dir2f||g" | sort | head
#
# # WITH SIZE
# #comm -12 <(findex "$dir1f" | sed -e "s|$dir1f||g" | sort ) <(findex "$dir2f" | sed -e "s|$dir2f||g" | sort) | awk -F' _ZDZ_' '{print $1}' > .commdir.sh
# # NAME ONLY
# comm -12 <(find "$dir1f" -type f | sed -e "s|$dir1f||g" | sort ) <(find "$dir2f" -type f | sed -e "s|$dir2f||g" | sort) > .commdir.sh
#
# cat .commdir.sh
# sed -i .commdir.sh -e 's|^/|rm "./|' && sed -i .commdir.sh -e 's/$/"/'
# chmod +x .commdir.sh
