---
status: draft
type: bug
slug: s3-file-path-remote-empty
date: 2026-05-13
---

# Bug: `davo s3 diff/update` with single file path sees zero remote objects

**Roadmap:** [Now -> s3 single-file path remote scan](../roadmap.md#now)

## Summary

When `davo s3 diff` or `davo s3 update` is run with a path to a specific local file (not a directory), local scan finds the file, but remote scan returns `0 remote objects` (from cache), so the file is treated as `LOCAL_NEW`.

## Scope

- `davo/services/s3sync/handlers.py` (`on_diff`, `on_update`)
- `davo/services/s3sync/utils.py` (`iter_remote_path`, `file_path_info`)
- `davo/services/s3sync/cache.py` (`Cache.select`)

## Observed / expected

- **Observed (reproduced on 2026-05-13):**
  - `cd /media/data/arch && davo s3 diff ./AGENTS.md`
  - Output includes:
    - `1 local objects`
    - `0 remote objects, using cache`
    - `+ AGENTS.md`
- **Observed (safe-check assumption was false):**
  - `cd /media/data/arch && davo s3 update -qU ./AGENTS.md`
  - Same `0 remote objects, using cache`, then upload was executed (`uploaded AGENTS.md`).
- **Expected:**
  - For a file path, remote lookup must include the exact object key (`AGENTS.md`) and compare it against local.
  - If remote object exists, state must be `=` / replace candidate, not always `LOCAL_NEW`.

## Hypothesis (for implementation)

`Cache.select(prefix=...)` currently filters with `name like "{prefix}/%"`, which excludes exact key matches (`name == prefix`) and only keeps children under `prefix/`. For a direct file key lookup, this yields zero rows from cache even when the object exists.

Secondary check to confirm during fix:

- Behavior parity between cached and non-cached remote iteration for exact file path.
- No regressions for directory prefix scans (`prefix/` semantics).

## Verification

- Manual reproduction:
  - `cd /media/data/arch && davo s3 diff ./AGENTS.md` should no longer report `0 remote objects` when key exists remotely.
- Add/extend automated tests:
  - Unit test for `Cache.select(prefix=<exact_file_key>)` returns exact record.
  - Test for directory prefix (`prefix=<dir>`) still returns nested records as before.
  - Optional integration test: `on_diff` with file path against prepared cache entry.

## Risks

- Changing cache prefix filtering can affect directory scans and delimiter/depth behavior.
- Incorrect fix can increase false positives in remote sets for sibling keys with common prefixes.

## Out of scope

- New CLI flags or UX changes for `s3 diff` / `s3 update`.
- Any behavior changes unrelated to exact-file remote matching.
