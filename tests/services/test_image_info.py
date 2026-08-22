import argparse

import pytest
from PIL import Image

from davo.services.photo import cli as photo_cli
from davo.services.photo import helpers, image_info


def _save_exif_image(path):
    exif = Image.Exif()
    exif[274] = 6
    exif[271] = "Davo"
    exif[272] = "Camera"
    exif[306] = "2026:08:22 10:00:00"
    exif[36867] = "2026:08:22 09:00:00"
    Image.new("RGB", (4, 2), "red").save(
        path, dpi=(300, 200), exif=exif
    )


def test_inspect_image_reads_metadata_and_exif_orientation(tmp_path):
    source = tmp_path / "photo.jpg"
    _save_exif_image(source)

    row = image_info.inspect_image(str(source))

    assert row["format"] == "JPEG"
    assert row["image_size_px"] == "2x4 px"
    assert row["resolution"] == "300x200 dpi"
    assert row["orientation"] == "portrait"
    assert row["mode"] == "RGB"
    assert row["exif"] == "yes"
    assert row["date"] == "2026:08:22 09:00:00"
    assert row["camera"] == "Davo Camera"


def test_inspect_image_uses_general_date_and_missing_camera_placeholders(
    tmp_path,
):
    source = tmp_path / "date.jpg"
    exif = Image.Exif()
    exif[306] = "2026:08:22 10:00:00"
    Image.new("RGB", (1, 1)).save(source, exif=exif)

    row = image_info.inspect_image(str(source))

    assert row["date"] == "2026:08:22 10:00:00"
    assert row["camera"] == "- -"


def test_format_exif_block_is_alphabetical_and_safe():
    tags = image_info._exif_tags({272: "a\nb", 306: "date"})  # pylint: disable=W0212
    block = image_info.format_exif_block({"exif_tags": tags})

    assert block == "DateTime: date\nModel: a\\nb"


def test_command_image_info_compact_table_combines_images(tmp_path, capsys):
    first = tmp_path / "first.png"
    second = tmp_path / "second.png"
    Image.new("RGB", (1, 1)).save(first)
    Image.new("RGB", (2, 1)).save(second)

    helpers.command_image_info(
        [str(first), str(second)], compact=True, table=True
    )

    lines = capsys.readouterr().out.splitlines()
    assert lines[0].startswith("+")
    assert len(lines) == 4
    assert "1/2" in lines[1]
    assert "2/2" in lines[2]


def test_compact_table_with_full_exif_keeps_one_table(tmp_path, capsys):
    source = tmp_path / "photo.jpg"
    _save_exif_image(source)

    helpers.command_image_info(
        [str(source)], compact=True, table=True, exif_full=True
    )

    lines = capsys.readouterr().out.splitlines()
    assert lines[0].startswith("+")
    assert lines[2] == lines[0]
    assert lines[3] == "1/1"
    assert any(line.startswith("DateTimeOriginal:") for line in lines)


def test_command_image_info_skips_bad_input_and_keeps_later_result(
    tmp_path, caplog, capsys
):
    good = tmp_path / "good.png"
    Image.new("RGB", (1, 1)).save(good)

    with caplog.at_level("WARNING"):
        helpers.command_image_info(
            [str(tmp_path / "missing.png"), str(good)], verbose=True
        )

    assert "not a regular file" in caplog.text
    assert "good.png" in capsys.readouterr().out


def test_image_info_cli_forwards_all_display_options(monkeypatch):
    calls = []
    monkeypatch.setattr(
        helpers, "command_image_info", lambda **kwargs: calls.append(kwargs)
    )
    parser = argparse.ArgumentParser()
    photo_cli.init_parser(parser, commands=("info",))

    namespace = parser.parse_args(
        ["info", "-v", "-t", "-c", "-e", "first.png"]
    )
    namespace.func(namespace)

    assert calls == [
        {
            "images": ["first.png"],
            "verbose": True,
            "table": True,
            "compact": True,
            "exif": True,
            "exif_full": False,
        }
    ]


def test_image_info_cli_accepts_no_input_files():
    parser = argparse.ArgumentParser()
    photo_cli.init_parser(parser, commands=("info",))

    namespace = parser.parse_args(["info"])

    assert namespace.images == []


def test_command_image_info_expands_empty_input_to_current_directory(
    monkeypatch,
):
    inspected = []
    monkeypatch.setattr(
        helpers.glob, "glob", lambda _pattern: ["b.png", "a.png"]
    )
    monkeypatch.setattr(
        image_info,
        "inspect_image",
        lambda path, **_kwargs: inspected.append(path) or None,
    )

    helpers.command_image_info([])

    assert inspected == ["a.png", "b.png"]


def test_image_info_cli_rejects_conflicting_exif_options():
    parser = argparse.ArgumentParser()
    photo_cli.init_parser(parser, commands=("info",))

    with pytest.raises(SystemExit):
        parser.parse_args(["info", "-e", "-E", "image.png"])
