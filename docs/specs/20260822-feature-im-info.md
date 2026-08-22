---
status: implemented
type: feature
slug: im-info
date: 2026-08-22
---

# Feature: add `davo im info` command

## Summary

Add a readonly Pillow metadata command:

```console
davo im info [-v] [-t|--table] [--compact] [-e|--exif | -E|--exif-full] IMAGE [IMAGE ...]
```

It reports each direct image path in argv order. Without input paths, it uses
the current directory contents as if `*` had been passed. The base report includes
format, EXIF-adjusted pixel dimensions and orientation, source DPI and mode,
file size, and whether Pillow finds EXIF metadata. `--exif` adds date and
camera columns; `--exif-full` prints the available tags in stable alphabetical
order after the image's ordinary report.

## Output and errors

Normal and table output follow `davo pdf info`: a relative path line followed
by one report, with a blank line between successful files. Compact output uses
an `NN/TT` input number and suppresses paths and headers. Compact table output
uses one table when no full EXIF blocks are requested.

Unreadable, corrupted, missing, and non-regular inputs are skipped. They emit
a warning only with `-v`, and never prevent later valid inputs from being
reported. The command never writes or otherwise changes a source file.
