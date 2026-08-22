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
davo im merge (-V|--vertical|-H|--horizontal) [-o OUTPUT] [--debug-fill] [-S|--smart] IMAGE [IMAGE ...]
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

`-S` / `--smart` handles only adjacent sequential frames. It does not rotate,
blend, apply perspective correction, or stretch unequally. For each pair,
OpenCV finds a 16-pixel leading overlap using several independent grayscale
edge probes. It searches a uniform scale for the next frame from 0.90 to 1.10
(1% coarse pass followed by 0.2% refinement) and allows a cross-axis shift of
at most 10% of the frame dimension, capped at 256 pixels. The next frame is
scaled in memory with LANCZOS and composited above the overlap. Pairwise
translations are accumulated; negative coordinates are normalized into a final
bounding box, retaining all outer edges. Failure to register every pair aborts
before an output is written.
