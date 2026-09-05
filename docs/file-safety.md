# Safe derived files

Commands that create a derived file keep their source by default.  Their
automatic name is based on the first input and a command-specific suffix.
An automatic target that already exists is refused unless `-W/--rewrite` is
provided.  An explicit `-o/--out` target (or an image conversion pattern) is
never overwritten, including with `-W`.

`-R/--rename-processed` marks every unique successfully processed source as
`<stem>_processed<ext>`.  It is checked before output is written: already
marked sources, existing marker targets, and output conflicts fail without
changing sources.

This applies to PDF output commands, `vid compress`, and `im convert`.
`file compare` and `file iphone-clean-live` are read/cleanup workflows with
their existing behaviour.  S3 sync retains its explicit destructive flags:
`--replace-upload`, `--replace-download`, `--delete-local`, and
`--delete-remote` (without short aliases).
