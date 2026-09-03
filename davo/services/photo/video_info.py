"""Readonly inspection and rendering for ``davo vid info``."""

import logging
import os
import textwrap
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Iterable, Optional, Sequence

import pymediainfo

from davo.utils import format as format_utils

logger = logging.getLogger(__name__)


DETAILED_SUMMARY_HEADERS = (
    "Format",
    "Duration",
    "Video",
    "ImageSizePx",
    "FPS",
    "VideoBitrate",
    "VideoBitDepth",
    "ColorSpace",
    "HDR",
    "Audio",
    "AudioBitrate",
    "Channels",
    "SampleRate",
    "AudioBitDepth",
    "FileSize",
)

DETAILED_SUMMARY_FIELDS = (
    "format",
    "duration",
    "video",
    "image_size_px",
    "fps",
    "video_bitrate",
    "video_bit_depth",
    "color_space",
    "hdr",
    "audio",
    "audio_bitrate",
    "channels",
    "sample_rate",
    "audio_bit_depth",
    "file_size",
)

SUMMARY_HEADERS = tuple(
    header
    for header in DETAILED_SUMMARY_HEADERS
    if header not in {
        "VideoBitDepth", "ColorSpace", "HDR", "SampleRate",
        "AudioBitDepth",
    }
)

SUMMARY_FIELDS = tuple(
    field
    for field in DETAILED_SUMMARY_FIELDS
    if field not in {
        "video_bit_depth", "color_space", "hdr", "sample_rate",
        "audio_bit_depth",
    }
)


# Physical width of an ASCII table line, including its outer borders.
MAX_METADATA_TABLE_WIDTH = 150


def _value(track: dict, *names: str) -> Any:
    for name in names:
        value = track.get(name)
        if value not in (None, ""):
            return value
    return None


def _text(value: Any) -> str:
    return str(value) if value not in (None, "") else "-"


def _format_duration(value: Any) -> str:
    """Render MediaInfo milliseconds as a stable ``H:MM:SS.mmm`` string."""
    if value in (None, ""):
        return "-"
    try:
        milliseconds = int(
            Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        )
    except (InvalidOperation, TypeError, ValueError):
        return "-"
    if milliseconds < 0:
        return "-"
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, milliseconds = divmod(remainder, 1_000)
    return f"{hours}:{minutes:02d}:{seconds:02d}.{milliseconds:03d}"


def _format_duration_seconds(value: Any) -> str:
    """Render MediaInfo milliseconds rounded to the nearest second."""
    if value in (None, ""):
        return "-"
    try:
        seconds = int(
            (Decimal(str(value)) / Decimal("1000")).quantize(
                Decimal("1"), rounding=ROUND_HALF_UP
            )
        )
    except (InvalidOperation, TypeError, ValueError):
        return "-"
    if seconds < 0:
        return "-"
    hours, remainder = divmod(seconds, 3_600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}:{minutes:02d}:{seconds:02d}"


def _format_size(value: Any, input_file: str) -> str:
    try:
        size = int(Decimal(str(value)))
    except (InvalidOperation, TypeError, ValueError):
        try:
            size = os.path.getsize(input_file)
        except OSError:
            return "-"
    return format_utils.humanize_bytes(size).strip()


def _formats(tracks: Sequence[dict]) -> str:
    values = [_codec(track) for track in tracks]
    return ", ".join(values) if values else "-"


def _codec(track: dict) -> str:
    """Return a compact codec name, including the MediaInfo profile."""
    codec = _text(_value(track, "format", "codec_id"))
    profile = _value(track, "format_profile", "codec_profile")
    if codec == "-" or profile is None:
        return codec
    return f"{codec} ({profile})"


def _image_sizes(tracks: Sequence[dict]) -> str:
    values = []
    for track in tracks:
        width = _value(track, "width")
        height = _value(track, "height")
        if width is None or height is None:
            values.append("-")
        else:
            values.append(f"{width}x{height} px")
    return ", ".join(values) if values else "-"


def _frame_rates(tracks: Sequence[dict], detailed: bool = True) -> str:
    values = []
    for track in tracks:
        frame_rate = _value(track, "frame_rate")
        if frame_rate is None:
            values.append("-")
            continue
        if detailed:
            values.append(f"{frame_rate} fps")
            continue
        try:
            formatted = format(
                Decimal(str(frame_rate)).quantize(
                    Decimal("0.1"), rounding=ROUND_HALF_UP
                ),
                "f",
            )
        except (InvalidOperation, TypeError, ValueError):
            values.append(f"{frame_rate} fps")
        else:
            values.append(f"{formatted} fps")
    return ", ".join(values) if values else "-"


def _format_bitrate(value: Any) -> str:
    """Render a bits-per-second value with decimal MediaInfo units."""
    if value in (None, ""):
        return "-"
    try:
        bitrate = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return "-"
    if bitrate < 0:
        return "-"
    units = ((Decimal("1000000000"), "Gbps"), (Decimal("1000000"), "Mbps"),
             (Decimal("1000"), "kbps"), (Decimal("1"), "bps"))
    for divisor, suffix in units:
        if bitrate >= divisor:
            rendered = bitrate / divisor
            text = format(
                rendered.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
                "f",
            )
            return f"{text.rstrip('0').rstrip('.')} {suffix}"
    return "0 bps"


def _track_values(tracks: Sequence[dict], formatter) -> str:
    values = [formatter(track) for track in tracks]
    return ", ".join(values) if values else "-"


def _bitrate(track: dict) -> str:
    return _format_bitrate(_value(track, "bit_rate", "bit_rate_nominal"))


def _bit_depth(track: dict) -> str:
    value = _value(track, "bit_depth")
    return f"{value} bit" if value is not None else "-"


def _channels(track: dict) -> str:
    value = _value(track, "channel_s", "channels")
    return f"{value} ch" if value is not None else "-"


def _sample_rate(track: dict) -> str:
    value = _value(track, "sampling_rate", "sample_rate")
    return f"{value} Hz" if value is not None else "-"


def _safe_meta_value(value: Any) -> str:
    """Keep MediaInfo values on one physical output line."""
    try:
        value = str(value)
    except Exception:  # pragma: no cover - defensive for extension values
        value = repr(value)
    return value.replace("\\", "\\\\").replace("\r", "\\r").replace(
        "\n", "\\n"
    )


def _meta_tracks(
    tracks: Sequence[dict],
) -> list[tuple[str, list[tuple[str, str]]]]:
    counters: dict[str, int] = {}
    rendered = []
    for track in tracks:
        track_type = _text(_value(track, "track_type"))
        if track_type == "-":
            continue
        counters[track_type] = counters.get(track_type, 0) + 1
        title = (
            track_type
            if track_type == "General"
            else f"{track_type} #{counters[track_type]}"
        )
        fields = [
            (str(name), _safe_meta_value(value))
            for name, value in track.items()
            if name and value not in (None, "")
        ]
        fields.sort(key=lambda item: (item[0].casefold(), item[0]))
        rendered.append((title, fields))
    return rendered


def inspect_video(input_file: str, verbose: bool = False) -> Optional[dict]:
    """Return MediaInfo data for a regular media file, or ``None``."""
    if not os.path.isfile(input_file):
        if verbose:
            logger.warning("clips.info: not a regular file: %s", input_file)
        return None

    try:
        tracks = pymediainfo.MediaInfo.parse(input_file).to_data().get(
            "tracks", []
        )
    except (OSError, RuntimeError, ValueError, KeyError) as exc:
        if verbose:
            logger.warning(
                "clips.info: cannot read media %s: %s", input_file, exc
            )
        return None

    general_tracks = [
        track for track in tracks if track.get("track_type") == "General"
    ]
    video_tracks = [
        track for track in tracks if track.get("track_type") == "Video"
    ]
    audio_tracks = [
        track for track in tracks if track.get("track_type") == "Audio"
    ]
    if not video_tracks and not audio_tracks:
        if verbose:
            logger.warning("clips.info: not a media container: %s", input_file)
        return None

    general = general_tracks[0] if general_tracks else {}
    return {
        "format": _text(_value(general, "format")),
        "duration": _format_duration(_value(general, "duration")),
        "summary_duration": _format_duration_seconds(
            _value(general, "duration")
        ),
        "video": _formats(video_tracks),
        "image_size_px": _image_sizes(video_tracks),
        "fps": _frame_rates(video_tracks),
        "summary_fps": _frame_rates(video_tracks, detailed=False),
        "video_bitrate": _track_values(video_tracks, _bitrate),
        "video_bit_depth": _track_values(video_tracks, _bit_depth),
        "color_space": _track_values(
            video_tracks, lambda track: _text(_value(track, "color_space"))
        ),
        "hdr": _track_values(
            video_tracks, lambda track: _text(_value(track, "hdr_format"))
        ),
        "audio": _formats(audio_tracks),
        "audio_bitrate": _track_values(audio_tracks, _bitrate),
        "channels": _track_values(audio_tracks, _channels),
        "sample_rate": _track_values(audio_tracks, _sample_rate),
        "audio_bit_depth": _track_values(audio_tracks, _bit_depth),
        "file_size": _format_size(_value(general, "file_size"), input_file),
        "general_track": general,
        "video_tracks": video_tracks,
        "audio_tracks": audio_tracks,
        "meta_tracks": _meta_tracks(tracks),
    }


def format_video_info_report(
    rows: Sequence[dict],
    table: bool = False,
    compact: bool = False,
    video_number_width: Optional[int] = None,
    *,
    detailed: bool = False,
) -> str:
    """Format media rows in the TSV/ASCII-table style of info commands."""
    headers, fields = _summary_columns(detailed)
    headers = list(headers)
    table_rows = []
    for row in rows:
        values = _summary_values_for_fields(row, fields, detailed)
        if compact:
            width = video_number_width or len(str(row["total_videos"]))
            values.insert(
                0,
                f'{row["video_number"]:0{width}d}/'
                f'{row["total_videos"]:0{width}d}',
            )
        table_rows.append(values)

    if compact:
        headers.insert(0, "Video")
    widths = [0 if compact else len(header) for header in headers]
    for row in table_rows:
        for index, value in enumerate(row):
            widths[index] = max(widths[index], len(value))

    if table:
        border = "+{}+".format("+".join("-" * (width + 2) for width in widths))

        def format_row(row: Iterable[str]) -> str:
            return "| {} |".format(
                " | ".join(
                    value.rjust(widths[index])
                    if index == 0
                    else value.ljust(widths[index])
                    for index, value in enumerate(row)
                )
            )

        if compact:
            return "\n".join(
                (border, *(format_row(row) for row in table_rows), border)
            )
        return "\n".join(
            (
                border,
                format_row(headers),
                border,
                *(format_row(row) for row in table_rows),
                border,
            )
        )

    rendered = []
    if not compact:
        rendered.append(
            "  ".join(
                header.ljust(widths[index])
                for index, header in enumerate(headers)
            )
        )
    for row in table_rows:
        rendered.append(
            "  ".join(
                value.ljust(widths[index])
                for index, value in enumerate(row)
            )
        )
    return "\n".join(rendered)


def _basic_fields(track: dict, track_type: str) -> list[tuple[str, str]]:
    if track_type == "General":
        return [
            ("Format", _text(_value(track, "format"))),
            ("Duration", _format_duration(_value(track, "duration"))),
            ("FileSize", _format_size(_value(track, "file_size"), "")),
        ]
    if track_type == "Video":
        width, height = _value(track, "width"), _value(track, "height")
        resolution = (
            f"{width}x{height} px"
            if width is not None and height is not None
            else "-"
        )
        frame_rate = _value(track, "frame_rate")
        return [
            ("Codec", _codec(track)), ("Resolution", resolution),
            ("FPS", f"{frame_rate} fps" if frame_rate is not None else "-"),
            ("Bitrate", _bitrate(track)), ("BitDepth", _bit_depth(track)),
            ("ColorSpace", _text(_value(track, "color_space"))),
            ("HDR", _text(_value(track, "hdr_format"))),
        ]
    return [
        ("Codec", _codec(track)), ("Bitrate", _bitrate(track)),
        ("Channels", _channels(track)), ("SampleRate", _sample_rate(track)),
        ("BitDepth", _bit_depth(track)),
    ]


def format_basic_meta_blocks(row: dict, include_general: bool = True) -> str:
    """Format the practical, formatted properties of each media track."""
    blocks = []
    if include_general:
        general = row["general_track"]
        lines = [
            "General",
            *(
                f"{name}: {value}"
                for name, value in _basic_fields(general, "General")
            ),
        ]
        blocks.append("\n".join(lines))
    track_groups = (
        ("Video", row["video_tracks"]),
        ("Audio", row["audio_tracks"]),
    )
    for track_type, tracks in track_groups:
        for index, track in enumerate(tracks, start=1):
            lines = [
                f"{track_type} #{index}",
                *(
                    f"{name}: {value}"
                    for name, value in _basic_fields(track, track_type)
                ),
            ]
            blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def format_full_meta_blocks(row: dict) -> str:
    """Format all non-empty raw MediaInfo fields grouped by track."""
    blocks = []
    for title, fields in row["meta_tracks"]:
        lines = [title, *(f"{name}: {value}" for name, value in fields)]
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def _format_meta_block(row: dict, meta_level: str) -> str:
    if meta_level == "full":
        return format_full_meta_blocks(row)
    return format_basic_meta_blocks(row)


def _summary_values(
    row: dict,
    compact: bool,
    detailed: bool,
    video_number_width: Optional[int],
) -> list[str]:
    _, fields = _summary_columns(detailed)
    values = _summary_values_for_fields(row, fields, detailed)
    if compact:
        width = video_number_width or len(str(row["total_videos"]))
        values.insert(
            0,
            f'{row["video_number"]:0{width}d}/'
            f'{row["total_videos"]:0{width}d}',
        )
    return values


def _summary_columns(detailed: bool) -> tuple[Sequence[str], Sequence[str]]:
    if detailed:
        return DETAILED_SUMMARY_HEADERS, DETAILED_SUMMARY_FIELDS
    return SUMMARY_HEADERS, SUMMARY_FIELDS


def _summary_values_for_fields(
    row: dict,
    fields: Sequence[str],
    detailed: bool,
) -> list[str]:
    values = []
    for field in fields:
        if not detailed and field == "duration":
            value = row.get("summary_duration", row.get(field, "-"))
        elif not detailed and field == "fps":
            value = row.get("summary_fps", row.get(field, "-"))
        else:
            value = row.get(field, "-")
        values.append(str(value))
    return values


def _format_video_info_metadata_table(
    inspections: Sequence[tuple[str, dict]],
    meta_level: str,
    compact: bool,
    video_number_width: Optional[int],
    *,
    detailed: bool,
) -> str:
    headers, _ = _summary_columns(detailed)
    headers = list(headers)
    summary_rows = [
        _summary_values(row, compact, detailed, video_number_width)
        for _, row in inspections
    ]
    if compact:
        headers.insert(0, "Video")
    widths = [0 if compact else len(header) for header in headers]
    for summary_row in summary_rows:
        for index, value in enumerate(summary_row):
            widths[index] = max(widths[index], len(value))

    metadata_lines = [
        _format_meta_block(row, meta_level).splitlines()
        for _, row in inspections
    ]
    spanning_lines = [line for lines in metadata_lines for line in lines]
    if not compact:
        spanning_lines.extend(
            os.path.relpath(input_file, os.getcwd())
            for input_file, _ in inspections
        )
    combined_width = sum(widths) + 3 * (len(widths) - 1)
    widest_line = max((len(line) for line in spanning_lines), default=0)
    # A spanning row has ``| `` and `` |`` around its content.  Keep the
    # summary columns intact if they already exceed the limit.
    maximum_combined_width = max(
        combined_width, MAX_METADATA_TABLE_WIDTH - 4
    )
    target_combined_width = min(
        maximum_combined_width, max(combined_width, widest_line)
    )
    widths[-1] += target_combined_width - combined_width
    combined_width = sum(widths) + 3 * (len(widths) - 1)
    border = "+{}+".format("+".join("-" * (width + 2) for width in widths))

    def format_summary_row(values: Iterable[str]) -> str:
        return "| {} |".format(
            " | ".join(
                value.rjust(widths[index])
                if index == 0
                else value.ljust(widths[index])
                for index, value in enumerate(values)
            )
        )

    def format_spanning_row(value: str) -> str:
        return f"| {value.ljust(combined_width)} |"

    def wrap_spanning_row(value: str) -> list[str]:
        """Wrap metadata without allowing it to widen the table."""
        if len(value) <= combined_width:
            return [value]
        return textwrap.wrap(
            value,
            width=combined_width,
            subsequent_indent="  ",
            break_long_words=True,
            break_on_hyphens=False,
        )

    rendered = [border]
    if not compact:
        rendered.extend((format_summary_row(headers), border))
    for index, (input_file, _) in enumerate(inspections):
        if not compact:
            rendered.extend(
                format_spanning_row(wrapped_line)
                for wrapped_line in wrap_spanning_row(
                    os.path.relpath(input_file, os.getcwd())
                )
            )
        rendered.append(format_summary_row(summary_rows[index]))
        if metadata_lines[index]:
            rendered.append(border)
            rendered.extend(
                format_spanning_row(wrapped_line)
                for line in metadata_lines[index]
                for wrapped_line in wrap_spanning_row(line)
            )
        rendered.append(border)
    return "\n".join(rendered)


def format_video_info_metadata_report(
    inspections: Sequence[tuple[str, dict]],
    meta_level: str,
    table: bool = False,
    compact: bool = False,
    video_number_width: Optional[int] = None,
    *,
    detailed: bool = False,
) -> str:
    """Format each media summary immediately followed by its metadata."""
    if table:
        return _format_video_info_metadata_table(
            inspections,
            meta_level,
            compact,
            video_number_width,
            detailed=detailed,
        )

    reports = []
    for input_file, row in inspections:
        report = format_video_info_report(
            [row],
            compact=compact,
            detailed=detailed,
            video_number_width=video_number_width,
        )
        if not compact:
            report = "\n".join(
                (os.path.relpath(input_file, os.getcwd()), report)
            )
        meta_block = _format_meta_block(row, meta_level)
        if meta_block:
            report = f"{report}\n{meta_block}"
        reports.append(report)
    return ("\n" if compact else "\n\n").join(reports)


# Compatibility alias for callers from the original feature.
format_meta_blocks = format_full_meta_blocks
