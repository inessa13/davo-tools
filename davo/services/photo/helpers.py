import datetime
import glob
import logging
import math
import os
import re
import shutil
import time

try:
    import cv2
except ImportError:
    cv2 = None
import numpy
from PIL import Image

import davo.utils
from davo import errors
from davo.utils import format as format_utils

try:
    from . import recover
except ImportError:
    pass

from . import (
    clients,
    fingerprint,
    image_info,
    pdf,
    replace_classes,
    utils,
    video_info,
)

logger = logging.getLogger(__name__)

P_LIVE = r"(:?IMG_\d{8}_\d{6} \()?IMG_(?P<num>\d+)\)?\.(?P<ext>.*)$"
FAST_DIFF_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".webp", ".heic"})
JPEG_FORMATS = frozenset({"JPEG", "MPO"})
MAGENTA = (255, 0, 255, 255)
VIDEO_EXTENSIONS = frozenset(
    {
        ".3gp",
        ".avi",
        ".flv",
        ".m2ts",
        ".m4v",
        ".mkv",
        ".mov",
        ".mp4",
        ".mpeg",
        ".mpg",
        ".mts",
        ".ogv",
        ".ts",
        ".webm",
        ".wmv",
    }
)


def command_tree(root, reverse, commit=False):
    if reverse:
        _command_tree_reverse(
            root=root,
            commit=commit,
        )
    else:
        _command_tree_straight(
            root=root,
            commit=commit,
        )


def _command_tree_straight(root, commit=False):
    sub_root_set = set()
    for file in utils.iter_files(root, recursive=False):
        sub_root, sub, base = utils.date_as_path(file)
        if not os.path.exists(sub_root) and sub_root not in sub_root_set:
            logger.info("mkdir -p %s", sub)
            if commit:
                os.makedirs(sub_root)
            else:
                sub_root_set.add(sub_root)

        logger.info("mv %s %s", base, sub)
        if commit:
            os.rename(file, os.path.join(sub_root, base))


def _command_tree_reverse(root, commit=False):
    context = {}
    for file in utils.iter_files(root, recursive=True):
        sub_root, base = os.path.split(file)
        context.setdefault(base, []).append(file)

    if any(len(value) != 1 for value in context.values()):
        logger.error("there is duplicates, aborting")

    for base, files in context.items():
        file = files[0]
        logger.info("mv %s %s", file.replace(root + "/", ""), base)
        if commit:
            os.rename(file, os.path.join(root, base))


def command_regexp_classes():
    print("Available classes:")
    for k, v in replace_classes.CLASSES.items():
        print(" {}{}".format("static ", k))

    for k, v in replace_classes.CLASSES_RE.items():
        print(" {}{}".format("regexp ", k))


def command_regexp_patterns():
    print("Available patterns:")
    for k, v in replace_classes.PATTERNS.items():
        print(" {}{}".format(k.ljust(20, " "), v.get("help")))


def _parse_date(value):
    if "-" in value:
        p = "%Y%m%d-%H%M%S"
    else:
        p = "%Y%m%d"
    try:
        value = datetime.datetime.strptime(value, p)
    except ValueError:
        raise errors.UserError(
            "Invalid date: {}. Use `Ymd[-HMS]` format".format(value)
        )
    return value


def command_regexp(
    root,
    recursive,
    filters,
    exclude,
    pattern,
    replace,
    output,
    date_around,
    date_fix,
    date_force,
    copy,
    skip_no_exif,
    limit=0,
    verbose=False,
    commit=False,
):
    if date_around:
        date_around = _parse_date(date_around)
    if date_fix:
        date_fix = _parse_date(date_fix)

    if pattern_options := utils.get_known_pattern(pattern):
        pattern, replace = pattern_options

    mkdir_no_commit = set()

    index = 1
    for file_path in sorted(utils.iter_files(root, recursive=recursive)):
        file_root, base = os.path.split(file_path)

        if not re.match(pattern, base):
            continue

        if filters:
            if not any(re.search(p, base) for p in filters):
                continue

        if exclude:
            if any(re.search(p, base) for p in exclude):
                continue

        context = {
            "verbose": verbose,
            "index": index,
            "date_around": date_around,
            "date_fix": date_fix,
            "date_force": date_force,
        }

        sub_path = file_root.replace(root, ".")
        if sub_path:
            base = os.path.join(sub_path, base)
            context["sub_root"] = sub_path

        if skip_no_exif:
            exif = utils.get_exif(file_path)
            if exif is None:
                continue
            context["exif_data"] = exif

        new_name = utils.replace_file_params(
            file_path, pattern, replace, **context
        )
        if not new_name:
            continue

        new_path = os.path.abspath(os.path.join(root, new_name))
        if sub_path:
            new_name = new_path.replace(root, ".")

        if output == "C":
            if copy:
                cmd = "cp"
            else:
                cmd = "mv"
            logger.info("%s %s %s", cmd, base, new_name)
        elif output == "T":
            logger.info("%-41s %s", base, new_name)

        # if '/' in new_name:
        new_root, _ = os.path.split(new_path)
        if not os.path.exists(new_root) and new_root not in mkdir_no_commit:
            if output == "C":
                logger.info("mkdir -p %s", os.path.dirname(new_name))
            elif output == "T":
                logger.info("%s", os.path.dirname(new_name))

            if commit:
                os.makedirs(new_root)
            else:
                mkdir_no_commit.add(new_root)

        if commit:
            if os.path.exists(new_path):
                raise errors.UserError(
                    "File already exists: {}".format(new_path)
                )
            if copy:
                shutil.copy2(file_path, new_path)
            else:
                os.rename(file_path, new_path)

        if limit and index >= limit:
            logger.info("limit reached")
            break
        index += 1


def command_live(root, recursive, commit=False):
    context = {}
    for file in utils.iter_files(root, recursive=recursive):
        root, basename = os.path.split(file)
        if not (m := re.match(P_LIVE, basename)):
            continue

        num = m.group("num")
        ext = m.group("ext").lower()
        if ext == "jpeg":
            ext = "jpg"

        context.setdefault(root, {}).setdefault(num, {}).setdefault(
            ext, basename
        )

    for root, nums in context.items():
        for num, ext_s in nums.items():
            if len(ext_s) != 2 or set(ext_s.keys()) != {"mov", "jpg"}:
                continue
            mov_path = ext_s["mov"]
            logger.info("rm %s", mov_path)
            if commit:
                os.remove(os.path.join(root, mov_path))


def command_thumbnail(root, size, recursive, type_, commit=False):
    thumbnails_dir = ".thumbnails"
    thumbnails_root = os.path.join(root, thumbnails_dir)
    if not os.path.exists(thumbnails_root):
        logger.info("mkdir -p %s", thumbnails_root)
        if commit:
            os.makedirs(thumbnails_root)

    for file in utils.iter_files(root, recursive=recursive):
        try:
            image = Image.open(file)
        except IOError:
            continue

        file_name = os.path.basename(file)
        if type_:
            file_name, file_ext = file_name.split(".", 1)
            file_dest = "{}.{}".format(file_name, type_)
        else:
            file_dest = file_name

        logger.info(
            "convert -thumbnail %d %s %s",
            size,
            file_name,
            os.path.join(thumbnails_dir, file_dest),
        )
        if commit:
            image.thumbnail((size, size))
            image.save(os.path.join(thumbnails_root, file_dest))


@utils.each_file(elt=True)
def command_clips_split(
    inf, output, points, ext=None, commit=False, verbose=False, **kwargs
):
    if not os.path.isfile(inf):
        return utils.ef_stop("missing", verbose)

    segments = []
    for i, point in enumerate(points):
        if not re.match(r"(\d{1,2}:)?\d{1,2}:\d{2}(\.\d+)?$", point):
            raise errors.UserError("invalid time: {}".format(point))
        if not i:
            segments.append([None, point])
        else:
            segments.append([points[i - 1], point])
    segments.append([points[-1], None])

    file_name, file_ext = os.path.splitext(inf)
    file_ext = "." + ext if ext else file_ext

    file_status = True
    for i, (start, end) in enumerate(segments):
        utils.ef_log_task_start(
            output, "  #{} {}-{}".format(i, start or "", end or ""), **kwargs
        )
        dest = "{} #{}{}".format(file_name, i, file_ext)
        _t = time.time()
        status = clients.run_ffmpeg_pref(
            inf, dest, seek=start, to=end, commit=commit
        )
        if not status:
            file_status = False
        status = utils.ef_status(status, output, **kwargs)
        utils.ef_log_task_end(output, inf, status, _t, **kwargs)
    return utils.ef_status(
        file_status, output, commit=commit, verbose=verbose, **kwargs
    )


@utils.each_file(elt=True)
def command_clips_trim(inf, output, ss=None, to=None, commit=False, **kwargs):
    out = "{}-trimmed{}".format(*os.path.splitext(inf))
    if os.path.exists(out):
        return "exists"

    status = clients.run_ffmpeg_pref(
        inf, out, seek=ss, to=to, copy=False, commit=commit
    )
    status = utils.ef_status(status, output, commit=commit, **kwargs)
    return status


@utils.each_file(elt=False, cycled=math.inf)
def command_clips_check_web(inf, _output, **_kwargs):
    status = clients.check_ffmpeg_faststart(inf)
    return "yes" if status else "no"


@utils.each_file(elt=True)
def command_clips_web(inf, output, verbose=False, commit=False, **kwargs):
    out = "{}-web{}".format(*os.path.splitext(inf))
    if os.path.exists(out):
        return utils.ef_stop("exists", verbose)

    if clients.check_ffmpeg_faststart(inf):
        return utils.ef_stop("already", verbose)

    status = clients.run_ffmpeg_pref(inf, out, copy=True, commit=commit)
    status = utils.ef_status(
        status, output, verbose=verbose, commit=commit, **kwargs
    )
    return status


def _clips_compress_inputs(inputs, recursive=False):
    """Return unique, sorted video files selected from command inputs."""
    files = []
    seen = set()
    for input_path in inputs:
        if os.path.isfile(input_path):
            candidates = [input_path]
        elif os.path.isdir(input_path):
            candidates = utils.iter_files(
                input_path, recursive=recursive, sort=True
            )
        else:
            logger.warning("skipped missing input: %s", input_path)
            continue

        for candidate in candidates:
            stem, extension = os.path.splitext(candidate)
            key = os.path.normcase(os.path.abspath(candidate))
            if (
                key in seen
                or extension.lower() not in VIDEO_EXTENSIONS
                or stem.lower().endswith("_compressed")
            ):
                continue
            seen.add(key)
            files.append(candidate)
    return files


def command_clips_compress(
    inputs: list[str],
    crf: int = 23,
    mp4: bool = False,
    dry_run: bool = False,
    rewrite: bool = False,
    recursive: bool = False,
    replace_source: bool = False,
):
    """Compress selected videos, continuing after individual failures."""
    successful_sizes = []
    for input_file in _clips_compress_inputs(inputs, recursive=recursive):
        stem, extension = os.path.splitext(input_file)
        output_file = f"{stem}_compressed{'.mp4' if mp4 else extension}"
        replacement_file = f"{stem}.mp4" if mp4 else input_file

        if (
            replace_source
            and mp4
            and extension.lower() != ".mp4"
            and os.path.exists(replacement_file)
        ):
            logger.error(
                "%s: cannot replace source; target exists: %s",
                input_file,
                replacement_file,
            )
            continue

        if os.path.exists(output_file) and not rewrite:
            logger.info("%s: exists", input_file)
            continue

        command = clients.run_ffmpeg(
            input_file,
            output_file,
            video_codec="libx264",
            crf=crf,
            audio_codec="copy",
            overwrite=rewrite,
            timeout=14400,
            commit=not dry_run,
        )
        if dry_run:
            logger.info(command)
            continue
        if not command:
            logger.error("%s: failed", input_file)
            continue

        try:
            source_size = os.path.getsize(input_file)
            result_size = os.path.getsize(output_file)
            if replace_source:
                os.replace(output_file, replacement_file)
                if mp4 and extension.lower() != ".mp4":
                    os.remove(input_file)
        except OSError as exc:
            logger.error("%s: failed: %s", input_file, exc)
            continue

        successful_sizes.append((source_size, result_size))
        reduction = _clips_compress_reduction(source_size, result_size)
        logger.info(
            "%s: %s -> %s (%.2f%% reduction)",
            input_file,
            format_utils.humanize_bytes(source_size),
            format_utils.humanize_bytes(result_size),
            reduction,
        )

    if len(successful_sizes) > 1:
        source_size = sum(sizes[0] for sizes in successful_sizes)
        result_size = sum(sizes[1] for sizes in successful_sizes)
        logger.info(
            "total: %s -> %s (%.2f%% reduction)",
            format_utils.humanize_bytes(source_size),
            format_utils.humanize_bytes(result_size),
            _clips_compress_reduction(source_size, result_size),
        )


def _clips_compress_reduction(source_size, result_size):
    if not source_size:
        return 0.0
    return (source_size - result_size) * 100.0 / source_size


def command_thumbs(
    root, recursive, force, size, cols, max_lines, commit=False
):
    thumbnails_dir = "thumb_map.jpg"
    thumbnails_path = os.path.join(root, thumbnails_dir)
    if os.path.exists(thumbnails_path) and not force:
        raise errors.UserError("Thumbnails map file already exists")

    thumbnails = Image.new("RGB", (size * cols, size * max_lines), "black")

    line = 0
    for i, file in enumerate(utils.iter_files(root, recursive=recursive)):
        line = i // cols
        pos = i % cols

        if thumbnails_dir in file:
            continue

        if line > max_lines:
            logger.warning("too much files, skip some from thumnails")
            break

        try:
            image = Image.open(file)
        except IOError:
            continue

        image.thumbnail((size, size))
        thumbnails.paste(image, (pos * size, line * size))
        logger.info("thumbnail: %s", file)

    line += 1
    if line < max_lines:
        th = thumbnails
        # th.crop((0, 0, size * cols - 1, size * line - 1))
        thumbnails = Image.new("RGB", (size * cols, size * line), "black")
        thumbnails.paste(th, (0, 0))

    if commit:
        thumbnails.save(thumbnails_path)


def command_search_copy(root, source_file, recursive):
    source_hash = davo.utils.path.file_hash(source_file)
    source_hash_digest = source_hash.digest()
    size = os.path.getsize(source_file)
    source_full = os.path.abspath(source_file)

    for file in utils.iter_files(root, recursive=recursive):
        if source_full == file or size != os.path.getsize(file):
            continue

        if (
            h := davo.utils.path.file_hash(file)
        ) and source_hash_digest == h.digest():
            logger.info("%s %s", file, source_hash.hexdigest())


def command_search_duplicates(root, md5, recursive, verbose):
    files = {}
    for file in utils.iter_files(root, recursive=recursive):
        files[file] = {
            "size": os.path.getsize(file),
        }

    logger.info("total: %d", len(files))

    for i in utils.iter_files(root, recursive=recursive):
        # file created after scan
        if i not in files:
            continue
        i_options = files[i]
        doubles = set()
        for j, j_options in files.items():
            if i == j or j_options["size"] != i_options["size"]:
                continue
            doubles.add(j)

        if doubles and md5:
            doubles2 = set()
            if not i_options.get("hash"):
                i_options["hash"] = davo.utils.path.file_hash(i)
            md5sum = i_options["hash"]
            for j in doubles:
                j_options = files[j]
                if not j_options.get("hash"):
                    j_options["hash"] = davo.utils.path.file_hash(i)
                if md5sum != j_options["hash"]:
                    continue
                doubles2.add(j)

            if doubles2:
                doubles = doubles2

        if doubles:
            logger.info(
                "%s, %s, %s",
                i.replace(root, "."),
                len(doubles),
                ",".join(doubles).replace(root, "."),
            )


def command_convert(
    root,
    replace,
    recursive,
    copy,
    delete,
    thumbnail,
    skip_no_exif,
    drop_alpha,
    commit=False,
):
    """
    Convert command.

    :param str root:
    :param str replace: replace pattern
    :param boot recursive:
    :param bool copy:
    :param bool delete: delete source on convert (for rename use copy option)
    :param int thumbnail:
    :param bool skip_no_exif: skip files with no exif data
    :param bool drop_alpha: drop alpha channel
    :param bool commit:
    """
    index = 1
    converted = 0
    for file_path in utils.iter_files(root, recursive=recursive, sort=True):
        file_root, file_base = os.path.split(file_path)

        exif = None
        if skip_no_exif:
            exif = utils.get_exif(file_path)
            if exif is None:
                continue

        new_name = utils.replace_file_params(
            file_path, ".*", replace, index=index, exif_data=exif
        )
        if not new_name:
            continue

        logger.info("%-41s %s", file_base, new_name)

        file_path_new = os.path.join(file_root, new_name)
        davo.utils.path.ensure(file_path_new, commit=commit)

        if thumbnail or not utils.is_ext_same(file_base, new_name):
            if copy and file_path == file_path_new:
                raise errors.NotImpl(
                    "--copy for inplace convert not implemented yet"
                )
            utils.image_convert(
                path_source=file_path,
                path_dest=file_path_new,
                thumbnail=thumbnail,
                save_exif=True,
                save_mtime=True,
                drop_alpha=drop_alpha,
                commit=commit,
            )
            # TODO: copy on file_path == file_path_new
            if commit and delete and file_path != file_path_new:
                os.remove(file_path)
            converted += 1
            continue

        if file_path == file_path_new:
            continue

        if copy:
            if commit:
                shutil.copy2(file_path, file_path_new)
            converted += 1

        else:
            if commit:
                os.rename(file_path, file_path_new)
            converted += 1

        index += 1

    logger.info("converted: %d", converted)


@utils.each_file(elt=True, cycled=30)
def command_convert_video(
    inf,
    output,
    replace="[source].[Ext]",
    thumbnail=False,
    verbose=False,
    commit=False,
    **kwargs,
):
    """
    Convert command for video using ffmpeg.
    """
    kwargs.setdefault("converted", 0)
    converted = kwargs["converted"]

    file_root, file_base = os.path.split(inf)
    new_name = utils.replace_file_params(
        file_base, ".*", replace, index=converted
    )
    out = os.path.join(file_root, new_name)
    if thumbnail:
        out = os.path.splitext(out)[0] + ".jpg"
    if out == inf and not thumbnail:
        return utils.ef_stop("skipped (same name/ext)", verbose)
    davo.utils.path.ensure(out, commit=commit)
    if os.path.exists(out):
        return utils.ef_stop("exists", verbose)
    if not os.path.exists(inf):
        return utils.ef_stop("not found", verbose)

    status = clients.run_ffmpeg_pref(inf, out, timeout=14400, commit=commit)
    status = utils.ef_status(status, output, verbose=verbose, **kwargs)

    if status == "succeed":
        converted += 1
    return status


def command_recover(
    root,
    algo: str = None,
    scale: int = None,
    min_contour: int = None,
    max_contour: int = None,
    debug: bool = False,
    recursive: bool = False,
    verbose: bool = False,
    commit: bool = False,
):
    scale, min_contour, max_contour = map(
        utils.int2frac, (scale, min_contour, max_contour)
    )
    pipelines = recover.cv3.get_pipelines(verbose=verbose)
    for file_path in utils.iter_files(root, recursive=recursive, sort=True):
        file_root, file_base = os.path.split(file_path)
        if verbose:
            logger.info(">%s", file_base)
        image = cv2.imread(file_path)

        contour = recover.image_recover(
            image.copy(),
            {
                "debug": debug,
                "file": file_base,
            },
            pipelines,
            algo=algo,
            scale=scale,
            min_contour=min_contour,
            max_contour=max_contour,
            debug=debug,
            verbose=verbose,
        )
        if contour is None:
            if verbose:
                logger.info("%s: contour not found", file_base)
            continue

        name, ext = file_base.rsplit(".", 1)
        name = os.path.join(file_root, "{}-fixed.{}".format(name, ext))

        if verbose:
            logger.info("%s: contour detected", file_base)
        if commit:
            recover.rotate(image, contour, name)


def command_downscale(
    root,
    min_width: int = None,
    min_height: int = None,
    speed: int = None,
    threshold: int = None,
    verbose: bool = False,
    commit: bool = False,
):
    threshold, speed = map(utils.int2frac, (threshold, speed))
    for file_path in utils.iter_files(root, recursive=False, sort=True):
        file_root, file_base = os.path.split(file_path)

        image = cv2.imread(file_path)
        downscaled, ssim = recover.cv3.image_downscale(
            image, min_width, min_height, speed, threshold
        )

        if downscaled is None or ssim == 1.0:
            if verbose:
                logger.info("%s: downscale failed", file_base)
            continue

        file_name, ext = file_base.rsplit(".", 1)
        file_name = os.path.join(
            file_root, "{}-downscaled.{}".format(file_name, ext)
        )
        scale = downscaled.shape[0] / image.shape[0] * 100
        logger.info(
            "%s: downscaled %.2f%% %d*%d, SSIM=%.3f",
            file_base,
            scale,
            downscaled.shape[1],
            downscaled.shape[0],
            ssim,
        )
        if commit:
            cv2.imwrite(file_name, downscaled)


def command_fingerprint(image: str):
    print(fingerprint.format_fingerprint(image))


def command_image_info(
    images: list[str],
    verbose: bool = False,
    table: bool = False,
    compact: bool = False,
    exif: bool = False,
    exif_full: bool = False,
):
    """Print readonly Pillow metadata for image paths in argv order."""
    if not images:
        images = sorted(glob.glob("*"))

    inspections = []
    total_images = len(images)
    for index, input_file in enumerate(images, start=1):
        row = image_info.inspect_image(input_file, verbose=verbose)
        if row is not None:
            row["image"] = index
            row["total_images"] = total_images
            inspections.append((input_file, row))

    if not inspections:
        return

    image_number_width = max(
        len(str(total_images)),
        len(str(max(row["image"] for _, row in inspections))),
    )
    include_exif = exif

    if compact and not exif_full:
        print(
            image_info.format_image_info_report(
                [row for _, row in inspections],
                table=table,
                compact=True,
                include_exif=include_exif,
                image_number_width=image_number_width,
            )
        )
        return

    if compact and table and exif_full:
        report = image_info.format_image_info_report(
            [row for _, row in inspections],
            table=True,
            compact=True,
            image_number_width=image_number_width,
        )
        blocks = []
        for _, row in inspections:
            exif_block = image_info.format_exif_block(row)
            if exif_block:
                width = image_number_width
                number = "{image:0{width}d}/{total:0{width}d}".format(
                    image=row["image"],
                    total=row["total_images"],
                    width=width,
                )
                blocks.append("{}\n{}".format(number, exif_block))
        print("\n".join((report, *blocks)))
        return

    reports = []
    for input_file, row in inspections:
        report = image_info.format_image_info_report(
            [row],
            table=table,
            compact=compact,
            include_exif=include_exif,
            image_number_width=image_number_width,
        )
        if not compact:
            report = "{}\n{}".format(
                os.path.relpath(input_file, os.getcwd()), report
            )
        if exif_full:
            exif_block = image_info.format_exif_block(row)
            if exif_block:
                report = "{}\n{}".format(report, exif_block)
        reports.append(report)

    print(("\n" if compact else "\n\n").join(reports))


def command_clips_info(
    inputs: list[str],
    verbose: bool = False,
    table: bool = False,
    compact: bool = False,
    meta: bool = False,
    *,
    detailed: bool = False,
):
    """Print readonly MediaInfo metadata for media paths in argv order."""
    if not inputs:
        inputs = sorted(glob.glob("*"))

    inspections = []
    total_videos = len(inputs)
    for index, input_file in enumerate(inputs, start=1):
        row = video_info.inspect_video(input_file, verbose=verbose)
        if row is not None:
            row["video_number"] = index
            row["total_videos"] = total_videos
            inspections.append((input_file, row))

    if not inspections:
        return

    video_number_width = max(
        len(str(total_videos)),
        len(str(max(row["video_number"] for _, row in inspections))),
    )
    rows = [row for _, row in inspections]
    if meta:
        print(
            video_info.format_video_info_metadata_report(
                inspections,
                meta_level="full",
                table=table,
                compact=compact,
                detailed=detailed,
                video_number_width=video_number_width,
            )
        )
        return

    if compact:
        print(
            video_info.format_video_info_report(
                rows,
                table=table,
                compact=True,
                detailed=detailed,
                video_number_width=video_number_width,
            )
        )
        return

    reports = []
    for input_file, row in inspections:
        report = video_info.format_video_info_report(
            [row],
            table=table,
            compact=compact,
            detailed=detailed,
            video_number_width=video_number_width,
        )
        if not compact:
            report = "{}\n{}".format(
                os.path.relpath(input_file, os.getcwd()), report
            )
        if len(row["video_tracks"]) > 1 or len(row["audio_tracks"]) > 1:
            track_blocks = video_info.format_basic_meta_blocks(
                row, include_general=False
            )
            if track_blocks:
                report = f"{report}\n{track_blocks}"
        reports.append(report)

    print(("\n" if compact else "\n\n").join(reports))


def command_image_merge(
    images: list[str],
    vertical: bool,
    out: str = None,
    debug_fill: bool = False,
    smart: bool = False,
):
    """Merge image files without altering their source files."""
    if len(images) < 2:
        raise errors.UserError("At least two images are required for merge")

    loaded_images, source_formats = _load_merge_images(images)
    output_path, output_format = _merge_output_path(
        images, source_formats, out
    )
    _validate_merge_output(output_path, images)

    if smart:
        loaded_images, offsets, size = _smart_merge_layout(
            loaded_images, vertical
        )
    else:
        offsets, size = _plain_merge_layout(loaded_images, vertical)

    fill = MAGENTA if debug_fill else (0, 0, 0, 0)
    result = Image.new("RGBA", size, fill)
    for image, offset in zip(loaded_images, offsets):
        result.alpha_composite(image, offset)

    try:
        if output_format in JPEG_FORMATS:
            background = MAGENTA[:3] if debug_fill else (255, 255, 255)
            flattened = Image.new("RGB", result.size, background)
            flattened.paste(result, mask=result.getchannel("A"))
            flattened.save(output_path, format=output_format)
        else:
            result.save(output_path, format=output_format)
    except (OSError, ValueError) as exc:
        raise errors.UserError(
            "Cannot save merged image {}: {}".format(output_path, exc)
        ) from exc


def _load_merge_images(paths):
    loaded_images = []
    source_formats = []
    for path in paths:
        if not os.path.isfile(path):
            raise errors.UserError(
                "Image is not a regular file: {}".format(path)
            )
        try:
            with Image.open(path) as image:
                image.load()
                if image.format is None:
                    raise errors.UserError(
                        "Cannot determine image format: {}".format(path)
                    )
                loaded_images.append(image.convert("RGBA"))
                source_formats.append(image.format.upper())
        except (OSError, ValueError) as exc:
            raise errors.UserError(
                "Cannot read image {}: {}".format(path, exc)
            ) from exc
    return loaded_images, source_formats


def _merge_output_path(paths, source_formats, out):
    if out is not None:
        extension = os.path.splitext(out)[1].lower()
        output_format = Image.registered_extensions().get(extension)
        if output_format is None:
            raise errors.UserError(
                "Unsupported output image extension: {}".format(
                    extension or "(missing)"
                )
            )
        return out, output_format.upper()

    first_path = paths[0]
    root, extension = os.path.splitext(first_path)
    if len(set(source_formats)) == 1 and extension:
        output_format = source_formats[0]
        output_path = "{}_merged{}".format(root, extension)
    else:
        output_format = "JPEG"
        output_path = "{}_merged.jpg".format(root)
    return output_path, output_format


def _validate_merge_output(output_path, input_paths):
    output_real_path = os.path.realpath(os.path.abspath(output_path))
    for input_path in input_paths:
        input_real_path = os.path.realpath(os.path.abspath(input_path))
        if output_real_path == input_real_path:
            raise errors.UserError(
                "Output image must not replace an input image"
            )
    if os.path.lexists(output_path):
        raise errors.UserError(
            "Output image already exists: {}".format(output_path)
        )


def _plain_merge_layout(images, vertical):
    if vertical:
        width = max(image.width for image in images)
        height = sum(image.height for image in images)
        offsets = []
        top = 0
        for image in images:
            offsets.append(((width - image.width) // 2, top))
            top += image.height
        return offsets, (width, height)

    width = sum(image.width for image in images)
    height = max(image.height for image in images)
    offsets = []
    left = 0
    for image in images:
        offsets.append((left, (height - image.height) // 2))
        left += image.width
    return offsets, (width, height)


def _smart_merge_layout(images, vertical):
    if cv2 is None:
        raise errors.UserError("Smart merge requires OpenCV")

    aligned_images = [images[0]]
    offsets = [(0, 0)]
    for current in images[1:]:
        previous = aligned_images[-1]
        registration = _find_merge_registration(previous, current, vertical)
        if registration is None:
            raise errors.UserError(
                "No strong overlap found between adjacent images"
            )
        scaled, translation = registration
        previous_offset = offsets[-1]
        offsets.append(
            (
                previous_offset[0] + translation[0],
                previous_offset[1] + translation[1],
            )
        )
        aligned_images.append(scaled)

    left = min(offset[0] for offset in offsets)
    top = min(offset[1] for offset in offsets)
    right = max(
        offset[0] + image.width
        for image, offset in zip(aligned_images, offsets)
    )
    bottom = max(
        offset[1] + image.height
        for image, offset in zip(aligned_images, offsets)
    )
    normalized_offsets = [
        (offset[0] - left, offset[1] - top) for offset in offsets
    ]
    return aligned_images, normalized_offsets, (right - left, bottom - top)


def _find_merge_registration(previous, current, vertical):
    """Return a scaled current image and its origin relative to *previous*."""
    best = _find_merge_scale(
        previous, current, vertical, _merge_scale_values()
    )
    if best is None:
        return None

    scale, _score, _translation, _scaled = best
    refinement = _merge_scale_values(scale - 0.01, scale + 0.01, 0.002)
    refined = _find_merge_scale(previous, current, vertical, refinement)
    if refined is not None:
        best = refined
    _scale, _score, translation, scaled = best
    return scaled, translation


def _merge_scale_values(start=0.90, stop=1.10, step=0.01):
    values = []
    value = max(0.90, start)
    while value <= min(1.10, stop) + 0.000001:
        values.append(round(value, 3))
        value += step
    return values


def _find_merge_scale(previous, current, vertical, scales):
    previous_gray = _merge_gray(previous)
    best = None
    best_score = -1
    for scale in scales:
        scaled = _scale_merge_image(current, scale)
        registration = _find_merge_translation(
            previous_gray, _merge_gray(scaled), vertical
        )
        if registration is None:
            continue
        score, translation = registration
        if score > best_score:
            best = (scale, score, translation, scaled)
            best_score = score
    return best


def _scale_merge_image(image, scale):
    size = (
        max(1, round(image.width * scale)),
        max(1, round(image.height * scale)),
    )
    return image.resize(size, Image.Resampling.LANCZOS)


def _find_merge_translation(previous, current, vertical):
    """Find a consensus edge translation using three independent probes."""
    previous_main = previous.shape[0] if vertical else previous.shape[1]
    current_main = current.shape[0] if vertical else current.shape[1]
    previous_cross = previous.shape[1] if vertical else previous.shape[0]
    current_cross = current.shape[1] if vertical else current.shape[0]
    # A 16-pixel probe permits the deliberately small overlaps this command is
    # intended for.  Several cross-axis probes provide the needed
    # protection against a coincidental short match.
    probe_main = min(16, current_main, previous_main)
    if probe_main < 16 or min(previous_cross, current_cross) < 16:
        return None

    matches = []
    for start, end in _merge_probe_ranges(current_cross):
        template = (
            current[:probe_main, start:end]
            if vertical
            else current[start:end, :probe_main]
        )
        if (
            template.shape[0] > previous.shape[0]
            or template.shape[1] > previous.shape[1]
        ):
            continue
        _minimum, score, _minimum_location, location = cv2.minMaxLoc(
            cv2.matchTemplate(previous, template, cv2.TM_CCOEFF_NORMED)
        )
        if not numpy.isfinite(score) or score < 0.90:
            continue
        translation = (
            location[0] - (start if vertical else 0),
            location[1] - (0 if vertical else start),
        )
        matches.append((score, translation))

    if len(matches) < 3:
        return None
    translations = [translation for _score, translation in matches]
    median = tuple(
        int(
            round(
                numpy.median(
                    [translation[axis] for translation in translations]
                )
            )
        )
        for axis in (0, 1)
    )
    matches = [
        (score, translation)
        for score, translation in matches
        if (
            abs(translation[0] - median[0]) <= 2
            and abs(translation[1] - median[1]) <= 2
        )
    ]
    if len(matches) < 3:
        return None

    main_translation = median[1] if vertical else median[0]
    cross_translation = median[0] if vertical else median[1]
    cross_limit = min(256, max(previous_cross, current_cross) // 10)
    if (
        main_translation <= 0
        or main_translation >= previous_main
        or abs(cross_translation) > cross_limit
    ):
        return None
    return numpy.mean([score for score, _translation in matches]), median


def _merge_probe_ranges(cross_axis):
    probe = max(8, cross_axis // 4)
    probe = min(probe, cross_axis)
    maximum_start = cross_axis - probe
    return [
        (
            round(maximum_start * fraction),
            round(maximum_start * fraction) + probe,
        )
        for fraction in (0.1, 0.3, 0.5, 0.7, 0.9)
    ]


def _merge_gray(image):
    rgb = numpy.asarray(image.convert("RGB"))
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)


def command_fingerprint_diff(
    images: list[str],
    recursive=False,
    table=False,
    show_all=False,
    fast=False,
    group=False,
):
    """Print image fingerprint distances or fast file-size comparisons."""
    candidates = []
    for image in images:
        if os.path.isdir(image):
            candidates.extend(
                (candidate, True, os.path.relpath(candidate, image))
                for candidate in sorted(
                    utils.iter_files(image, recursive=recursive)
                )
            )
        else:
            candidates.append((image, False, image))

    resolved_images = []
    parent_counts = {}
    parent_paths = {}
    parent_order = {}
    seen_paths = set()
    files_total = len(candidates)
    show_progress = files_total >= 10
    bytes_processed = 0
    files_started_at = None

    try:
        def report_files_progress(ready, filename):
            if not show_progress:
                return
            elapsed = time.time() - files_started_at
            estimated = None
            if ready:
                estimated = int(elapsed * (files_total - ready) / ready)
            utils.stderr_progress(
                "files",
                ready,
                files_total,
                elapsed=elapsed,
                bytes_processed=bytes_processed,
                estimated=estimated,
                filename=filename,
            )

        for processed, (candidate, skip_invalid, progress_path) in enumerate(
            candidates, 1
        ):
            if files_started_at is None:
                files_started_at = time.time()
            report_files_progress(processed - 1, progress_path)
            canonical_path = os.path.realpath(candidate)
            try:
                if canonical_path in seen_paths:
                    continue
                if fast:
                    if not os.path.isfile(candidate):
                        if skip_invalid:
                            continue
                        raise errors.UserError(
                            "Image is not a regular file: {}".format(
                                candidate
                            )
                        )
                    if os.path.splitext(candidate)[1].lower() not in (
                        FAST_DIFF_EXTENSIONS
                    ):
                        if skip_invalid:
                            continue
                        raise errors.UserError(
                            "Unsupported image extension: {}".format(
                                candidate
                            )
                        )
                    try:
                        size = os.stat(candidate).st_size
                    except OSError as exc:
                        if skip_invalid:
                            continue
                        raise errors.UserError(
                            "Cannot stat image {}: {}".format(candidate, exc)
                        ) from exc

                    seen_paths.add(canonical_path)
                    display_path = "{} {}".format(
                        candidate,
                        format_utils.humanize_bytes(
                            size, format_="{:.1f}{}b"
                        ).replace(" ", ""),
                    )
                    _append_fingerprint_diff_image(
                        resolved_images,
                        (parent_counts, parent_paths, parent_order),
                        (display_path, size),
                        candidate,
                    )
                    continue
                try:
                    features = fingerprint.fingerprint_comparison_features(
                        candidate
                    )
                except errors.UserError:
                    if skip_invalid:
                        continue
                    raise

                seen_paths.add(canonical_path)
                (width, height), vector, phash = features
                display_path = "{} {}*{} {}".format(
                    candidate,
                    width,
                    height,
                    format_utils.humanize_bytes(
                        os.path.getsize(candidate), format_="{:.1f}{}b"
                    ).replace(" ", ""),
                )
                _append_fingerprint_diff_image(
                    resolved_images,
                    (parent_counts, parent_paths, parent_order),
                    (display_path, vector, phash),
                    candidate,
                )
            finally:
                try:
                    bytes_processed += os.path.getsize(candidate)
                except OSError:
                    pass
                report_files_progress(processed, progress_path)
    finally:
        if show_progress:
            utils.stderr_progress(
                "files", files_total, files_total, finish=True
            )

    if len(resolved_images) < 2:
        raise errors.UserError("At least two images are required for diff")

    headers = ("left", "right", "l2_percent", "phash_percent", "status")
    rows = []
    folder_matches = {}
    pairs_total = len(resolved_images) * (len(resolved_images) - 1) // 2
    processed_pairs = 0
    pairs_started_at = time.time() if show_progress else None

    def report_pairs_progress(ready):
        if not show_progress:
            return
        elapsed = 0 if not ready else time.time() - pairs_started_at
        estimated = None
        if ready:
            estimated = int(elapsed * (pairs_total - ready) / ready)
        utils.stderr_progress(
            "pairs",
            ready,
            pairs_total,
            elapsed=elapsed,
            estimated=estimated,
        )

    try:
        report_pairs_progress(0)
        for left_index, left_image in enumerate(resolved_images[:-1]):
            for right_index, right_image in enumerate(
                resolved_images[left_index + 1 :], left_index + 1
            ):
                if fast:
                    left_path, left_size, left_parent, _ = left_image
                    right_path, right_size, right_parent, _ = right_image
                    status = (
                        "same_size"
                        if left_size == right_size
                        else "different"
                    )
                    l2_percent = phash_percent = "—"
                else:
                    (
                        left_path,
                        left_vector,
                        left_phash,
                        left_parent,
                        _,
                    ) = left_image
                    (
                        right_path,
                        right_vector,
                        right_phash,
                        right_parent,
                        _,
                    ) = right_image
                    l2 = math.sqrt(
                        sum(
                            (left_value - right_value) ** 2
                            for left_value, right_value in zip(
                                left_vector, right_vector
                            )
                        )
                    )
                    phash_hamming = (
                        int(left_phash, 16) ^ int(right_phash, 16)
                    ).bit_count()
                    l2_percent = l2 / math.sqrt(2) * 100
                    phash_percent = phash_hamming / 64 * 100
                    difference_percent = (l2_percent + phash_percent) / 2
                    if difference_percent == 0:
                        status = "identical"
                    elif difference_percent < 1:
                        status = "duplicate"
                    elif difference_percent < 10:
                        status = "similar"
                    elif difference_percent < 25:
                        status = "differ"
                    else:
                        status = "different"
                rows.append(
                    (
                        left_path,
                        right_path,
                        (
                            l2_percent
                            if fast
                            else f"{l2_percent:.2f}"
                        ),
                        (
                            phash_percent
                            if fast
                            else f"{phash_percent:.2f}"
                        ),
                        status,
                    )
                )
                if (
                    left_parent != right_parent
                    and status
                    in (
                        {"same_size"}
                        if fast
                        else {"identical", "duplicate", "similar"}
                    )
                ):
                    if parent_order[left_parent] < parent_order[right_parent]:
                        pair = (left_parent, right_parent)
                        match_indexes = (left_index, right_index)
                    else:
                        pair = (right_parent, left_parent)
                        match_indexes = (right_index, left_index)
                    matches = folder_matches.setdefault(pair, (set(), set()))
                    matches[0].add(match_indexes[0])
                    matches[1].add(match_indexes[1])
                processed_pairs += 1
                report_pairs_progress(processed_pairs)
    finally:
        if show_progress:
            utils.stderr_progress(
                "pairs", pairs_total, pairs_total, finish=True
            )
    if group:
        _print_fingerprint_diff_groups(
            folder_matches, parent_counts, parent_paths, parent_order, table
        )
        return
    statuses = (
        "identical",
        "duplicate",
        "similar",
        "differ",
        "same_size",
        "different",
    )
    summary = ", ".join(
        "{}: {}".format(status, count)
        for status in statuses
        if (count := sum(row[-1] == status for row in rows))
    )
    visible_rows = rows if show_all or len(rows) == 1 else [
        row for row in rows if row[-1] != "different"
    ]
    if not visible_rows:
        print("total {}".format(summary))
        return
    if table:
        report = _format_fingerprint_diff_table(headers, visible_rows)
    else:
        report = "\n".join(
            ("\t".join(headers), *("\t".join(row) for row in visible_rows))
        )
    print("{}\ntotal {}".format(report, summary))


def _append_fingerprint_diff_image(
    resolved_images,
    parents,
    image,
    candidate,
):
    """Store an accepted image with its physical and display parent paths."""
    parent_counts, parent_paths, parent_order = parents
    parent_path = os.path.dirname(candidate) or "."
    parent = os.path.realpath(parent_path)
    if parent not in parent_order:
        parent_order[parent] = len(parent_order)
        parent_paths[parent] = parent_path
        parent_counts[parent] = 0
    parent_counts[parent] += 1
    resolved_images.append((*image, parent, parent_path))


def _print_fingerprint_diff_groups(
    folder_matches, parent_counts, parent_paths, parent_order, table
):
    """Print folder groups whose matching images pass the threshold."""
    links = []
    for (left, right), (left_images, right_images) in folder_matches.items():
        left_count = len(left_images)
        right_count = len(right_images)
        if (
            left_count * 10 < parent_counts[left] * 3
            and right_count * 10 < parent_counts[right] * 3
        ):
            continue
        links.append((left, right, left_count, right_count))

    if not links:
        print("total groups: 0")
        return

    links.sort(key=lambda link: (parent_order[link[0]], parent_order[link[1]]))
    parents = {parent for link in links for parent in link[:2]}
    neighbours = {parent: set() for parent in parents}
    for left, right, _, _ in links:
        neighbours[left].add(right)
        neighbours[right].add(left)

    components = []
    remaining = set(parents)
    while remaining:
        root = min(remaining, key=parent_order.__getitem__)
        component = set()
        pending = [root]
        remaining.remove(root)
        while pending:
            parent = pending.pop()
            component.add(parent)
            for neighbour in neighbours[parent]:
                if neighbour in remaining:
                    remaining.remove(neighbour)
                    pending.append(neighbour)
        components.append(component)
    components.sort(
        key=lambda component: min(map(parent_order.__getitem__, component))
    )

    headers = (
        "group",
        "left",
        "right",
        "left_matches",
        "right_matches",
        "left_percent",
        "right_percent",
    )
    rows = []
    for group_number, component in enumerate(components, 1):
        for left, right, left_count, right_count in links:
            if left not in component:
                continue
            rows.append(
                (
                    str(group_number),
                    parent_paths[left],
                    parent_paths[right],
                    "{}/{}".format(left_count, parent_counts[left]),
                    "{}/{}".format(right_count, parent_counts[right]),
                    "{:.2f}".format(left_count / parent_counts[left] * 100),
                    "{:.2f}".format(right_count / parent_counts[right] * 100),
                )
            )
    if table:
        report = _format_fingerprint_diff_table(
            headers, rows, numeric_columns=(3, 4, 5, 6)
        )
    else:
        report = "\n".join(
            ("\t".join(headers), *("\t".join(row) for row in rows))
        )
    print("{}\ntotal groups: {}".format(report, len(components)))


def _format_fingerprint_diff_table(headers, rows, numeric_columns=(2, 3)):
    """Format fingerprint diff rows as an ASCII table."""
    widths = [
        max((len(header), *(len(row[index]) for row in rows)))
        for index, header in enumerate(headers)
    ]
    border = "+{}+".format("+".join("-" * (width + 2) for width in widths))

    def format_row(row):
        return "| {} |".format(
            " | ".join(
                (
                    value.rjust(widths[index])
                    if index in numeric_columns
                    else value.ljust(widths[index])
                )
                for index, value in enumerate(row)
            )
        )

    return "\n".join(
        (
            border,
            format_row(headers),
            border,
            *(format_row(row) for row in rows),
            border,
        )
    )


def _pdf_path(root: str | None, path: str | None) -> str | None:
    if path is None or root is None:
        return path
    return os.path.join(root, path)


def command_pdf_merge(
    root,
    out: str,
    inf: list,
    verbose: bool = False,
    rewrite: bool = False,
):
    status = pdf.merge_files(
        [_pdf_path(root, file_path) for file_path in inf],
        _pdf_path(root, out),
        rewrite=rewrite,
        verbose=verbose,
    )
    status_h = "prepared" if status else "failed"
    logger.info("pdf %s: %s", status_h, out)


def command_pdf_rotate(
    root,
    out: str,
    inf: str,
    direction: str,
    verbose: bool = False,
    rewrite: bool = False,
):
    status = pdf.rotate_pages(
        _pdf_path(root, inf),
        _pdf_path(root, out),
        direction,
        rewrite=rewrite,
        verbose=verbose,
    )
    status_h = "prepared" if status else "failed"
    logger.info("pdf %s: %s", status_h, out)


def command_pdf_delete(
    root,
    out: str,
    inf: str,
    pages: list,
    verbose: bool = False,
    rewrite: bool = False,
):
    status = pdf.delete_pages(
        _pdf_path(root, inf),
        _pdf_path(root, out),
        pages,
        rewrite=rewrite,
        verbose=verbose,
    )
    status_h = "prepared" if status else "failed"
    logger.info("pdf %s: %s", status_h, out)


def command_pdf_split(
    root,
    out: str,
    inf: str,
    pages: list,
    verbose: bool = False,
    rewrite: bool = False,
):
    status = pdf.split_pages(
        _pdf_path(root, inf),
        _pdf_path(root, out),
        pages,
        rewrite=rewrite,
        verbose=verbose,
    )
    status_h = "prepared" if status else "failed"
    logger.info("pdf %s: %s", status_h, out)


def command_pdf_clean(
    root,
    out: str,
    inf: str,
    verbose: bool = False,
    rewrite: bool = False,
):
    status = pdf.clean_file(
        _pdf_path(root, inf),
        _pdf_path(root, out),
        rewrite=rewrite,
        verbose=verbose,
    )
    status_h = "prepared" if status else "failed"
    logger.info("pdf %s: %s", status_h, out)


def command_pdf_compress(
    root,
    out: str,
    inf: str,
    dpi: int,
    quality: int,
    grayscale: bool = False,
    rebuild: bool = True,
    verbose: bool = False,
    rewrite: bool = False,
):
    status = pdf.compress_file(
        _pdf_path(root, inf),
        _pdf_path(root, out),
        dpi=dpi,
        quality=quality,
        grayscale=grayscale,
        rebuild=rebuild,
        rewrite=rewrite,
        verbose=verbose,
    )
    status_h = "prepared" if status else "failed"
    logger.info("pdf %s: %s", status_h, out or inf)


def command_pdf_form(
    root,
    out: str,
    inf: list,
    paper_format: str = None,
    size_cm: list = None,
    dpi: int = 300,
    quality: int = 80,
    debug_fill: bool = False,
    rename_processed: bool = False,
    verbose: bool = False,
    rewrite: bool = False,
    force_orientation: str = None,
):
    if size_cm is not None:
        page_size = tuple(value * 72.0 / 2.54 for value in size_cm)
    else:
        page_size = pdf._PAPER_FORMATS[paper_format]  # pylint: disable=W0212
    status = pdf.form_files(
        [_pdf_path(root, file_path) for file_path in inf],
        _pdf_path(root, out),
        page_size=page_size,
        force_orientation=force_orientation,
        dpi=dpi,
        quality=quality,
        debug_fill=debug_fill,
        rename_processed=rename_processed,
        rewrite=rewrite,
        verbose=verbose,
    )
    status_h = "prepared" if status else "failed"
    logger.info("pdf %s: %s", status_h, out or inf[0])
    if status:
        output_path = _pdf_path(root, out)
        if output_path is None:
            output_path = pdf._default_output(  # pylint: disable=W0212
                _pdf_path(root, inf[0]), "_formed"
            )
        command_pdf_info(
            None,
            output_path,
            verbose=verbose,
            show_paths=False,
        )


def command_pdf_extract(
    root,
    inf: str,
    out: str = None,
    pages: list = None,
    output_type: str = None,
    whole_page: bool = False,
    verbose: bool = False,
    rewrite: bool = False,
):
    status = pdf.extract_images(
        _pdf_path(root, inf),
        _pdf_path(root, out),
        pages=pages,
        output_type=output_type,
        whole_page=whole_page,
        rewrite=rewrite,
        verbose=verbose,
    )
    status_h = "prepared" if status else "failed"
    logger.info("pdf %s: %s", status_h, inf)


def command_pdf_info(
    root,
    inf: str | list[str],
    pages: list = None,
    verbose: bool = False,
    pt: bool = False,
    table: bool = False,
    compact: bool = False,
    show_paths: bool = True,
):
    input_files = [inf] if isinstance(inf, str) else inf or []
    if not input_files:
        input_files = sorted(glob.glob("*"))
    inspections = []
    for input_file in input_files:
        input_path = _pdf_path(root, input_file)
        rows = pdf.inspect_pages(
            input_path,
            pages=pages,
            verbose=verbose,
            pt=pt,
        )
        if rows is None:
            continue
        inspections.append((input_path, rows))

    page_number_width = None
    if compact:
        page_number_width = max(
            (
                len(str(row["total_pages"]))
                for _input_path, rows in inspections
                for row in rows
            ),
            default=1,
        )

    reports = []
    for input_path, rows in inspections:
        report = pdf.format_page_info_report(
            rows,
            table=table,
            compact=compact,
            page_number_width=page_number_width,
        )
        if show_paths and not compact:
            report = "{}\n{}".format(
                os.path.relpath(input_path, os.getcwd()),
                report,
            )
        reports.append(report)

    if reports:
        if compact and table:
            reports = [
                reports[0],
                *(
                    "\n".join(report.splitlines()[1:])
                    for report in reports[1:]
                ),
            ]
        print(("\n" if compact else "\n\n").join(reports))


def command_pdf_scale(
    root,
    out: str,
    inf: str,
    pages: list = None,
    paper_format: str = "a4",
    verbose: bool = False,
    rewrite: bool = False,
):
    status = pdf.scale_file(
        _pdf_path(root, inf),
        _pdf_path(root, out),
        pages=pages,
        paper_format=paper_format,
        rewrite=rewrite,
        verbose=verbose,
    )
    status_h = "prepared" if status else "failed"
    logger.info("pdf %s: %s", status_h, out or inf)
