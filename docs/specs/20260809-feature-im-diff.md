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
davo im diff [-r|--recursive] [-t|--table] [-a|--all] PATH1 PATH2 [PATH3 ...]
```

It calculates each image's existing 96-dimensional normalized fingerprint and
64-bit pHash directly from the supplied files, then reports percentage-based
distance metrics and a similarity status for every pair.

## Command contract

- `PATH` is a positional argument accepting files and directories. Directories
  contribute their immediate files by default; `-r` / `--recursive` includes
  all nested files. Directory results are sorted for deterministic output.
- A direct file is decoded and validated strictly. A missing, non-regular, or
  corrupt direct file produces no partial stdout report. Files encountered
  while expanding a directory that Pillow cannot decode are skipped.
- Fewer than two resolved images produce a user-facing error without stdout.
- Each accepted image is decoded once while its vector and pHash are
  calculated.
- The command does not read stored database BLOBs and does not modify source
  files.
- Inputs are expanded in positional-argument order. Duplicate physical files
  from overlapping paths are kept only once, using their first written path in
  the report. Pairs are emitted in that order: `(0,1)`, `(0,2)`, …,
  `(N-2,N-1)`.

## Interactive progress

When `stderr` is a terminal, the command shows two dynamic 40-character
progress bars on `stderr`: `files` while every expanded input candidate is
processed, then `pairs` while all unique image pairs are calculated. Each bar
shows its percentage and `ready/total` count, clears its current line, and
ends with a newline. The `files` bar additionally shows elapsed processing
time, the average processed-byte rate, and the current candidate path. Paths
from a directory are relative to that directory; direct file arguments retain
their supplied path. Its timer starts immediately before the first candidate,
and its average includes completed candidates with an available size (including
duplicates and unsuitable directory entries). Before a measurable result, the
rate is `0 Bps`. The `pairs` bar remains limited to its count and percentage.
The `files` count includes duplicate and unsuitable files encountered while
expanding directories; the `pairs` count is `N × (N − 1) / 2` for the
successfully resolved images.

No progress is written when `stderr` is not a TTY. Consequently, the report on
`stdout` remains suitable for pipes and redirection.

## Output contract

By default, output is tab-separated and begins with exactly this header:

```text
left	right	l2_percent	phash_percent	status
```

Each following row contains the two supplied paths with their portrait-oriented
pixel dimensions and humanized file size (for example, `path.jpg 1600*2000
2.1Mb`), `l2_percent` and `phash_percent` formatted with two digits after the
decimal point, and a similarity `status`. By default, pairs whose status is
`different` are hidden;
`-a` / `--all` includes them. If only one pair was calculated, it is always
shown regardless of its status or this flag. All pairs are still calculated
before output.

`-t` / `--table` prints the same report as a readable ASCII table. Its column
widths are calculated from the headers and all report values; paths and status
are left-aligned while percentage columns are right-aligned.

- `l2_percent = l2 / sqrt(2) * 100`, where raw L2 is in `0..sqrt(2)`.
- `phash_percent = phash_hamming / 64 * 100`, where pHash Hamming distance is
  in `0..64`.
- The status uses the unrounded average of those percentages: `identical` for
  exactly `0%`, `duplicate` below `1%`, `similar` below `10%`, `differ` below
  `25%`, and `different` otherwise.
- The report is immediately followed by a summary beginning with `total `.
  It contains statuses with non-zero counts, including every calculated pair
  (including hidden `different` pairs):

  ```text
  total identical: N, similar: N, different: N
  ```

  In table mode, the summary is outside the ASCII table, after its lower
  border. If no rows are visible, the normal empty report header/table is
  still printed.

## Implementation status

Implemented.

- Registered `diff` in the `davo im` command group.
- Reused the fingerprint module's portrait/RGB normalization and feature
  algorithms with one image decode per input.
- Added tests for parser wiring, identical images, pair order, both metrics,
  invalid inputs without partial output, and source immutability.
