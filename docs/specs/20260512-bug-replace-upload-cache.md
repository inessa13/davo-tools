---
status: draft
type: bug
slug: replace-upload-cache
date: 2026-05-12
---

# Bug: s3sync replace-upload cache not updating

**Roadmap:** [Now → replace-upload cache](../roadmap.md#now)

## Summary

With **`--replace-upload`**, the local SQLite cache used by s3sync does not reflect the remote state as expected after a replace upload (stale or missing rows / metadata).

## Scope

- Code: `davo/services/s3sync/` — especially `tasks.py` (`ReplaceUpload`, `_upload` + `cache.cache.update`) and `cache.py`.
- CLI flag: `--replace-upload` (`davo/services/s3sync/cli.py`).

## Observed / expected

- **Observed (from backlog):** cache not updating correctly on replace-upload path.
- **Expected:** after a successful replace upload, cached `name`, `size`, `last_modified`, and `etag` match S3 (same rules as a normal upload path).

## Hypothesis (for implementation)

`ReplaceUpload` uses `self.data['key']` in `_upload` instead of a fresh key like `Upload`; post-upload **`key.etag`** / identity used in `cache.update` may be wrong or the row key may not match the DB row used for lookups. Confirm with a minimal repro (one object, `STATE_LOCAL_NEWER`, replace-upload) and inspect SQLite before/after.

## Verification

- Reproduce with a controlled bucket prefix; run `update` / `diff` (or equivalent) and assert cache rows match list head output.
- Add or extend automated tests if there is a test harness for s3sync tasks and cache (otherwise document manual steps in this spec until tests exist).

## Out of scope

- Unrelated s3sync flags or UI changes unless required to fix cache consistency.
