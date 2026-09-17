---
status: implemented
type: feature
slug: im-convert-separate-dir
date: 2026-09-15
---

# Feature: `-D/--separate-dir` for `davo im convert`

## Summary

`davo im convert -D` writes derived files into `./davo_im_convert/` instead of
adding a `_converted` suffix beside the source. The directory name follows
`davo_<group>_<command>` so later commands can reuse the same layout.

## Usage

```bash
davo im convert -D photo.jpg
davo im convert -D photos/a.jpg
davo im convert -D -0 photo.jpg
davo im convert -D -W photo.jpg
```

Outputs use the source path relative to the current working directory:
`photos/a.jpg` becomes `davo_im_convert/photos/a.jpg`. The original filename
is kept when `-P` is left at its default. A custom `-P` applies only to the
basename inside that mirrored directory.

Sources already under `davo_im_convert/` are skipped. Sources outside the
current working directory are skipped with a warning. `-0/--dry-run` reports
the plan and does not create the directory.

## Safety

The automatic target with `-D` is the mirrored file under `davo_im_convert/`.
An existing automatic target is skipped unless `-W/--rewrite` is provided.
A custom `-P` is never overwritten, including with `-W`.
