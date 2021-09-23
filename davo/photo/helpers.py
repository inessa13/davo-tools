import logging
import os
import re

from PIL import Image

from . import utils

logger = logging.getLogger(__name__)

P_LIVE = r'(:?IMG_\d{8}_\d{6} \()?IMG_(?P<num>\d+)\)?\.(?P<ext>.*)$'


def command_tree(root, commit=False):
    sub_root_set = set()
    for file in utils.iter_files(root, recursive=False):
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


def command_tree_reverse(root, commit=False):
    context = {}
    for file in utils.iter_files(root, recursive=True):
        sub_root, base = os.path.split(file)
        context.setdefault(base, []).append(file)

    if any(len(value) != 1 for value in context.values()):
        logger.error('there is duplicates, aborting')

    for base, files in context.items():
        file = files[0]
        logger.info('mv %s %s', file.replace(root + '/', ''), base)
        if commit:
            os.rename(file, os.path.join(root, base))


def command_regexp(root, pattern, replace, output, commit=False):
    if pattern_options := utils.get_known_pattern(pattern):
        pattern, replace = pattern_options

    index = 1
    for file in sorted(utils.iter_files(root, recursive=False)):
        root, base = os.path.split(file)
        new_name = utils.replace_file_params(
            file, pattern, replace, index=index)
        if not new_name:
            continue

        if output == 'C':
            logger.info('mv %s %s', base, new_name)
        elif output == 'T':
            logger.info('%-41s %s', base, new_name)

        if '/' in new_name:
            p, n = os.path.split(new_name)
            if not os.path.exists(p):
                if output == 'C':
                    logger.info('mkdir -p %s', p)
                elif output == 'T':
                    logger.info('%s', p)

                if commit:
                    os.makedirs(p)
        if commit:
            os.rename(file, os.path.join(root, new_name))

        index += 1


def command_live(root, recursive, commit=False):
    context = {}
    for file in utils.iter_files(root, recursive=recursive):
        root, basename = os.path.split(file)
        if not (m := re.match(P_LIVE, basename)):
            continue

        num = m.group('num')
        ext = m.group('ext').lower()

        context \
            .setdefault(root, {}) \
            .setdefault(num, {}) \
            .setdefault(ext, basename)

    for root, nums in context.items():
        for num, ext_s in nums.items():
            if len(ext_s) != 2 or set(ext_s.keys()) != {'mov', 'jpg'}:
                continue
            mov_path = ext_s['mov']
            logger.info('rm %s', mov_path)
            if commit:
                os.remove(os.path.join(root, mov_path))


def command_thumbnail(root, size, recursive, commit=False):
    thumbnails_dir = '.thumbnails'
    thumbnails_root = os.path.join(root, thumbnails_dir)
    if not os.path.exists(thumbnails_root):
        logger.info('mkdir -p %s', thumbnails_root)
        if commit:
            os.makedirs(thumbnails_root)

    for file in utils.iter_files(root, recursive=recursive):
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


def command_search_copy(root, source_file, recursive):
    source_hash = utils.file_hash(source_file)
    source_hash_digest = source_hash.digest()
    size = os.path.getsize(source_file)
    source_full = os.path.abspath(source_file)

    for file in utils.iter_files(root, recursive=recursive):
        if source_full == file or size != os.path.getsize(file):
            continue

        if (h := utils.file_hash(file)) and source_hash_digest == h.digest():
            logger.info('%s %s', file, source_hash.hexdigest())


def command_search_duplicates(root, md5, recursive):
    files = {}
    for file in utils.iter_files(root, recursive=recursive):
        files[file] = {
            'size': os.path.getsize(file),
        }

    for i in utils.iter_files(root, recursive=recursive):
        # file created after scan
        if i not in files:
            continue
        i_options = files[i]
        doubles = set()
        for j, j_options in files.items():
            if i == j or j_options['size'] != i_options['size']:
                continue
            doubles.add(j)

        if doubles and md5:
            doubles2 = set()
            if not i_options.get('hash'):
                i_options['hash'] = utils.file_hash(i)
            md5sum = i_options['hash']
            for j in doubles:
                j_options = files[j]
                if not j_options.get('hash'):
                    j_options['hash'] = utils.file_hash(i)
                if md5sum != j_options['hash']:
                    continue
                doubles2.add(j)

            if doubles2:
                doubles = doubles2

        if doubles:
            logger.info(
                '%s %s %s', len(doubles), i.replace(root, '.'),
                ','.join(doubles).replace(root, '.'),
            )
