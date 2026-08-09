import pytest
from PIL import Image

from davo import errors
from davo.services.photo import helpers, histogram


def _values(line):
    return [float(value) for value in line.split(": ", 1)[1].split()]


def test_command_histogram_outputs_normalized_rgb_report(tmp_path, capsys):
    path = tmp_path / "pixels.png"
    image = Image.new("RGB", (2, 1))
    image.putdata([(255, 0, 0), (0, 255, 0)])
    image.save(path)

    helpers.command_histogram(str(path))

    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == "size: 1x2"
    assert [line.split(":", 1)[0] for line in lines[1:]] == [
        "red",
        "green",
        "blue",
    ]
    red, green, blue = map(_values, lines[1:])
    assert all(len(values) == 256 for values in (red, green, blue))
    assert red[0] == 0.5
    assert red[255] == 0.5
    assert green[0] == 0.5
    assert green[255] == 0.5
    assert blue[0] == 1.0
    assert all(sum(values) == 1.0 for values in (red, green, blue))


def test_histogram_converts_grayscale_and_ignores_alpha(tmp_path):
    path = tmp_path / "gray-alpha.png"
    Image.new("LA", (1, 1), (128, 0)).save(path)

    _size, channels = histogram.image_histogram(str(path))

    assert all(channel[128] == 1 for channel in channels)


def test_histogram_converts_palette(tmp_path):
    path = tmp_path / "palette.png"
    image = Image.new("P", (1, 1))
    image.putpalette([10, 20, 30] + [0] * (256 * 3 - 3))
    image.save(path)

    _size, channels = histogram.image_histogram(str(path))

    assert channels[0][10] == 1
    assert channels[1][20] == 1
    assert channels[2][30] == 1


def test_histogram_applies_exif_and_portrait_orientation(tmp_path, mocker):
    path = tmp_path / "landscape.jpg"
    image = Image.new("RGB", (4, 2), (30, 40, 50))
    exif = Image.Exif()
    exif[274] = 6
    image.save(path, exif=exif)
    exif_transpose = mocker.spy(histogram.ImageOps, "exif_transpose")

    size, _channels = histogram.image_histogram(str(path))

    assert size == (2, 4)
    exif_transpose.assert_called_once()


@pytest.mark.parametrize("name", ("missing.png", "not-an-image.txt"))
def test_histogram_errors_without_partial_output(tmp_path, capsys, name):
    path = tmp_path / name
    if path.suffix == ".txt":
        path.write_text("not an image")

    with pytest.raises(errors.UserError):
        helpers.command_histogram(str(path))

    assert capsys.readouterr().out == ""


def test_histogram_rejects_directories_without_output(tmp_path, capsys):
    with pytest.raises(errors.UserError):
        helpers.command_histogram(str(tmp_path))

    assert capsys.readouterr().out == ""


def test_histogram_rejects_corrupt_image_without_output(tmp_path, capsys):
    path = tmp_path / "corrupt.png"
    Image.new("RGB", (1, 1), (255, 0, 0)).save(path)
    path.write_bytes(path.read_bytes()[:16])

    with pytest.raises(errors.UserError):
        helpers.command_histogram(str(path))

    assert capsys.readouterr().out == ""


def test_histogram_does_not_modify_source(tmp_path):
    path = tmp_path / "source.png"
    Image.new("RGB", (1, 1), (255, 0, 0)).save(path)
    original = path.read_bytes()

    histogram.format_histogram(str(path))

    assert path.read_bytes() == original
