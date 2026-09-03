---
status: implemented
slug: pdf-form
---

# Feature: add `davo pdf form`

`davo pdf form` combines PDF, JPEG, PNG, and BMP inputs into a new PDF whose
pages fit an explicitly requested A4, A5, A6, or centimetre-based paper size.

- One of `-4`, `-5`, `-6`, or `-s WIDTH HEIGHT` is required.
- Each source page selects portrait or landscape independently, keeps its
  aspect ratio, and is centered. PDF and DPI-tagged images are not enlarged
  unless `--crop` is used.
- `--crop TOP RIGHT BOTTOM LEFT` removes source edges before layout. Each
  value is a finite non-negative number with a `%` or `px` suffix; unitless
  `0` is also accepted. Percentages use the corresponding source axis, and
  units may be mixed. Pixel values refer to source-image pixels and therefore
  are supported for JPEG, PNG, and BMP only; PDF sources accept percentages
  only. The remaining width and height must both be non-zero. The cropped area
  is allowed to enlarge to fill the sheet by the normal fit layout.
- `--force-landscape` and `--force-portrait` are mutually exclusive and set
  every output sheet to that orientation without rotating source content.
- PDF source pages remain vector placements. JPEG, PNG, and BMP inputs are
  resized before insertion to no more than the selected DPI at their actual
  placed size; low-resolution inputs are never enlarged. JPEG quality defaults
  to 80 and can be set with `-q/--quality 0..100`; transparent PNGs retain
  their alpha channel.
- `-H`, `-Q`, `-M`, `-l`, and `-L` select 400, 300, 200, 150, and 96 DPI;
  `--dpi` accepts 72 through 800 and defaults to 300.
- `--debug-fill` fills each output page with magenta before placing its source,
  making page margins and transparent PNG areas visible.
- The default output is `[first-input]_formed.pdf`. Existing outputs need
  `-W/--rewrite`; output may never be an input file.
- `-R/--rename-processed` renames each unique input to add `_processed` before
  its extension only after the output PDF has been saved. Existing processed
  names, already processed inputs, and output-name conflicts are rejected.
- All inputs are validated before the result document is created.

Examples:

```bash
davo pdf form -4M file.jpg
davo pdf form -5 *.pdf
davo pdf form -s 21 29.7 -o result.pdf *.jpg
davo pdf form -4 --debug-fill file.jpg
davo pdf form -4 -R file.jpg
davo pdf form -4 --force-portrait file.jpg
davo pdf form -4 --crop 5% 20px 5% 20px file.jpg
```
