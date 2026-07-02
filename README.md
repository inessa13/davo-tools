# davo-tools

Personal CLI utilities (`davo`, `cit`, `davo-photo`, `davo-s3sync`). Package metadata, dependencies, scripts, and tool config live in **`pyproject.toml`**.

## Installation

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
make test         # same as: make tests; uses .venv/bin/python when present
make coverage     # pytest + coverage for davo/ (report in terminal + htmlcov/)
make lint         # ruff, isort (check-only), pylint
```

With an activated venv: `source .venv/bin/activate`, then `make test` or `python -m pytest`.

Equivalent without Make (requires [uv](https://docs.astral.sh/uv/)):

```bash
uv venv && uv pip install -e ".[test,lint]"
```

Install only into an existing venv: `pip install -e ".[test,lint]"` or `uv pip install -e ".[test,lint]"`.

Lint and test configuration live in **`pyproject.toml`** (`[tool.ruff]`, `[tool.isort]`, `[tool.pylint.*]`, `[tool.pytest.ini_options]`).
