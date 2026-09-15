---
status: implemented
type: feature
slug: im-convert-write-contract
date: 2026-09-15
---

# Feature: write-by-default contract for `davo im convert`

## Summary

`davo im convert` follows the same derived-file contract as `davo vid compress`
and the bank CSV converters: it writes by default, has no `-C/--commit` flag,
and uses `-0/--dry-run` to report a plan without changing files.

## Usage

```bash
davo im convert photo.jpg
davo im convert -0 photo.jpg
davo im convert -W photo.jpg
davo im convert -t 800 photo.jpg
```

The default output is `<stem>_converted<extension>` from
`[source]_converted.[Ext]`. Sources are kept unless `-R/--rename-processed`
succeeds after a write.

## Safety

Existing automatic `_converted` outputs are skipped. `-W/--rewrite` replaces
only that automatic target. An explicit `-P/--replace-pattern` and a path that
matches the source are never overwritten, including with `-W`.
`-0/--dry-run` runs the same collision checks and logs the plan without
creating or replacing files.
