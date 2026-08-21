---
status: implemented
slug: pdf-form
---

# Feature: add `davo pdf form`

`davo pdf form` combines PDF, JPEG, PNG, and BMP inputs into a new PDF whose
pages fit an explicitly requested A4, A5, A6, or centimetre-based paper size.

- One of `-4`, `-5`, `-6`, or `-s WIDTH HEIGHT` is required.
- Each source page selects portrait or landscape independently, keeps its
  aspect ratio, is centered, and is never cropped. PDF and DPI-tagged images
  are not enlarged.
- PDF source pages remain vector placements. Embedded rasters above the chosen
  target DPI are downsampled with JPEG quality 80.
- `-H`, `-Q`, `-M`, `-l`, and `-L` select 400, 300, 200, 150, and 96 DPI;
  `--dpi` accepts 72 through 800 and defaults to 300.
- The default output is `[first-input]_formed.pdf`. Existing outputs need
  `-W/--rewrite`; output may never be an input file.
- All inputs are validated before the result document is created.

Examples:

```bash
davo pdf form -4M file.jpg
davo pdf form -5 *.pdf
davo pdf form -s 21 29.7 -o result.pdf *.jpg
```
