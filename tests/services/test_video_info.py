import argparse

from davo.services.photo import cli as photo_cli
from davo.services.photo import helpers, video_info


class _MediaInfo:
    def __init__(self, tracks):
        self.tracks = tracks

    def to_data(self):
        return {"tracks": self.tracks}


def _media_tracks():
    return [
        {
            "track_type": "General",
            "format": "MPEG-4",
            "duration": "3723004.4",
            "file_size": "2048",
        },
        {
            "track_type": "Video",
            "format": "AVC",
            "format_profile": "High",
            "width": "1920",
            "height": "1080",
            "frame_rate": "23.976",
            "bit_rate": "4850000",
            "bit_depth": "10",
            "color_space": "YUV",
            "hdr_format": "HDR10",
        },
        {
            "track_type": "Audio",
            "format": "AAC",
            "format_profile": "LC",
            "bit_rate": "128000",
            "channel_s": "2",
            "sampling_rate": "48000",
            "bit_depth": "16",
        },
    ]


def _mock_parse(monkeypatch, tracks):
    monkeypatch.setattr(
        video_info.pymediainfo.MediaInfo,
        "parse",
        lambda _path: _MediaInfo(tracks),
    )


def _metadata_table_row():
    return {
        **{field: "-" for field in video_info.SUMMARY_FIELDS},
        "general_track": {
            "format": "MPEG-4",
            "duration": "1000",
            "file_size": "10",
        },
        "video_tracks": [],
        "audio_tracks": [],
        "meta_tracks": [],
        "video_number": 1,
        "total_videos": 1,
    }


def test_inspect_video_reads_general_video_and_audio(tmp_path, monkeypatch):
    source = tmp_path / "movie.mp4"
    source.write_bytes(b"x" * 2048)
    _mock_parse(monkeypatch, _media_tracks())

    row = video_info.inspect_video(str(source))

    assert row["format"] == "MPEG-4"
    assert row["duration"] == "1:02:03.004"
    assert row["summary_duration"] == "1:02:03"
    assert row["video"] == "AVC (High)"
    assert row["image_size_px"] == "1920x1080 px"
    assert row["fps"] == "23.976 fps"
    assert row["summary_fps"] == "24.0 fps"
    assert row["video_bitrate"] == "4.85 Mbps"
    assert row["video_bit_depth"] == "10 bit"
    assert row["color_space"] == "YUV"
    assert row["hdr"] == "HDR10"
    assert row["audio"] == "AAC (LC)"
    assert row["audio_bitrate"] == "128 kbps"
    assert row["channels"] == "2 ch"
    assert row["sample_rate"] == "48000 Hz"
    assert row["audio_bit_depth"] == "16 bit"
    assert row["file_size"] == "2.00 K"


def test_inspect_video_handles_missing_values_and_multiple_tracks(
    tmp_path, monkeypatch
):
    source = tmp_path / "movie.bin"
    source.write_bytes(b"x")
    _mock_parse(
        monkeypatch,
        [
            {"track_type": "General"},
            {"track_type": "Video", "format": "AVC"},
            {"track_type": "Video", "format": "HEVC", "width": 2, "height": 1},
            {"track_type": "Audio", "format": "AAC"},
            {"track_type": "Audio", "format": "Opus"},
        ],
    )

    row = video_info.inspect_video(str(source))

    assert row["format"] == "-"
    assert row["duration"] == "-"
    assert row["video"] == "AVC, HEVC"
    assert row["image_size_px"] == "-, 2x1 px"
    assert row["fps"] == "-, -"
    assert row["audio"] == "AAC, Opus"
    assert row["video_bitrate"] == "-, -"
    assert row["audio_bitrate"] == "-, -"
    assert row["file_size"] == "1.00"


def test_compact_duration_rounds_to_nearest_second():
    assert video_info._format_duration_seconds(  # pylint: disable=W0212
        "1499.9"
    ) == "0:00:01"
    assert video_info._format_duration_seconds(  # pylint: disable=W0212
        "1500"
    ) == "0:00:02"


def test_format_video_info_report_compact_ascii_table():
    row = {
        "format": "MPEG-4",
        "duration": "0:00:01.000",
        "video": "AVC",
        "image_size_px": "1x1 px",
        "fps": "24 fps",
        "audio": "AAC",
        "file_size": "1.00 K",
        "video_number": 1,
        "total_videos": 2,
    }

    report = video_info.format_video_info_report(
        [row, {**row, "video_number": 2}], table=True, compact=True
    )

    lines = report.splitlines()
    assert len(lines) == 4
    assert "1/2" in lines[1]
    assert "2/2" in lines[2]


def test_format_video_info_report_uses_compact_summary_by_default():
    row = {
        "format": "MPEG-4",
        "duration": "1:02:03.004",
        "summary_duration": "1:02:03",
        "video": "AVC",
        "image_size_px": "1920x1080 px",
        "fps": "23.976 fps",
        "summary_fps": "24.0 fps",
        "video_bitrate": "4.85 Mbps",
        "video_bit_depth": "10 bit",
        "color_space": "YUV",
        "hdr": "HDR10",
        "audio": "AAC",
        "audio_bitrate": "128 kbps",
        "channels": "2 ch",
        "sample_rate": "48000 Hz",
        "audio_bit_depth": "16 bit",
        "file_size": "2.00 K",
    }

    summary = video_info.format_video_info_report([row])
    detailed = video_info.format_video_info_report([row], detailed=True)

    assert "VideoBitDepth" not in summary
    assert "ColorSpace" not in summary
    assert "HDR" not in summary
    assert "SampleRate" not in summary
    assert "AudioBitDepth" not in summary
    assert "1:02:03" in summary
    assert "1:02:03.004" not in summary
    assert "24.0 fps" in summary
    assert "23.976 fps" not in summary
    assert "VideoBitDepth" in detailed
    assert "10 bit" in detailed
    assert "1:02:03.004" in detailed
    assert "23.976 fps" in detailed


def test_format_meta_blocks_is_sorted_and_newline_safe():
    block = video_info.format_meta_blocks(
        {
            "meta_tracks": video_info._meta_tracks(  # pylint: disable=W0212
                [
                    {
                        "track_type": "General",
                        "zebra": "a\nb",
                        "Alpha": "yes",
                        "empty": "",
                    },
                    {"track_type": "Video", "format": "AVC"},
                    {"track_type": "Audio", "format": "AAC"},
                ]
            )
        }
    )

    assert block == (
        "General\nAlpha: yes\ntrack_type: General\nzebra: a\\nb\n\n"
        "Video #1\nformat: AVC\ntrack_type: Video\n\n"
        "Audio #1\nformat: AAC\ntrack_type: Audio"
    )


def test_format_basic_meta_blocks_keeps_track_properties_together():
    row = {
        "general_track": {
            "format": "MPEG-4",
            "duration": "1000",
            "file_size": "10",
        },
        "video_tracks": [
            {
                "format": "AVC",
                "width": "1920",
                "height": "1080",
                "bit_rate": "1000000",
            },
            {
                "format": "HEVC",
                "width": "1280",
                "height": "720",
                "bit_rate": "500000",
            },
        ],
        "audio_tracks": [{"format": "AAC", "channel_s": "2"}],
    }

    assert video_info.format_basic_meta_blocks(row) == (
        "General\nFormat: MPEG-4\nDuration: 0:00:01.000\nFileSize: 10.00\n\n"
        "Video #1\nCodec: AVC\nResolution: 1920x1080 px\nFPS: -\n"
        "Bitrate: 1 Mbps\nBitDepth: -\nColorSpace: -\nHDR: -\n\n"
        "Video #2\nCodec: HEVC\nResolution: 1280x720 px\nFPS: -\n"
        "Bitrate: 500 kbps\nBitDepth: -\nColorSpace: -\nHDR: -\n\n"
        "Audio #1\nCodec: AAC\nBitrate: -\nChannels: 2 ch\n"
        "SampleRate: -\nBitDepth: -"
    )

def test_command_clips_info_keeps_order_and_skips_bad_input(
    tmp_path, monkeypatch, caplog, capsys
):
    first = tmp_path / "first.mp4"
    second = tmp_path / "second.mp4"
    first.write_bytes(b"x")
    second.write_bytes(b"x")
    _mock_parse(monkeypatch, _media_tracks())

    with caplog.at_level("WARNING"):
        helpers.command_clips_info(
            [str(first), str(tmp_path / "missing.mp4"), str(second)],
            verbose=True,
        )

    output = capsys.readouterr().out
    assert output.index("first.mp4") < output.index("second.mp4")
    assert "not a regular file" in caplog.text


def test_command_clips_info_compact_table_and_meta(
    tmp_path, monkeypatch, capsys
):
    source = tmp_path / "movie.mp4"
    source.write_bytes(b"x")
    _mock_parse(monkeypatch, _media_tracks())

    helpers.command_clips_info(
        [str(source)], compact=True, table=True, meta=True
    )

    lines = capsys.readouterr().out.splitlines()
    assert lines[0].startswith("+")
    assert "1/1" in lines[1]
    assert lines[2] == lines[0]
    assert lines[3].startswith("| General")
    assert lines[-1] == lines[0]
    assert all(line.startswith(("+", "|")) for line in lines)
    assert lines[3].count("|") == 2


def test_command_clips_info_compact_meta_follows_its_summary_row(
    tmp_path, monkeypatch, capsys
):
    first = tmp_path / "first.mp4"
    second = tmp_path / "second.mp4"
    first.write_bytes(b"x")
    second.write_bytes(b"x")
    _mock_parse(monkeypatch, _media_tracks())

    helpers.command_clips_info(
        [str(first), str(second)], compact=True, meta=True
    )

    lines = capsys.readouterr().out.splitlines()
    assert lines[0].startswith("1/2")
    first_metadata = lines.index("General")
    second_summary = next(
        index for index, line in enumerate(lines) if line.startswith("2/2")
    )
    assert 0 < first_metadata < second_summary


def test_command_clips_info_meta_follows_its_file_summary(
    tmp_path, monkeypatch, capsys
):
    first = tmp_path / "first.mp4"
    second = tmp_path / "second.mp4"
    first.write_bytes(b"x")
    second.write_bytes(b"x")
    _mock_parse(monkeypatch, _media_tracks())

    helpers.command_clips_info([str(first), str(second)], meta=True)

    lines = capsys.readouterr().out.splitlines()
    first_path = next(
        index for index, line in enumerate(lines) if "first.mp4" in line
    )
    first_summary = next(
        index for index, line in enumerate(lines) if line.startswith("MPEG-4")
    )
    first_metadata = lines.index("General")
    second_path = next(
        index for index, line in enumerate(lines) if "second.mp4" in line
    )
    assert first_path < first_summary < first_metadata < second_path


def test_command_clips_info_compact_meta_follows_summary_with_raw_fields(
    tmp_path, monkeypatch, capsys
):
    first = tmp_path / "first.mp4"
    second = tmp_path / "second.mp4"
    first.write_bytes(b"x")
    second.write_bytes(b"x")
    tracks = _media_tracks()
    tracks[1]["custom_field"] = "raw value"
    _mock_parse(monkeypatch, tracks)

    helpers.command_clips_info(
        [str(first), str(second)], compact=True, meta=True
    )

    lines = capsys.readouterr().out.splitlines()
    first_metadata = lines.index("General")
    second_summary = next(
        index for index, line in enumerate(lines) if line.startswith("2/2")
    )
    assert lines[0].startswith("1/2")
    raw_field = lines.index("custom_field: raw value")
    assert first_metadata < raw_field < second_summary


def test_command_clips_info_table_keeps_meta_with_each_file(
    tmp_path, monkeypatch, capsys
):
    first = tmp_path / "first.mp4"
    second = tmp_path / "second.mp4"
    first.write_bytes(b"x")
    second.write_bytes(b"x")
    tracks = _media_tracks()
    tracks[1]["custom_field"] = "raw value"
    _mock_parse(monkeypatch, tracks)

    helpers.command_clips_info(
        [str(first), str(second)], table=True, meta=True
    )

    lines = capsys.readouterr().out.splitlines()
    first_path = next(
        index for index, line in enumerate(lines) if "first.mp4" in line
    )
    first_metadata = next(
        index
        for index, line in enumerate(lines)
        if line.startswith("| General")
    )
    second_path = next(
        index for index, line in enumerate(lines) if "second.mp4" in line
    )
    assert lines[0].startswith("+")
    assert lines[2] == lines[0]
    assert lines[-1] == lines[0]
    assert first_path < first_metadata < second_path
    assert lines[first_path + 1].count("|") > 2
    assert lines[first_path + 2] == lines[0]
    assert lines[first_metadata - 1] == lines[0]
    assert all(line.startswith(("+", "|")) for line in lines)
    assert lines[first_metadata].count("|") == 2
    assert any("custom_field: raw value" in line for line in lines)


def test_metadata_table_wraps_raw_metadata_and_long_paths(tmp_path):
    row = _metadata_table_row()
    row["meta_tracks"] = [
        ("General", [("raw_field", " ".join(["descriptive"] * 40))])
    ]
    input_file = tmp_path / ("long-directory-" * 20) / "movie.mp4"

    lines = video_info.format_video_info_metadata_report(
        [(str(input_file), row)], "full", table=True
    ).splitlines()

    assert all(
        len(line) <= video_info.MAX_METADATA_TABLE_WIDTH for line in lines
    )
    assert any("raw_field: descriptive" in line for line in lines)
    assert any(line.startswith("|   descriptive") for line in lines)
    assert any("long-directory-" in line for line in lines)


def test_metadata_table_wraps_unbroken_full_metadata_values():
    row = _metadata_table_row()
    raw_value = "q" * 400
    row["meta_tracks"] = [("General", [("raw_field", raw_value)])]

    for compact in (False, True):
        lines = video_info.format_video_info_metadata_report(
            [("movie.mp4", row)], "full", table=True, compact=compact
        ).splitlines()

        raw_lines = [line for line in lines if "q" in line]
        assert all(
            len(line) <= video_info.MAX_METADATA_TABLE_WIDTH for line in lines
        )
        assert len(raw_lines) == 3
        assert raw_lines[1].startswith("|   ")
        assert raw_lines[2].startswith("|   ")


def test_metadata_table_does_not_shrink_an_already_wide_summary():
    row = _metadata_table_row()
    row["format"] = "x" * 220

    lines = video_info.format_video_info_metadata_report(
        [("movie.mp4", row)], "full", table=True
    ).splitlines()

    assert "x" * 220 in lines[4]
    assert len(lines[4]) > video_info.MAX_METADATA_TABLE_WIDTH


def test_command_clips_info_prints_track_blocks_for_multiple_tracks(
    tmp_path, monkeypatch, capsys
):
    source = tmp_path / "movie.mp4"
    source.write_bytes(b"x")
    tracks = _media_tracks()
    tracks.append({"track_type": "Audio", "format": "Opus"})
    _mock_parse(monkeypatch, tracks)

    helpers.command_clips_info([str(source)])

    output = capsys.readouterr().out
    assert "Audio #1" in output
    assert "Audio #2" in output
    assert "General\nFormat:" not in output


def test_command_clips_info_meta_uses_raw_fields(
    tmp_path, monkeypatch, capsys
):
    source = tmp_path / "movie.mp4"
    source.write_bytes(b"x")
    tracks = _media_tracks()
    tracks[1]["custom_field"] = "raw value"
    _mock_parse(monkeypatch, tracks)

    helpers.command_clips_info([str(source)], meta=True)

    output = capsys.readouterr().out
    assert "custom_field: raw value" in output
    assert "track_type: Video" in output


def test_command_clips_info_without_meta_prints_only_summary(
    tmp_path, monkeypatch, capsys
):
    source = tmp_path / "movie.mp4"
    source.write_bytes(b"x")
    tracks = _media_tracks()
    tracks[1]["custom_field"] = "raw value"
    _mock_parse(monkeypatch, tracks)

    helpers.command_clips_info([str(source)])

    output = capsys.readouterr().out
    assert "AVC (High)" in output
    assert "custom_field" not in output
    assert "track_type:" not in output
    assert "General\n" not in output


def test_clips_info_cli_forwards_display_options(monkeypatch):
    calls = []
    monkeypatch.setattr(
        helpers, "command_clips_info", lambda **kwargs: calls.append(kwargs)
    )
    parser = argparse.ArgumentParser()
    photo_cli.init_parser_clips(parser)

    namespace = parser.parse_args(
        ["info", "-v", "-t", "-c", "-d", "--meta", "movie.mp4"]
    )
    namespace.func(namespace)

    assert calls == [
        {
            "inputs": ["movie.mp4"],
            "verbose": True,
            "table": True,
                "compact": True,
                "meta": True,
                "detailed": True,
            }
        ]


def test_clips_info_cli_rejects_meta_full():
    parser = argparse.ArgumentParser()
    photo_cli.init_parser_clips(parser)

    try:
        parser.parse_args(["info", "--meta-full"])
    except SystemExit:
        pass
    else:  # pragma: no cover - argparse must reject removed flag
        raise AssertionError("--meta-full must be rejected")


def test_clips_info_cli_accepts_no_input_and_legacy_name():
    parser = argparse.ArgumentParser()
    photo_cli.init_parser_clips(parser)
    assert parser.parse_args(["info"]).inputs == []

    legacy = photo_cli.init_parser()[0]
    assert callable(legacy.parse_args(["clips-info", "movie.mp4"]).func)
