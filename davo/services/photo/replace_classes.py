import datetime
import logging
import os

import exif

logger = logging.getLogger(__name__)


def modified_date(filename, _context):
    date = datetime.datetime.fromtimestamp(os.path.getmtime(filename))
    return date.strftime('%Y%m%d')


def _modified(filename, _context):
    date = datetime.datetime.fromtimestamp(os.path.getmtime(filename))
    return date


def modified_time(filename, _context):
    date = datetime.datetime.fromtimestamp(os.path.getmtime(filename))
    return date.strftime('%H%M%S')


def modified_datetime(filename, _context, sep='_'):
    date = datetime.datetime.fromtimestamp(os.path.getmtime(filename))
    return date.strftime('%Y%m%d{}%H%M%S'.format(sep))


def modified_date_path(filename, _context):
    date = datetime.datetime.fromtimestamp(os.path.getmtime(filename))
    return date.strftime('%Y/%m/%d/')


def created_date(filename, _context):
    date = datetime.datetime.fromtimestamp(os.path.getctime(filename))
    return date.strftime('%Y%m%d')


def created_time(filename, _context):
    date = datetime.datetime.fromtimestamp(os.path.getctime(filename))
    return date.strftime('%H%M%S')


def created_datetime(filename, _context, sep='_'):
    date = datetime.datetime.fromtimestamp(os.path.getctime(filename))
    return date.strftime('%Y%m%d{}%H%M%S'.format(sep))


def ext_without_dot(filename, _context):
    if '.' in filename:
        ext = filename.rsplit('.', 1)[1]
    else:
        ext = ''
    return ext


def ext_with_dot(filename, _context):
    if '.' in filename:
        ext = '.' + filename.rsplit('.', 1)[1]
    else:
        ext = ''
    return ext


def source_no_ext(filename, context):
    if context.get('source'):
        return context['source']

    base = os.path.basename(filename)
    if '.' in base:
        base = base.rsplit('.', 1)[0]
    return base


def counter(_filename, context, size=3):
    pattern = f'{{:0{size}}}'
    return pattern.format(context.get('index', 0))


def _exif_field(filename, field, default=''):
    with open(filename, 'rb') as file:
        try:
            image = exif.Image(file)
        except Exception as exc:
            logger.warning('exif parse error: %s', exc)
            return default

    if not image.has_exif:
        return default

    return image.get(field) or default


def exif_date(filename, _context):
    if value := _exif_field(filename, 'datetime'):
        return value[:10].replace(':', '')

    return ''


def exif_time(filename, _context):
    if dt := _exif_field(filename, 'datetime'):
        return dt[11:].replace(':', '')

    return ''


def exif_datetime(filename, _context):
    if dt := _exif_field(filename, 'datetime'):
        return dt.replace(':', '').replace(' ', '_')

    return ''


def exif_date_original(filename, _context):
    if datetime_original := _exif_field(filename, 'datetime_original'):
        return datetime_original[:10].replace(':', '')

    return ''


def exif_time_original(filename, _context):
    if datetime_original := _exif_field(filename, 'datetime_original'):
        return datetime_original[11:].replace(':', '')

    return ''


def exif_datetime_original(filename, _context):
    if datetime_original := _exif_field(filename, 'datetime_original'):
        return datetime_original.replace(':', '').replace(' ', '_')

    return ''


CLASSES = {
    '[mdate_path]': modified_date_path,
    '[mdate]': modified_date,
    '[myear]': lambda f, c: _modified(f, c).strftime('%Y'),
    '[mtime]': modified_time,
    '[mdatetime]': modified_datetime,
    '[mdate_time]': modified_datetime,
    '[mdate time]': lambda f, c: modified_datetime(f, c, ' '),
    '[cdate]': created_date,
    '[ctime]': created_time,
    '[cdatetime]': created_datetime,
    '[cdate time]': lambda f, c: created_datetime(f, c, ' '),
    '[Ext]': ext_without_dot,
    '[EXT]': lambda f, c: ext_without_dot(f, c).upper(),
    '[ext]': lambda f, c: ext_without_dot(f, c).lower(),
    '[.ext]': ext_with_dot,
    '[source]': source_no_ext,
    '[CCC]': lambda f, c: counter(f, c, size=3),
    '[index3]': lambda f, c: counter(f, c, size=3),
    '[index2]': lambda f, c: counter(f, c, size=2),
    '[CC]': lambda f, c: counter(f, c, size=2),
    '[exif:date]': exif_date,
    '[exif:time]': exif_time,
    '[exif:datetime]': exif_datetime,
    '[exif:date_original]': exif_date_original,
    '[exif:time_original]': exif_time_original,
    '[exif:datetime_original]': exif_datetime_original,
}


PATTERNS = {
    'iphone': {
        'pattern': r'IMG_(?P<source>\d+)\..*$',
        'replace': 'IMG_[mdate]_[mtime] (IMG_[source]).[Ext]',
    },
}
