# Documentation (`docs/`)

Entry point for human-written docs in davo-tools. **Trust:** implementation wins on conflict; see root [`AGENTS.md`](../AGENTS.md) and [`docs/shared/docs/conventions/agent-policy.md`](shared/docs/conventions/agent-policy.md).

| Path | Role |
| --- | --- |
| [`roadmap.md`](roadmap.md) | Priority and sequencing (Now / Next / Later / Ideas); [process](shared/docs/conventions/roadmap-process.md). |
| [`specs/`](specs/) | Per-change specs (date, type, slug in filename). |
| [`shared/`](shared/) | Git submodule — **shared policies and conventions**; use for agent context and global rules. |
| `context/` | Reserved for per-module live notes (`docs-layout`); add `context/README.md` when the first file appears. |

Shared **documentation layout** vocabulary: [`docs/shared/docs/conventions/docs-layout.md`](shared/docs/conventions/docs-layout.md).

**Tests / lint** (from repository root, not under `docs/`): **`make venv`** installs **`.[test,lint]`** (uv when available, else venv + pip), then **`make test`** or **`make lint`**. Config: [`pyproject.toml`](../pyproject.toml). Details: root [`README.md`](../README.md).
