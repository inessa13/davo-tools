import html
import logging
import os
import re
import shutil
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

_DATE_RE = re.compile(
    r"Дата\s*:\s*(?P<day>\d{2})\.(?P<month>\d{2})\.(?P<year>\d{2})\b",
    re.IGNORECASE,
)
_PLACE_RE = re.compile(
    r"Место\s+расчета\s*:\s*(?P<place>.*?)\s*</td\s*>",
    re.IGNORECASE | re.DOTALL,
)
_TAGS_RE = re.compile(r"<[^>]+>")


@dataclass(frozen=True)
class FnsRename:
    source: Path
    target: Path


def _normalise_place(value):
    value = html.unescape(_TAGS_RE.sub(" ", value))
    return " ".join(value.split()).rstrip("/").rstrip()


def extract_fns_name(path):
    """Return the unnumbered target filename encoded in an FNS receipt."""
    try:
        contents = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        contents = path.read_text(encoding="utf-8-sig")

    date = _DATE_RE.search(contents)
    if date is None:
        raise ValueError("receipt date is missing")

    place = _PLACE_RE.search(contents)
    if place is None:
        raise ValueError("receipt place is missing")

    store = _normalise_place(place.group("place"))
    if not store:
        raise ValueError("receipt place is empty")

    return "20{}{}{} Ч {}.html".format(
        date.group("year"), date.group("month"), date.group("day"), store
    )


def _number_names(files):
    grouped = defaultdict(list)
    for source, base_name in files:
        grouped[base_name].append(source)

    names = {}
    for base_name, sources in grouped.items():
        if len(sources) == 1:
            names[sources[0]] = base_name
            continue

        stem = Path(base_name).stem
        width = len(str(len(sources)))
        for index, source in enumerate(sources, start=1):
            names[source] = "{} {}.html".format(stem, str(index).zfill(width))
    return names


def plan_fns_rename(root):
    """Build an FNS receipt rename plan for direct HTML children of *root*."""
    root = Path(root)
    candidates = []
    for path in sorted(root.iterdir(), key=lambda item: item.name):
        if not path.is_file() or path.suffix.lower() not in {".htm", ".html"}:
            continue
        try:
            candidates.append((path, extract_fns_name(path)))
        except (OSError, ValueError) as exc:
            logger.warning(
                "fns-rename: skip %s: %s", _display_path(path, root), exc
            )

    names = _number_names(candidates)
    return [
        FnsRename(source=source, target=root / names[source])
        for source, _base_name in candidates
    ]


def _copy_without_overwrite(source, target):
    with source.open("rb") as source_file, target.open("xb") as target_file:
        shutil.copyfileobj(source_file, target_file)
    shutil.copystat(source, target)


def _display_path(path, root):
    return path.relative_to(root)


def command_fns_rename(root, commit=False, rename=False):
    """Plan or apply names for FNS receipt HTML files in one directory."""
    root = Path(root)
    if not root.is_dir():
        logger.warning("fns-rename: directory not found: %s", root)
        return

    plan = plan_fns_rename(root)
    collisions = {item.target for item in plan if item.target.exists()}
    for target in sorted(collisions):
        logger.warning(
            "fns-rename: target already exists: %s",
            _display_path(target, root),
        )

    action = "rename" if rename else "copy"
    for item in plan:
        if item.target in collisions:
            continue
        logger.info(
            "fns-rename: %s %s -> %s",
            action,
            _display_path(item.source, root),
            _display_path(item.target, root),
        )
        if not commit:
            continue
        try:
            if rename:
                # link() atomically refuses an existing target.  Both files
                # are direct children of root, so this is a same-filesystem
                # rename without os.rename()'s overwrite behaviour.
                os.link(item.source, item.target)
                item.source.unlink()
            else:
                _copy_without_overwrite(item.source, item.target)
        except FileExistsError:
            logger.warning(
                "fns-rename: target already exists: %s",
                _display_path(item.target, root),
            )
