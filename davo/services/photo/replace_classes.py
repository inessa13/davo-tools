import datetime
import logging
import mimetypes
import os
import pprint
import re

import exif
import pymediainfo

logger = logging.getLogger(__name__)


def _mtime(filename, context, fmt):
    return datetime.datetime.fromtimestamp(
        os.path.getmtime(_path(filename, context))).strftime(fmt)


def _ctime(filename, context, fmt):
    return datetime.datetime.fromtimestamp(
        os.path.getctime(_path(filename, context))).strftime(fmt)


def extension(filename, context):
    if context.get('ext'):
        return context['ext']

    if '.' in filename:
        ext = filename.rsplit('.', 1)[1]
    else:
        ext = ''

    context['ext'] = ext
    return ext


def source_no_ext(filename, context):
    if context.get('source'):
        return context['source']

    base = os.path.basename(filename)
    if '.' in base:
        base = base.rsplit('.', 1)[0]
    return base


def source_int(filename, context):
    return re.sub(r'\D+', '', source_no_ext(filename, context))


def source_img_(filename, context):
    if m := re.match(r'IMG_(\d+)$', source_no_ext(filename, context)):
        return m.group(1)
    return ''


def source_rel(filename, context):
    return context.get('sub_root', '')


def source_full(filename, context):
    return os.path.join(
        source_rel(filename, context),
        source_no_ext(filename, context),
    )


def _source_classes(_filename, context, match):
    # print(match.groupdict())
    class_name = match.group('class_name')
    if context.get('source_match_group_dict', {}).get(class_name):
        return context['source_match_group_dict'][class_name]

    if (class_name.isdigit()
            and int(class_name) < len(context.get('source_match_groups', ()))):
        return context['source_match_groups'][int(class_name)]

    return ''


def counter(_filename, context, size=3):
    pattern = f'{{:0{size}}}'
    return pattern.format(context.get('index', 0))


def get_exif(filename, verbose=True):
    with open(filename, 'rb') as file:
        try:
            image = exif.Image(file)
        except Exception as exc:
            if verbose:
                logger.warning('exif parse error: %s', exc)
            return None

    if not image.has_exif:
        return None

    if verbose:
        logger.info('exif: %s', pprint.pformat(image.get_all()))

    return image


def _path(filename, context):
    return os.path.join(context.get('sub_root', ''), filename)


def _exif_field(context, filename, field, default=''):
    if context.get('exif') is not None:
        image = context['exif']
    else:
        image = get_exif(
            _path(filename, context),
            verbose=context.get('verbose', False),
        )

    if image is None or not image.has_exif:
        return default

    return image.get(field) or default


def exif_date(filename, context):
    if value := _exif_field(context, filename, 'datetime'):
        return value[:10].replace(':', '')

    return ''


def exif_time(filename, context):
    if value := _exif_field(context, filename, 'datetime'):
        return value[11:].replace(':', '')

    return ''


def exif_datetime(filename, context, sep='_'):
    if value := _exif_field(context, filename, 'datetime'):
        return value.replace(':', '').replace(' ', sep)

    return ''


def exif_date_original(filename, context):
    if value := _exif_field(context, filename, 'datetime_original'):
        return value[:10].replace(':', '')

    return ''


def exif_time_original(filename, context):
    if value := _exif_field(context, filename, 'datetime_original'):
        return value[11:].replace(':', '')

    return ''


def exif_datetime_original(filename, context, sep='_'):
    if value := _exif_field(context, filename, 'datetime_original'):
        return value.replace(':', '').replace(' ', sep)

    return ''


def guess_mime(filename, context):
    if context.get('mimetype'):
        return context['mimetype']

    mime, enc = mimetypes.guess_type(filename)
    context['mimetype'] = mime
    return mime


def _media_info(filename, context):
    if context.get('mediainfo') is not None:
        return context['mediainfo']

    path = _path(filename, context)
    media = pymediainfo.MediaInfo.parse(path).to_data()['tracks'][0]
    if media:
        context['mediainfo'] = media

    return media


def _media_info_field(filename, context, field, default=''):
    media = _media_info(filename, context)

    if not media:
        return default

    if media.get(f'comapplequicktime{field}'):
        return media[f'comapplequicktime{field}']

    if media.get(field):
        return media[field]

    return default


def date_time_prioritized(filename, context, sep='_'):
    mime = guess_mime(filename, context)
    if mime in ('image/jpeg',):
        if value := exif_datetime_original(filename, context, sep=sep):
            return value

        if value := exif_datetime(filename, context, sep=sep):
            return value

    elif mime in ('video/quicktime', 'video/mp4'):
        if value := _media_info_field(filename, context, 'creationdate', ''):
            if m := re.match(
                    r'(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2})[Z+-]', value):
                value = m.group(1)
            value = datetime.datetime.fromisoformat(value).strftime(
                f'%Y%m%d{sep}%H%M%S')
            return value

        if value := _media_info_field(filename, context, 'encoded_date', ''):
            value = value.replace('UTC ', '')
            value = datetime.datetime.fromisoformat(value).strftime(
                f'%Y%m%d{sep}%H%M%S')
            return value

    if value := _mtime(filename, context, f'%Y%m%d{sep}%H%M%S'):
        return value

    if value := _ctime(filename, context, f'%Y%m%d{sep}%H%M%S'):
        return value

    return ''


def df_prioritized(filename, context):
    value = date_time_prioritized(filename, context, sep=' ')
    value = datetime.datetime.strptime(value, '%Y%m%d %H%M%S')
    return value


CLASSES = {
    '[source:int]': source_int,
    '[source:img_]': source_img_,
    '[source:rel]': source_rel,
    '[source:name]': source_no_ext,
    '[source]': source_full,
    '[Ext]': extension,
    '[EXT]': lambda f, c: extension(f, c).upper(),
    '[ext]': lambda f, c: extension(f, c).lower(),
    '[CCC]': lambda f, c: counter(f, c, size=3),
    '[CC]': lambda f, c: counter(f, c, size=2),

    # stat mtime
    '[mdatetime]': lambda f, c: _mtime(f, c, '%Y%m%d_%H%M%S'),
    '[mdate_time]': lambda f, c: _mtime(f, c, '%Y%m%d_%H%M%S'),
    '[mdate time]': lambda f, c: _mtime(f, c, '%Y%m%d %H%M%S'),
    '[mdate_path]': lambda f, c: _mtime(f, c, '%Y/%m/%d/'),
    '[mdate]': lambda f, c: _mtime(f, c, '%Y%m%d'),
    '[myear]': lambda f, c: _mtime(f, c, '%Y'),
    '[mtime]': lambda f, c: _mtime(f, c, '%H%M%S'),

    # stat ctime
    '[cdatetime]': lambda f, c: _ctime(f, c, '%Y%m%d_%H%M%S'),
    '[cdate time]': lambda f, c: _ctime(f, c, '%Y%m%d %H%M%S'),
    '[cdate]': lambda f, c: _ctime(f, c, '%Y%m%d'),
    '[ctime]': lambda f, c: _ctime(f, c, '%H%M%S'),

    '[exif:date]': exif_date,
    '[exif:time]': exif_time,
    '[exif:datetime]': exif_datetime,
    '[exif:date_original]': exif_date_original,
    '[exif:time_original]': exif_time_original,
    '[exif:datetime_original]': exif_datetime_original,

    '[datetime]': date_time_prioritized,
    '[date time]': lambda f, c: date_time_prioritized(f, c, sep=' '),
    '[year]': lambda f, c: df_prioritized(f, c).strftime('%Y'),
    '[month]': lambda f, c: df_prioritized(f, c).strftime('%m'),
    '[day]': lambda f, c: df_prioritized(f, c).strftime('%d'),
    '[mime]': lambda f, c: guess_mime(f, c).replace('/', '_'),
}
CLASSES_RE = {
    r'\[exif:(?P<class>[a-zA-Z0-9 _-]+)(\:(?P<default>[0-9a-zA-Z-]+))?\]':
        lambda f, c, m: _exif_field(
            c, f, m.group('class'), default=m.group('default') or ''),
    r'\[source:(?P<class_name>[a-zA-Z0-9]+)\]': _source_classes,
    # TODO: r'\[date:(?P<class>[a-zA-Z%]+)\]'
}


PATTERNS = {
    'iphone': {
        'pattern': r'IMG_(?P<source>\d+)\..*$',
        'replace': 'IMG_[mdate]_[mtime] (IMG_[source]).[Ext]',
    },
}
