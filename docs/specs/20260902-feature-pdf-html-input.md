---
status: implemented
slug: pdf-html-input
---

# Feature: support HTML in PDF merge and form

`davo pdf merge` and `davo pdf form` accept `.html` and `.htm` inputs,
case-insensitively. A locally installed Chrome or Chromium prints each source
as a temporary browser PDF with local resources enabled and no print headers
or footers. Browser-produced text, CSS, tables, and vector graphics are kept
as PDF content rather than rasterized.

- `merge` retains tolerant source handling: missing browser or render failures
  skip that HTML source, with a warning only in verbose mode. Each rendered
  page is fitted to an A4 portrait sheet at its original input position.
- `form` renders and validates every HTML source before it creates the output
  document. It then applies the normal PDF layout behaviour, including A4/A5/A6
  or custom size, forced orientation, percentage crop, and debug fill. Pixel
  crop is rejected; DPI and JPEG quality do not modify browser PDF content.
- With `-R/--rename-processed`, successful form output safely renames HTML to
  `*_processed.html` or `*_processed.htm` using the same checks as other input
  sources.
