import os
import re

from davo import errors
from davo.utils import concur


def run_ffmpeg(
        inf,
        out,
        seek=None,
        to=None,
        faststart=False,
        copy=False,
        copy_antz=False,
        quiet=False,
        save_mtime=False,
        timeout=1 * 60 * 60,
        commit=True,
):
    """

    :param str inf:
    :param str out:
    :param str seek:
    :param str to:
    :param bool faststart:
    :param bool copy:
    :param bool copy_antz:
    :param bool quiet:
    :param bool save_mtime:
    :param int timeout:
    :param bool commit:
    :return:
    """
    chain = ['/usr/bin/ffmpeg']
    if seek:
        chain += ['-ss', seek]
    chain += ['-i', inf]
    if faststart:
        chain += ['-movflags', '+faststart']
    if copy_antz:
        chain += ['-c', 'copy', '-avoid_negative_ts', 'make_zero']
    elif copy:
        chain += ['-c', 'copy']
    if to:
        chain += ['-to', to]
    chain.append(out)

    if commit:
        try:
            concur.run_subproc(chain, quiet=quiet, timeout_sec=timeout)
        except errors.Error:
            return False
    else:
        return ' '.join(chain)

    status = os.path.isfile(out)
    if status:
        if save_mtime:
            os.utime(out, (os.path.getatime(inf), os.path.getmtime(inf)))
    return status


def run_ffmpeg_pref(inf, out, **kwargs):
    options = {
        'faststart': True,
        'quiet': True,
        'save_mtime': True,
    }
    options.update(kwargs)
    return run_ffmpeg(inf, out, **options)


def check_ffmpeg_faststart(path):
    ext = os.path.splitext(path)[1]
    if ext in {'.m4a', '.mp3', '.wav'}:
        stream = 'a'
    else:
        stream = 'v'

    cmd = [
        '/usr/bin/ffprobe', '-v', 'error',
        '-show_entries', 'format=start_time',
        '-select_streams', stream,
        '-show_entries', 'packet=pos',
        '-read_intervals', '%+#1', path,
    ]
    output = concur.run_subproc(cmd, quiet=False, pipe=True)
    if m := re.search(r'pos=(\d+)', output.decode()):
        return int(m.group(1)) > 500
    return None
