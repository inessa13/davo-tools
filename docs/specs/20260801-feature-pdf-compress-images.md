---
status: implemented
type: feature
slug: pdf-compress-images
date: 2026-08-01
---

# Feature: add `davo pdf compress` command

**Roadmap:** implemented and removed from the active roadmap.

**Note:** this spec was written after the fact, following the initial MVP implementation.

## Summary

Add `davo pdf compress` for reducing PDF file size by downsampling embedded
images to a target DPI preset while preserving text and vector content where
possible.

The MVP supports `200`, `300`, and `400 DPI` presets and intentionally avoids
full-page rasterization.

## Scope

- CLI parser: `davo/services/photo/cli.py`
- CLI wrapper: `davo/services/photo/helpers.py`
- PDF implementation: `davo/services/photo/pdf.py`
- Tests: `tests/services/test_pdf.py`

## Current MVP contract

- Command name: `davo pdf compress`
- Required input flag:
  - `-i` for the source PDF file
- Optional flags:
  - `-o` for the output PDF path
  - `--dpi` for the target embedded image DPI preset
  - `--quality` for explicit JPEG recompression quality (`0..100`)
  - `--grayscale` to convert the output document to grayscale before image rewriting
- Supported DPI presets:
  - `200`
  - `300`
  - `400`
- Default DPI preset:
  - `300`
- Default JPEG quality:
  - `75`
- No `davo file` / `davo-photo` alias is required for the MVP.

## Output behavior

- If `-o` is omitted, derive the output file name from the source PDF file name.
- The default file naming pattern is:
  - `[orig_name]_compressed_[dpi]dpi.pdf`
- The command writes a new output PDF and does not modify the source file in
  place.
- CLI output should report the input size, output size, and resulting
  compression ratio after a successful run.

## Expected behavior

- Validate that the input exists and is a PDF before compression starts.
- Rewrite embedded images only; do not rasterize full pages in the MVP.
- Preserve text and vector content where the PDF structure allows it.
- When `--grayscale` is enabled, grayscale conversion applies to the output
  document before image rewriting.
- Compress image-heavy / scanned PDFs more effectively than text-first or
  vector-heavy PDFs.
- Accept that some PDFs may shrink only slightly if most of their size does not
  come from embedded images.

## Verification

- Focused automated tests should cover:
  - preset mapping to the image rewrite call
  - custom quality override
  - grayscale mode
  - default output naming when `-o` is omitted
  - invalid / missing input handling
  - output save behavior
  - size report logging
- Manual spot check:
  - run `davo pdf compress -i sample.pdf`
  - run `davo pdf compress -i sample.pdf --dpi 200`
  - run `davo pdf compress -i sample.pdf --quality 55`
  - run `davo pdf compress -i sample.pdf --grayscale`
  - run `davo pdf compress -i sample.pdf --dpi 400 -o sample-small.pdf`
  - confirm text remains selectable on text-based PDFs
  - compare output size for scanned vs text-first PDFs

## Out of scope

- Full-page rasterization as the default compression strategy
- OCR or text extraction
- Automatic target file size tuning
- Non-PDF command changes unrelated to PDF compression
