---
status: implemented
type: feature
slug: im-diff
date: 2026-08-09
---

# Feature: add `davo im diff` command

**Roadmap:** implemented and removed from the active roadmap.

## Summary

Add a readonly command for comparing every unique pair of supplied images:

```console
davo im diff IMAGE1 IMAGE2 [IMAGE3 ...]
```

It calculates each image's existing 96-dimensional normalized fingerprint and
64-bit pHash directly from the supplied files, then reports percentage-based
distance metrics and a similarity status for every pair.

## Command contract

- `IMAGE` is a positional argument accepting one or more paths; fewer than two
  images produce a user-facing error.
- All files are decoded and validated before any report is written. A missing,
  directory, or corrupt input therefore produces no partial stdout report.
- Each input image is decoded once while its vector and pHash are calculated.
- The command does not read stored database BLOBs and does not modify source
  files.
- Pairs are emitted in positional-argument order: `(0,1)`, `(0,2)`, …,
  `(N-2,N-1)`.

## Output contract

Output is tab-separated and begins with exactly this header:

```text
left	right	l2_percent	phash_percent	status
```

Each following row contains the two supplied paths, `l2_percent` and
`phash_percent` formatted with two digits after the decimal point, and a
similarity `status`.

- `l2_percent = l2 / sqrt(2) * 100`, where raw L2 is in `0..sqrt(2)`.
- `phash_percent = phash_hamming / 64 * 100`, where pHash Hamming distance is
  in `0..64`.
- The status uses the unrounded average of those percentages: `identical` for
  exactly `0%`, `duplicate` below `1%`, `similar` below `10%`, `differ` below
  `25%`, and `different` otherwise.

## Implementation status

Implemented.

- Registered `diff` in the `davo im` command group.
- Reused the fingerprint module's portrait/RGB normalization and feature
  algorithms with one image decode per input.
- Added tests for parser wiring, identical images, pair order, both metrics,
  invalid inputs without partial output, and source immutability.
