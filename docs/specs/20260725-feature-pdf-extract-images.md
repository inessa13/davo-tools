---
status: draft
type: feature
slug: pdf-extract-images
date: 2026-07-25
---

# Feature: add `davo pdf extract` command

**Roadmap:** [Now -> pdf extract images](../roadmap.md#now)

## Summary

Add a new `davo pdf extract` command that extracts embedded images from selected PDF pages into image files.

The command must support the same input/output/page flag family as sibling PDF commands, plus a new image type flag for selecting the output format.

## Scope

- CLI parser: `davo/services/photo/cli.py`
- CLI wrapper: `davo/services/photo/helpers.py`
- PDF implementation: `davo/services/photo/pdf.py`
- Tests: `tests/services/test_pdf.py`

## Command contract

- Command name: `davo pdf extract`
- Required input flag:
  - `-i` for the source PDF file
- Optional flags:
  - `-o` for the output path prefix or base name
  - `-p N1 N2 ... NX` for explicit source PDF page numbers to inspect
  - `-t`, `--type` for output image type
- Supported output types:
  - `jpg`
  - `png`
- No `davo file` alias is required for this command.

## Defaults

- `-o`, `-p`, and `-t` are optional.
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
- When `-p` is provided, inspect only the listed source pages for extraction.
- When `-p` is omitted, process the full document.

## Expected behavior

- Validate that the input exists and is a PDF before extraction starts.
- Reject unsupported output types with a clear error.
- Extract embedded images from the selected PDF pages; do not rasterize text-only pages into images.
- If a selected page contains one or more embedded images, extract those images.
- Preserve extraction order in the generated output files.
- Avoid silent overwrite of outputs by always emitting unique names via the required counter suffix.

## Verification

- Add or extend focused tests in `tests/services/test_pdf.py` for:
  - default scan of all pages
  - custom page selection
  - 1-based page selection semantics
  - default `jpg` output
  - `png` output via `-t` / `--type`
  - generated file naming with global zero-padded suffixes
  - multiple extracted images from a single page
  - invalid type rejection
- Manual spot check:
  - run `davo pdf extract -i sample.pdf`
  - run `davo pdf extract -i sample.pdf -p 1 3 -t png`
  - confirm files are emitted as `[orig_name]_[counter].[ext]`
  - confirm text-only pages are not rasterized into images

## Out of scope

- OCR or text extraction from PDFs
- Rendering text-only pages into raster images
- Additional image formats beyond `jpg` and `png`
- Changes to unrelated `davo file` or non-PDF commands
