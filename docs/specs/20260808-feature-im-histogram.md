---
status: implemented
type: feature
slug: im-histogram
date: 2026-08-08
---

# Feature: add `davo im histogram` command

**Roadmap:** implemented and removed from the active roadmap.

## Summary

Add a readonly `davo im histogram` command that calculates an image colour
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

- `davo im histogram IMAGE` is registered in the `im` command group.
- The command prints a four-line, normalized RGB histogram report to stdout.
- Pillow applies EXIF orientation; landscape images are then rotated to
  portrait before the report is formed.
- Focused tests cover CLI wiring, histogram values and formatting, source
  modes, orientation, errors, and source-file immutability.

## Command contract

- Command name: `davo im histogram`
- Usage: `davo im histogram IMAGE`
- `IMAGE` is one required positional path to an image file.
- The command writes the histogram to stdout and does not create, modify, or
  delete any files.
- The command does not scan directories and has no recursive, commit, input
  flag, or output-file flags in the MVP.
- The command should use Pillow, which is already the image backend used by
  this project, rather than adding an image-processing dependency.

Examples:

```console
davo im histogram photo.jpg
davo im histogram /photos/photo.png
```

## Histogram semantics

- Decode the input with Pillow, apply its EXIF orientation, and rotate a
  landscape result by 90 degrees to bring it to portrait orientation before
  calculating the histogram. Leave portrait and square images unrotated.
- Normalize the resulting pixel data to `RGB` before calculating the
  histogram.
- Compute three independent 8-bit channel histograms: `red`, `green`, and
  `blue`.
- Each channel has exactly 256 bins.  Bin `N` (`0` through `255`) contains the
  count of pixels whose corresponding normalized RGB channel value is `N`.
- Normalize every bin count by the total number of pixels. Each emitted value
  is therefore a number in the inclusive range `0` through `1`, and the 256
  values of each channel sum to `1` before output rounding. This makes
  histograms from images of different dimensions directly comparable.
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

- Write exactly four newline-terminated records, in this order:
  1. `size: <width>x<height>`
  2. `red: <256 space-separated normalized values>`
  3. `green: <256 space-separated normalized values>`
  4. `blue: <256 space-separated normalized values>`
- Channel names are lowercase ASCII and use the literal `: ` separator shown
  above.
- Bin order is ascending from `0` to `255`; do not omit zero-valued bins.
- Format every normalized value in fixed-point decimal notation with ten digits
  after the decimal separator, using `.` regardless of locale. For example,
  zero is `0.0000000000` and one is `1.0000000000`.
- Do not print progress bars, success messages, labels beyond these four
  records, or diagnostic logging to stdout.  User-facing failures should go
  through the project's established CLI error handling (normally stderr).

For a one-pixel pure-red image, the channel records therefore have these
non-zero bins: `red[255] = 1.0000000000`,
`green[0] = 1.0000000000`, and `blue[0] = 1.0000000000`.

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

- Register `histogram` in the `commands=(...)` list used by the `im` command
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

- parser wiring: `davo im histogram sample.png` resolves to a callable command
- a known small RGB fixture produces four records in the required order
- every channel emits exactly 256 normalized bins, including zero-valued bins
- known pixels are counted in their correct RGB bins
- the per-channel values sum to `1` before output rounding
- grayscale and palette fixtures are converted to the expected RGB counts
- RGBA input ignores alpha values
- an EXIF-rotated or landscape fixture is oriented to portrait before the
  result is formatted
- no source file is modified
- a missing path, a directory, a non-image file, and a corrupt image fail
  without writing a partial report to stdout

Manual spot check:

```console
davo im histogram sample.jpg
```

Confirm that the command prints `size` and three 256-bin channel rows, and
that changing a pixel's colour changes the corresponding channel bins.

## Out of scope

- Comparing two images or computing a similarity score
- Searching a directory for similar images
- Persisting histograms, JSON/CSV output, or an output-file option
- Grayscale, HSV, Lab, luminance, alpha, or multi-dimensional histograms
- Bin-count configuration, resizing, perceptual hashing, or additional
  colour-management policy changes
