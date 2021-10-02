import functools
import logging

import argcomplete

from davo import errors

logger = logging.getLogger(__name__)

_PROGRESS = (
    '[{progress}{arrow}{left}]'
    ' {progress_percent:3.0f}%'
    ' {ready}/{total}'
    '{elapsed}'
)


def run(func):
    @functools.wraps(func)
    def _wrap(*args, **kwargs):
        try:
            return func(*args, **kwargs)

        except KeyboardInterrupt:
            logger.warning('Interrupted')

        except errors.UserError as exc:
            logger.warning(exc.args[0])

        except errors.BaseError as exc:
            logger.error(exc.args[0])

    return _wrap


@run
def run_parser(parser, use_completion=True):
    if use_completion:
        argcomplete.autocomplete(parser)

    namespace = parser.parse_args()

    if getattr(namespace, 'func', None):
        namespace.func(namespace)
    else:
        parser.print_help()


def progress_line(
    ready, total, char_fill='=', char_arrow='>', char_pad=' ', len_full=40,
    elapsed=None,
):
    percent = ready / total
    progress = round(percent, 2) * 100
    progress_len = int(progress) * len_full // 100
    if elapsed is None:
        elapsed = ''
    else:
        elapsed = ' Elapsed: {:.2f}s'.format(elapsed)

    return _PROGRESS.format(
        progress=char_fill * progress_len,
        arrow=char_arrow,
        left=char_pad * (len_full - progress_len),
        progress_percent=progress,
        ready=ready,
        total=total,
        elapsed=elapsed,
    )


def spinner(index=0, pattern='|/-\\'):
    return pattern[index % len(pattern)]
