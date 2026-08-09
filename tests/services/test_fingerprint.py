import io
import math
import re
import struct

import pytest
from PIL import Image

from davo import errors
from davo.services.photo import fingerprint, helpers
from davo.utils import prnt


def _values(line):
    return [float(value) for value in line.split(": ", 1)[1].split()]


def _display_path(value):
    return value.rsplit(" ", 2)[0]


class _InteractiveStderr(io.StringIO):
    def isatty(self):
        return True


def test_command_fingerprint_outputs_compact_db_features(tmp_path, capsys):
    path = tmp_path / "pixels.png"
    image = Image.new("RGB", (2, 1))
    image.putdata([(255, 0, 0), (0, 255, 0)])
    image.save(path)

    helpers.command_fingerprint(str(path))

    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == "size: 1x2"
    blob = bytes.fromhex(lines[1].split(": ", 1)[1])
    vector = struct.unpack(">96H", blob)
    assert len(vector) == 96
    assert re.fullmatch(r"fingerprint_blob: [0-9a-f]{384}", lines[1])
    assert len(blob) == 192
    assert all(0 <= value <= fingerprint.UINT16_MAX for value in vector)
    scale = fingerprint.UINT16_MAX * math.sqrt(fingerprint.CHANNELS)
    assert vector[0] == round(math.sqrt(1 / 6) * scale)
    assert vector[31] == round(math.sqrt(1 / 6) * scale)
    assert vector[32] == round(math.sqrt(1 / 6) * scale)
    assert vector[63] == round(math.sqrt(1 / 6) * scale)
    assert vector[64] == round(math.sqrt(1 / 3) * scale)
    assert re.fullmatch(r"phash: [0-9a-f]{16}", lines[2])


def test_fingerprint_phash_is_deterministic(tmp_path):
    path = tmp_path / "hash.png"
    image = Image.new("L", (32, 32))
    image.paste(255, (0, 0, 16, 16))
    image.save(path)

    phash = fingerprint.fingerprint_phash(str(path))

    assert re.fullmatch(r"[0-9a-f]{16}", phash)
    assert fingerprint.fingerprint_phash(str(path)) == phash


def test_fingerprint_converts_grayscale_and_ignores_alpha(tmp_path):
    path = tmp_path / "gray-alpha.png"
    Image.new("LA", (1, 1), (128, 0)).save(path)

    _size, channels = fingerprint.image_fingerprint(str(path))

    assert all(channel[128] == 1 for channel in channels)


def test_fingerprint_converts_palette(tmp_path):
    path = tmp_path / "palette.png"
    image = Image.new("P", (1, 1))
    image.putpalette([10, 20, 30] + [0] * (256 * 3 - 3))
    image.save(path)

    _size, channels = fingerprint.image_fingerprint(str(path))

    assert channels[0][10] == 1
    assert channels[1][20] == 1
    assert channels[2][30] == 1


def test_fingerprint_applies_exif_and_portrait_orientation(tmp_path, mocker):
    path = tmp_path / "landscape.jpg"
    image = Image.new("RGB", (4, 2), (30, 40, 50))
    exif = Image.Exif()
    exif[274] = 6
    image.save(path, exif=exif)
    exif_transpose = mocker.spy(fingerprint.ImageOps, "exif_transpose")

    size, _channels = fingerprint.image_fingerprint(str(path))

    assert size == (2, 4)
    exif_transpose.assert_called_once()


@pytest.mark.parametrize("name", ("missing.png", "not-an-image.txt"))
def test_fingerprint_errors_without_partial_output(tmp_path, capsys, name):
    path = tmp_path / name
    if path.suffix == ".txt":
        path.write_text("not an image")

    with pytest.raises(errors.UserError):
        helpers.command_fingerprint(str(path))

    assert capsys.readouterr().out == ""


def test_fingerprint_rejects_directories_without_output(tmp_path, capsys):
    with pytest.raises(errors.UserError):
        helpers.command_fingerprint(str(tmp_path))

    assert capsys.readouterr().out == ""


def test_fingerprint_rejects_corrupt_image_without_output(tmp_path, capsys):
    path = tmp_path / "corrupt.png"
    Image.new("RGB", (1, 1), (255, 0, 0)).save(path)
    path.write_bytes(path.read_bytes()[:16])

    with pytest.raises(errors.UserError):
        helpers.command_fingerprint(str(path))

    assert capsys.readouterr().out == ""


def test_fingerprint_does_not_modify_source(tmp_path):
    path = tmp_path / "source.png"
    Image.new("RGB", (1, 1), (255, 0, 0)).save(path)
    original = path.read_bytes()

    fingerprint.format_fingerprint(str(path))

    assert path.read_bytes() == original


def test_fingerprint_diff_reports_zero_for_identical_images(tmp_path, capsys):
    first = tmp_path / "first.png"
    second = tmp_path / "second.png"
    image = Image.new("RGB", (2, 1))
    image.putdata([(255, 0, 0), (0, 255, 0)])
    image.save(first)
    image.save(second)

    helpers.command_fingerprint_diff([str(first), str(second)])
    first_display = "{} 1*2 {}".format(
        first,
        helpers.format_utils.humanize_bytes(
            first.stat().st_size, format_="{:.1f}{}b"
        ).replace(" ", ""),
    )
    second_display = "{} 1*2 {}".format(
        second,
        helpers.format_utils.humanize_bytes(
            second.stat().st_size, format_="{:.1f}{}b"
        ).replace(" ", ""),
    )

    assert capsys.readouterr().out.splitlines() == [
        "left\tright\tl2_percent\tphash_percent\tstatus",
        "{}\t{}\t0.00\t0.00\tidentical".format(
            first_display, second_display
        ),
        "total identical: 1",
    ]


def test_fingerprint_diff_table_output(tmp_path, capsys):
    first = tmp_path / "a.png"
    second = tmp_path / "b.png"
    Image.new("RGB", (1, 1), (255, 0, 0)).save(first)
    Image.new("RGB", (1, 1), (255, 0, 0)).save(second)

    helpers.command_fingerprint_diff([str(first), str(second)], table=True)

    first_display = "{} 1*1 {}".format(
        first,
        helpers.format_utils.humanize_bytes(
            first.stat().st_size, format_="{:.1f}{}b"
        ).replace(" ", ""),
    )
    second_display = "{} 1*1 {}".format(
        second,
        helpers.format_utils.humanize_bytes(
            second.stat().st_size, format_="{:.1f}{}b"
        ).replace(" ", ""),
    )
    widths = (len(first_display), len(second_display), 10, 13, 9)
    border = "+{}+".format(
        "+".join("-" * (width + 2) for width in widths)
    )
    expected = [
        border,
        "| {:<{}} | {:<{}} | l2_percent | phash_percent | status    |".format(
            "left", widths[0], "right", widths[1]
        ),
        border,
        "| {} | {} |       0.00 |          0.00 | identical |".format(
            first_display, second_display
        ),
        border,
        "total identical: 1",
    ]
    assert capsys.readouterr().out.splitlines() == expected


def test_fingerprint_diff_table_expands_columns_for_long_paths(capsys, mocker):
    mocker.patch.object(
        fingerprint,
        "fingerprint_comparison_features",
        return_value=((1, 1), (0.0,), "0" * 16),
    )
    mocker.patch.object(helpers.os.path, "getsize", return_value=1)
    long_path = "a-very-long-image-name.png"

    helpers.command_fingerprint_diff([long_path, "b.png"], table=True)

    assert capsys.readouterr().out.splitlines()[0] == (
        "+{}+".format(
            "+".join(
                "-" * (width + 2)
                for width in (
                    len("{} 1*1 1.0b".format(long_path)),
                    len("b.png 1*1 1.0b"),
                    10,
                    13,
                    9,
                )
            )
        )
    )


def test_fingerprint_diff_hides_different_rows_and_counts_all_statuses(
    capsys, mocker
):
    percentages = (0, 0, 1, 10, 40, 61)
    mocker.patch.object(
        fingerprint,
        "fingerprint_comparison_features",
        side_effect=[
            ((1, 1), (math.sqrt(2) * percentage / 100,), "0" * 16)
            for percentage in percentages
        ],
    )
    mocker.patch.object(helpers.os.path, "getsize", return_value=1)

    helpers.command_fingerprint_diff(
        ["{}.png".format(index) for index in range(6)]
    )

    lines = capsys.readouterr().out.splitlines()
    assert [line.split("\t")[-1] for line in lines[1:-1]] == [
        "identical",
        "duplicate",
        "similar",
        "differ",
        "duplicate",
        "similar",
        "differ",
        "similar",
        "differ",
        "differ",
        "differ",
    ]
    assert lines[-1] == (
        "total identical: 1, duplicate: 2, similar: 3, differ: 5, different: 4"
    )


def test_fingerprint_diff_shows_single_different_pair_without_all(
    capsys, mocker
):
    mocker.patch.object(
        fingerprint,
        "fingerprint_comparison_features",
        side_effect=[
            ((1, 1), (0.0,), "0" * 16),
            ((1, 1), (math.sqrt(2) * 0.6,), "0" * 16),
        ],
    )
    mocker.patch.object(helpers.os.path, "getsize", return_value=2048)

    helpers.command_fingerprint_diff(["first.png", "second.png"])

    assert capsys.readouterr().out.splitlines() == [
        "left\tright\tl2_percent\tphash_percent\tstatus",
        "first.png 1*1 2.0Kb\tsecond.png 1*1 2.0Kb\t60.00\t0.00\tdifferent",
        "total different: 1",
    ]


def test_fingerprint_diff_table_shows_single_different_pair_without_all(
    capsys, mocker
):
    mocker.patch.object(
        fingerprint,
        "fingerprint_comparison_features",
        side_effect=[
            ((1, 1), (0.0,), "0" * 16),
            ((1, 1), (math.sqrt(2) * 0.6,), "0" * 16),
        ],
    )
    mocker.patch.object(helpers.os.path, "getsize", return_value=2048)

    helpers.command_fingerprint_diff(["first.png", "second.png"], table=True)

    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == lines[2] == lines[4]
    assert "different" in lines[3]
    assert lines[5:] == ["total different: 1"]


def test_fingerprint_diff_reports_all_pairs_in_argument_order(
    tmp_path, capsys, mocker
):
    paths = [
        tmp_path / "first.png",
        tmp_path / "second.png",
        tmp_path / "third.png",
    ]
    for index, path in enumerate(paths):
        Image.new("RGB", (1, 1), (index * 100, 0, 0)).save(path)
    load_image = mocker.spy(fingerprint, "_load_image")

    helpers.command_fingerprint_diff(
        [str(path) for path in paths], show_all=True
    )

    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == "left\tright\tl2_percent\tphash_percent\tstatus"
    assert [
        [_display_path(value) for value in line.split("\t")[:2]]
        for line in lines[1:-1]
    ] == [
        [str(paths[0]), str(paths[1])],
        [str(paths[0]), str(paths[2])],
        [str(paths[1]), str(paths[2])],
    ]
    assert load_image.call_count == 3


def test_fingerprint_diff_progress_bars_use_interactive_stderr(
    tmp_path, capsys, monkeypatch
):
    paths = [tmp_path / "{}.png".format(index) for index in range(3)]
    for index, path in enumerate(paths):
        Image.new("RGB", (1, 1), (index * 100, 0, 0)).save(path)
    stderr = _InteractiveStderr()
    monkeypatch.setattr(helpers.utils.sys, "stderr", stderr)

    helpers.command_fingerprint_diff(
        [str(path) for path in paths], show_all=True
    )

    progress = stderr.getvalue()
    assert "files: {}".format(prnt.progress_bar(3, 3)) in progress
    assert "pairs: {}".format(prnt.progress_bar(3, 3)) in progress
    assert progress.endswith("\n")
    assert progress.count("\n") == 2
    assert len(capsys.readouterr().out.splitlines()) == 5


def test_fingerprint_diff_files_progress_shows_rate_elapsed_and_paths(
    tmp_path, monkeypatch, mocker
):
    images = tmp_path / "images"
    nested = images / "nested"
    nested.mkdir(parents=True)
    nested_file = nested / "nested.png"
    direct_file = tmp_path / "direct.png"
    Image.new("RGB", (1, 1), (255, 0, 0)).save(nested_file)
    Image.new("RGB", (1, 1), (0, 255, 0)).save(direct_file)
    stderr = _InteractiveStderr()
    monkeypatch.setattr(helpers.utils.sys, "stderr", stderr)
    mocker.patch.object(
        helpers.os.path, "getsize", side_effect=[100, 100, 200, 200]
    )
    mocker.patch.object(
        helpers.time, "time", side_effect=[10, 10, 12, 12, 14]
    )

    helpers.command_fingerprint_diff(
        [str(images), str(direct_file)], recursive=True, show_all=True
    )

    progress = stderr.getvalue()
    assert "Elapsed: 0.00s 0 Bps nested/nested.png" in progress
    assert "Elapsed: 2.00s 50.00  Bps nested/nested.png" in progress
    assert "Elapsed: 4.00s 75.00  Bps {}".format(direct_file) in progress
    assert "pairs: {} Elapsed:".format(prnt.progress_bar(1, 1)) not in progress


def test_fingerprint_diff_progress_counts_all_expanded_candidates(
    tmp_path, monkeypatch
):
    images = tmp_path / "images"
    images.mkdir()
    first = images / "first.png"
    second = images / "second.png"
    Image.new("RGB", (1, 1), (255, 0, 0)).save(first)
    Image.new("RGB", (1, 1), (0, 255, 0)).save(second)
    (images / "not-an-image.txt").write_text("not an image")
    stderr = _InteractiveStderr()
    monkeypatch.setattr(helpers.utils.sys, "stderr", stderr)

    helpers.command_fingerprint_diff([str(first), str(images)])

    progress = stderr.getvalue()
    assert "files: {}".format(prnt.progress_bar(4, 4)) in progress
    assert "pairs: {}".format(prnt.progress_bar(1, 1)) in progress


def test_fingerprint_diff_progress_is_disabled_for_non_tty(tmp_path, capsys):
    first = tmp_path / "first.png"
    second = tmp_path / "second.png"
    Image.new("RGB", (1, 1), (255, 0, 0)).save(first)
    Image.new("RGB", (1, 1), (0, 255, 0)).save(second)

    helpers.command_fingerprint_diff([str(first), str(second)])

    captured = capsys.readouterr()
    assert captured.err == ""
    assert captured.out.splitlines()[0] == (
        "left\tright\tl2_percent\tphash_percent\tstatus"
    )


def test_fingerprint_diff_calculates_percentages_and_status(tmp_path, capsys):
    left = tmp_path / "black.png"
    right = tmp_path / "split.png"
    Image.new("RGB", (32, 32), (0, 0, 0)).save(left)
    image = Image.new("RGB", (32, 32), (0, 0, 0))
    image.paste((255, 0, 0), (0, 0, 16, 32))
    image.save(right)

    helpers.command_fingerprint_diff([str(left), str(right)], show_all=True)

    _header, row, _summary = capsys.readouterr().out.splitlines()
    _left, _right, l2_percent, phash_percent, status = row.split("\t")
    _left_size, left_vector = fingerprint.fingerprint_vector(str(left))
    _right_size, right_vector = fingerprint.fingerprint_vector(str(right))
    expected_l2 = math.sqrt(
        sum(
            (left_value - right_value) ** 2
            for left_value, right_value in zip(left_vector, right_vector)
        )
    )
    expected_hamming = (
        int(fingerprint.fingerprint_phash(str(left)), 16)
        ^ int(fingerprint.fingerprint_phash(str(right)), 16)
    ).bit_count()

    expected_l2_percent = expected_l2 / math.sqrt(2) * 100
    expected_phash_percent = expected_hamming / 64 * 100

    assert float(l2_percent) == pytest.approx(expected_l2_percent, abs=0.005)
    assert float(phash_percent) == pytest.approx(
        expected_phash_percent, abs=0.005
    )
    expected_difference_percent = (
        expected_l2_percent + expected_phash_percent
    ) / 2
    assert status == (
        "identical"
        if expected_difference_percent == 0
        else "duplicate"
        if expected_difference_percent < 1
        else "similar"
        if expected_difference_percent < 10
        else "differ"
        if expected_difference_percent < 25
        else "different"
    )


@pytest.mark.parametrize(
    ("difference_percent", "expected_status"),
    [
        (0, "identical"),
        (0.9999, "duplicate"),
        (1, "similar"),
        (9.9999, "similar"),
        (10, "differ"),
        (24.9999, "differ"),
        (25, "different"),
    ],
)
def test_fingerprint_diff_status_uses_unrounded_average(
    capsys, mocker, difference_percent, expected_status
):
    # Keep pHash equal and set L2 so the average is the requested boundary.
    l2 = difference_percent * 2 / 100 * math.sqrt(2)
    mocker.patch.object(
        fingerprint,
        "fingerprint_comparison_features",
        side_effect=[
            ((1, 1), (0.0,), "0" * 16),
            ((1, 1), (l2,), "0" * 16),
        ],
    )
    mocker.patch.object(helpers.os.path, "getsize", return_value=1)

    helpers.command_fingerprint_diff(
        ["first.png", "second.png"], show_all=True
    )

    _left, _right, _l2_percent, _phash_percent, status = (
        capsys.readouterr().out.splitlines()[1].split("\t")
    )
    assert status == expected_status


@pytest.mark.parametrize("invalid", ("missing", "directory", "corrupt"))
def test_fingerprint_diff_invalid_input_has_no_partial_output(
    tmp_path, capsys, invalid
):
    valid = tmp_path / "valid.png"
    Image.new("RGB", (1, 1), (255, 0, 0)).save(valid)
    invalid_path = tmp_path / "invalid.png"
    if invalid == "directory":
        invalid_path.mkdir()
    elif invalid == "corrupt":
        invalid_path.write_bytes(b"not an image")

    with pytest.raises(errors.UserError):
        helpers.command_fingerprint_diff([str(valid), str(invalid_path)])

    assert capsys.readouterr().out == ""


def test_fingerprint_diff_requires_two_images_without_output(tmp_path, capsys):
    path = tmp_path / "image.png"
    Image.new("RGB", (1, 1), (255, 0, 0)).save(path)

    with pytest.raises(errors.UserError, match="At least two images"):
        helpers.command_fingerprint_diff([str(path)])

    assert capsys.readouterr().out == ""


def test_fingerprint_diff_does_not_modify_sources(tmp_path):
    paths = [tmp_path / "first.png", tmp_path / "second.png"]
    Image.new("RGB", (1, 1), (255, 0, 0)).save(paths[0])
    Image.new("RGB", (1, 1), (0, 255, 0)).save(paths[1])
    originals = [path.read_bytes() for path in paths]

    helpers.command_fingerprint_diff([str(path) for path in paths])

    assert [path.read_bytes() for path in paths] == originals


def test_fingerprint_diff_expands_top_level_directory_in_sorted_order(
    tmp_path, capsys
):
    images = tmp_path / "images"
    images.mkdir()
    Image.new("RGB", (1, 1), (255, 0, 0)).save(images / "b.png")
    Image.new("RGB", (1, 1), (0, 255, 0)).save(images / "a.png")
    (images / "not-an-image.txt").write_text("not an image")

    helpers.command_fingerprint_diff([str(images)], show_all=True)

    lines = capsys.readouterr().out.splitlines()
    assert [
        [_display_path(value) for value in line.split("\t")[:2]]
        for line in lines[1:-1]
    ] == [
        [str(images / "a.png"), str(images / "b.png")]
    ]


def test_fingerprint_diff_expands_nested_directories_only_recursively(
    tmp_path, capsys
):
    images = tmp_path / "images"
    nested = images / "nested"
    nested.mkdir(parents=True)
    Image.new("RGB", (1, 1), (255, 0, 0)).save(images / "top-a.png")
    Image.new("RGB", (1, 1), (0, 255, 0)).save(images / "top-b.png")
    Image.new("RGB", (1, 1), (0, 0, 255)).save(nested / "nested.png")

    helpers.command_fingerprint_diff([str(images)])

    assert len(capsys.readouterr().out.splitlines()) == 3

    helpers.command_fingerprint_diff(
        [str(images)], recursive=True, show_all=True
    )

    lines = capsys.readouterr().out.splitlines()
    assert [
        [_display_path(value) for value in line.split("\t")[:2]]
        for line in lines[1:-1]
    ] == [
        [str(images / "nested" / "nested.png"), str(images / "top-a.png")],
        [str(images / "nested" / "nested.png"), str(images / "top-b.png")],
        [str(images / "top-a.png"), str(images / "top-b.png")],
    ]


def test_fingerprint_diff_keeps_relative_directory_paths(
    tmp_path, capsys, monkeypatch
):
    Image.new("RGB", (1, 1), (255, 0, 0)).save(tmp_path / "a.png")
    Image.new("RGB", (1, 1), (0, 255, 0)).save(tmp_path / "b.png")
    monkeypatch.chdir(tmp_path)

    helpers.command_fingerprint_diff(["."], show_all=True)

    assert [
        _display_path(value)
        for value in capsys.readouterr().out.splitlines()[1].split("\t")[:2]
    ] == [
        "./a.png",
        "./b.png",
    ]


def test_fingerprint_diff_deduplicates_overlapping_paths(
    tmp_path, capsys, mocker
):
    first = tmp_path / "first.png"
    second = tmp_path / "second.png"
    Image.new("RGB", (1, 1), (255, 0, 0)).save(first)
    Image.new("RGB", (1, 1), (0, 255, 0)).save(second)
    load_image = mocker.spy(fingerprint, "_load_image")

    helpers.command_fingerprint_diff(
        [str(first), str(tmp_path)], show_all=True
    )

    output_pairs = [
        [_display_path(value) for value in line.split("\t")[:2]]
        for line in capsys.readouterr().out.splitlines()[1:-1]
    ]
    assert output_pairs == [[str(first), str(second)]]
    assert load_image.call_count == 2


def test_fingerprint_diff_requires_two_resolved_directory_images(
    tmp_path, capsys
):
    images = tmp_path / "images"
    images.mkdir()
    (images / "not-an-image.txt").write_text("not an image")

    with pytest.raises(errors.UserError, match="At least two images"):
        helpers.command_fingerprint_diff([str(images)])

    assert capsys.readouterr().out == ""
