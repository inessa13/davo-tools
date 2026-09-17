---
status: implemented
type: feature
slug: clips-compress
date: 2026-08-23
---

# Feature: add `davo vid compress` command

## Summary

`davo vid compress` creates H.264-compressed copies of one or more videos.
The command is available only in the `vid` command group; legacy flat
`clips-*` commands are not supported.

## Usage

```bash
davo vid compress movie.mov
davo vid compress first.mp4 second.mkv --crf 20
davo vid compress -r .
davo vid compress --mp4 movie.mov
davo vid compress -R movie.mov
davo vid compress --dry-run movie.mov
davo vid compress -W movie.mov
davo vid compress -H 720 movie.mov
```

The default CRF is `23`. Outputs are written beside their sources as
`<stem>_compressed<extension>`, or as `<stem>_compressed.mp4` with `--mp4`.
Directories contribute common video formats (recursively with `-r`); non-video
files and already-compressed names are skipped. Input processing is stable and
deduplicated.

Existing outputs are skipped unless `-W/--rewrite` is supplied. That flag adds
ffmpeg's non-interactive overwrite option; on its own, it never changes the
input file.
`--dry-run` prints each ffmpeg command without running it. Each selected input
is processed independently, so a failure does not stop later files.

Each successful compression reports the source path, original and resulting
sizes, and percentage reduction (which is negative if the file grows). When two
or more files succeed, a final total uses the summed sizes. Skipped, failed, and
dry-run inputs are excluded.

`-R/--rename-processed` renames a source to `<stem>_processed<extension>` only
after ffmpeg successfully creates its output. Already marked inputs and
existing processed targets are refused. `-W/--rewrite` applies only to the
automatic `_compressed` output.

`-H/--height HEIGHT` limits the output height to 144--2160 pixels; typical
values are `240`, `360`, and `720`. The width is calculated automatically to
preserve aspect ratio and is even for H.264. Videos already shorter than the
requested height are not enlarged. Odd values are rounded down to the nearest
even value.

## ffmpeg invocation

For each output, the command uses:

```text
ffmpeg -i INPUT -vcodec libx264 -crf CRF -acodec copy OUTPUT
```

With `-H HEIGHT`, ffmpeg also receives the video filter
`scale=-2:min(ih\\,HEIGHT)`, which derives an even width and prevents upscaling.
