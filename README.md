# davo-tools

Personal CLI utilities (`davo`, `cit`, `davo-photo`, `davo-s3sync`). Package metadata, dependencies, scripts, and tool config live in **`pyproject.toml`**.

## Installation

Requires Python 3.11.

Basic installation, without deps for keepass and other optional and heavy deps

```bash
uv tool install "davo-tools @ https://github.com/inessa13/davo-tools/archive/refs/heads/master.tar.gz"
```

Full installation with all functional deps (except dev deps)

```bash
sudo apt get install libxml2 libxslt
uv tool install "davo-tools[full] @ https://github.com/inessa13/davo-tools/archive/refs/heads/master.tar.gz"
```

## Development

Use a **virtual environment** so tests and editable install do not touch system Python.

Recommended: **[uv](https://docs.astral.sh/uv/getting-started/installation/)** (fast resolver and installs). `make venv` uses **`uv venv`** + **`uv pip install -e ".[test,lint]"`** when `uv` is on your `PATH`; otherwise it falls back to **`python3 -m venv`** and pip.

```bash
make              # or: make help — lists targets
make venv         # .venv + editable install with test + lint extras
make test         # pytest, uses .venv/bin/python when present
make test-lib     # pytest for configured supported python versions
make coverage     # pytest + coverage for davo/ (report in terminal + htmlcov/)
make lint         # ruff, isort (check-only), pylint
```

With an activated venv: `source .venv/bin/activate`, then `make test` or `python -m pytest`.

## PDF page formatting

`davo pdf form` creates a PDF from PDF, JPEG, PNG, and BMP inputs, fitting each
page onto the requested paper size without cropping.  A source page's
orientation is preserved; use `-W` to replace an existing output file.
Use `--force-landscape` or `--force-portrait` to use that orientation for
every output sheet. These mutually exclusive flags do not rotate source
content.

```bash
davo pdf form -4M file.jpg
davo pdf form -5 *.pdf
davo pdf form -s 21 29.7 -o result.pdf *.jpg
davo pdf form -4 --debug-fill file.jpg
davo pdf form -4 -R file.jpg
davo pdf form -4 --force-landscape file.jpg
```

The image-DPI presets are `-H` (400), `-Q` (300), `-M` (200), `-l` (150), and
`-L` (96); `--dpi N` accepts values from 72 to 800. Raster inputs are reduced
to that DPI at their placed size (never enlarged); `-q/--quality 0..100`
controls JPEG quality and defaults to 80.
Use `--debug-fill` to fill each output page with magenta before source content
is placed, making margins and transparent PNG areas visible.
Use `-R/--rename-processed` to rename every unique source after the PDF is
successfully saved, for example `file.jpg` to `file_processed.jpg`. Inputs
already marked this way, existing processed targets, and processed targets that
would conflict with the output PDF are rejected before creating the PDF.

## Image merging

`davo im merge` places image files in the supplied order without resizing or
rotating them. Choose exactly one direction: `-V` for a vertical stack or `-H`
for a horizontal row. Smaller images are centred in the unused cross-axis area.

```bash
davo im merge -V first.png second.png
davo im merge -H -o panorama.jpg left.jpg right.jpg
davo im merge -V --debug-fill -o review.png *.png
davo im merge -V -S screenshot-1.png screenshot-2.png
```

Without `-o`, the output is named from the first input (for example,
`first_merged.png`). `--debug-fill` paints unused and transparent areas
magenta. `-S/--smart` detects a strong edge overlap between each adjacent
pair, allowing a small sideways shift and a uniform scale difference of up to
10%. It preserves all outer edges on a transparently padded canvas (or a white
one for JPEG output).

## Image metadata

`davo im info` reads image metadata without changing the source files. It
accepts one or more direct image paths in the supplied order.
Without paths, it inspects the current directory as if `*` had been passed.

```bash
davo im info photo.jpg
davo im info -e photo.jpg                 # Date and Camera columns
davo im info --exif-full photo.jpg        # all readable EXIF tags
```

## Media metadata

`davo clips info` reads video and audio container metadata without changing the
source file. By default its compact summary shows practical codec, bitrate, and
quality information; duration is rounded to seconds and FPS to one decimal.
`-d/--detailed` restores all quality columns and full duration/FPS precision.
`--meta` prints every non-empty raw MediaInfo field. For files with multiple
video or audio tracks, the normal report also prints a basic block for each
track.

```bash
davo clips info movie.mp4
davo clips info --detailed movie.mp4
davo clips info --meta movie.mp4
```
