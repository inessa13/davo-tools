import subprocess
import threading

from .. import errors


def run_subproc(cmd, quiet=True, pipe=False, timeout_sec=1 * 60 * 60):
    def kill_proc(process):
        return process.kill()

    options = {}
    if quiet:
        options.update({
            'stdout': subprocess.DEVNULL,
            'stderr': subprocess.DEVNULL,
        })
    elif pipe:
        options.update({
            'stdout': subprocess.PIPE,
            'stderr': subprocess.PIPE,
        })
    with subprocess.Popen(cmd, shell=False, **options) as proc:
        timer = threading.Timer(timeout_sec, kill_proc, [proc])
        try:
            timer.start()
            stdout, stderr = proc.communicate()
            full_output = stdout + stderr
        except FileNotFoundError:
            raise errors.Error('executable not found')
        except Exception as exc:
            raise errors.Error('subprocess failed', exc)
        finally:
            timer.cancel()
    return full_output
