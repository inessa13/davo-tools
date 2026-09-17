---
status: implemented
slug: fns-extract-output-type
---

# Feature: choose FNS receipt export type and filename marker

`davo arch fns-extract` writes HTML by default and accepts `-t/--type pdf` to
render the same generated receipt HTML through the shared Chrome/Chromium PDF
renderer. PDF output stores the fiscal identity in its `keywords` metadata;
HTML retains its generator comment. Resume detection only examines the selected
type, so the same fiscal receipt can be exported once as HTML and once as PDF.

Use `-A/--no-autogen` to omit `autogen` from the filename. It does not remove
the internal fiscal-identity marker used to resume safely. Both output types
retain existing collision-safe numbering and `-0/--dry-run` only plans names:
it neither creates files nor starts a browser.
