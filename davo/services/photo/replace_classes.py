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


def extension(filename, _context):
    if '.' in filename:
        ext = filename.rsplit('.', 1)[1]
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

    return image


def _exif_field(context, filename, field, default=''):
    if context.get('exif') is not None:
        image = context['exif']
    else:
        image = get_exif(filename, verbose=context.get('verbose', False))

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


def date_time_prioritized(filename, context, sep='_'):
    if value := exif_datetime_original(filename, context, sep=sep):
        return value

    if value := exif_datetime(filename, context, sep=sep):
        return value

    if value := modified_datetime(filename, context, sep=sep):
        return value

    if value := created_datetime(filename, context, sep=sep):
        return value

    return ''


def df_prioritized(filename, context):
    value = date_time_prioritized(filename, context, sep=' ')
    value = datetime.datetime.strptime(value, '%Y%m%d %H%M%S')
    return value


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
    '[Ext]': extension,
    '[EXT]': lambda f, c: extension(f, c).upper(),
    '[ext]': lambda f, c: extension(f, c).lower(),
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
    '[datetime]': date_time_prioritized,
    '[date time]': lambda f, c: date_time_prioritized(f, c, sep=' '),
    '[year]': lambda f, c: df_prioritized(f, c).strftime('%Y'),
    '[month]': lambda f, c: df_prioritized(f, c).strftime('%m'),
    '[day]': lambda f, c: df_prioritized(f, c).strftime('%d'),
}


PATTERNS = {
    'iphone': {
        'pattern': r'IMG_(?P<source>\d+)\..*$',
        'replace': 'IMG_[mdate]_[mtime] (IMG_[source]).[Ext]',
    },
}
