import os

from PIL import Image, ImageOps

from davo import errors


def image_histogram(path: str) -> tuple[tuple[int, int], list[list[int]]]:
    """Return portrait-oriented RGB histogram counts for one image file."""
    if not os.path.isfile(path):
        raise errors.UserError("Image is not a regular file: {}".format(path))

    try:
        with Image.open(path) as source:
            source.load()
            image = ImageOps.exif_transpose(source)
            if image.width > image.height:
                image = image.transpose(Image.Transpose.ROTATE_90)

            with image.convert("RGB") as rgb:
                counts = rgb.histogram()
                size = rgb.size
    except (Image.DecompressionBombError, OSError, ValueError) as exc:
        raise errors.UserError(
            "Cannot read image {}: {}".format(path, exc)
        ) from exc

    if len(counts) != 256 * 3:
        raise errors.UserError(
            "Cannot calculate RGB histogram: {}".format(path)
        )

    return size, [counts[index : index + 256] for index in range(0, 768, 256)]


def format_histogram(path: str) -> str:
    """Format a normalized RGB histogram as the CLI's four-line report."""
    (width, height), channels = image_histogram(path)
    pixels = width * height
    if pixels == 0:
        raise errors.UserError("Image has no pixels: {}".format(path))

    lines = ["size: {}x{}".format(width, height)]
    for name, counts in zip(("red", "green", "blue"), channels):
        values = " ".join("{:.10f}".format(count / pixels) for count in counts)
        lines.append("{}: {}".format(name, values))
    return "\n".join(lines)
