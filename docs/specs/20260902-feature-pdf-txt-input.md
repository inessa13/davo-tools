---
status: implemented
slug: pdf-txt-input
---

# Feature: support TXT in PDF merge and form

`davo pdf merge` and `davo pdf form` accept `.txt` inputs, case-insensitively,
in addition to their existing source formats.

- Text is decoded in this order: UTF-8 with or without a BOM, then
  Windows-1251. Newlines are normalized, tabs become four spaces, blank lines
  remain, words wrap, and overlong uninterrupted text wraps hard.
- Text uses selectable Courier 10 pt with 1 cm margins and PyMuPDF's Unicode
  fallback. Characters unavailable to PDF text are rendered as `?`.
- `merge` inserts rendered TXT pages at their input position on A4 portrait
  sheets. It retains tolerant handling: unavailable or invalid TXT is skipped,
  with a verbose warning.
- `form` validates and decodes every TXT before opening its result document.
  TXT pages use the selected sheet size, including forced orientation;
  `--debug-fill` is behind text, while crop, DPI, and JPEG quality do not apply.
  `-R/--rename-processed` safely renames successful TXT sources to
  `*_processed.txt`.
