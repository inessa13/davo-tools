import time

_PROGRESS = (
    '[{progress}{arrow}{left}]'
    ' {progress_percent:3.0f}%'
    ' {ready}/{total}'
    '{notes}'
)


def spinner(index=0, pattern='|/-\\'):
    return pattern[index % len(pattern)]


def progress_bar(
    ready, total, char_fill='=', char_arrow='>', char_pad=' ', len_full=40,
    elapsed=None, elt='', extra='',
):
    percent = ready / total
    progress = round(percent, 2) * 100
    progress_len = int(progress) * len_full // 100

    if elapsed is None:
        elapsed = ''
    else:
        elapsed = ' Elapsed: {:.2f}s'.format(elapsed)

    if isinstance(elt, float):
        elt = ' Elapsed: {:.2f}s'.format(time.time() - elt)

    return _PROGRESS.format(
        progress=char_fill * progress_len,
        arrow=char_arrow,
        left=char_pad * (len_full - progress_len),
        progress_percent=progress,
        ready=ready,
        total=total,
        notes=elapsed + extra + elt,
    )


def rp_plain(string):
    """
    For mocking.
    :param str string:
    """
    print(string)


def rp_cycled(string, output, plain=False, prefix=1, max_lines=10):
    if plain or output is None:
        rp_plain(string)
        return

    total = prefix + max_lines
    if len(output) >= total:
        output[prefix:total] = output[prefix + 1:total] + [string]
    else:
        output.append(string)
