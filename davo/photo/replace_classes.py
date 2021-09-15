import datetime
import os


def m_date(filename, _context):
    st_mtime = datetime.datetime.fromtimestamp(os.path.getmtime(filename))
    return st_mtime.strftime('%Y%m%d')


def m_time(filename, _context):
    st_mtime = datetime.datetime.fromtimestamp(os.path.getmtime(filename))
    return st_mtime.strftime('%H%M%S')


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


CLASSES = {
    '[mdate]': m_date,
    '[mtime]': m_time,
    '[Ext]': ext_without_dot,
    '[EXT]': lambda f, c: ext_without_dot(f, c).upper(),
    '[ext]': lambda f, c: ext_without_dot(f, c).lower(),
    '[.ext]': ext_with_dot,
    '[source]': source_no_ext,
    '[CCC]': lambda f, c: counter(f, c, size=3),
    '[index3]': lambda f, c: counter(f, c, size=3),
    '[index2]': lambda f, c: counter(f, c, size=2),
    '[CC]': lambda f, c: counter(f, c, size=2),
}


PATTERNS = {
    'iphone': {
        'pattern': r'IMG_(?P<source>\d+)\..*$',
        'replace': 'IMG_[mdate]_[mtime] (IMG_[source]).[Ext]',
    },
}
