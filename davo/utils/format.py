import datetime
import math

LEVELS_SIZE = {
    'T': 1024 ** 4,
    'G': 1024 ** 3,
    'M': 1024 ** 2,
    'K': 1024 ** 1,
    ' ': 1024 ** 0,
}
LEVELS_SPEED = {
    'TBps': 1024 ** 4,
    'GBps': 1024 ** 3,
    'MBps': 1024 ** 2,
    'KBps': 1024 ** 1,
    ' Bps': 1024 ** 0,
}

FORMAT_DEFAULT = '{:7.2f} {}'


def humanize_number_sizes(value, sizes=(), format_=FORMAT_DEFAULT):
    label = ''
    for label, level in sizes:
        if value > level:
            if level:
                value /= level
            break

    return format_.format(value, label)


def humanize_bytes(value, format_=FORMAT_DEFAULT):
    return humanize_number_sizes(value, LEVELS_SIZE.items(), format_=format_)


def humanize_speed(value, format_=FORMAT_DEFAULT):
    return humanize_number_sizes(value, LEVELS_SPEED.items(), format_=format_)


def elapsed(seconds):
    return 'Elapse: {}'.format(datetime.timedelta(seconds=int(seconds)))


def reprint_cycled(string, output, prefix=1, max_lines=10):
    if output is None:
        print(string)
        return

    total = prefix + max_lines
    if len(output) >= total:
        output[prefix:total] = output[prefix + 1:total] + [string]
    else:
        output.append(string)
