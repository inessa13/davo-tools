# AGENTS.md — davo-tools

Instructions for coding agents working in this repository.

## How to build context (shared policies)

**Shared policies, conventions, and agent playbooks live in the git submodule at `docs/shared`.** They are the canonical source for cross-project rules. Do **not** paraphrase or copy long policy text into this file; read the linked documents when you need that context.

1. Open the index in the submodule: [`docs/shared/AGENTS.md`](docs/shared/AGENTS.md) — it lists the canonical documents (agent policy, workflow, Python style, architecture, playbooks, and so on).
2. Follow the table there and pull in only what is relevant to the current task (trust order, execution rules, style, playbooks).
3. If `docs/shared` is missing, run from the repo root: `git submodule update --init --recursive`.

Treat implementation in this repo (`pyproject.toml`, `davo/`, `tests/`, CI) as the source of truth for behaviour; shared markdown is secondary per [`docs/shared/docs/conventions/agent-policy.md`](docs/shared/docs/conventions/agent-policy.md).

## Project overlay (davo-tools–specific)

| Item | Location / note |
| --- | --- |
| Roadmap (read first for planned work) | [`docs/roadmap.md`](docs/roadmap.md); lifecycle in [`docs/shared/docs/conventions/roadmap-process.md`](docs/shared/docs/conventions/roadmap-process.md) |
| Specs | [`docs/specs/`](docs/specs/) |
| Package | `davo` (declared in [`pyproject.toml`](pyproject.toml) → `[project]` / `[tool.setuptools.packages.find]`) |
| CLI entry | `davo.cli:main` → `[project.scripts]` `davo` in [`pyproject.toml`](pyproject.toml) |
| Other console scripts | `cit`, `davo-photo`, `davo-s3sync` — see `[project.scripts]` in [`pyproject.toml`](pyproject.toml) |
| Tests | `tests/` — **`make venv`** (prefers **uv**, else `python3 -m venv`) installs **`.[test,lint]`**, then **`make test`**. Pytest: `pyproject.toml` → `[tool.pytest.ini_options]`. |
| Lint | **`make lint`** — `ruff check`, `isort --check-only`, `pylint davo`. Settings in `pyproject.toml`. |
| Dependencies | [`pyproject.toml`](pyproject.toml) → `[project.dependencies]`; optional **`[project.optional-dependencies]`** groups **`test`**, **`lint`** |

When changing behaviour or public CLI, align with existing patterns under `davo/services/` and `davo/utils/`.
