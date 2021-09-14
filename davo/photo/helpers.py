import logging
import os

from . import utils


logger = logging.getLogger(__name__)


def command_move(root, commit=False):
    sub_root_set = set()
    for file in utils.iter_files(root):
        if not os.path.isfile(file):
            continue

        sub_root, base = utils.date_as_path(file)
        if not os.path.exists(sub_root) and sub_root not in sub_root_set:
            logger.info('mkdir -p %s', sub_root)
            if commit:
                os.makedirs(sub_root)
            else:
                sub_root_set.add(sub_root)

        logger.info('mv %s %s', file, os.path.join(sub_root, base))
        if commit:
            os.rename(file, os.path.join(sub_root, base))
