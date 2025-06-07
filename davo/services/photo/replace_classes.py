import datetime
import logging
import mimetypes
import os
import re

import davo.utils

from . import utils

logger = logging.getLogger(__name__)

PREFIXES = (
    'IMG_',
    'DSCN',
    'DSC_',
    'DSC0',
    'MOV0',
    'S500',
    'PICT',
    'Фото',
    'HPIM',
    'CIMG',
    'IMGP',
    'SDC1',
    'P104',
    'MVI_',
    'PB',
)
PREFIXES_P = '|'.join(PREFIXES)

P_SOURCE_CODE = r'.*(?P<source_prefix>' + PREFIXES_P + ')(?P<source_num>\d{3,6})\D*.*$'


def _mtime_(filename, context):
    return datetime.datetime.fromtimestamp(
        os.path.getmtime(_path(filename, context)))


def _mtime(filename, context, fmt):
    return _mtime_(filename, context).strftime(fmt)


def _ctime_(filename, context):
    return datetime.datetime.fromtimestamp(
        os.path.getctime(_path(filename, context)))


def _ctime(filename, context, fmt):
    return _ctime_(filename, context).strftime(fmt)


def extension(filename, context):
    if context.get('ext') is None:
        context['ext'] = davo.utils.path.get_extension(filename)

    return context['ext']


def source_no_ext(filename, context):
    if context.get('source') is None:
        context['source'] = davo.utils.path.get_filename_no_extension(filename)

    return context['source']


def source_rjust(filename, context, size=3):
    if context.get('source') is None:
        context['source'] = davo.utils.path.get_filename_no_extension(filename)

    val = context['source']
    return val.rjust(size, '0')


def source_int(filename, context):
    return re.sub(r'\D+', '', source_no_ext(filename, context))


def source_datetime(filename, context):
    name = source_no_ext(filename, context)
    prefixes = '(' + PREFIXES_P + ')'
    if m := re.match(prefixes + r'(\d{8})[_ -](\d{6}).*', name):
        return datetime.datetime.strptime('{} {}'.format(m.group(2), m.group(3)), '%Y%m%d %H%M%S')
    if m := re.match(prefixes + r'(\d{8})\D+.*', name):
        return datetime.datetime.strptime('{} {}'.format(m.group(2)), '%Y%m%d')
    return None


def source_img_(filename, context):
    if m := re.match(r'IMG_(\d+)$', source_no_ext(filename, context)):
        return m.group(1)
    return ''


def source_img_2(filename, context):
    if m := re.search(r'IMG_(\d+)$', source_no_ext(filename, context)):
        return m.group(1)
    return ''


def source_dsc_2(filename, context):
    if m := re.search(r'DSC_(\d+)$', source_no_ext(filename, context)):
        return m.group(1)
    return ''


def source_rel(_filename, context):
    return context.get('sub_root', '')


def source_full(filename, context):
    return os.path.join(
        source_rel(filename, context),
        source_no_ext(filename, context),
    )


def _source_classes(_filename, context, match):
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


def _path(filename, context):
    return os.path.join(context.get('sub_root', ''), filename)


def _exif_field(context, filename, field, default=''):
    if context.get('exif_data') is not None:
        exif_data = context['exif_data']
    else:
        exif_data, _details = utils.get_exif_with_details(
            _path(filename, context),
            verbose=context.get('verbose', False),
        )

    if exif_data is None:
        return default

    value = exif_data.get(field, default).strip()

    # for k, v in exif_data.items():
    #     print(k, v)

    # strip confusing chars
    if len(os.path.split(value)) > 1:
        value = value.replace('/', '_').replace('\\', '_')

    return value


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


def _date_time_fmt(value, sep):
    if value:
        return value.strftime('%Y%m%d' + sep + '%H%M%S')
    return ''


def _date_fmt(value):
    if value:
        return value.strftime('%Y%m%d')
    return ''


def _time_fmt(value):
    if value:
        return value.strftime('%H%M%S')
    return ''


def exif_datetime_min_(filename, context):
    date_value = None
    for key in ('datetime_original', 'datetime', 'datetime_digitized'):
        if value := _exif_field(context, filename, key):
            value = value.replace(':', '')
            try:
                date = datetime.datetime.strptime(value, '%Y%m%d %H%M%S')
            except ValueError:
                continue
            if not date_value or date < date_value:
                date_value = date
    return date_value


def guess_mime(filename, context):
    if context.get('mimetype'):
        return context['mimetype']

    mime, enc = mimetypes.guess_type(filename)
    context['mimetype'] = mime
    return mime


def guess_prefix(filename, context):
    if val := context.get('source_match_group_dict', {}).get('source_prefix'):
        source_prefix = val
    else:
        # try to extract prefix from filename
        if m := re.match(P_SOURCE_CODE, os.path.split(filename)[1]):
            matches = m.groupdict()
            context.setdefault('source_match_group_dict', {}).update(matches)
            source_prefix = matches['source_prefix']
        else:
            source_prefix = ''

    # try to guess prefix based on exif data
    model = _exif_field(context, filename, 'model').lower()
    manufacturer = _exif_field(context, filename, 'make').lower()
    exif_prefix = ''
    if model or manufacturer:
        if manufacturer == 'nikon':
            exif_prefix = 'DSCN'
        elif manufacturer == 'camera':
            exif_prefix = 'PICT'
        elif manufacturer == 'Nokia':
            exif_prefix = 'Фото'
        elif manufacturer == 'Samsung':
            exif_prefix = 'SDC1'
        elif manufacturer == 'hewlett-packard':
            exif_prefix = 'HPIM'
        elif manufacturer == 'panasonic' and model == 'DMC-FS12'.lower():
            exif_prefix = 'P104'
        elif manufacturer == 'sony' and model == 'DSC-W7'.lower():
            exif_prefix = 'DSC0'
        elif 'casio' in manufacturer:
            exif_prefix = 'CIMG'
        elif 'pentax' in manufacturer:
            exif_prefix = 'IMGP'
        elif 'canon' in manufacturer:
            exif_prefix = 'IMG_'
        elif 'digimax s500' in model:
            exif_prefix = 'S500'

    if source_prefix and not exif_prefix:
        return source_prefix
    elif not source_prefix and exif_prefix:
        return exif_prefix
    elif source_prefix and exif_prefix and source_prefix != exif_prefix:
        return source_prefix + '_' + exif_prefix
    return ''


def _media_info(filename, context):
    if context.get('mediainfo') is not None:
        return context['mediainfo']

    media = utils.get_media_info(_path(filename, context))
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


def _datetime_for_video_(filename, context):
    if value := _media_info_field(filename, context, 'creationdate', ''):
        if m := re.match(
                r'(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2})[Z+-]', value):
            value = m.group(1)
        value = datetime.datetime.fromisoformat(value)
        return value

    if value := _media_info_field(filename, context, 'encoded_date', ''):
        value = value.replace('UTC ', '')
        value = datetime.datetime.fromisoformat(value)
        return value

    return None


def date_time_prioritized(filename, context, sep='_'):
    pattern = f'%Y%m%d{sep}%H%M%S'
    mime = guess_mime(filename, context)
    if mime in ('image/jpeg',):
        if value := exif_datetime_original(filename, context, sep=sep):
            return value

        if value := exif_datetime(filename, context, sep=sep):
            return value

    elif mime in ('video/quicktime', 'video/mp4'):
        if value := _date_time_fmt(
                _datetime_for_video_(filename, context), sep):
            return value

    if value := _mtime(filename, context, pattern):
        return value

    if value := _ctime(filename, context, pattern):
        return value

    return ''


def dt_optimal(filename, context, priority=False):
    values = []

    # datetime from filename
    if ds := source_datetime(filename, context):
        values.append(ds)

    mime = guess_mime(filename, context)
    if mime in ('image/jpeg',):
        for key in ('datetime_original', 'datetime_digitized', 'datetime'):
            if value := _exif_field(context, filename, key):
                value = value.replace(':', '')
                try:
                    date = datetime.datetime.strptime(value, '%Y%m%d %H%M%S')
                except ValueError:
                    continue
                values.append(date)

    elif mime in ('video/quicktime', 'video/mp4'):
        if date := _datetime_for_video_(filename, context):
            values.append(date)

    values.append(_mtime_(filename, context))
    values.append(_ctime_(filename, context))

    value = None
    if values:
        if da := context.get('date_around'):
            dx_l = 0
            for date in values:
                dx = abs((date - da).total_seconds())
                if not dx_l or dx < dx_l:
                    dx_l = dx
                    value = date

            if date_fix := context.get('date_fix'):
                value = value - date_fix + da

            elif context.get('date_force') and dx_l / 86400 > 30:
                value = value.replace(year=da.year, month=da.month, day=da.day)

        elif priority:
            value = values[0]
        else:
            value = min(values)

    return value


def dt_oldest(filename, context):
    values = []
    mime = guess_mime(filename, context)

    if mime in ('image/jpeg',):
        if value := exif_datetime_min_(filename, context):
            values.append(value)

    elif mime in ('video/quicktime', 'video/mp4'):
        if value := _datetime_for_video_(filename, context):
            values.append(value)

    if value := _mtime_(filename, context):
        values.append(value)

    if value := _ctime_(filename, context):
        values.append(value)

    if values:
        return min(values)
    return None


def date_prioritized(filename, context):
    pattern = '%Y%m%d'
    mime = guess_mime(filename, context)
    if mime in ('image/jpeg',):
        if value := exif_date_original(filename, context):
            return value

        if value := exif_date(filename, context):
            return value

    elif mime in ('video/quicktime', 'video/mp4'):
        if value := _date_fmt(_datetime_for_video_(filename, context)):
            return value

    if value := _mtime(filename, context, pattern):
        return value

    if value := _ctime(filename, context, pattern):
        return value

    return ''


def df_prioritized(filename, context):
    value = date_time_prioritized(filename, context, sep=' ')
    value = datetime.datetime.strptime(value, '%Y%m%d %H%M%S')
    return value


CLASSES = {
    '[source:int]': source_int,
    '[source:datetime]': source_datetime,
    '[source:img_]': source_img_,
    '[source:img_$]': source_img_2,
    '[source:dsc_$]': source_dsc_2,
    '[source:rel]': source_rel,
    '[source:name]': source_no_ext,
    '[source]': source_full,
    '[Ext]': extension,
    '[EXT]': lambda f, c: extension(f, c).upper(),
    '[ext]': lambda f, c: extension(f, c).lower(),
    '[CCC]': lambda f, c: counter(f, c, size=3),
    '[CC]': lambda f, c: counter(f, c, size=2),
    '[C]': lambda f, c: counter(f, c, size=1),

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

    '[date]': date_prioritized,
    '[datetime]': date_time_prioritized,
    '[datetime_oldest]': lambda f, c: _date_time_fmt(dt_oldest(f, c), sep='_'),
    '[datetime oldest]': lambda f, c: _date_time_fmt(dt_oldest(f, c), sep=' '),
    '[date time]': lambda f, c: date_time_prioritized(f, c, sep=' '),
    '[year]': lambda f, c: df_prioritized(f, c).strftime('%Y'),
    '[month]': lambda f, c: df_prioritized(f, c).strftime('%m'),
    '[day]': lambda f, c: df_prioritized(f, c).strftime('%d'),
    '[mime]': lambda f, c: guess_mime(f, c).replace('/', '_'),
    '[prefix]': guess_prefix,
    '[dto:time]': lambda f, c: _time_fmt(dt_optimal(f, c)),
    '[dto:datetime]': lambda f, c: _date_time_fmt(dt_optimal(f, c), sep='_'),
}

CLASSES_RE = {
    r'\[exif:(?P<class>[a-zA-Z0-9 _-]+)(\:(?P<default>[0-9a-zA-Z-]+))?\]':
        lambda f, c, m: _exif_field(
            c, f, m.group('class'), default=m.group('default') or ''),
    r'\[source:rjust(:(?P<size>\d+))?\]': lambda f, c, m: source_rjust(
        f, c, int(m.groupdict().get('size', '3'))),
    r'\[source:(?P<class_name>[a-zA-Z0-9_]+)\]': _source_classes,
    # TODO: r'\[date:(?P<class>[a-zA-Z%]+)\]'
}


PATTERNS = {
    'base': {
        'pattern': P_SOURCE_CODE,
        'replace': 'IMG_[dto:datetime] [source:source_prefix][source:source_num].[Ext]',
        'help': 'for most cases',
    },
    'base_nc': {
        'pattern': r'.*',
        'replace': 'IMG_[datetime_oldest] [source:name].[Ext]',
        'help': 'base with no constraints',
    },
    'count': {
        'pattern': r'.*\.(jpg|JPG|jpeg|avi|mov)$',
        'replace': 'IMG_[datetime_oldest] [CCC].[Ext]',
        'help': 'base with counter, doesn\'t use source name',
    },
    'date': {
        'pattern': r'.*\.(jpg|JPG|jpeg|avi|mov)$',
        'replace': 'IMG_[datetime_oldest].[Ext]',
        'help': 'rename using oldest date only',
    },
    'base_int': {
        'pattern': r'.*',
        'replace': 'IMG_[datetime_oldest] [source:int].[Ext]',
        'help': 'base with no constraints',
    },
    'base_fix': {
        'pattern': r'IMG_\d{8}_\d{6}_(?P<source_num>\d{4})\..*$',
        'replace': 'IMG_[datetime] [prefix][source:source_num].[Ext]',
        'help': 'convert from old base to new',
    },
    'fix_old': {
        'pattern': r'IMG_\d{8}_\d{6}_\((?P<source_num>.*)\)\..*$',
        'replace': 'IMG_[datetime_oldest] [source:source_num].[Ext]',
        'help': 'convert from old base to new',
    },
    'strip': {
        'pattern': P_SOURCE_CODE,
        'replace': '[source:source_prefix][source:source_num].[Ext]',
        'help': 'strip to original if enough data',
    },
    'model': {
        'pattern': r'.*',
        'replace': '[source:name] [exif:make] [exif:model].[Ext]',
        'help': '(don\'t not use for commit) shows model and manufacturer',
    },
    'model+': {
        'pattern': r'.*',
        'replace': '[source:name] [exif:make] [exif:model] [exif:software].[Ext]',
        'help': '(don\'t not use for commit) shows model and manufacturer',
    },
    'iphone': {
        'pattern': r'IMG_(?P<source>\d+)\..*$',
        'replace': 'IMG_[mdate]_[mtime] (IMG_[source]).[Ext]',
        'help': '(deprecated) use base instead',
    },
    'temp': {
        'pattern': r'\d+ (?P<source>.*).*\..*',
        'replace': 'IMG_[datetime_oldest] [source:rjust:3].[Ext]',
        'help': 'temp',
    },
}
