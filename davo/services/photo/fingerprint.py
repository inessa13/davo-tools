import math
import os
import struct

import numpy
from PIL import Image, ImageOps

from davo import errors

CHANNELS = 3
HISTOGRAM_BINS = 256
VECTOR_BINS = 32
BINS_PER_VECTOR_BIN = HISTOGRAM_BINS // VECTOR_BINS
UINT16_MAX = 2**16 - 1
PHASH_IMAGE_SIZE = 32
PHASH_SIZE = 8
DCT_MATRIX = numpy.cos(
    numpy.pi
    / PHASH_IMAGE_SIZE
    * numpy.outer(
        numpy.arange(PHASH_IMAGE_SIZE),
        numpy.arange(PHASH_IMAGE_SIZE) + 0.5,
    )
)
DCT_MATRIX[0] /= math.sqrt(2)
DCT_MATRIX *= math.sqrt(2 / PHASH_IMAGE_SIZE)


def _load_image(path: str) -> Image.Image:
    """Load one image as portrait-oriented RGB pixels."""
    if not os.path.isfile(path):
        raise errors.UserError("Image is not a regular file: {}".format(path))

    try:
        with Image.open(path) as source:
            source.load()
            image = ImageOps.exif_transpose(source)
            if image.width > image.height:
                image = image.transpose(Image.Transpose.ROTATE_90)
            return image.convert("RGB")
    except (Image.DecompressionBombError, OSError, ValueError) as exc:
        raise errors.UserError(
            "Cannot read image {}: {}".format(path, exc)
        ) from exc


def image_fingerprint(path: str) -> tuple[tuple[int, int], list[list[int]]]:
    """Return portrait-oriented RGB histogram counts for one image file."""
    with _load_image(path) as image:
        return _image_histogram(image, path)


def _image_histogram(
    image: Image.Image, path: str
) -> tuple[tuple[int, int], list[list[int]]]:
    """Return RGB histogram counts from an already-normalized image."""
    counts = image.histogram()
    if len(counts) != HISTOGRAM_BINS * CHANNELS:
        raise errors.UserError(
            "Cannot calculate RGB histogram: {}".format(path)
        )

    return image.size, [
        counts[index : index + HISTOGRAM_BINS]
        for index in range(0, HISTOGRAM_BINS * CHANNELS, HISTOGRAM_BINS)
    ]


def _fingerprint_vector_from_image(
    image: Image.Image, path: str
) -> tuple[tuple[int, int], list[float]]:
    """Return the comparison vector from an already-normalized image."""
    (width, height), channels = _image_histogram(image, path)
    pixels = width * height
    if pixels == 0:
        raise errors.UserError("Image has no pixels: {}".format(path))

    vector = []
    for channel in channels:
        for start in range(0, HISTOGRAM_BINS, BINS_PER_VECTOR_BIN):
            count = sum(channel[start : start + BINS_PER_VECTOR_BIN])
            vector.append(math.sqrt(count / pixels / CHANNELS))
    return (width, height), vector


def fingerprint_vector(path: str) -> tuple[tuple[int, int], list[float]]:
    """Return a unit-length 96-dimensional vector for image comparison."""
    with _load_image(path) as image:
        return _fingerprint_vector_from_image(image, path)


def fingerprint_uint16(path: str) -> tuple[tuple[int, int], list[int]]:
    """Return the comparison vector quantized for big-endian uint16 storage."""
    size, vector = fingerprint_vector(path)
    scale = UINT16_MAX * math.sqrt(CHANNELS)
    return size, [round(value * scale) for value in vector]


def fingerprint_blob(path: str) -> tuple[tuple[int, int], bytes]:
    """Return the comparison vector packed as a 192-byte big-endian BLOB."""
    size, values = fingerprint_uint16(path)
    return size, struct.pack(
        ">{:d}H".format(VECTOR_BINS * CHANNELS),
        *values,
    )


def fingerprint_phash(path: str) -> str:
    """Return a 64-bit DCT perceptual hash as sixteen lowercase hex digits."""
    with _load_image(path) as image:
        return _fingerprint_phash_from_image(image)


def _fingerprint_phash_from_image(image: Image.Image) -> str:
    """Return a pHash from an already-normalized image."""
    grayscale = image.convert("L").resize(
        (PHASH_IMAGE_SIZE, PHASH_IMAGE_SIZE),
        Image.Resampling.LANCZOS,
    )
    pixels = numpy.asarray(grayscale, dtype=numpy.float32)
    dct = DCT_MATRIX @ pixels @ DCT_MATRIX.T
    low_frequency = dct[:PHASH_SIZE, :PHASH_SIZE].flatten()
    median = numpy.median(low_frequency[1:])
    value = 0
    for coefficient in low_frequency:
        value = (value << 1) | int(coefficient > median)
    return "{:016x}".format(value)


def fingerprint_comparison_features(path: str) -> tuple[list[float], str]:
    """Return comparison vector and pHash after decoding an image once."""
    with _load_image(path) as image:
        _size, vector = _fingerprint_vector_from_image(image, path)
        phash = _fingerprint_phash_from_image(image)
    return vector, phash


def format_fingerprint(path: str) -> str:
    """Format compact histogram and perceptual-hash image features."""
    (width, height), blob = fingerprint_blob(path)
    lines = [
        "size: {}x{}".format(width, height),
        "fingerprint_blob: {}".format(blob.hex()),
        "phash: {}".format(fingerprint_phash(path)),
    ]
    return "\n".join(lines)
