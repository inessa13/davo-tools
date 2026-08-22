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

```bash
davo pdf form -4M file.jpg
davo pdf form -5 *.pdf
davo pdf form -s 21 29.7 -o result.pdf *.jpg
davo pdf form -4 --debug-fill file.jpg
davo pdf form -4 -R file.jpg
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
