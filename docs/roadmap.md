# Roadmap

Single index of **order and priority** for davo-tools. Process: [`docs/shared/docs/conventions/roadmap-process.md`](../shared/docs/conventions/roadmap-process.md) (submodule). **Closed work is removed** from this file — history is in git.

## Now

- [Bug: s3sync replace-upload cache not updating](specs/20260512-bug-replace-upload-cache.md) — `davo/services/s3sync/`
- [photo/helpers] Implement copy behavior when `file_path == file_path_new` in convert flow (`davo/services/photo/helpers.py:508`)

## Next

- [utils/path] Add missing filters support in `iter_file_options` (`davo/utils/path.py:116`)
- [photo/recover] Tune `epsilon` for `cv2.approxPolyDP` (`davo/services/photo/recover.py:156`)
- [photo/cv3] Add dedicated noisy high-contrast receipt/check pipeline (`davo/services/photo/cv3/pipelines.py:285`)
- [photo/replace-classes] Add `[date:<class>]` replacement class support (`davo/services/photo/replace_classes.py:549`)

## Later

- [s3sync] Windows-safe path normalization in `file_path_info` (`davo/services/s3sync/utils.py:52`)
- [utils/path] Windows-safe root handling in `find_config_root` (`davo/utils/path.py:469`)

## Ideas

Flat capture list — no inner ranking. When an idea ripens, add a dated spec under `docs/specs/` and move the line into **Now** / **Next** / **Later** with a link.

_(none)_
