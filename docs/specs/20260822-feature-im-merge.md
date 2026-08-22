---
status: implemented
type: feature
slug: im-merge
date: 2026-08-22
---

# Feature: add `davo im merge` command

## Summary

Add sequential Pillow image merging:

```console
davo im merge (-V|--vertical|-H|--horizontal) [-o OUTPUT] [--debug-fill] [--smart] IMAGE [IMAGE ...]
```

At least two readable regular files are required. Sources are never modified,
and an existing output or one that resolves to an input is rejected.

## Layout and output

- `-V` stacks frames top-to-bottom; `-H` places them left-to-right.
- The main-axis dimensions are summed and the cross-axis dimension is the
  maximum. Smaller frames are centred on the cross axis.
- PNG-style outputs retain transparent free areas. JPEG output composites
  transparency onto white; `--debug-fill` uses opaque magenta instead.
- An omitted output path uses `<first-stem>_merged.<ext>`. The first extension
  is retained only when Pillow detects the same format for every source;
  otherwise the command writes JPEG. An explicit output extension selects the
  Pillow encoder and must be supported.

## Smart overlap mode

`--smart` handles only adjacent sequential frames. It does not rotate, scale,
shift sideways, or blend. It requires common widths for vertical operation and
common heights for horizontal operation. OpenCV matches a 16–64 pixel leading
grayscale probe from the next image against the previous image; a normalized
correlation of at least `0.98` is required. The following image is composited
above the overlap. Failure to find every overlap aborts before an output is
written.
