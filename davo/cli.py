# PYTHON_ARGCOMPLETE_OK
import argparse
import logging
import logging.config
import os

from . import errors, services, settings, utils, version

logger = logging.getLogger(__name__)


def init_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-V",
        "--version",
        action="version",
        version="%(prog)s " + version.__version__,
        help="show version and exit",
    )

    subparsers = parser.add_subparsers(title="list of commands")

    cmd = subparsers.add_parser("conf", help="conf tools")
    services.common.init_parser(cmd, commands=("keyring",))

    cmd = subparsers.add_parser("arch", help="archive tools")
    arch_subparsers = cmd.add_subparsers(title="list of commands")
    fns_rename = arch_subparsers.add_parser(
        "fns-rename", help="name FNS receipt HTML files"
    )
    fns_rename.add_argument("path", nargs="?", default=os.getcwd())
    fns_rename.add_argument(
        "-R",
        "--rename",
        action="store_true",
        help="rename source files instead of copying them",
    )
    fns_rename.add_argument(
        "-0",
        "--dry-run",
        action="store_true",
        help="show the rename plan without changing files",
    )
    fns_rename.set_defaults(
        func=lambda namespace: services.arch.command_fns_rename(
            root=namespace.path,
            rename=namespace.rename,
            dry_run=namespace.dry_run,
        )
    )

    check_norm = arch_subparsers.add_parser(
        "check-norm", help="normalize legacy archive document names"
    )
    check_norm.add_argument("paths", nargs="*", metavar="PATH")
    check_norm.add_argument(
        "-0",
        "--dry-run",
        action="store_true",
        help="show the rename plan without changing files",
    )
    check_norm.add_argument(
        "-r",
        "--recursive",
        action="store_true",
        help="scan subdirectories recursively",
    )
    check_norm.add_argument(
        "-u",
        "--underscores",
        action="store_true",
        help="use underscores instead of spaces in normalized names",
    )
    check_norm.add_argument(
        "-t",
        "--table",
        action="store_true",
        help="print the rename plan as an ASCII table",
    )
    check_norm.set_defaults(
        func=lambda namespace: services.arch.command_check_norm(
            paths=namespace.paths or [os.getcwd()],
            recursive=namespace.recursive,
            dry_run=namespace.dry_run,
            underscores=namespace.underscores,
            table=namespace.table,
        )
    )

    fns_extract = arch_subparsers.add_parser(
        "fns-extract", help="render FNS JSON receipts as HTML or PDF"
    )
    fns_extract.add_argument("json_path")
    fns_extract.add_argument("-o", "--out-dir")
    fns_extract.add_argument(
        "-A",
        "--no-autogen",
        action="store_true",
        help="omit autogen from generated filenames",
    )
    fns_extract.add_argument(
        "-t",
        "--type",
        choices=("html", "pdf"),
        default="html",
        help="output type (default: html)",
    )
    fns_extract.add_argument("-0", "--dry-run", action="store_true")
    fns_extract.set_defaults(func=_run_fns_extract)

    fns_dedup = arch_subparsers.add_parser(
        "fns-dedup", help="find FNS receipts already present in an archive"
    )
    fns_dedup.add_argument(
        "-d",
        "--directories",
        nargs="+",
        required=True,
        metavar="DIR",
        help="candidate directories to scan recursively",
    )
    fns_dedup.add_argument(
        "-r",
        "--reference",
        nargs="+",
        required=True,
        metavar="DIR",
        help="reference archive directories to scan recursively",
    )
    fns_dedup.add_argument(
        "-D",
        "--delete",
        action="store_true",
        help="delete duplicate files from candidate directories",
    )
    fns_dedup.add_argument(
        "-0",
        "--dry-run",
        action="store_true",
        help="show deletions without changing files",
    )
    fns_dedup.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="show files without an FNS fiscal identity",
    )
    fns_dedup.set_defaults(
        func=lambda namespace: services.arch.command_fns_dedup(
            directories=namespace.directories,
            reference=namespace.reference,
            delete=namespace.delete,
            dry_run=namespace.dry_run,
            verbose=namespace.verbose,
        )
    )

    fns_config = arch_subparsers.add_parser(
        "fns-config", help="manage FNS receipt settings"
    )
    fns_config_subparsers = fns_config.add_subparsers(title="list of commands")
    fns_init_map = fns_config_subparsers.add_parser(
        "init-map", help="add sellers from FNS JSON to davo-tools config"
    )
    fns_init_map.add_argument("json_path")
    fns_init_map.add_argument(
        "--local",
        action="store_true",
        help="write the nearest project .davo-tools.yaml",
    )
    fns_init_map.add_argument("-v", "--verbose", action="store_true")
    fns_init_map.add_argument(
        "-n",
        "--normalise",
        action="store_true",
        help="pre-fill new aliases with normalized seller names",
    )
    fns_init_map.add_argument(
        "-0",
        "--dry-run",
        action="store_true",
        help="show changes without writing",
    )
    fns_init_map.add_argument(
        "-e",
        "--extra-meta",
        action="store_true",
        help="add receipt metadata comments for new sellers",
    )
    fns_init_map.set_defaults(
        func=lambda namespace: services.arch.command_fns_config_init_map(
            namespace.json_path,
            local=namespace.local,
            verbose=namespace.verbose,
            normalise=namespace.normalise,
            dry_run=namespace.dry_run,
            extra_meta=namespace.extra_meta,
        )
    )
    fns_show_map = fns_config_subparsers.add_parser(
        "show-map", help="show effective FNS seller aliases"
    )
    fns_show_map.set_defaults(
        func=lambda namespace: services.arch.command_fns_config_show_map()
    )

    cmd = subparsers.add_parser("file", help="file tools")
    cmd, _subparsers = services.photo.cli.init_parser(
        cmd,
        commands=("rename", "iphone-clean-live", "search-duplicates"),
    )
    services.common.init_parser(cmd, _subparsers, commands=("compare",))

    cmd = subparsers.add_parser("vid", help="video tools")
    services.photo.cli.init_parser_clips(cmd)

    cmd = subparsers.add_parser("im", help="image tools")
    services.photo.cli.init_parser(
        cmd,
        commands=(
            "convert",
            "thumbs",
            "recover",
            "downscale",
            "fp",
            "diff",
            "info",
            "merge",
        ),
    )

    cmd = subparsers.add_parser("pdf", help="pdf tools")
    services.photo.cli.init_parser_pdf(cmd)

    cmd = subparsers.add_parser("vpn", help="connect vpn")
    cmd.add_argument("account", nargs="?", action="store")
    cmd.set_defaults(
        func=lambda namespace: services.vpn.helpers.connect(
            account_name=namespace.account,
        )
    )

    cmd = subparsers.add_parser(
        "cit", help="run git commands on multiple repos"
    )
    services.git_tools.init_parser(cmd)

    cmd = subparsers.add_parser("s3", help="s3 tools")
    services.s3sync.cli.init_parser(
        cmd,
        commands=(
            "config",
            "init",
            "info",
            "buckets",
            "list",
            "diff",
            "update",
            "cache-clean",
            "cache-update",
        ),
    )

    return parser


def _run_fns_extract(namespace):
    """Make extraction failures observable as a non-zero CLI exit status."""
    try:
        return services.arch.command_fns_extract(
            namespace.json_path,
            out_dir=namespace.out_dir,
            dry_run=namespace.dry_run,
            output_type=namespace.type,
            no_autogen=namespace.no_autogen,
        )
    except errors.UserError as exc:
        logger.error(exc)
        raise SystemExit(1) from exc


def main():
    logging.config.dictConfig(settings.LOGGING)
    parser = init_parser()
    utils.cli.run_parser(parser, use_completion=True)


if __name__ == "__main__":
    main()
