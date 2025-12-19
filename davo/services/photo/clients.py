import os
import re

from davo.utils import concur


def convert_ffmpeg(
    path_source, path_dest, thumbnail=None, timeout=1 * 60 * 60, commit=False,
):
    """
    :param str path_source:
    :param Union[str] path_dest:
    :param int thumbnail:
    :param int timeout:
    :param bool commit:
    """
    if not os.path.isfile(path_source):
        return False, 'missing'

    if thumbnail:
        file_name, ext = os.path.splitext(path_dest)
        path_dest = file_name + '.jpg'

    if path_source == path_dest:
        return False, 'same name'

    if os.path.exists(path_dest):
        return False, 'exists'

    status = True
    if commit:
        status = run_ffmpeg_pref(path_source, path_dest, timeout=timeout)
        if not status:
            path_dest = 'failed'

    return status, path_dest


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
        concur.run_subproc(chain, quiet=quiet, timeout_sec=timeout)
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
    cmd = [
        '/usr/bin/ffprobe', '-v', 'error', '-show_entries',
        'format=start_time', '-select_streams', 'v', '-show_entries',
        'packet=pos', '-read_intervals', '%+#1', path,
    ]
    output = concur.run_subproc(cmd, quiet=False, pipe=True)
    if m := re.search(r'pos=(\d+)', output.decode()):
        return int(m.group(1)) > 500
    return None
