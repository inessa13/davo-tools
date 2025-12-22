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


def init_parser(parser=None, subparsers=None, commands=()):
    if parser is None:
        parser = argparse.ArgumentParser()
        parser.add_argument(
            '-V', '--version',
            action='version',
            version='%(prog)s ' + davo.version.__version__,
            help='show version and exit')

    p_recursive = argparse.ArgumentParser(add_help=False)
    p_recursive.add_argument(
        '-r', '--recursive', action='store_true', help='recursive scan')

    p_commit = argparse.ArgumentParser(add_help=False)
    p_commit.add_argument(
        '-c', '--commit', action='store_true', help='commit mode')

    p_verbose = argparse.ArgumentParser(add_help=False)
    p_verbose.add_argument('-v', '--verbose', action='store_true')

    p_silent = argparse.ArgumentParser(add_help=False)
    p_silent.add_argument('-s', '--silent', action='store_true')

    p_root = argparse.ArgumentParser(add_help=False)
    p_root.add_argument('path', nargs='?', default=os.getcwd())

    p_common = [p_root, p_recursive, p_commit, p_silent]
    p_PRCV = [p_root, p_recursive, p_commit, p_verbose]
    p_prcvs = [p_root, p_recursive, p_commit, p_verbose, p_silent]

    if subparsers is None:
        subparsers = parser.add_subparsers(title='list of commands')

    if not commands or 'tree' in commands:
        cmd = subparsers.add_parser(
            'tree', parents=[p_root, p_commit],
            help='move files into tree struct')
        cmd.add_argument(
            '-R', '--reverse', action='store_true',
            help='reverse tree to flat')
        cmd.set_defaults(func=lambda namespace: helpers.command_tree(
            root=namespace.path,
            reverse=namespace.reverse,
            commit=namespace.commit,
        ))

    if not commands or 'rename' in commands:
        choices_output = ('-', 'C', 'T')
        cmd = subparsers.add_parser(
            'rename',
            parents=[p_root, p_recursive, p_commit, p_verbose],
            help='rename files by regexp')
        cmd.add_argument(
            '-p', '--pattern', action='store', default='.*',
            help='search pattern, default %(default)s')
        cmd.add_argument(
            '-R', '--replace-pattern', action='store',
            default='[source].[Ext]',
            help='replace pattern')
        cmd.add_argument(
            '-d', '--date-around', action='store',
            help='approximate date, helps with extracting correct one. YYYYMMDD. used with `[dto:...]` classes')
        cmd.add_argument(
            '--date-fix', action='store',
            help='force to fix, used to calculate delta for date-around. used with `[dto:...]` classes')
        cmd.add_argument(
            '-D', '--date-force', action='store_true',
            help='force date-around, is difference is too big. used with `[dto:...]` classes')
        cmd.add_argument(
            '-o', '--output', action='store', choices=choices_output,
            default='T',
            help='replace pattern, default %(default)s')
        cmd.add_argument('-l', '--limit', action='store', type=int, default=0)
        cmd.add_argument('-C', '--copy', action='store_true')
        cmd.add_argument(
            '-F', '--filter', action='append', help='filter pattern')
        cmd.add_argument(
            '-X', '--exclude', action='append', help='exclude pattern')
        cmd.add_argument('--skip-no-exif', action='store_true')
        cmd.set_defaults(func=lambda namespace: helpers.command_regexp(
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
        ))

        cmd = subparsers.add_parser(
            'rename-classes',
            help='show classes list for rename command')
        cmd.set_defaults(func=lambda ns: helpers.command_regexp_classes())

        cmd = subparsers.add_parser(
            'rename-patterns',
            help='show pattern list for rename command')
        cmd.set_defaults(func=lambda ns: helpers.command_regexp_patterns())

    if not commands or 'thumbnail' in commands:
        cmd = subparsers.add_parser(
            'thumbnail', parents=p_common, help='prepare thumbnails')
        cmd.add_argument(
            '-s', '--size',
            action='store',
            type=int,
            default=120,
            help='default %(default)s')
        cmd.add_argument('-t', '--type', help='convert type')
        cmd.set_defaults(func=lambda namespace: helpers.command_thumbnail(
            root=namespace.path,
            size=namespace.size,
            type_=namespace.type,
            recursive=namespace.recursive,
            commit=namespace.commit,
        ))

    if not commands or 'convert' in commands:
        cmd = subparsers.add_parser(
            'convert',
            parents=p_common,
            help='convert images (PIL)')
        cmd.add_argument('-R', '--replace-pattern', default='[source].[Ext]')
        cmd.add_argument(
            '-D', '--delete-source', action='store_true',
            help='delete source files on image conversion if name had not '
                 'been changed',
        )
        cmd.add_argument(
            '-C', '--copy', action='store_true',
            help='make backup copies of source images on  conversion if '
                 'name had been changed',
        )
        cmd.add_argument('-t', '--thumbnail', type=int)
        cmd.add_argument('--skip-no-exif', action='store_true')
        cmd.add_argument('--drop-alpha', action='store_true')
        cmd.set_defaults(func=lambda namespace: helpers.command_convert(
            root=namespace.path,
            replace=namespace.replace_pattern,
            recursive=namespace.recursive,
            copy=namespace.copy,
            delete=namespace.delete_source,
            thumbnail=namespace.thumbnail,
            skip_no_exif=namespace.skip_no_exif,
            drop_alpha=namespace.drop_alpha,
            commit=namespace.commit,
        ))

    if not commands or 'thumbs' in commands:
        cmd = subparsers.add_parser(
            'thumbs',
            parents=[p_root, p_recursive],
            help='create thumbnails snapshot')
        cmd.add_argument(
            '-F', '--force', action='store_true', default=False)
        cmd.add_argument(
            '-s', '--size', action='store', type=int, default=300,
            help='thumbnail size, by default %(default)s')
        cmd.add_argument(
            '-c', '--cols', action='store', type=int, default=8,
            help='thumbnail max cols, by default %(default)s')
        cmd.add_argument(
            '-m', '--max-lines', action='store', type=int, default=10,
            help='thumbnail max lines, by default %(default)s')
        cmd.set_defaults(func=lambda namespace: helpers.command_thumbs(
            root=namespace.path,
            recursive=namespace.recursive,
            force=namespace.force,
            size=namespace.size,
            cols=namespace.cols,
            max_lines=namespace.max_lines,
            commit=True,
        ))

    if not commands or 'clips' in commands:
        cmd = subparsers.add_parser(
            'clips-convert',
            parents=p_prcvs,
            help='convert video (ffmpeg)')
        cmd.add_argument('-R', '--replace-pattern', default='[source].[Ext]')
        cmd.add_argument('-t', '--thumbnail', type=int)
        cmd.set_defaults(func=lambda namespace: helpers.command_convert_video(
            root=namespace.path,
            replace=namespace.replace_pattern,
            recursive=namespace.recursive,
            thumbnail=namespace.thumbnail,
            verbose=namespace.verbose,
            silent=namespace.silent,
            commit=namespace.commit,
        ))

        cmd = subparsers.add_parser(
            'clips-split',
            parents=[p_commit, p_silent, p_verbose],
            help='split video to clips (ffmpeg)')
        cmd.add_argument('path')
        cmd.add_argument('-e', '--ext', action='store')
        cmd.add_argument('points', nargs='+')
        cmd.set_defaults(func=lambda namespace: helpers.command_clips_split(
            root=namespace.path,
            points=namespace.points,
            ext=namespace.ext,
            verbose=namespace.verbose,
            silent=namespace.silent,
            commit=namespace.commit,
        ))

        cmd = subparsers.add_parser(
            'clips-trim',
            parents=p_prcvs,
            help='trim video (ffmpeg)')
        cmd.add_argument('--ss', action='store')
        cmd.add_argument('--to', action='store')
        cmd.set_defaults(func=lambda namespace: helpers.command_clips_trim(
            root=namespace.path,
            recursive=namespace.recursive,
            ss=namespace.ss,
            to=namespace.to,
            verbose=namespace.verbose,
            commit=namespace.commit,
        ))

        cmd = subparsers.add_parser(
            'clips-web',
            parents=p_prcvs,
            help='encode +faststart (ffmpeg)')
        cmd.set_defaults(func=lambda namespace: helpers.command_clips_web(
            root=namespace.path,
            recursive=namespace.recursive,
            verbose=namespace.verbose,
            silent=namespace.silent,
            commit=namespace.commit,
        ))

        cmd = subparsers.add_parser(
            'clips-isweb',
            parents=[p_root, p_recursive, p_silent],
            help='check is video encoded with +faststart (ffmpeg)')
        cmd.set_defaults(func=lambda namespace: helpers.command_clips_check_web(
            root=namespace.path,
            recursive=namespace.recursive,
        ))

    if not commands or 'iphone-clean-live' in commands:
        cmd = subparsers.add_parser(
            'iphone-clean-live',
            parents=p_common,
            help='clean iphone live photo .mov files')
        cmd.set_defaults(func=lambda namespace: helpers.command_live(
            root=namespace.path,
            recursive=namespace.recursive,
            commit=namespace.commit,
        ))

    if not commands or 'search-copies' in commands:
        cmd = subparsers.add_parser(
            'search-copies', parents=p_common, help='search file copies')
        cmd.add_argument('file')
        cmd.set_defaults(func=lambda namespace: helpers.command_search_copy(
            root=namespace.path,
            source_file=namespace.file,
            recursive=namespace.recursive,
        ))

    if not commands or 'search-duplicates' in commands:
        cmd = subparsers.add_parser(
            'search-duplicates', parents=[p_root, p_recursive, p_verbose],
            help='search duplicates')
        cmd.add_argument(
            '-m', '--md5', action='store_true', help='check md5 hash')
        cmd.set_defaults(func=lambda namespace: helpers.command_search_duplicates(  # noqa
            root=namespace.path,
            md5=namespace.md5,
            recursive=namespace.recursive,
            verbose=namespace.verbose,
        ))

    if not commands or 'recover' in commands:
        cmd = subparsers.add_parser(
            'recover', parents=[
                p_root,
                p_verbose,
                p_commit,
            ],
            help='recover (opencv)')
        cmd.add_argument('-a', '--algo', action='store')
        cmd.add_argument(
            '-s', '--scale', action='store', type=int, default=25,
            help='scaledown size for speedup in %%, default %(default)s%%'
        )
        cmd.add_argument(
            '-m', '--min-contour', action='store', type=int, default=30,
            help='min acceptable size of contour found in %%, default %(default)s%%'
        )
        cmd.add_argument(
            '-M', '--max-contour', action='store', type=int, default=99,
            help='max acceptable size of contour found in %%, default %(default)s%%',
        )
        cmd.add_argument(
            '-d', '--debug', action='store_true', default=False,
        help='create debug images for intermediate steps')
        cmd.set_defaults(func=lambda namespace: helpers.command_recover(  # noqa
            root=namespace.path,
            algo=namespace.algo,
            scale=namespace.scale,
            min_contour=namespace.min_contour,
            max_contour=namespace.max_contour,
            debug=namespace.debug,
            # recursive=namespace.recursive,
            verbose=namespace.verbose,
            commit=namespace.commit,
        ))

    if not commands or 'downscale' in commands:
        cmd = subparsers.add_parser(
            'downscale', parents=[
                p_root,
                p_verbose,
                p_commit,
            ],
            help='downscale with SSIM threshold (opencv)')
        cmd.add_argument(
            '-t', '--threshold', action='store', type=int, default=95,
            help='SSIM threshold in %%, default %(default)s%%'
        )
        cmd.add_argument(
            '-s', '--speed', action='store', type=int, default=5,
            help='downscale speed in %%, default %(default)s%%'
        )
        cmd.add_argument(
            '-w', '--min-width', action='store', type=int, default=1024,
        )
        cmd.add_argument(
            '-H', '--min-height', action='store', type=int, default=1024,
        )
        cmd.set_defaults(func=lambda namespace: helpers.command_downscale(  # noqa
            root=namespace.path,
            min_width=namespace.min_width,
            min_height=namespace.min_height,
            speed=namespace.speed,
            threshold=namespace.threshold,
            verbose=namespace.verbose,
            commit=namespace.commit,
        ))

    return parser, subparsers


def main():
    logging.config.dictConfig(davo.settings.LOGGING)
    parser = init_parser()
    davo.utils.cli.run_parser(parser, use_completion=True)


if __name__ == '__main__':
    main()
