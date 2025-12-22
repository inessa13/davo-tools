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
