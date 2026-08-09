---
status: implemented
type: feature
slug: im-histogram
date: 2026-08-08
---

# Feature: add `davo im fp` command

**Roadmap:** implemented and removed from the active roadmap.

## Summary

Add a readonly `davo im fp` command that calculates an image colour
histogram and prints it to stdout.

The initial command is a building block for later image similarity search and
comparison.  Its sole MVP result is a deterministic, machine-readable
histogram for one input image; it does not yet compare images or select similar
ones.

## Scope

- CLI parser: `davo/services/photo/cli.py`
- Image-histogram implementation: a focused module under
  `davo/services/photo/`
- Tests: `tests/services/` and, where useful, `tests/test_cli.py`

## Implementation status

Implemented.

- `davo im fp IMAGE` is registered in the `im` command group.
- The command prints a compact histogram BLOB as hexadecimal text and a 64-bit
  pHash to stdout.
- Pillow applies EXIF orientation; landscape images are then rotated to
  portrait before the report is formed.
- Focused tests cover CLI wiring, compact histogram and pHash formatting,
  source modes, orientation, errors, and source-file immutability.

## Command contract

- Command name: `davo im fp`
- Usage: `davo im fp IMAGE`
- `IMAGE` is one required positional path to an image file.
- The command writes the histogram to stdout and does not create, modify, or
  delete any files.
- The command does not scan directories and has no recursive, commit, input
  flag, or output-file flags in the MVP.
- The command should use the existing Pillow and NumPy dependencies; do not add
  an image-processing dependency for this feature.

Examples:

```console
davo im fp photo.jpg
davo im fp /photos/photo.png
```

## Histogram semantics

- Decode the input with Pillow, apply its EXIF orientation, and rotate a
  landscape result by 90 degrees to bring it to portrait orientation before
  calculating the histogram. Leave portrait and square images unrotated.
- Normalize the resulting pixel data to `RGB` before calculating the
  histogram.
- Compute three independent 8-bit channel histograms: `red`, `green`, and
  `blue`; each initially contains 256 bins.
- Build the output vector by summing each consecutive group of eight source
  bins. This produces 32 bins per channel and 96 dimensions in total.
- Order dimensions as `red[0..31]`, `green[0..31]`, then `blue[0..31]`.
- Divide each grouped bin count by the image pixel count and by three, then
  take its square root. The resulting 96-dimensional vector has L2 norm `1`;
  L2 distance between two such vectors is suitable for histogram comparison.
- Quantize each component as
  `round(component * 65535 * sqrt(3))`. The 96 resulting values are unsigned
  16-bit integers and are the values emitted by the command. To store them in
  a database BLOB, pack them in this order as big-endian `uint16` values;
  this consumes exactly 192 bytes per image. Divide stored values by
  `65535 * sqrt(3)` before comparing them as the normalized vector.
- Ignore any alpha channel while calculating the MVP histogram.  For images
  with transparency, use their RGB colour values regardless of alpha.
- Palette, grayscale, CMYK, and other Pillow-supported source modes must be
  converted to RGB through Pillow's normal conversion path before counting.
- Do not resize, crop, apply colour-profile transforms, or otherwise alter
  pixel values in the MVP beyond the required orientation transformations.

These choices make the result directly comparable between images of the same
rendered RGB content while keeping the initial format simple. A later
comparison command may calculate a distance metric, but that is not part of
this feature.

## Output contract

- Write exactly three newline-terminated records, in this order:
  1. `size: <width>x<height>`
  2. `fingerprint_blob: <384 lowercase hexadecimal digits>`
  3. `phash: <16 lowercase hexadecimal digits>`
- `fingerprint_blob` and `phash` are lowercase ASCII and use the literal `: `
  separator shown above.
- Preserve all zero-valued dimensions and the required RGB/channel-bin order.
- `fingerprint_blob` is the 192-byte big-endian `uint16` sequence encoded as 384
  lowercase hexadecimal digits. `phash` represents the 64-bit hash in
  big-endian hexadecimal form and can be packed into eight bytes.
- Compute pHash from the same portrait-oriented image by converting it to
  grayscale, resizing it to `32x32`, applying a 2D DCT with NumPy, and
  thresholding the top-left `8x8` low-frequency coefficients against their
  median (excluding the DC coefficient).
- Do not print progress bars, success messages, labels beyond these three
  records, or diagnostic logging to stdout.  User-facing failures should go
  through the project's established CLI error handling (normally stderr).

For a one-pixel pure-red image, the decoded BLOB values at `red[31]`,
`green[0]`, and `blue[0]` are `65535`; every other value is zero.

## Expected behaviour and errors

- Validate that `IMAGE` exists and is a regular readable file before emitting
  histogram output.
- Reject directories, unreadable files, and files Pillow cannot identify as an
  image with a clear user-facing error and a non-zero exit status.
- Let Pillow fully load and orient the decoded image before producing output,
  so truncated or otherwise corrupt inputs do not cause partial histogram
  output.
- Support every image format that the installed Pillow build can decode;
  formats are not constrained by filename extension.
- Preserve the source image unchanged, including metadata and timestamps.

## Implementation notes

- Register `fp` in the `commands=(...)` list used by the `im` command
  group in `davo/cli.py` and add its parser branch in
  `davo/services/photo/cli.py`.
- Keep CLI wiring thin and put decoding/counting/formatting in a testable
  helper or dedicated histogram module.
- The implementation may use Pillow's `Image.histogram()` after orientation
  processing and explicit RGB conversion, provided the output contract and
  full-load error behaviour above are preserved.
- Use the project error type and output helpers consistently with neighboring
  photo commands.

## Verification

Add focused automated tests for:

- parser wiring: `davo im fp sample.png` resolves to a callable command
- a known small RGB fixture produces three records in the required order
- the histogram BLOB is exactly 192 bytes and decodes to 96 `uint16` values
- known pixels contribute to their correct grouped RGB bins
- every histogram value is within the `uint16` range
- pHash is deterministic and formatted as sixteen lowercase hexadecimal digits
- grayscale and palette fixtures are converted to the expected RGB counts
- RGBA input ignores alpha values
- an EXIF-rotated or landscape fixture is oriented to portrait before the
  result is formatted
- no source file is modified
- a missing path, a directory, a non-image file, and a corrupt image fail
  without writing a partial report to stdout

Manual spot check:

```console
davo im fp sample.jpg
```

Confirm that the command prints `size`, one 192-byte `fingerprint_blob` hex row,
and one pHash row, and that changing a pixel's colour changes the histogram.

## Out of scope

- Comparing two images or computing a similarity score
- Searching a directory for similar images
- Persisting histograms, JSON/CSV output, or an output-file option
- Grayscale, HSV, Lab, luminance, alpha, or multi-dimensional histograms
- Bin-count configuration or additional colour-management policy changes
