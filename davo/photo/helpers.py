import logging
import os

from PIL import Image

from . import utils

logger = logging.getLogger(__name__)


def command_move(root, commit=False):
    sub_root_set = set()
    for file in utils.iter_files(root, recursive=False):
        if not os.path.isfile(file):
            continue

        sub_root, sub, base = utils.date_as_path(file)
        if not os.path.exists(sub_root) and sub_root not in sub_root_set:
            logger.info('mkdir -p %s', sub)
            if commit:
                os.makedirs(sub_root)
            else:
                sub_root_set.add(sub_root)

        logger.info('mv %s %s', base, sub)
        if commit:
            os.rename(file, os.path.join(sub_root, base))


def command_thumbnail(root, size, recursive, commit=False):
    thumbnails_dir = '.thumbnails'
    thumbnails_root = os.path.join(root, thumbnails_dir)
    if not os.path.exists(thumbnails_root):
        logger.info('mkdir -p %s', thumbnails_root)
        if commit:
            os.makedirs(thumbnails_root)

    for file in utils.iter_files(root, recursive=recursive):
        if not os.path.isfile(file):
            continue
        try:
            image = Image.open(file)
        except IOError:
            continue

        file_name = os.path.basename(file)
        logger.info(
            'convert -thumbnail %d %s %s',
            size, file_name, os.path.join(thumbnails_dir, file_name))
        if commit:
            image.thumbnail((size, size))
            image.save(os.path.join(thumbnails_root, file_name))
