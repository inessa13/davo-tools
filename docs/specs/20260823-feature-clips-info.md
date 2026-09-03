---
status: implemented
type: feature
slug: clips-info
date: 2026-08-23
---

# Feature: add `davo vid info` command

## Summary

Add the readonly command `davo vid info [INPUT ...]`. It reads media metadata
with the existing `pymediainfo` dependency and never changes the source files.

Without inputs, the command scans sorted entries in the current directory.
Direct inputs retain their supplied order. It accepts files containing a Video
or Audio track; missing, unreadable, regular-file failures, and non-media
containers are skipped, with a warning only under `-v`.

## Output

The default report is a compact container summary with codec/profile, video
resolution/FPS/bitrate, audio bitrate/channels, and file size. It omits video
bit depth, color space, HDR, sample rate, and audio bit depth; duration is
rounded to the nearest second as `H:MM:SS` and FPS to one decimal place.
`-d/--detailed` restores those five columns and the full `H:MM:SS.mmm` duration
and FPS precision. Missing values are `-`; bitrate uses bps/kbps/Mbps/Gbps,
and file size uses the shared byte formatter. Multiple video or audio tracks
stay in MediaInfo order. When a file has more than one Video or Audio track,
its normal report also includes a formatted basic block for every such track.

`-t/--table` uses an ASCII table and `-c/--compact` hides paths and headers,
prefixing output with `NN/TT`. Compact table output combines rows into one
table. `--meta` appends all non-empty raw MediaInfo fields, sorted by name with
newline-safe values, directly after the corresponding file's summary. In table
mode, paths and metadata are full-width rows within one continuous ASCII table.
