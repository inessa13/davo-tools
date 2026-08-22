# PYTHON_ARGCOMPLETE_OK
import argparse
import logging
import logging.config
import os

import davo
import davo.utils
import davo.version

from . import helpers

logger = logging.getLogger(__name__)


def _form_dpi(value):
    try:
        dpi = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("DPI must be an integer") from exc
    if not 72 <= dpi <= 800:
        raise argparse.ArgumentTypeError("DPI must be from 72 to 800")
    return dpi


def init_parser(parser=None, subparsers=None, commands=()):
    if parser is None:
        parser = argparse.ArgumentParser()
        parser.add_argument(
            "-V",
            "--version",
            action="version",
            version="%(prog)s " + davo.version.__version__,
            help="show version and exit",
        )

    p_recursive = argparse.ArgumentParser(add_help=False)
    p_recursive.add_argument(
        "-r", "--recursive", action="store_true", help="recursive scan"
    )

    p_commit = argparse.ArgumentParser(add_help=False)
    p_commit.add_argument(
        "-c", "--commit", action="store_true", help="commit mode"
    )

    p_verbose = argparse.ArgumentParser(add_help=False)
    p_verbose.add_argument("-v", "--verbose", action="store_true")

    p_silent = argparse.ArgumentParser(add_help=False)
    p_silent.add_argument("-s", "--silent", action="store_true")

    p_root = argparse.ArgumentParser(add_help=False)
    p_root.add_argument("path", nargs="?", default=os.getcwd())

    p_common = [p_root, p_recursive, p_commit, p_silent]

    if subparsers is None:
        subparsers = parser.add_subparsers(title="list of commands")

    if not commands or "tree" in commands:
        cmd = subparsers.add_parser(
            "tree",
            parents=[p_root, p_commit],
            help="move files into tree struct",
        )
        cmd.add_argument(
            "-R", "--reverse", action="store_true", help="reverse tree to flat"
        )
        cmd.set_defaults(
            func=lambda namespace: helpers.command_tree(
                root=namespace.path,
                reverse=namespace.reverse,
                commit=namespace.commit,
            )
        )

    if not commands or "rename" in commands:
        choices_output = ("-", "C", "T")
        cmd = subparsers.add_parser(
            "rename",
            parents=[p_root, p_recursive, p_commit, p_verbose],
            help="rename files by regexp",
        )
        cmd.add_argument(
            "-p",
            "--pattern",
            action="store",
            default=".*",
            help="search pattern, default %(default)s",
        )
        cmd.add_argument(
            "-R",
            "--replace-pattern",
            action="store",
            default="[source].[Ext]",
            help="replace pattern",
        )
        cmd.add_argument(
            "-d",
            "--date-around",
            action="store",
            help=(
                "approximate date, helps with extracting correct one. "
                "YYYYMMDD. used with `[dto:...]` classes"
            ),
        )
        cmd.add_argument(
            "--date-fix",
            action="store",
            help=(
                "force to fix, used to calculate delta for date-around. "
                "used with `[dto:...]` classes"
            ),
        )
        cmd.add_argument(
            "-D",
            "--date-force",
            action="store_true",
            help=(
                "force date-around, is difference is too big. "
                "used with `[dto:...]` classes"
            ),
        )
        cmd.add_argument(
            "-o",
            "--output",
            action="store",
            choices=choices_output,
            default="T",
            help="replace pattern, default %(default)s",
        )
        cmd.add_argument("-l", "--limit", action="store", type=int, default=0)
        cmd.add_argument("-C", "--copy", action="store_true")
        cmd.add_argument(
            "-F", "--filter", action="append", help="filter pattern"
        )
        cmd.add_argument(
            "-X", "--exclude", action="append", help="exclude pattern"
        )
        cmd.add_argument("--skip-no-exif", action="store_true")
        cmd.set_defaults(
            func=lambda namespace: helpers.command_regexp(
                root=namespace.path,
                recursive=namespace.recursive,
                filters=namespace.filter,
                exclude=namespace.exclude,
                pattern=namespace.pattern,
                replace=namespace.replace_pattern,
                output=namespace.output,
                date_around=namespace.date_around,
                date_fix=namespace.date_fix,
                date_force=namespace.date_force,
                copy=namespace.copy,
                skip_no_exif=namespace.skip_no_exif,
                limit=namespace.limit,
                verbose=namespace.verbose,
                commit=namespace.commit,
            )
        )

        cmd = subparsers.add_parser(
            "rename-classes", help="show classes list for rename command"
        )
        cmd.set_defaults(func=lambda ns: helpers.command_regexp_classes())

        cmd = subparsers.add_parser(
            "rename-patterns", help="show pattern list for rename command"
        )
        cmd.set_defaults(func=lambda ns: helpers.command_regexp_patterns())

    if not commands or "thumbnail" in commands:
        cmd = subparsers.add_parser(
            "thumbnail",
            parents=[p_root, p_recursive, p_commit],
            help="prepare thumbnails",
        )
        cmd.add_argument(
            "-s",
            "--size",
            action="store",
            type=int,
            default=120,
            help="default %(default)s",
        )
        cmd.add_argument("-t", "--type", help="convert type")
        cmd.set_defaults(
            func=lambda namespace: helpers.command_thumbnail(
                root=namespace.path,
                size=namespace.size,
                type_=namespace.type,
                recursive=namespace.recursive,
                commit=namespace.commit,
            )
        )

    if not commands or "convert" in commands:
        cmd = subparsers.add_parser(
            "convert", parents=p_common, help="convert images (PIL)"
        )
        cmd.add_argument("-R", "--replace-pattern", default="[source].[Ext]")
        cmd.add_argument(
            "-D",
            "--delete-source",
            action="store_true",
            help="delete source files on image conversion if name had not "
            "been changed",
        )
        cmd.add_argument(
            "-C",
            "--copy",
            action="store_true",
            help="make backup copies of source images on  conversion if "
            "name had been changed",
        )
        cmd.add_argument("-t", "--thumbnail", type=int)
        cmd.add_argument("--skip-no-exif", action="store_true")
        cmd.add_argument("--drop-alpha", action="store_true")
        cmd.set_defaults(
            func=lambda namespace: helpers.command_convert(
                root=namespace.path,
                replace=namespace.replace_pattern,
                recursive=namespace.recursive,
                copy=namespace.copy,
                delete=namespace.delete_source,
                thumbnail=namespace.thumbnail,
                skip_no_exif=namespace.skip_no_exif,
                drop_alpha=namespace.drop_alpha,
                commit=namespace.commit,
            )
        )

    if not commands or "thumbs" in commands:
        cmd = subparsers.add_parser(
            "thumbs",
            parents=[p_root, p_recursive],
            help="create thumbnails snapshot",
        )
        cmd.add_argument("-F", "--force", action="store_true", default=False)
        cmd.add_argument(
            "-s",
            "--size",
            action="store",
            type=int,
            default=300,
            help="thumbnail size, by default %(default)s",
        )
        cmd.add_argument(
            "-c",
            "--cols",
            action="store",
            type=int,
            default=8,
            help="thumbnail max cols, by default %(default)s",
        )
        cmd.add_argument(
            "-m",
            "--max-lines",
            action="store",
            type=int,
            default=10,
            help="thumbnail max lines, by default %(default)s",
        )
        cmd.set_defaults(
            func=lambda namespace: helpers.command_thumbs(
                root=namespace.path,
                recursive=namespace.recursive,
                force=namespace.force,
                size=namespace.size,
                cols=namespace.cols,
                max_lines=namespace.max_lines,
                commit=True,
            )
        )

    if not commands or "clips" in commands:
        init_parser_clips(parser, subparsers, prefix="clips-")

    if not commands or "iphone-clean-live" in commands:
        cmd = subparsers.add_parser(
            "iphone-clean-live",
            parents=p_common,
            help="clean iphone live photo .mov files",
        )
        cmd.set_defaults(
            func=lambda namespace: helpers.command_live(
                root=namespace.path,
                recursive=namespace.recursive,
                commit=namespace.commit,
            )
        )

    if not commands or "search-copies" in commands:
        cmd = subparsers.add_parser(
            "search-copies", parents=p_common, help="search file copies"
        )
        cmd.add_argument("file")
        cmd.set_defaults(
            func=lambda namespace: helpers.command_search_copy(
                root=namespace.path,
                source_file=namespace.file,
                recursive=namespace.recursive,
            )
        )

    if not commands or "search-duplicates" in commands:
        cmd = subparsers.add_parser(
            "search-duplicates",
            parents=[p_root, p_recursive, p_verbose],
            help="search duplicates",
        )
        cmd.add_argument(
            "-m", "--md5", action="store_true", help="check md5 hash"
        )
        cmd.set_defaults(
            func=lambda namespace: helpers.command_search_duplicates(  # noqa
                root=namespace.path,
                md5=namespace.md5,
                recursive=namespace.recursive,
                verbose=namespace.verbose,
            )
        )

    if not commands or "recover" in commands:
        cmd = subparsers.add_parser(
            "recover",
            parents=[
                p_root,
                p_verbose,
                p_commit,
            ],
            help="recover (opencv)",
        )
        cmd.add_argument("-a", "--algo", action="store")
        cmd.add_argument(
            "-s",
            "--scale",
            action="store",
            type=int,
            default=25,
            help="scaledown size for speedup in %%, default %(default)s%%",
        )
        cmd.add_argument(
            "-m",
            "--min-contour",
            action="store",
            type=int,
            default=30,
            help=(
                "min acceptable size of contour found in %%, "
                "default %(default)s%%"
            ),
        )
        cmd.add_argument(
            "-M",
            "--max-contour",
            action="store",
            type=int,
            default=99,
            help=(
                "max acceptable size of contour found in %%, "
                "default %(default)s%%"
            ),
        )
        cmd.add_argument(
            "-d",
            "--debug",
            action="store_true",
            default=False,
            help="create debug images for intermediate steps",
        )
        cmd.set_defaults(
            func=lambda namespace: helpers.command_recover(  # noqa
                root=namespace.path,
                algo=namespace.algo,
                scale=namespace.scale,
                min_contour=namespace.min_contour,
                max_contour=namespace.max_contour,
                debug=namespace.debug,
                # recursive=namespace.recursive,
                verbose=namespace.verbose,
                commit=namespace.commit,
            )
        )

    if not commands or "downscale" in commands:
        cmd = subparsers.add_parser(
            "downscale",
            parents=[
                p_root,
                p_verbose,
                p_commit,
            ],
            help="downscale with SSIM threshold (opencv)",
        )
        cmd.add_argument(
            "-t",
            "--threshold",
            action="store",
            type=int,
            default=95,
            help="SSIM threshold in %%, default %(default)s%%",
        )
        cmd.add_argument(
            "-s",
            "--speed",
            action="store",
            type=int,
            default=5,
            help="downscale speed in %%, default %(default)s%%",
        )
        cmd.add_argument(
            "-w",
            "--min-width",
            action="store",
            type=int,
            default=1024,
        )
        cmd.add_argument(
            "-H",
            "--min-height",
            action="store",
            type=int,
            default=1024,
        )
        cmd.set_defaults(
            func=lambda namespace: helpers.command_downscale(  # noqa
                root=namespace.path,
                min_width=namespace.min_width,
                min_height=namespace.min_height,
                speed=namespace.speed,
                threshold=namespace.threshold,
                verbose=namespace.verbose,
                commit=namespace.commit,
            )
        )

    if not commands or "fp" in commands:
        cmd = subparsers.add_parser(
            "fp",
            help="print image feature vector and pHash",
        )
        cmd.add_argument("image", metavar="IMAGE")
        cmd.set_defaults(
            func=lambda namespace: helpers.command_fingerprint(
                image=namespace.image,
            )
        )

    if not commands or "diff" in commands:
        cmd = subparsers.add_parser(
            "diff",
            help="compare image features or file sizes",
        )
        cmd.add_argument(
            "-r",
            "--recursive",
            action="store_true",
            help="scan directories recursively",
        )
        cmd.add_argument(
            "-t",
            "--table",
            action="store_true",
            help="print an ASCII table instead of TSV",
        )
        cmd.add_argument(
            "-a",
            "--all",
            action="store_true",
            help="include pairs with different status",
        )
        cmd.add_argument(
            "-f",
            "--fast",
            action="store_true",
            help="compare image file sizes without reading image contents",
        )
        cmd.add_argument(
            "-g",
            "--group",
            action="store_true",
            help="group folders with matching images",
        )
        cmd.add_argument("images", metavar="IMAGE", nargs="+")
        cmd.set_defaults(
            func=lambda namespace: helpers.command_fingerprint_diff(
                images=namespace.images,
                recursive=namespace.recursive,
                table=namespace.table,
                show_all=namespace.all,
                fast=namespace.fast,
                group=namespace.group,
            )
        )

    if not commands or "info" in commands:
        cmd = subparsers.add_parser(
            "info",
            help="show image metadata (Pillow)",
        )
        cmd.add_argument("-v", "--verbose", action="store_true")
        cmd.add_argument(
            "-t",
            "--table",
            action="store_true",
            help="print an ASCII table",
        )
        cmd.add_argument(
            "-c",
            "--compact",
            action="store_true",
            help="print image rows without file names or column headers",
        )
        exif_group = cmd.add_mutually_exclusive_group()
        exif_group.add_argument(
            "-e",
            "--exif",
            action="store_true",
            help="include basic EXIF date and camera columns",
        )
        exif_group.add_argument(
            "-E",
            "--exif-full",
            action="store_true",
            help="print all available EXIF tags after each image",
        )
        cmd.add_argument("images", metavar="IMAGE", nargs="*")
        cmd.set_defaults(
            func=lambda namespace: helpers.command_image_info(
                images=namespace.images,
                verbose=namespace.verbose,
                table=namespace.table,
                compact=namespace.compact,
                exif=namespace.exif,
                exif_full=namespace.exif_full,
            )
        )

    if not commands or "merge" in commands:
        cmd = subparsers.add_parser(
            "merge",
            help="merge images sequentially",
        )
        direction = cmd.add_mutually_exclusive_group(required=True)
        direction.add_argument(
            "-V",
            "--vertical",
            action="store_true",
            help="place images from top to bottom",
        )
        direction.add_argument(
            "-H",
            "--horizontal",
            action="store_true",
            help="place images from left to right",
        )
        cmd.add_argument("-o", "--out", help="output image path")
        cmd.add_argument(
            "--debug-fill",
            action="store_true",
            help="fill unused and transparent areas with magenta",
        )
        cmd.add_argument(
            "-S",
            "--smart",
            action="store_true",
            help="align adjacent overlaps, sideways shifts, and scale",
        )
        cmd.add_argument("images", metavar="IMAGE", nargs="+")
        cmd.set_defaults(
            func=lambda namespace: helpers.command_image_merge(
                images=namespace.images,
                vertical=namespace.vertical,
                out=namespace.out,
                debug_fill=namespace.debug_fill,
                smart=namespace.smart,
            )
        )

    if not commands or "pdf" in commands:
        init_parser_pdf(
            parser,
            subparsers,
            prefix="pdf-",
            legacy=True,
            commands=(
                "merge",
                "rotate",
                "delete",
            ),
        )

    return parser, subparsers


def init_parser_clips(parser=None, subparsers=None, prefix=""):
    """Register video commands with either grouped or legacy names."""
    if parser is None:
        parser = argparse.ArgumentParser()

    p_recursive = argparse.ArgumentParser(add_help=False)
    p_recursive.add_argument(
        "-r", "--recursive", action="store_true", help="recursive scan"
    )

    p_commit = argparse.ArgumentParser(add_help=False)
    p_commit.add_argument(
        "-c", "--commit", action="store_true", help="commit mode"
    )

    p_verbose = argparse.ArgumentParser(add_help=False)
    p_verbose.add_argument("-v", "--verbose", action="store_true")

    p_silent = argparse.ArgumentParser(add_help=False)
    p_silent.add_argument("-s", "--silent", action="store_true")

    p_root = argparse.ArgumentParser(add_help=False)
    p_root.add_argument("path", nargs="?", default=os.getcwd())
    p_prcvs = [p_root, p_recursive, p_commit, p_verbose, p_silent]

    if subparsers is None:
        subparsers = parser.add_subparsers(title="list of commands")

    def command_name(name):
        return "{}{}".format(prefix, name)

    cmd = subparsers.add_parser(
        command_name("convert"),
        parents=p_prcvs,
        help="convert video (ffmpeg)",
    )
    cmd.add_argument("-R", "--replace-pattern", default="[source].[Ext]")
    cmd.add_argument("-t", "--thumbnail", type=int)
    cmd.set_defaults(
        func=lambda namespace: helpers.command_convert_video(
            root=namespace.path,
            replace=namespace.replace_pattern,
            recursive=namespace.recursive,
            thumbnail=namespace.thumbnail,
            verbose=namespace.verbose,
            silent=namespace.silent,
            commit=namespace.commit,
        )
    )

    cmd = subparsers.add_parser(
        command_name("split"),
        parents=[p_commit, p_silent, p_verbose],
        help="split video to clips (ffmpeg)",
    )
    cmd.add_argument("path")
    cmd.add_argument("-e", "--ext", action="store")
    cmd.add_argument("points", nargs="+")
    cmd.set_defaults(
        func=lambda namespace: helpers.command_clips_split(
            root=namespace.path,
            points=namespace.points,
            ext=namespace.ext,
            verbose=namespace.verbose,
            silent=namespace.silent,
            commit=namespace.commit,
        )
    )

    cmd = subparsers.add_parser(
        command_name("trim"),
        parents=p_prcvs,
        help="trim video (ffmpeg)",
    )
    cmd.add_argument("--ss", action="store")
    cmd.add_argument("--to", action="store")
    cmd.set_defaults(
        func=lambda namespace: helpers.command_clips_trim(
            root=namespace.path,
            recursive=namespace.recursive,
            ss=namespace.ss,
            to=namespace.to,
            verbose=namespace.verbose,
            commit=namespace.commit,
        )
    )

    cmd = subparsers.add_parser(
        command_name("web"),
        parents=p_prcvs,
        help="encode +faststart (ffmpeg)",
    )
    cmd.set_defaults(
        func=lambda namespace: helpers.command_clips_web(
            root=namespace.path,
            recursive=namespace.recursive,
            verbose=namespace.verbose,
            silent=namespace.silent,
            commit=namespace.commit,
        )
    )

    cmd = subparsers.add_parser(
        command_name("isweb"),
        parents=[p_root, p_recursive, p_silent],
        help="check is video encoded with +faststart (ffmpeg)",
    )
    cmd.set_defaults(
        func=lambda namespace: helpers.command_clips_check_web(
            root=namespace.path,
            recursive=namespace.recursive,
            silent=namespace.silent,
        )
    )


def init_parser_pdf(
    parser=None,
    subparsers=None,
    prefix="",
    commands=(),
    legacy=False,
):
    if subparsers is None:
        if parser is None:
            parser = argparse.ArgumentParser()
            parser.add_argument(
                "-V",
                "--version",
                action="version",
                version="%(prog)s " + davo.version.__version__,
                help="show version and exit",
            )
        subparsers = parser.add_subparsers(title="list of commands")

    p_verbose = argparse.ArgumentParser(add_help=False)
    p_verbose.add_argument("-v", "--verbose", action="store_true")
    parents = [p_verbose]
    if legacy:
        p_root = argparse.ArgumentParser(add_help=False)
        p_root.add_argument("path", nargs="?", default=os.getcwd())
        parents.insert(0, p_root)
    p_rewrite = argparse.ArgumentParser(add_help=False)
    p_rewrite.add_argument(
        "-W",
        "--rewrite",
        action="store_true",
        help="overwrite existing output files (never input files)",
    )
    write_parents = [*parents, p_rewrite]

    def add_input_argument(command, multiple=False):
        if legacy:
            command.add_argument(
                "-i",
                "--inf",
                nargs="+" if multiple else None,
            )
            return
        command.add_argument(
            "inf",
            nargs="+" if multiple else None,
            metavar="INPUT",
        )

    def root(namespace):
        return namespace.path if legacy else None

    if not commands or "merge" in commands:
        cmd = subparsers.add_parser(
            "{}merge".format(prefix),
            parents=write_parents,
            help="merge pdf files (PyMuPDF)",
        )
        cmd.add_argument("-o", "--out", action="store")
        add_input_argument(cmd, multiple=True)
        cmd.set_defaults(
            func=lambda namespace: helpers.command_pdf_merge(  # noqa
                root=root(namespace),
                out=namespace.out,
                inf=namespace.inf,
                rewrite=namespace.rewrite,
                verbose=namespace.verbose,
            )
        )

    if not commands or "rotate" in commands:
        cmd = subparsers.add_parser(
            "{}rotate".format(prefix),
            parents=write_parents,
            help="pdf: rotate pages (PyMuPDF)",
        )
        cmd.add_argument("-o", "--out", action="store")
        add_input_argument(cmd)
        cmd.add_argument(
            "-d",
            "--dir",
            action="store",
            choices=("left", "right"),
            default="right",
        )
        cmd.set_defaults(
            func=lambda namespace: helpers.command_pdf_rotate(  # noqa
                root=root(namespace),
                out=namespace.out,
                inf=namespace.inf,
                direction=namespace.dir,
                rewrite=namespace.rewrite,
                verbose=namespace.verbose,
            )
        )

    if not commands or "delete" in commands:
        cmd = subparsers.add_parser(
            "{}delete".format(prefix),
            parents=write_parents,
            help="pdf: delete pages (PyMuPDF)",
        )
        cmd.add_argument("-o", "--out", action="store")
        add_input_argument(cmd)
        cmd.add_argument(
            "-p",
            "--pages",
            nargs="+",
            type=int,
            help="pages to delete, 1-based",
        )
        cmd.set_defaults(
            func=lambda namespace: helpers.command_pdf_delete(  # noqa
                root=root(namespace),
                out=namespace.out,
                inf=namespace.inf,
                pages=namespace.pages,
                rewrite=namespace.rewrite,
                verbose=namespace.verbose,
            )
        )

    if not commands or "split" in commands:
        cmd = subparsers.add_parser(
            "{}split".format(prefix),
            parents=write_parents,
            help="pdf: split into separate docs (PyMuPDF)",
        )
        cmd.add_argument("-o", "--out", action="store")
        add_input_argument(cmd)
        cmd.add_argument(
            "-p",
            "--pages",
            nargs="+",
            type=int,
            help="pages to split, 1-based, first page of block to split",
        )
        cmd.set_defaults(
            func=lambda namespace: helpers.command_pdf_split(  # noqa
                root=root(namespace),
                out=namespace.out,
                inf=namespace.inf,
                pages=namespace.pages,
                rewrite=namespace.rewrite,
                verbose=namespace.verbose,
            )
        )

    if not commands or "clean" in commands:
        cmd = subparsers.add_parser(
            "{}clean".format(prefix),
            parents=write_parents,
            help="pdf: delete pages (PyMuPDF)",
        )
        cmd.add_argument("-o", "--out", action="store")
        add_input_argument(cmd)
        cmd.set_defaults(
            func=lambda namespace: helpers.command_pdf_clean(  # noqa
                root=root(namespace),
                out=namespace.out,
                inf=namespace.inf,
                rewrite=namespace.rewrite,
                verbose=namespace.verbose,
            )
        )

    if not commands or "compress" in commands:
        cmd = subparsers.add_parser(
            "{}compress".format(prefix),
            parents=write_parents,
            help="pdf: compress embedded images (PyMuPDF)",
        )
        cmd.add_argument("-o", "--out", action="store")
        add_input_argument(cmd)
        cmd.add_argument(
            "-d", "--dpi",
            action="store",
            type=int,
            choices=(72, 96, 150, 200, 300, 400),
            default=300,
            help="target embedded image dpi, default %(default)s",
        )
        cmd.add_argument(
            "-q", "--quality",
            action="store",
            type=int,
            metavar="0..100",
            default=80,
            help="jpeg recompression quality 0..100, default %(default)s",
        )
        cmd.add_argument(
            "-g", "--grayscale",
            action="store_true",
            help=(
                "convert the output document to grayscale before rewriting "
                "images"
            ),
        )
        cmd.set_defaults(
            func=lambda namespace: helpers.command_pdf_compress(  # noqa
                root=root(namespace),
                out=namespace.out,
                inf=namespace.inf,
                dpi=namespace.dpi,
                quality=namespace.quality,
                grayscale=namespace.grayscale,
                rebuild=True,
                rewrite=namespace.rewrite,
                verbose=namespace.verbose,
            )
        )

    if not commands or "form" in commands:
        cmd = subparsers.add_parser(
            "{}form".format(prefix),
            parents=write_parents,
            help="form PDF and image pages to a paper size (PyMuPDF)",
        )
        cmd.add_argument("-o", "--out", action="store")
        format_group = cmd.add_mutually_exclusive_group(required=True)
        format_group.add_argument(
            "-4", dest="paper_format", action="store_const", const="a4",
            help="A4 paper size",
        )
        format_group.add_argument(
            "-5", dest="paper_format", action="store_const", const="a5",
            help="A5 paper size",
        )
        format_group.add_argument(
            "-6", dest="paper_format", action="store_const", const="a6",
            help="A6 paper size",
        )
        format_group.add_argument(
            "-s", "--size", nargs=2, type=float, metavar=("WIDTH", "HEIGHT"),
            help="custom paper size in centimetres",
        )
        orientation_group = cmd.add_mutually_exclusive_group()
        orientation_group.add_argument(
            "--force-landscape", dest="force_orientation",
            action="store_const", const="landscape",
            help="use landscape sheets for all output pages",
        )
        orientation_group.add_argument(
            "--force-portrait", dest="force_orientation",
            action="store_const", const="portrait",
            help="use portrait sheets for all output pages",
        )
        dpi_group = cmd.add_mutually_exclusive_group()
        dpi_group.add_argument(
            "-H", dest="dpi", action="store_const", const=400,
            help="target image DPI: 400",
        )
        dpi_group.add_argument(
            "-Q", dest="dpi", action="store_const", const=300,
            help="target image DPI: 300",
        )
        dpi_group.add_argument(
            "-M", dest="dpi", action="store_const", const=200,
            help="target image DPI: 200",
        )
        dpi_group.add_argument(
            "-l", dest="dpi", action="store_const", const=150,
            help="target image DPI: 150",
        )
        dpi_group.add_argument(
            "-L", dest="dpi", action="store_const", const=96,
            help="target image DPI: 96",
        )
        dpi_group.add_argument(
            "--dpi", type=_form_dpi, metavar="N",
            help="target image DPI, from 72 to 800",
        )
        cmd.add_argument(
            "-q", "--quality",
            action="store",
            type=int,
            metavar="0..100",
            default=80,
            help="jpeg recompression quality 0..100, default %(default)s",
        )
        cmd.add_argument(
            "--debug-fill",
            action="store_true",
            help="fill page margins with magenta for layout debugging",
        )
        cmd.add_argument(
            "-R", "--rename-processed",
            action="store_true",
            help="rename each source with a _processed suffix after success",
        )
        add_input_argument(cmd, multiple=True)
        cmd.set_defaults(
            dpi=300,
            func=lambda namespace: helpers.command_pdf_form(  # noqa
                root=root(namespace),
                out=namespace.out,
                inf=namespace.inf,
                paper_format=namespace.paper_format,
                size_cm=namespace.size,
                force_orientation=namespace.force_orientation,
                dpi=namespace.dpi,
                quality=namespace.quality,
                debug_fill=namespace.debug_fill,
                rename_processed=namespace.rename_processed,
                rewrite=namespace.rewrite,
                verbose=namespace.verbose,
            )
        )

    if not commands or "extract" in commands:
        cmd = subparsers.add_parser(
            "{}extract".format(prefix),
            parents=write_parents,
            help="pdf: extract embedded images (PyMuPDF)",
        )
        cmd.add_argument("-o", "--out", action="store")
        add_input_argument(cmd)
        cmd.add_argument(
            "-p",
            "--pages",
            nargs="+",
            type=int,
            help="pages to inspect, 1-based",
        )
        cmd.add_argument(
            "-t",
            "--type",
            action="store",
            choices=("jpg", "png"),
        )
        cmd.add_argument(
            "-w",
            "--whole-page",
            action="store_true",
            help="render each selected page into one image",
        )
        cmd.set_defaults(
            func=lambda namespace: helpers.command_pdf_extract(  # noqa
                root=root(namespace),
                inf=namespace.inf,
                out=namespace.out,
                pages=namespace.pages,
                output_type=namespace.type,
                whole_page=namespace.whole_page,
                rewrite=namespace.rewrite,
                verbose=namespace.verbose,
            )
        )

    if not commands or "info" in commands:
        cmd = subparsers.add_parser(
            "{}info".format(prefix),
            parents=parents,
            help="pdf: show page metadata (PyMuPDF)",
        )
        if legacy:
            add_input_argument(cmd, multiple=True)
        else:
            cmd.add_argument("inf", nargs="*", metavar="INPUT")
        cmd.add_argument(
            "-p",
            "--pages",
            nargs="+",
            type=int,
            help="pages to inspect, 1-based",
        )
        cmd.add_argument(
            "--pt",
            action="store_true",
            help="show non-standard page sizes in points",
        )
        cmd.add_argument(
            "-t",
            "--table",
            action="store_true",
            help="print an ASCII table",
        )
        cmd.add_argument(
            "--compact",
            action="store_true",
            help="print page rows without file names or column headers",
        )
        cmd.set_defaults(
            func=lambda namespace: helpers.command_pdf_info(  # noqa
                root=root(namespace),
                inf=namespace.inf,
                pages=namespace.pages,
                verbose=namespace.verbose,
                pt=namespace.pt,
                table=namespace.table,
                compact=namespace.compact,
            )
        )

    if not commands or "scale" in commands:
        cmd = subparsers.add_parser(
            "{}scale".format(prefix),
            parents=write_parents,
            help="pdf: scale pages to A4/A5 (PyMuPDF)",
        )
        cmd.add_argument("-o", "--out", action="store")
        add_input_argument(cmd)
        cmd.add_argument(
            "-p",
            "--pages",
            nargs="+",
            type=int,
            help="pages to scale, 1-based",
        )
        cmd.add_argument(
            "-f",
            "--format",
            dest="paper_format",
            action="store",
            choices=("a4", "a5"),
            default="a4",
            help="target paper format, default %(default)s",
        )
        cmd.set_defaults(
            func=lambda namespace: helpers.command_pdf_scale(  # noqa
                root=root(namespace),
                out=namespace.out,
                inf=namespace.inf,
                pages=namespace.pages,
                paper_format=namespace.paper_format,
                rewrite=namespace.rewrite,
                verbose=namespace.verbose,
            )
        )


def main():
    logging.config.dictConfig(davo.settings.LOGGING)
    parser, _subparsers = init_parser()
    davo.utils.cli.run_parser(parser, use_completion=True)


if __name__ == "__main__":
    main()
