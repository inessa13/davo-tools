---
status: implemented
type: feature
slug: pdf-extract-images
date: 2026-07-25
---

# Feature: add `davo pdf extract` command

**Roadmap:** implemented and removed from the active roadmap.

## Summary

Add a new `davo pdf extract` command that extracts embedded images from selected PDF pages into image files.

The command must support the same input/output/page flag family as sibling PDF commands, plus a new image type flag for selecting the output format and a mode flag for whole-page conversion.

## Scope

- CLI parser: `davo/services/photo/cli.py`
- CLI wrapper: `davo/services/photo/helpers.py`
- PDF implementation: `davo/services/photo/pdf.py`
- Tests: `tests/services/test_pdf.py`

## Implementation status

Implemented.

- `davo pdf extract` is wired in the CLI parser.
- Default mode extracts embedded images from selected PDF pages.
- `-w` / `--whole-page` renders one output image per selected page.
- Whole-page rendering uses `300 DPI`.
- Focused unit tests cover the command contract and naming behavior.

## Command contract

- Command name: `davo pdf extract`
- Required input flag:
  - `-i` for the source PDF file
- Optional flags:
  - `-o` for the output path prefix or base name
  - `-p N1 N2 ... NX` for explicit source PDF page numbers to inspect
  - `-t`, `--type` for output image type
  - `-w`, `--whole-page` to convert each selected source page into one output image
- Supported output types:
  - `jpg`
  - `png`
- No `davo file` alias is required for this command.

## Defaults

- `-o`, `-p`, and `-t` are optional.
- `-w` is optional and disabled by default.
- If `-o` is omitted, derive the base output name from the source PDF file name.
- If `-t` is omitted, default to `jpg`.
- If `-p` is omitted, extract all pages.

## Output naming

- `-o` may be an absolute path or a path relative to the current working directory.
- `-o` defines the output prefix / stem for generated files; the final extension is controlled by `-t`.
- Each extracted image must be written as a separate file.
- Use the file naming pattern `[orig_name]_[counter].[ext]`.
- `orig_name` is the input file stem unless overridden by `-o`.
- `counter` is a global extraction counter, not a source page number.
- `counter` must be zero-padded to at least three digits: `001`, `002`, `003`, ...
- Multiple extracted images from the same page still use the same global counter sequence in extraction order.
- `ext` must match the selected image type (`jpg` or `png`).

## Page selection

- Reuse the existing `-p` / `--pages` style used by sibling PDF commands.
- `-p N1 N2 ... NX` refers to source PDF page numbers.
- Page numbering is 1-based.
- When `-p` is provided, inspect only the listed source pages.
- When `-p` is omitted, process the full document.

## Modes

- Default mode:
  - inspect selected pages and extract embedded images only
- Whole-page mode:
  - when `-w` / `--whole-page` is enabled, convert each selected source page into a single output image
  - this mode renders the full page, including text and non-image content
  - whole-page rendering uses `300 DPI`
  - output count in this mode is one file per selected page

## Expected behavior

- Validate that the input exists and is a PDF before extraction starts.
- Reject unsupported output types with a clear error.
- In default mode, extract embedded images from the selected PDF pages; do not rasterize text-only pages into images.
- If a selected page contains one or more embedded images, extract those images.
- In whole-page mode, render the entire selected page into a single output image even if the page contains only text.
- In whole-page mode, request `300 DPI` rendering for the page rasterization step.
- Preserve extraction order in the generated output files.
- Avoid silent overwrite of outputs by always emitting unique names via the required counter suffix.

## Verification

- Add or extend focused tests in `tests/services/test_pdf.py` for:
  - default scan of all pages
  - custom page selection
  - 1-based page selection semantics
  - default `jpg` output
  - `png` output via `-t` / `--type`
  - whole-page mode via `-w` / `--whole-page`
  - `300 DPI` rendering in whole-page mode
  - one output per selected page in whole-page mode
  - generated file naming with global zero-padded suffixes
  - multiple extracted images from a single page
  - invalid type rejection
- Manual spot check:
  - run `davo pdf extract -i sample.pdf`
  - run `davo pdf extract -i sample.pdf -p 1 3 -t png`
  - run `davo pdf extract -i sample.pdf -p 1 3 -t png -w`
  - confirm files are emitted as `[orig_name]_[counter].[ext]`
  - confirm text-only pages are not rasterized into images in default mode
  - confirm whole-page mode emits exactly one image per selected page

## Out of scope

- OCR or text extraction from PDFs
- Additional image formats beyond `jpg` and `png`
- Changes to unrelated `davo file` or non-PDF commands
