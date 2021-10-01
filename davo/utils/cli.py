import functools
import logging

import argcomplete

from davo import errors

logger = logging.getLogger(__name__)


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
