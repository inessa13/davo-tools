import logging
import os
import re
import shutil

from PIL import Image

import davo.utils
from davo import errors

from . import utils

logger = logging.getLogger(__name__)

P_LIVE = r'(:?IMG_\d{8}_\d{6} \()?IMG_(?P<num>\d+)\)?\.(?P<ext>.*)$'


def command_tree(root, reverse, commit=False):
    if reverse:
        _command_tree_reverse(
            root=root,
            commit=commit,
        )
    else:
        _command_tree_straight(
            root=root,
            commit=commit,
        )


def _command_tree_straight(root, commit=False):
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


def _command_tree_reverse(root, commit=False):
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


def command_regexp(
    root, recursive, filters, exclude, pattern, replace, output, copy,
    skip_no_exif, limit=0, verbose=False, commit=False,
):
    if pattern_options := utils.get_known_pattern(pattern):
        pattern, replace = pattern_options

    mkdir_no_commit = set()

    index = 1
    for file_path in sorted(utils.iter_files(root, recursive=recursive)):
        file_root, base = os.path.split(file_path)

        if not re.match(pattern, base):
            continue

        if filters:
            if not any(re.search(p, base) for p in filters):
                continue

        if exclude:
            if any(re.search(p, base) for p in exclude):
                continue

        context = {'verbose': verbose, 'index': index}

        sub_path = file_root.replace(root, '.')
        if sub_path:
            base = os.path.join(sub_path, base)
            context['sub_root'] = sub_path

        if skip_no_exif:
            exif = utils.get_exif(file_path)
            if exif is None:
                continue
            context['exif'] = exif

        new_name = utils.replace_file_params(
            file_path, pattern, replace, **context)
        if not new_name:
            continue

        new_path = os.path.abspath(os.path.join(root, new_name))
        if sub_path:
            new_name = new_path.replace(root, '.')

        if output == 'C':
            if copy:
                cmd = 'cp'
            else:
                cmd = 'mv'
            logger.info('%s %s %s', cmd, base, new_name)
        elif output == 'T':
            logger.info('%-41s %s', base, new_name)

        # if '/' in new_name:
        new_root, _ = os.path.split(new_path)
        if not os.path.exists(new_root) and new_root not in mkdir_no_commit:
            if output == 'C':
                logger.info('mkdir -p %s', os.path.dirname(new_name))
            elif output == 'T':
                logger.info('%s', os.path.dirname(new_name))

            if commit:
                os.makedirs(new_root)
            else:
                mkdir_no_commit.add(new_root)

        if commit:
            if os.path.exists(new_path):
                raise errors.UserError(
                    'File already exists: {}'.format(new_path))
            if copy:
                shutil.copy2(file_path, new_path)
            else:
                os.rename(file_path, new_path)

        if limit and index >= limit:
            logger.info('limit reached')
            break
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


def command_thumbnail(root, size, recursive, type_, commit=False):
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
        if type_:
            file_name, file_ext = file_name.split('.', 1)
            file_dest = '{}.{}'.format(file_name, type_)
        else:
            file_dest = file_name

        logger.info(
            'convert -thumbnail %d %s %s',
            size, file_name, os.path.join(thumbnails_dir, file_dest))
        if commit:
            image.thumbnail((size, size))
            image.save(os.path.join(thumbnails_root, file_dest))


def command_search_copy(root, source_file, recursive):
    source_hash = davo.utils.path.file_hash(source_file)
    source_hash_digest = source_hash.digest()
    size = os.path.getsize(source_file)
    source_full = os.path.abspath(source_file)

    for file in utils.iter_files(root, recursive=recursive):
        if source_full == file or size != os.path.getsize(file):
            continue

        if ((h := davo.utils.path.file_hash(file))
                and source_hash_digest == h.digest()):
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
                i_options['hash'] = davo.utils.path.file_hash(i)
            md5sum = i_options['hash']
            for j in doubles:
                j_options = files[j]
                if not j_options.get('hash'):
                    j_options['hash'] = davo.utils.path.file_hash(i)
                if md5sum != j_options['hash']:
                    continue
                doubles2.add(j)

            if doubles2:
                doubles = doubles2

        if doubles:
            logger.info(
                '%s, %s, %s', i.replace(root, '.'), len(doubles),
                ','.join(doubles).replace(root, '.'),
            )


def command_convert(
    root, replace, recursive, copy, delete, thumbnail, skip_no_exif,
        commit=False,
):
    """
    Convert command.

    :param str root:
    :param str replace: replace pattern
    :param boot recursive:
    :param bool copy:
    :param bool delete: delete source on convert (for rename use copy option)
    :param int thumbnail:
    :param bool skip_no_exif: skip files with no exif data
    :param bool commit:
    """
    index = 1
    converted = 0
    for file_path in utils.iter_files(root, recursive=recursive, sort=True):
        file_root, file_base = os.path.split(file_path)

        exif = None
        if skip_no_exif:
            exif = utils.get_exif(file_path)
            if exif is None:
                continue

        new_name = utils.replace_file_params(
            file_path, '.*', replace, index=index, exif=exif)
        if not new_name:
            continue

        logger.info('%-41s %s', file_base, new_name)

        file_path_new = os.path.join(file_root, new_name)
        davo.utils.path.ensure(file_path_new, commit=commit)

        if (thumbnail
                or not utils.is_ext_same(file_base, new_name)):
            if copy and file_path == file_path_new:
                raise errors.NotImpl(
                    '--copy for inplace convert not implemented yet')
            utils.image_convert(
                path_source=file_path,
                path_dest=file_path_new,
                thumbnail=thumbnail,
                save_exif=True,
                save_mtime=True,
                commit=commit,
            )
            # TODO: copy on file_path == file_path_new
            if commit and delete and file_path != file_path_new:
                os.remove(file_path)
            converted += 1
            continue

        if file_path == file_path_new:
            continue

        if copy:
            if commit:
                shutil.copy2(file_path, file_path_new)
            converted += 1

        else:
            if commit:
                os.rename(file_path, file_path_new)
            converted += 1

        index += 1

    logger.info('converted: %d', converted)
