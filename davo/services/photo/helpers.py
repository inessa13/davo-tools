import datetime
import logging
import math
import os
import re
import shutil
import time

try:
    import cv2
except ImportError:
    cv2 = None
from PIL import Image

import davo.utils
from davo import errors

try:
    from . import recover
except ImportError:
    pass

from . import clients, replace_classes, utils

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


def command_regexp_classes():
    print('Available classes:')
    for k, v in replace_classes.CLASSES.items():
        print(' {}{}'.format('static ', k))

    for k, v in replace_classes.CLASSES_RE.items():
        print(' {}{}'.format('regexp ', k))


def command_regexp_patterns():
    print('Available patterns:')
    for k, v in replace_classes.PATTERNS.items():
        print(' {}{}'.format(k.ljust(20, ' '), v.get('help')))


def _parse_date(value):
    if '-' in value:
        p = '%Y%m%d-%H%M%S'
    else:
        p = '%Y%m%d'
    try:
        value = datetime.datetime.strptime(value, p)
    except ValueError:
        raise errors.UserError('Invalid date: {}. Use `Ymd[-HMS]` format'.format(value))
    return value


def command_regexp(
    root, recursive, filters, exclude, pattern, replace, output,
    date_around, date_fix, date_force,
    copy, skip_no_exif, limit=0, verbose=False, commit=False,
):
    if date_around:
        date_around = _parse_date(date_around)
    if date_fix:
        date_fix = _parse_date(date_fix)

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

        context = {
            'verbose': verbose,
            'index': index,
            'date_around': date_around,
            'date_fix': date_fix,
            'date_force': date_force,
        }

        sub_path = file_root.replace(root, '.')
        if sub_path:
            base = os.path.join(sub_path, base)
            context['sub_root'] = sub_path

        if skip_no_exif:
            exif = utils.get_exif(file_path)
            if exif is None:
                continue
            context['exif_data'] = exif

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


@utils.each_file(elt=True)
def command_clips_split(inf, output, points, ext=None, commit=False, verbose=False, **kwargs):
    if not os.path.isfile(inf):
        return utils.ef_stop('missing', verbose)

    segments = []
    for i, point in enumerate(points):
        if not re.match(r'(\d{1,2}:)?\d{1,2}:\d{2}(\.\d+)?$', point):
            raise errors.UserError('invalid time: {}'.format(point))
        if not i:
            segments.append([None, point])
        else:
            segments.append([points[i - 1], point])
    segments.append([points[-1], None])

    file_name, file_ext = os.path.splitext(inf)
    file_ext = '.' + ext if ext else file_ext

    file_status = True
    for i, (start, end) in enumerate(segments):
        utils.ef_log_task_start(output, '  #{} {}-{}'.format(i, start or '', end or ''), **kwargs)
        dest = '{} #{}{}'.format(file_name, i, file_ext)
        _t = time.time()
        status = clients.run_ffmpeg_pref(
            inf, dest, seek=start, to=end, commit=commit)
        if not status:
            file_status = False
        status = utils.ef_status(status, output, **kwargs)
        utils.ef_log_task_end(output, inf, status, _t, **kwargs)
    return utils.ef_status(file_status, output, **kwargs)


@utils.each_file(elt=True)
def command_clips_trim(inf, output, ss=None, to=None, commit=False, **kwargs):
    out = '{}-trimmed{}'.format(*os.path.splitext(inf))
    if os.path.exists(out):
        return 'exists'

    status = clients.run_ffmpeg_pref(
        inf, out, seek=ss, to=to, copy=False, commit=commit)
    status = utils.ef_status(status, output, commit=commit, **kwargs)
    return status


@utils.each_file(elt=False, cycled=math.inf)
def command_clips_check_web(inf, _output, **_kwargs):
    status = clients.check_ffmpeg_faststart(inf)
    return 'yes' if status else 'no'


@utils.each_file(elt=True)
def command_clips_web(inf, output, verbose=False, commit=False, **kwargs):
    out = '{}-web{}'.format(*os.path.splitext(inf))
    if os.path.exists(out):
        return utils.ef_stop('exists', verbose)

    if clients.check_ffmpeg_faststart(inf):
        return utils.ef_stop('already', verbose)

    status = clients.run_ffmpeg_pref(inf, out, copy=True, commit=commit)
    status = utils.ef_status(status, output, verbose=verbose, commit=commit, **kwargs)
    return status


def command_thumbs(root, recursive, force, size, cols, max_lines, commit=False):
    thumbnails_dir = 'thumb_map.jpg'
    thumbnails_path = os.path.join(root, thumbnails_dir)
    if os.path.exists(thumbnails_path) and not force:
        raise errors.UserError('Thumbnails map file already exists')

    thumbnails = Image.new(
        'RGB',
        (size * cols, size * max_lines),
        'black')

    line = 0
    for i, file in enumerate(utils.iter_files(root, recursive=recursive)):
        line = i // cols
        pos = i % cols

        if thumbnails_dir in file:
            continue

        if line > max_lines:
            logger.warning('too much files, skip some from thumnails')
            break

        try:
            image = Image.open(file)
        except IOError:
            continue

        image.thumbnail((size, size))
        thumbnails.paste(image, (pos * size, line * size))
        logger.info('thumbnail: %s', file)

    line += 1
    if line < max_lines:
        th = thumbnails
        # th.crop((0, 0, size * cols - 1, size * line - 1))
        thumbnails = Image.new(
        'RGB',
        (size * cols, size * line),
        'black')
        thumbnails.paste(th, (0, 0))

    if commit:
        thumbnails.save(thumbnails_path)


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


def command_search_duplicates(root, md5, recursive, verbose):
    files = {}
    for file in utils.iter_files(root, recursive=recursive):
        files[file] = {
            'size': os.path.getsize(file),
        }

    logger.info('total: %d', len(files))

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
    drop_alpha, commit=False,
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
    :param bool drop_alpha: drop alpha channel
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
            file_path, '.*', replace, index=index, exif_data=exif)
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
                drop_alpha=drop_alpha,
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


@utils.each_file(elt=True, cycled=30)
def command_convert_video(inf, output, replace='[source].[Ext]', thumbnail=False, verbose=False, commit=False, **kwargs):
    """
    Convert command for video using ffmpeg.
    """
    kwargs.setdefault('converted', 0)
    converted = kwargs['converted']

    file_root, file_base = os.path.split(inf)
    new_name = utils.replace_file_params(
        file_base, '.*', replace, index=converted)
    out = os.path.join(file_root, new_name)
    if thumbnail:
        out = os.path.splitext(out)[0] + '.jpg'
    if out == inf and not thumbnail:
        return utils.ef_stop('skipped (same name/ext)', verbose)
    davo.utils.path.ensure(out, commit=commit)
    if os.path.exists(out):
        return utils.ef_stop('exists', verbose)
    if not os.path.exists(inf):
        return utils.ef_stop('not found', verbose)

    status = clients.run_ffmpeg_pref(inf, out, timeout=14400, commit=commit)
    status = utils.ef_status(status, output, verbose=verbose, **kwargs)

    if status == 'succeed':
        converted += 1
    return status


def command_recover(
        root,
        algo: str = None,
        scale: int = None,
        min_contour: int = None,
        max_contour: int = None,
        debug: bool = False,
        recursive: bool = False,
        verbose: bool = False,
        commit: bool = False,
):
    scale, min_contour, max_contour = map(
        utils.int2frac, (scale, min_contour, max_contour))
    pipelines = recover.cv3.get_pipelines(verbose=verbose)
    for file_path in utils.iter_files(root, recursive=recursive, sort=True):
        file_root, file_base = os.path.split(file_path)
        if verbose:
            logger.info('>%s', file_base)
        image = cv2.imread(file_path)

        contour = recover.image_recover(
            image.copy(),
            {
                'debug': debug,
                'file': file_base,
            },
            pipelines,
            algo=algo,
            scale=scale,
            min_contour=min_contour,
            max_contour=max_contour,
            debug=debug,
            verbose=verbose,
        )
        if contour is None:
            if verbose:
                logger.info('%s: contour not found', file_base)
            continue

        name, ext = file_base.rsplit('.', 1)
        name = os.path.join(file_root, '{}-fixed.{}'.format(name, ext))

        if verbose:
            logger.info('%s: contour detected', file_base)
        if commit:
            recover.rotate(image, contour, name)


def command_downscale(
        root,
        min_width: int = None,
        min_height: int = None,
        speed: int = None,
        threshold: int = None,
        verbose: bool = False,
        commit: bool = False,
):
    threshold, speed = map(utils.int2frac, (threshold, speed))
    for file_path in utils.iter_files(root, recursive=False, sort=True):
        file_root, file_base = os.path.split(file_path)

        image = cv2.imread(file_path)
        downscaled, ssim = recover.cv3.image_downscale(
            image, min_width, min_height, speed, threshold)

        if downscaled is None or ssim == 1.0:
            if verbose:
                logger.info('%s: downscale failed', file_base)
            continue

        file_name, ext = file_base.rsplit('.', 1)
        file_name = os.path.join(file_root, '{}-downscaled.{}'.format(file_name, ext))
        scale = downscaled.shape[0] / image.shape[0] * 100
        logger.info(
            '%s: downscaled %.2f%% %d*%d, SSIM=%.3f',
            file_base,
            scale,
            downscaled.shape[1],
            downscaled.shape[0],
            ssim)
        if commit:
            cv2.imwrite(file_name, downscaled)
