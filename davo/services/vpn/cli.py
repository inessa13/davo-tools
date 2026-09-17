import sys

import davo.utils

from . import helpers


@davo.utils.cli.run
def main():
    account_name = sys.argv[1] if len(sys.argv) > 1 else None
    helpers.connect(account_name)


if __name__ == "__main__":
    main()
