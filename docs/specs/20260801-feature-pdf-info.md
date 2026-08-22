---
status: draft
type: feature
slug: pdf-info
date: 2026-08-01
---

# Feature: add `davo pdf info` command

## Summary

Add a new readonly `davo pdf info` command that prints one metadata row per
selected PDF page.

The command should report page type, effective raster resolution, orientation,
and page size without writing a new PDF file.

## Scope

- CLI parser: `davo/services/photo/cli.py`
- CLI wrapper: `davo/services/photo/helpers.py`
- PDF inspection implementation: `davo/services/photo/pdf.py`
- Tests: `tests/services/test_pdf.py`

## Command contract

- Command name: `davo pdf info`
- Optional positional arguments:
  - `INPUT [INPUT ...]` for source PDF files. With no inputs, inspect the
    current directory contents as if `*` had been passed.
- Optional flags:
  - `-p N1 N2 ... NX` for explicit source PDF page numbers to inspect
  - `--pt` to show non-standard page sizes in points instead of millimetres
  - `-t` / `--table` for an ASCII-table rendering
  - `-v` / `--verbose` for warnings consistent with sibling PDF commands
- No output file flag in the MVP; the command writes the report to stdout only.
- No `davo file pdf-info` alias is required for the MVP.

## Output contract

- Emit one header row followed by one row per selected page.
- Columns for the MVP:
  - `Page`
  - `Type`
  - `Resolution`
  - `ImageSizePx`
  - `Orientation`
  - `PageSize`
- Page numbering in output is 1-based.
- `Resolution` is formatted as `<DPI> dpi` when rounded horizontal and
  vertical DPI match, otherwise `<XDPI>x<YDPI> dpi`.
- For pages with no raster content, `Resolution` should render as `-`.
- `PageSize` defaults to millimetres, such as `210x297 mm`; `--pt` switches
  non-standard sizes to points. ISO A3, A4, A5, and A6 pages (in either
  orientation and within 1 mm on each side) render as `a3`, `a4`, `a5`, or
  `a6`, including with `--pt`.
- Without `--table`, use the aligned text report. With it, use the project's
  bordered ASCII table style.
- The report itself is the primary success output; avoid adding a synthetic
  per-file success line after the table in the MVP.

## Page type classification

Use a deterministic heuristic based on content detected by PyMuPDF.

- `text`:
  - page has extractable text
  - page has no raster images
  - page has no vector drawing paths
- `vector`:
  - page has vector drawing paths
  - page has no raster images
  - page has no extractable text
- `raster`:
  - page has raster images
  - page has no extractable text
  - page has no vector drawing paths
  - the page contains exactly one displayed raster placement
  - the dominant raster placement covers most of the page area
- `multi-raster`:
  - page has multiple displayed raster placements
  - page has no extractable text
  - page has no vector drawing paths
- `empty`:
  - page has no extractable text
  - page has no raster images
  - page has no vector drawing paths
- `mixed`:
  - any combination of text + vector, text + raster, vector + raster,
    text + multi-raster, vector + multi-raster, or any other combination

For the MVP, define "covers most of the page area" as a configurable internal
threshold, defaulting to about `90%` of visible page area.

## Resolution semantics

Because PDF pages do not have a single intrinsic DPI, the command should derive
effective raster DPI from placed image content.

- Inspect displayed raster images on the page.
- For each displayed raster image, compute effective DPI from:
  - image pixel width / visible displayed width in inches
  - image pixel height / visible displayed height in inches
- Use the final visible placement bbox after page transforms, rotation, and
  clipping, not the source image's nominal size.
- Treat each displayed placement independently even when the same embedded image
  object is reused multiple times on the page.
- Choose the page-level DPI pair from the dominant raster placement, where
  "dominant" means the displayed raster with the largest area on the page.
- If a page has multiple raster images, classify the page as `multi-raster`
  and still emit a single DPI pair using the dominant placement.
- If a page has no displayed raster images, emit `-` for resolution.
- Do not use full-page render DPI as the reported page resolution in the MVP.

## Orientation semantics

- Derive orientation from the effective page rectangle after page rotation is
  applied.
- Output values:
  - `portrait` when height > width
  - `landscape` when width > height
  - `square` when width and height are effectively equal

## Expected behavior

- Validate that the input exists and is a PDF before inspection starts.
- Reuse the existing 1-based `-p` page selection style used by sibling commands
  such as `extract`, `delete`, and `split`.
- When `-p` is omitted, inspect the full document.
- Preserve requested page order in the output.
- Avoid partial or ambiguous output for invalid inputs.
- Keep the implementation readonly; do not modify the source document.
- Reuse existing PDF utilities in `davo/services/photo/pdf.py`, especially the
  current PyMuPDF import / open / validation path, rather than introducing a
  second PDF backend.

## Verification

- Focused automated tests should cover:
  - CLI wiring for `davo pdf info`
  - default full-document inspection
  - custom page selection and 1-based semantics
  - output row order matching selected page order
  - `text` classification
  - `vector` classification
  - `raster` classification
  - `multi-raster` classification
  - `empty` classification
  - `mixed` classification
  - dominant-image DPI selection for pages with multiple raster images
  - `-` resolution for non-raster pages
  - orientation derivation for portrait and landscape pages
  - page size formatting
  - missing / non-PDF input handling
- Manual spot check:
  - run `davo pdf info sample.pdf`
  - run `davo pdf info sample.pdf -p 1 3`
  - confirm scanned pages report non-empty DPI values
  - confirm text-first pages report `Type=text` and `Resolution=-`
  - confirm pages with several raster images report `Type=multi-raster`
  - confirm blank pages report `Type=empty`
  - confirm mixed pages with text + image report `Type=mixed`

## Out of scope

- JSON / CSV output formats
- OCR or semantic content understanding beyond extractable text
- Multiple DPI ranges per page
- Paper name detection such as `A4` / `Letter`
- A `davo file` alias for the command in the MVP
