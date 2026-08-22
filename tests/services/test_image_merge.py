import pytest
from PIL import Image

from davo import errors
from davo.services.photo import helpers


def _image(path, size, color, mode="RGBA"):
    image = Image.new(mode, size, color)
    image.save(path)
    return path


def test_vertical_merge_centers_images_and_preserves_order(tmp_path):
    first = _image(tmp_path / "first.png", (4, 2), (255, 0, 0, 255))
    second = _image(tmp_path / "second.png", (2, 3), (0, 0, 255, 255))
    output = tmp_path / "result.png"

    helpers.command_image_merge([str(first), str(second)], True, str(output))

    with Image.open(output) as result:
        assert result.size == (4, 5)
        assert result.getpixel((0, 0)) == (255, 0, 0, 255)
        assert result.getpixel((0, 2)) == (0, 0, 0, 0)
        assert result.getpixel((1, 2)) == (0, 0, 255, 255)


def test_horizontal_merge_centers_images(tmp_path):
    first = _image(tmp_path / "first.png", (2, 4), (255, 0, 0, 255))
    second = _image(tmp_path / "second.png", (3, 2), (0, 255, 0, 255))
    output = tmp_path / "result.png"

    helpers.command_image_merge([str(first), str(second)], False, str(output))

    with Image.open(output) as result:
        assert result.size == (5, 4)
        assert result.getpixel((2, 0)) == (0, 0, 0, 0)
        assert result.getpixel((2, 1)) == (0, 255, 0, 255)


def test_merge_debug_fill_replaces_empty_and_transparent_areas(tmp_path):
    first = _image(tmp_path / "first.png", (2, 2), (0, 0, 0, 0))
    second = _image(tmp_path / "second.png", (4, 2), (0, 255, 0, 255))
    output = tmp_path / "result.png"

    helpers.command_image_merge(
        [str(first), str(second)], True, str(output), debug_fill=True
    )

    with Image.open(output) as result:
        assert result.getpixel((0, 0)) == (255, 0, 255, 255)
        assert result.getpixel((0, 2)) == (0, 255, 0, 255)


def test_merge_flattens_transparent_png_to_white_for_jpeg(tmp_path):
    first = _image(tmp_path / "first.png", (2, 2), (0, 0, 0, 0))
    second = _image(tmp_path / "second.png", (2, 2), (255, 0, 0, 255))
    output = tmp_path / "result.jpg"

    helpers.command_image_merge([str(first), str(second)], True, str(output))

    with Image.open(output) as result:
        assert result.mode == "RGB"
        red, green, blue = result.getpixel((0, 0))
        assert red > 245 and green > 245 and blue > 245


@pytest.mark.parametrize(
    ("extension", "expected_name", "expected_format"),
    [
        ("jpg", "first_merged.jpg", "JPEG"),
        ("png", "first_merged.png", "PNG"),
    ],
)
def test_merge_uses_first_input_name_for_uniform_formats(
    tmp_path, extension, expected_name, expected_format
):
    first = _image(tmp_path / ("first." + extension), (2, 2), "red", "RGB")
    second = _image(tmp_path / ("second." + extension), (2, 2), "blue", "RGB")

    helpers.command_image_merge([str(first), str(second)], True)

    with Image.open(tmp_path / expected_name) as result:
        assert result.format == expected_format


def test_merge_uses_jpeg_name_for_mixed_input_formats(tmp_path):
    first = _image(tmp_path / "first.png", (2, 2), "red", "RGB")
    second = _image(tmp_path / "second.jpg", (2, 2), "blue", "RGB")

    helpers.command_image_merge([str(first), str(second)], True)

    with Image.open(tmp_path / "first_merged.jpg") as result:
        assert result.format == "JPEG"


def test_merge_uses_explicit_output_extension_format(tmp_path):
    first = _image(tmp_path / "first.png", (2, 2), "red", "RGB")
    second = _image(tmp_path / "second.png", (2, 2), "blue", "RGB")
    output = tmp_path / "result.webp"

    helpers.command_image_merge([str(first), str(second)], True, str(output))

    with Image.open(output) as result:
        assert result.format == "WEBP"


@pytest.mark.parametrize("bad_output", ["result", "result.unknown"])
def test_merge_rejects_unsupported_output_extension(tmp_path, bad_output):
    first = _image(tmp_path / "first.png", (2, 2), "red")
    second = _image(tmp_path / "second.png", (2, 2), "blue")

    with pytest.raises(errors.UserError, match="Unsupported output"):
        helpers.command_image_merge(
            [str(first), str(second)], True, str(tmp_path / bad_output)
        )


def test_merge_rejects_invalid_and_unsafe_inputs_and_outputs(tmp_path):
    first = _image(tmp_path / "first.png", (2, 2), "red")
    output = tmp_path / "output.png"
    output.touch()

    with pytest.raises(errors.UserError, match="At least two"):
        helpers.command_image_merge([str(first)], True)
    with pytest.raises(errors.UserError, match="regular file"):
        helpers.command_image_merge(
            [str(first), str(tmp_path / "missing.png")], True
        )
    with pytest.raises(errors.UserError, match="already exists"):
        helpers.command_image_merge(
            [str(first), str(first)], True, str(output)
        )
    with pytest.raises(errors.UserError, match="must not replace"):
        helpers.command_image_merge([str(first), str(first)], True, str(first))


def _overlap_images(tmp_path, vertical):
    if vertical:
        whole = Image.effect_noise((32, 96), 80).convert("RGB")
        first = whole.crop((0, 0, 32, 64))
        second = whole.crop((0, 40, 32, 96))
    else:
        whole = Image.effect_noise((96, 32), 80).convert("RGB")
        first = whole.crop((0, 0, 64, 32))
        second = whole.crop((40, 0, 96, 32))
    first_path = tmp_path / "first.png"
    second_path = tmp_path / "second.png"
    first.save(first_path)
    second.save(second_path)
    return first_path, second_path


@pytest.mark.skipif(helpers.cv2 is None, reason="OpenCV is not installed")
@pytest.mark.parametrize("vertical", [True, False])
def test_smart_merge_removes_known_overlap(tmp_path, vertical):
    first, second = _overlap_images(tmp_path, vertical)
    output = tmp_path / "result.png"

    helpers.command_image_merge(
        [str(first), str(second)], vertical, str(output), smart=True
    )

    with Image.open(output) as result:
        assert result.size == ((32, 96) if vertical else (96, 32))


@pytest.mark.skipif(helpers.cv2 is None, reason="OpenCV is not installed")
@pytest.mark.parametrize("vertical", [True, False])
def test_smart_merge_rejects_no_overlap_without_output(tmp_path, vertical):
    if vertical:
        first = _image(tmp_path / "first.png", (32, 64), "black", "RGB")
        second = _image(tmp_path / "second.png", (32, 64), "white", "RGB")
    else:
        first = _image(tmp_path / "first.png", (64, 32), "black", "RGB")
        second = _image(tmp_path / "second.png", (64, 32), "white", "RGB")
    output = tmp_path / "result.png"

    with pytest.raises(errors.UserError, match="No strong overlap"):
        helpers.command_image_merge(
            [str(first), str(second)], vertical, str(output), smart=True
        )
    assert not output.exists()


@pytest.mark.parametrize("vertical", [True, False])
def test_smart_merge_rejects_mismatched_cross_axis(tmp_path, vertical):
    first = _image(tmp_path / "first.png", (32, 64), "red", "RGB")
    second = _image(tmp_path / "second.png", (64, 32), "blue", "RGB")

    with pytest.raises(errors.UserError, match="equal"):
        helpers.command_image_merge(
            [str(first), str(second)], vertical, str(tmp_path / "out.png"),
            smart=True,
        )
