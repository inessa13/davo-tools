import base64
import html
import io
import json
import logging
import os
import re
import shutil
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import qrcode
import yaml

from davo import errors

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
_AUTOGEN_ID_RE = re.compile(
    r"<!--\s*davo-fns-autogen\s+fiscal-identity:\s*"
    r"fn=(?P<fn>[^\s]+)\s+fd=(?P<fd>[^\s]+)\s+fp=(?P<fp>[^\s]+)\s*-->",
    re.IGNORECASE,
)
_UNSAFE_FILENAME_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


@dataclass(frozen=True)
class FnsRename:
    source: Path
    target: Path


def _normalise_place(value):
    value = html.unescape(_TAGS_RE.sub(" ", value))
    return " ".join(value.split()).rstrip("/").rstrip()


def _safe_store_name(value):
    """Return a portable, human-readable filename component."""
    value = _UNSAFE_FILENAME_RE.sub(" ", _normalise_place(str(value)))
    return " ".join(value.split()).strip(". ") or "receipt"


def find_fns_config(start=None, config=None):
    """Find a supplied config or the nearest project .dtconf file."""
    if config:
        return Path(config).expanduser().resolve()
    current = Path(start or os.getcwd()).expanduser().resolve()
    if current.is_file():
        current = current.parent
    for directory in (current, *current.parents):
        candidate = directory / ".dtconf"
        if candidate.is_file():
            return candidate
    return None


def load_fns_store_names(start=None, config=None):
    """Read FNS store aliases without requiring a project configuration."""
    config_path = find_fns_config(start=start, config=config)
    if config_path is None:
        return {}, None
    try:
        contents = (
            yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
            if config_path.exists()
            else {}
        )
    except (OSError, yaml.YAMLError) as exc:
        raise errors.UserError(
            "Invalid config {}: {}".format(config_path, exc)
        )
    if not isinstance(contents, dict):
        raise errors.UserError(
            "Invalid config {}: expected a mapping".format(config_path)
        )
    store_names = contents.get("fns", {}).get("store_names", {})
    if not isinstance(store_names, dict):
        raise errors.UserError("Invalid fns.store_names: expected a mapping")
    return {
        str(key): str(value) for key, value in store_names.items()
    }, config_path


def _store_name(place, store_names):
    return _safe_store_name(store_names.get(str(place), place))


def extract_fns_name(path, store_names=None):
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

    raw_store = _normalise_place(place.group("place"))
    store = _store_name(raw_store, store_names or {})
    if not store:
        raise ValueError("receipt place is empty")

    return "20{}{}{} REC {}.html".format(
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


def plan_fns_rename(root, config=None):
    """Build an FNS receipt rename plan for direct HTML children of *root*."""
    root = Path(root)
    store_names, _config_path = load_fns_store_names(root, config=config)
    candidates = []
    for path in sorted(root.iterdir(), key=lambda item: item.name):
        if not path.is_file() or path.suffix.lower() not in {".htm", ".html"}:
            continue
        try:
            candidates.append((path, extract_fns_name(path, store_names)))
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


def command_fns_rename(root, commit=False, rename=False, config=None):
    """Plan or apply names for FNS receipt HTML files in one directory."""
    root = Path(root)
    if not root.is_dir():
        logger.warning("fns-rename: directory not found: %s", root)
        return

    plan = plan_fns_rename(root, config=config)
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


@dataclass(frozen=True)
class FnsReceipt:
    receipt: dict
    identity: tuple[str, str, str]
    date: str
    store: str


def _money(value):
    return "{:.2f}".format(int(value) / 100)


def _required(receipt, name):
    value = receipt.get(name)
    if value is None or value == "":
        raise ValueError("{} is missing".format(name))
    return value


def _receipt_from_entry(entry, store_names):
    try:
        receipt = entry["ticket"]["document"]["receipt"]
    except (KeyError, TypeError) as exc:
        raise ValueError("ticket.document.receipt is missing") from exc
    if not isinstance(receipt, dict):
        raise ValueError("ticket.document.receipt is not an object")
    try:
        date_time = str(_required(receipt, "dateTime"))
        date, time = date_time.split("T", 1)
        date = "".join(date.split("-"))
        if len(date) != 8 or not date.isdigit() or len(time) < 5:
            raise ValueError("dateTime is invalid")
        identity = tuple(
            str(_required(receipt, name)).strip()
            for name in (
                "fiscalDriveNumber",
                "fiscalDocumentNumber",
                "fiscalSign",
            )
        )
        _required(receipt, "totalSum")
        place = str(_required(receipt, "retailPlace"))
        items = _required(receipt, "items")
        if not isinstance(items, list):
            raise ValueError("items is not a list")
        if any(not isinstance(item, dict) for item in items):
            raise ValueError("an item is not an object")
    except (TypeError, ValueError) as exc:
        raise ValueError(str(exc)) from exc
    return FnsReceipt(receipt, identity, date, _store_name(place, store_names))


def _qr_payload(receipt):
    date, time = str(receipt["dateTime"]).split("T", 1)
    date_time = "{}T{}".format(
        date.replace("-", ""), time[:5].replace(":", "")
    )
    return "t={}&s={}&fn={}&fd={}&fp={}&n={}".format(
        date_time,
        _money(receipt["totalSum"]),
        receipt["fiscalDriveNumber"],
        receipt["fiscalDocumentNumber"],
        receipt["fiscalSign"],
        receipt.get("operationType", 1),
    )


def _qr_png(payload):
    image = qrcode.make(payload)
    output = io.BytesIO()
    image.save(output, format="PNG")
    return base64.b64encode(output.getvalue()).decode("ascii")


def _receipt_html(item):
    receipt = item.receipt

    def value(name, default="—"):
        return html.escape(str(receipt.get(name, default)))

    item_rows = []
    for line in receipt["items"]:
        if not isinstance(line, dict):
            raise ValueError("an item is not an object")
        item_rows.append(
            "<tr><td>{}</td><td>{} × {}</td><td>{}</td></tr>".format(
                html.escape(str(line.get("name", "—"))),
                html.escape(_money(line.get("price", line.get("sum", 0)))),
                html.escape(str(line.get("quantity", 1))),
                html.escape(_money(line.get("sum", 0))),
            )
        )
    payments = (
        ("Наличными", receipt.get("cashTotalSum", 0)),
        ("Безналичными", receipt.get("ecashTotalSum", 0)),
        ("Предоплата", receipt.get("prepaidSum", 0)),
        ("Кредит", receipt.get("creditSum", 0)),
    )
    payment_rows = (
        "".join(
            "<tr><td>{}</td><td>{}</td></tr>".format(name, _money(sum_))
            for name, sum_ in payments
            if sum_
        )
        or "<tr><td>Оплата</td><td>—</td></tr>"
    )
    taxes = receipt.get("amountsReceiptNds", {}).get("amountsNds", [])
    tax_rows = "".join(
        "<tr><td>НДС (ставка {})</td><td>{}</td></tr>".format(
            html.escape(str(tax.get("nds", "—"))), _money(tax.get("ndsSum", 0))
        )
        for tax in taxes
        if isinstance(tax, dict)
    )
    fn, fd, fp = item.identity
    return """<!doctype html>
<!-- davo-fns-autogen fiscal-identity: fn={fn} fd={fd} fp={fp} -->
<html lang="ru"><head><meta charset="utf-8"><title>Кассовый чек</title>
<style>
body{{font:14px Arial,sans-serif;margin:2em auto;max-width:680px}}
h1,h2{{text-align:center}} table{{width:100%;border-collapse:collapse}}
td{{padding:4px;border-bottom:1px solid #ddd}}
td:last-child{{text-align:right;white-space:nowrap}}
.total{{font-size:1.2em;font-weight:bold}}
.qr{{display:block;margin:1.5em auto;width:220px}}
</style></head><body><h1>КАССОВЫЙ ЧЕК</h1>
<p><b>{user}</b><br>ИНН: {inn}<br>{address}</p>
<p>Место расчета: {place}<br>Дата: {date}<br>Смена: {shift}</p>
<table>{items}</table><p class="total">ИТОГ: {total} ₽</p>
<table>{payments}{taxes}</table>
<p>ФН: {fn}<br>ФД: {fd}<br>ФП: {fp}<br>РН ККТ: {kkt}</p>
<img class="qr" alt="QR-код чека"
src="data:image/png;base64,{qr}"></body></html>""".format(
        fn=html.escape(fn),
        fd=html.escape(fd),
        fp=html.escape(fp),
        user=value("user"),
        inn=value("userInn"),
        address=value("retailPlaceAddress"),
        place=value("retailPlace"),
        date=value("dateTime"),
        shift=value("shiftNumber"),
        items="".join(item_rows),
        total=_money(receipt["totalSum"]),
        payments=payment_rows,
        taxes=tax_rows,
        kkt=value("kktRegId"),
        qr=_qr_png(_qr_payload(receipt)),
    )


def _existing_fiscal_identities(root):
    existing = set()
    for path in root.iterdir():
        if path.is_file() and path.suffix.lower() in {".htm", ".html"}:
            try:
                match = _AUTOGEN_ID_RE.search(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError):
                continue
            if match:
                existing.add((match["fn"], match["fd"], match["fp"]))
    return existing


def _target_name(receipt, multiple, root, reserved):
    base = "{} REC {} autogen".format(receipt.date, receipt.store)
    if not multiple:
        candidate = root / (base + ".html")
        if candidate not in reserved and not candidate.exists():
            return candidate
    index = 1
    while True:
        candidate = root / "{} {}.html".format(base, index)
        if candidate not in reserved and not candidate.exists():
            return candidate
        index += 1


def command_fns_extract(json_path, out_dir=None, config=None, dry_run=False):
    """Render FNS JSON receipts and return generated paths."""
    source = Path(json_path)
    try:
        entries = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise errors.UserError("fns-extract: invalid JSON: {}".format(exc))
    if not isinstance(entries, list):
        raise errors.UserError("fns-extract: expected a JSON array")
    root = Path(out_dir or os.getcwd())
    if not root.is_dir():
        raise errors.UserError(
            "fns-extract: output directory not found: {}".format(root)
        )
    store_names, _config_path = load_fns_store_names(
        os.getcwd(), config=config
    )
    receipts, failed = [], []
    for index, entry in enumerate(entries, start=1):
        try:
            receipts.append(_receipt_from_entry(entry, store_names))
        except ValueError as exc:
            failed.append("entry {}: {}".format(index, exc))
    if failed:
        for problem in failed:
            logger.error("fns-extract: %s", problem)
    if not receipts:
        raise errors.UserError(
            "fns-extract: {} invalid receipt(s)".format(len(failed))
        )
    identities = [item.identity for item in receipts]
    if len(set(identities)) != len(identities):
        raise errors.UserError(
            "fns-extract: input contains duplicate fiscal identities"
        )
    existing = _existing_fiscal_identities(root)
    missing = [item for item in receipts if item.identity not in existing]
    if not missing:
        if failed:
            raise errors.UserError(
                "fns-extract: {} invalid receipt(s)".format(len(failed))
            )
        raise errors.UserError(
            "fns-extract: repeated run; all receipts already exist"
        )
    counts = defaultdict(int)
    for item in receipts:
        counts[(item.date, item.store)] += 1
    reserved, plan = set(), []
    for item in missing:
        target = _target_name(
            item, counts[(item.date, item.store)] > 1, root, reserved
        )
        reserved.add(target)
        plan.append((item, target))
    for item in receipts:
        if item.identity in existing:
            logger.info("fns-extract: existing receipt %s", item.identity)
    rendered = []
    try:
        rendered = [(target, _receipt_html(item)) for item, target in plan]
    except (TypeError, ValueError, KeyError) as exc:
        raise errors.UserError("fns-extract: invalid receipt: {}".format(exc))
    for target, receipt_html in rendered:
        message = "would create" if dry_run else "create"
        logger.info("fns-extract: %s %s", message, target.name)
        if not dry_run:
            target.write_text(receipt_html, encoding="utf-8")
    if failed:
        raise errors.UserError(
            "fns-extract: {} invalid receipt(s)".format(len(failed))
        )
    return [target for _item, target in plan]


def command_fns_config_init_map(json_path, config=None, verbose=False):
    """Add previously unseen retail places to fns.store_names."""
    source = Path(json_path)
    try:
        entries = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise errors.UserError("fns-config: invalid JSON: {}".format(exc))
    if not isinstance(entries, list):
        raise errors.UserError("fns-config: expected a JSON array")
    config_path = find_fns_config(os.getcwd(), config=config)
    if config_path is None:
        raise errors.UserError(
            "fns-config: no .dtconf found; use --config PATH"
        )
    try:
        contents = (
            yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
            if config_path.exists()
            else {}
        )
    except (OSError, yaml.YAMLError) as exc:
        raise errors.UserError(
            "Invalid config {}: {}".format(config_path, exc)
        )
    if not isinstance(contents, dict):
        raise errors.UserError(
            "Invalid config {}: expected a mapping".format(config_path)
        )
    fns = contents.setdefault("fns", {})
    if not isinstance(fns, dict):
        raise errors.UserError("Invalid fns: expected a mapping")
    store_names = fns.setdefault("store_names", {})
    if not isinstance(store_names, dict):
        raise errors.UserError("Invalid fns.store_names: expected a mapping")
    seen_places = set()
    changes = []
    for entry in entries:
        try:
            place = str(entry["ticket"]["document"]["receipt"]["retailPlace"])
        except (KeyError, TypeError):
            continue
        if place in seen_places:
            continue
        seen_places.add(place)
        if place in store_names:
            changes.append(("existing", place, store_names[place]))
            continue
        store_name = _safe_store_name(place)
        store_names[place] = store_name
        changes.append(("added", place, store_name))
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        yaml.safe_dump(contents, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    logger.info("fns-config: updated %s", config_path)
    if verbose:
        for status, place, store_name in changes:
            logger.info("fns-config: %s %s -> %s", status, place, store_name)


def command_fns_config_show_map(config=None):
    store_names, config_path = load_fns_store_names(os.getcwd(), config=config)
    logger.info("fns-config: %s", config_path or "no .dtconf")
    for source, target in sorted(store_names.items()):
        logger.info("%s: %s", source, target)
