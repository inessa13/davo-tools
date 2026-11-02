"""Shared filesystem planning for personal-accounting converters."""

from pathlib import Path

from davo import errors


def input_pdfs(paths):
    result = []
    for value in paths:
        path = Path(value).expanduser()
        if path.is_dir():
            result.extend(
                sorted(
                    item
                    for item in path.iterdir()
                    if item.is_file() and item.suffix.lower() == ".pdf"
                )
            )
        elif path.is_file():
            if path.suffix.lower() != ".pdf":
                raise errors.UserError("Input is not a PDF: {}".format(path))
            result.append(path)
        else:
            raise errors.UserError("Missing input: {}".format(path))
    if not result:
        raise errors.UserError("No PDF files found")
    return result


def output_target(source, explicit, targets, rewrite):
    target = explicit or source.with_name(source.stem + ".csv")
    if target in targets:
        raise errors.UserError("Duplicate output target: {}".format(target))
    if target.exists() and (explicit or not rewrite):
        raise errors.UserError("Output already exists: {}".format(target))
    targets.add(target)
    return target


def conversion_plan(inputs, paths, *, out_path, rewrite, verbose, parser):
    """Parse every input and plan targets without writing partial output."""
    plan = []
    targets = set()
    explicit = Path(out_path).expanduser() if out_path else None
    requested = {Path(value).expanduser() for value in paths}
    for source in inputs:
        try:
            rows = parser(source)
        except errors.UserError as exc:
            if source in requested or not str(exc).startswith(
                "Not a supported"
            ):
                raise
            if verbose:
                print("skip unsupported PDF: {}".format(source))
            continue
        target = output_target(source, explicit, targets, rewrite)
        plan.append((source, target, rows))
    return plan
