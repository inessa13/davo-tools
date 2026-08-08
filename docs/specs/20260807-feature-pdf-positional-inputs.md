---
status: implemented
type: feature
slug: pdf-positional-inputs
date: 2026-08-07
---

# Feature: accept positional input paths in `davo pdf`

## Summary

Make every `davo pdf` subcommand receive its source file path as a required
positional argument. Remove the old `-i` / `--inf` options and the inherited
positional root-directory argument.

For example, this command:

```console
davo pdf info -i file.pdf
```

becomes:

```console
davo pdf info file.pdf
```

This is an intentional breaking change for the nested `davo pdf` CLI.
Backwards compatibility there for `-i` / `--inf` and the positional root
argument is not required.

## Scope

- PDF CLI parser: `davo/services/photo/cli.py`
- PDF command wrappers: adapt path handling for direct `davo pdf` inputs while
  retaining the root-based behavior needed by legacy aliases in
  `davo/services/photo/helpers.py`
- Focused CLI tests: `tests/services/test_pdf.py`

No PDF processing behavior should change.
Existing specs describe the contracts under which their features were built
and must not be rewritten as part of this change. This spec defines the new
`davo pdf` input syntax without altering those historical documents.

## Current CLI inventory and conflicts

All nine current `davo pdf` subcommands inherit an optional positional `path`
argument. It represents a root directory and defaults to the current working
directory. Therefore, `davo pdf info file.pdf` currently parses `file.pdf` as
`path`, while `inf` remains unset.

| Command | Current input | Other value-taking arguments | Positional target |
| --- | --- | --- | --- |
| `merge` | `-i/--inf`, one or more paths | `-o/--out` | `INPUT [INPUT ...]` |
| `rotate` | `-i/--inf`, one path | `-o/--out`, `-d/--dir` | `INPUT` |
| `delete` | `-i/--inf`, one path | `-o/--out`, `-p/--pages` (`nargs="+"`) | `INPUT` |
| `split` | `-i/--inf`, one path | `-o/--out`, `-p/--pages` (`nargs="+"`) | `INPUT` |
| `clean` | `-i/--inf`, one path | `-o/--out` | `INPUT` |
| `compress` | `-i/--inf`, one path | `-o/--out`, `-d/--dpi`, `-q/--quality` | `INPUT` |
| `extract` | `-i/--inf`, one path | `-o/--out`, `-p/--pages` (`nargs="+"`), `-t/--type` | `INPUT` |
| `info` | `-i/--inf`, one path | `-p/--pages` (`nargs="+"`) | `INPUT` |
| `scale` | `-i/--inf`, one path | `-o/--out`, `-p/--pages` (`nargs="+"`), `-f/--format` | `INPUT` |

The existing positional `path` is the direct conflict and cannot coexist
unambiguously with a positional input path. Remove it from PDF commands. Do
not add a replacement `--root` option: callers can pass relative paths from
the current working directory or explicit absolute paths.

The `-p` / `--pages` option is also order-sensitive because it accepts one or
more integers and greedily consumes following tokens. The canonical form must
place `INPUT` before `-p`, for example:

```console
davo pdf info file.pdf -p 1 3
```

An input path after the page values, such as
`davo pdf info -p 1 3 file.pdf`, is not required to work. It may be written as
`davo pdf info -p 1 3 -- file.pdf`, but this is not the documented form.

Options that consume exactly one value (`-o`, `-d`, `-q`, `-t`, and `-f`) and
boolean flags do not create an ambiguity with a positional input.

## Command contract

### Single-input commands

`rotate`, `delete`, `split`, `clean`, `compress`, `extract`, `info`, and
`scale` accept exactly one required source path:

```console
davo pdf COMMAND INPUT [OPTIONS]
```

### Multi-input command

`merge` accepts one or more positional source paths:

```console
davo pdf merge INPUT [INPUT ...] [-o OUTPUT] [OPTIONS]
```

### Input resolution and errors

- Register `INPUT` as a required positional argument so a missing input
  terminates through `argparse` with a clear error.
- Remove `-i` / `--inf` from every nested `davo pdf` subparser rather than
  keeping aliases.
- Remove the nested `davo pdf` parser's inherited positional `path` argument.
- Pass input and output paths from `davo pdf` to the PDF operations without
  joining them to a separate root value. Command helpers may retain isolated
  root-aware handling for the legacy `davo file pdf-*` aliases.
- Preserve input order for `merge`.
- Resolve relative paths naturally against the process working directory;
  accept absolute paths unchanged.
- Keep `-o` / `--out` optional. When it is omitted, pass `None` to the PDF
  operation and use its existing default output naming behavior.
- Paths beginning with `-` require the standard `--` separator.

## Removed arguments

- Remove the positional root-directory argument from all nested `davo pdf`
  commands.
- Do not introduce `--root` or another replacement root option.
- Remove `-i` / `--inf` from all nested `davo pdf` commands.
- Invocations using any removed form should fail argument parsing rather than
  being reinterpreted silently.
- Callers that previously relied on a root directory can pass full paths or
  change the process working directory:

```console
# Removed form
davo pdf info /documents -i scan.pdf

# New form
davo pdf info /documents/scan.pdf
```

## Legacy aliases

`davo file pdf-merge`, `davo file pdf-rotate`, and `davo file pdf-delete` are
built by the same parser function today but are outside the scope of this
change. Preserve their existing positional root argument and `-i` / `--inf`
input syntax unchanged. The implementation must isolate the new contract to
the nested `davo pdf` commands, even if that requires separate parser setup or
an explicit parser mode.

## Expected examples

```console
davo pdf info file.pdf
davo pdf info file.pdf -p 1 3
davo pdf extract scan.pdf -p 1 3 -t png -w
davo pdf compress scan.pdf --dpi 200 --rebuild
davo pdf scale scan.pdf -o scan-a5.pdf --format a5
davo pdf rotate scan.pdf -o rotated.pdf --dir right
davo pdf delete scan.pdf -o trimmed.pdf -p 2 4
davo pdf split scan.pdf -o part.pdf -p 3 7
davo pdf clean scan.pdf -o clean.pdf
davo pdf merge cover.pdf body.pdf appendix.pdf -o complete.pdf
davo pdf info /documents/scan.pdf
```

## Verification

Focused parser tests should cover:

- positional input for every `davo pdf` subcommand;
- multiple positional inputs and preserved ordering for `merge`;
- a parser error when input is missing;
- a parser error for removed `-i` / `--inf` invocations;
- `INPUT -p 1 3` parsing for `delete`, `split`, `extract`, `info`, and `scale`;
- positional inputs combined with every other value-taking option;
- relative and absolute input and output paths;
- omitted `-o` using the existing default output name for every command that
  supports automatic output naming;
- absence of the old positional root and any new `--root` option;
- unchanged parsing for the three `davo file pdf-*` legacy aliases;
- nested `davo pdf` help output showing `INPUT` or `INPUT [INPUT ...]`, without
  `-i`, `--inf`, or a root argument.

Run the full test and lint suites after the focused tests.

## Out of scope

- Changing output-path syntax from `-o` / `--out`.
- Rewriting older feature specs that document the previous `-i` input syntax.
- Changing `davo file pdf-merge`, `davo file pdf-rotate`, or
  `davo file pdf-delete`.
- Changing `-p` / `--pages` syntax or accepting an unseparated input after its
  greedy value list.
- Adding multiple inputs to commands other than `merge`.
- Changing PDF processing, validation, or output naming behavior.
