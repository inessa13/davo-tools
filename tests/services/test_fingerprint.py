import math
import re
import struct

import pytest
from PIL import Image

from davo import errors
from davo.services.photo import fingerprint, helpers


def _values(line):
    return [float(value) for value in line.split(": ", 1)[1].split()]


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
