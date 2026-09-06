import base64
import html
import io
import json
import logging
import os
import re
import shutil
import tempfile
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import qrcode
import yaml

from davo import errors, settings
from davo.utils import conf as config_utils

logger = logging.getLogger(__name__)

_DATE_RE = re.compile(
    r"Дата\s*:\s*(?P<day>\d{2})\.(?P<month>\d{2})\.(?P<year>\d{2})\b",
    re.IGNORECASE,
)
_USER_RE = re.compile(
    r"Пользователь\s*:\s*(?P<user>.*?)\s*</td\s*>",
    re.IGNORECASE | re.DOTALL,
)
_TAGS_RE = re.compile(r"<[^>]+>")
_AUTOGEN_ID_RE = re.compile(
    r"<!--\s*davo-fns-autogen\s+fiscal-identity:\s*"
    r"fn=(?P<fn>[^\s]+)\s+fd=(?P<fd>[^\s]+)\s+fp=(?P<fp>[^\s]+)\s*-->",
    re.IGNORECASE,
)
_PDF_AUTOGEN_ID_RE = re.compile(
    r"davo-fns-autogen\s+fiscal-identity:\s*"
    r"fn=(?P<fn>[^\s]+)\s+fd=(?P<fd>[^\s]+)\s+fp=(?P<fp>[^\s;]+)",
    re.IGNORECASE,
)
_FNS_EXTRACT_TYPES = {"html", "pdf"}
_UNSAFE_FILENAME_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_FNS_META_FIELDS = (
    "retailPlace",
    "userInn",
    "retailPlaceAddress",
    "sellerAddress",
)


@dataclass(frozen=True)
class FnsRename:
    source: Path
    target: Path


def _normalise_value(value):
    value = html.unescape(_TAGS_RE.sub(" ", value))
    return " ".join(value.split()).rstrip("/").rstrip()


def _safe_user_name(value):
    """Return a portable, human-readable filename component."""
    value = _UNSAFE_FILENAME_RE.sub(" ", _normalise_value(str(value)))
    return " ".join(value.split()).strip(". ") or "receipt"


_QUOTES_RE = re.compile(r'["\'«»„“”‟‹›〝〞「」『』《》]')
_LEGAL_FORM_RE = re.compile(
    r"\b(?:"
    r"индивидуальн(?:ый|ая)\s+предпринимател(?:ь|я)|"
    r"общество\s+с\s+ограниченной\s+ответственностью|"
    r"публичное\s+акционерное\s+общество|"
    r"непубличное\s+акционерное\s+общество|"
    r"акционерное\s+общество|"
    r"общество\s+с\s+дополнительной\s+ответственностью|"
    r"ооо|зао|пао|оао|нао|ао|ип"
    r")\b",
    re.IGNORECASE,
)
_EDGE_SEPARATORS_RE = re.compile(
    r"^[\s,.;:—–\-_()\[\]{}]+|[\s,.;:—–\-_()\[\]{}]+$"
)
_FIO_INITIALS_RE = re.compile(
    r"^(?P<surname>[А-ЯЁ][А-ЯЁа-яё-]+)\s+"
    r"[А-ЯЁ]\.?\s*[А-ЯЁ]\.?$"
)
_FIO_PATRONYMIC_RE = re.compile(
    r"^(?P<surname>[А-ЯЁ][А-ЯЁа-яё-]+)\s+"
    r"[А-ЯЁ][А-ЯЁа-яё-]+\s+"
    r"[А-ЯЁ][А-ЯЁа-яё-]+(?:вич|вна|ична|оглы|кызы)$",
    re.IGNORECASE,
)


def _normalise_user(value):
    """Make an unmapped FNS seller name suitable for a receipt filename."""
    value = _normalise_value(str(value))
    value = _QUOTES_RE.sub("", value)
    while True:
        previous = value
        value = _EDGE_SEPARATORS_RE.sub("", value)
        value = _LEGAL_FORM_RE.sub("", value, count=1)
        value = _EDGE_SEPARATORS_RE.sub("", value)
        if value == previous:
            break
    value = " ".join(value.split())
    match = _FIO_INITIALS_RE.match(value) or _FIO_PATRONYMIC_RE.match(value)
    if match:
        value = "ИП " + match.group("surname")
    return _safe_user_name(value)


def find_fns_config(start=None):
    """Return the nearest project configuration used by FNS writes."""
    return config_utils.find_project_config(start)


def load_fns_user_names(start=None):
    """Read FNS seller aliases without requiring a project configuration."""
    contents, _user_path, config_path = config_utils.load_davo_config(start)
    fns = contents.get("fns", {})
    if not isinstance(fns, dict):
        raise errors.UserError("Invalid fns: expected a mapping")
    user_names = fns.get("user_names", {})
    if not isinstance(user_names, dict):
        raise errors.UserError("Invalid fns.user_names: expected a mapping")
    return {
        str(key): str(value) for key, value in user_names.items()
    }, config_path


def _user_name(user, user_names):
    user = str(user)
    if user in user_names:
        alias = user_names[user]
        return "" if alias == "" else _safe_user_name(alias)
    return _normalise_user(user)


def extract_fns_name(path, user_names=None):
    """Return the unnumbered target filename encoded in an FNS receipt."""
    try:
        contents = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        contents = path.read_text(encoding="utf-8-sig")

    date = _DATE_RE.search(contents)
    if date is None:
        raise ValueError("receipt date is missing")

    user = _USER_RE.search(contents)
    if user is None:
        raise ValueError("receipt user is missing")

    raw_user = _normalise_value(user.group("user"))
    if not raw_user:
        raise ValueError("receipt user is empty")
    seller = _user_name(raw_user, user_names or {})

    date_part = "20{}{}{}".format(
        date.group("year"), date.group("month"), date.group("day")
    )
    parts = [date_part, "REC"]
    if seller:
        parts.append(seller)
    return " ".join(parts) + ".html"


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
    user_names, _config_path = load_fns_user_names(root)
    candidates = []
    for path in sorted(root.iterdir(), key=lambda item: item.name):
        if not path.is_file() or path.suffix.lower() not in {".htm", ".html"}:
            continue
        try:
            candidates.append((path, extract_fns_name(path, user_names)))
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


def command_fns_rename(root, rename=False, dry_run=False):
    """Copy or rename FNS receipts, optionally only reporting the plan."""
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
    log_action = "would {}".format(action) if dry_run else action
    for item in plan:
        if item.target in collisions:
            continue
        logger.info(
            "fns-rename: %s %s -> %s",
            log_action,
            _display_path(item.source, root),
            _display_path(item.target, root),
        )
        if dry_run:
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
    user: str


def _money(value):
    return "{:.2f}".format(int(value) / 100)


def _required(receipt, name):
    value = receipt.get(name)
    if value is None or value == "":
        raise ValueError("{} is missing".format(name))
    return value


def _receipt_from_entry(entry, user_names):
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
        user = str(_required(receipt, "user"))
        items = _required(receipt, "items")
        if not isinstance(items, list):
            raise ValueError("items is not a list")
        if any(not isinstance(item, dict) for item in items):
            raise ValueError("an item is not an object")
    except (TypeError, ValueError) as exc:
        raise ValueError(str(exc)) from exc
    return FnsReceipt(receipt, identity, date, _user_name(user, user_names))


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


def _existing_fiscal_identities(root, output_type):
    """Return identities already exported in the requested output type."""
    existing = set()
    for path in root.iterdir():
        if not path.is_file():
            continue
        if output_type == "html" and path.suffix.lower() in {".htm", ".html"}:
            try:
                match = _AUTOGEN_ID_RE.search(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError):
                continue
            if match:
                existing.add((match["fn"], match["fd"], match["fp"]))
        elif output_type == "pdf" and path.suffix.lower() == ".pdf":
            try:
                from davo.services.photo import pdf  # pylint: disable=C0415

                fitz = pdf._import_fitz(  # pylint: disable=W0212
                    "FNS receipt inspection"
                )
                with pdf._open_pdf(  # pylint: disable=W0212
                    fitz, str(path), "FNS receipt inspection"
                ) as doc:
                    match = _PDF_AUTOGEN_ID_RE.search(
                        (doc.metadata or {}).get(  # pylint: disable=E1101
                            "keywords"
                        )
                        or ""
                    )
            except Exception:  # pylint: disable=W0718
                # Foreign and corrupt PDFs are irrelevant here.
                continue
            if match:
                existing.add((match["fn"], match["fd"], match["fp"]))
    return existing


def _target_name(
    receipt, multiple, root, reserved, *, output_type, no_autogen
):
    parts = [receipt.date, "REC"]
    if receipt.user:
        parts.append(receipt.user)
    if not no_autogen:
        parts.append("autogen")
    base = " ".join(parts)
    suffix = ".{}".format(output_type)
    if not multiple:
        candidate = root / (base + suffix)
        if candidate not in reserved and not candidate.exists():
            return candidate
    index = 1
    while True:
        candidate = root / "{} {}{}".format(base, index, suffix)
        if candidate not in reserved and not candidate.exists():
            return candidate
        index += 1


def _pdf_metadata_identity(receipt):
    fn, fd, fp = receipt.identity
    return "davo-fns-autogen fiscal-identity: fn={} fd={} fp={}".format(
        fn, fd, fp
    )


def _write_fns_pdf(target, receipt_html, receipt):
    """Render receipt HTML into a checked PDF carrying its resume marker."""
    from davo.services.photo import pdf  # pylint: disable=C0415

    try:
        fitz = pdf._import_fitz("FNS receipt creation")  # pylint: disable=W0212
        with tempfile.TemporaryDirectory(prefix="davo-fns-") as temp_dir:
            source = Path(temp_dir) / "receipt.html"
            source.write_text(receipt_html, encoding="utf-8")
            rendered = pdf._render_html_to_pdf(  # pylint: disable=W0212
                fitz, str(source), temp_dir
            )
            marked = Path(temp_dir) / "receipt.pdf"
            with pdf._open_pdf(  # pylint: disable=W0212
                fitz, rendered, "FNS receipt creation"
            ) as doc:
                metadata = dict(doc.metadata or {})  # pylint: disable=E1101
                keywords = metadata.get("keywords") or ""
                marker = _pdf_metadata_identity(receipt)
                metadata["keywords"] = "; ".join(
                    part for part in (keywords, marker) if part
                )
                doc.set_metadata(metadata)  # pylint: disable=E1101
                doc.save(str(marked))
            with pdf._open_pdf(  # pylint: disable=W0212
                fitz, str(marked), "FNS receipt creation"
            ) as doc:
                if doc.page_count == 0:
                    raise ValueError("renderer produced an empty PDF")
            created = False
            try:
                with target.open("xb") as output:
                    created = True
                    with marked.open("rb") as source_pdf:
                        shutil.copyfileobj(source_pdf, output)
            except Exception:
                # Only remove a file created here; never replace a collision.
                if created and target.exists():
                    target.unlink()
                raise
    except Exception as exc:
        raise errors.UserError(
            "fns-extract: PDF render failed: {}".format(exc)
        ) from exc


def command_fns_extract(
    json_path,
    out_dir=None,
    dry_run=False,
    *,
    output_type="html",
    no_autogen=False,
):
    """Render FNS JSON receipts and return generated paths."""
    if output_type not in _FNS_EXTRACT_TYPES:
        raise errors.UserError(
            "fns-extract: invalid output type: {}".format(output_type)
        )
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
    user_names, _config_path = load_fns_user_names(os.getcwd())
    receipts, failed = [], []
    for index, entry in enumerate(entries, start=1):
        try:
            receipts.append(_receipt_from_entry(entry, user_names))
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
    existing = _existing_fiscal_identities(root, output_type)
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
        counts[(item.date, item.user)] += 1
    reserved, plan = set(), []
    for item in missing:
        target = _target_name(
            item,
            counts[(item.date, item.user)] > 1,
            root,
            reserved,
            output_type=output_type,
            no_autogen=no_autogen,
        )
        reserved.add(target)
        plan.append((item, target))
    for item in receipts:
        if item.identity in existing:
            logger.info("fns-extract: existing receipt %s", item.identity)
    rendered = []
    try:
        rendered = [
            (item, target, _receipt_html(item)) for item, target in plan
        ]
    except (TypeError, ValueError, KeyError) as exc:
        raise errors.UserError("fns-extract: invalid receipt: {}".format(exc))
    for item, target, receipt_html in rendered:
        message = "would create" if dry_run else "create"
        logger.info("fns-extract: %s %s", message, target.name)
        if not dry_run:
            if output_type == "html":
                target.write_text(receipt_html, encoding="utf-8")
            else:
                _write_fns_pdf(target, receipt_html, item)
    if failed:
        raise errors.UserError(
            "fns-extract: {} invalid receipt(s)".format(len(failed))
        )
    return [target for _item, target in plan]


def _add_fns_metadata(metadata, user, receipt):
    for field in _FNS_META_FIELDS:
        value = receipt.get(field)
        if value is None or value == "":
            continue
        value = _normalise_value(str(value))
        if value and value not in metadata[user][field]:
            metadata[user][field].append(value)


def _metadata_comments(metadata):
    return [
        "# {}: {}".format(field, "; ".join(values))
        for field in _FNS_META_FIELDS
        for values in [metadata.get(field, [])]
        if values
    ]


def _yaml_mapping_entry(key, value):
    return yaml.safe_dump(
        {key: value}, allow_unicode=True, sort_keys=False
    ).splitlines()[0]


def _existing_user_comments(config_text, user_names):
    """Return comments immediately preceding existing user_names entries."""
    lines = config_text.splitlines()
    user_names_line = next(
        (
            index
            for index, line in enumerate(lines)
            if line.strip() == "user_names:"
        ),
        None,
    )
    if user_names_line is None:
        return {}
    parent_indent = len(lines[user_names_line]) - len(
        lines[user_names_line].lstrip()
    )
    entry_indent = parent_indent + 2
    entries = {
        " " * entry_indent + _yaml_mapping_entry(user, value): str(user)
        for user, value in user_names.items()
    }
    comments, pending = {}, []
    for line in lines[user_names_line + 1 :]:
        stripped = line.strip()
        indent = len(line) - len(line.lstrip())
        if (
            stripped
            and not stripped.startswith("#")
            and indent <= parent_indent
        ):
            break
        if indent == entry_indent and stripped.startswith("#"):
            pending.append(stripped)
            continue
        user = entries.get(line)
        if user is not None:
            if pending:
                comments[user] = pending
            pending = []
            continue
        if stripped or indent <= entry_indent:
            pending = []
    return comments


def _dump_fns_config(contents, metadata, preserved_comments):
    """Dump config and restore comments before user_names mappings."""
    rendered = yaml.safe_dump(contents, allow_unicode=True, sort_keys=False)
    comments_by_user = dict(preserved_comments)
    comments_by_user.update(
        {
            user: _metadata_comments(user_metadata)
            for user, user_metadata in metadata.items()
        }
    )
    if not comments_by_user:
        return rendered
    lines = rendered.splitlines()
    for user, comments in comments_by_user.items():
        if not comments:
            continue
        entry = _yaml_mapping_entry(user, contents["fns"]["user_names"][user])
        try:
            index = lines.index("    " + entry)
        except ValueError:
            continue
        lines[index:index] = ["    " + comment for comment in comments]
    return "\n".join(lines) + "\n"


def command_fns_config_init_map(
    json_path,
    local=False,
    verbose=False,
    normalise=False,
    dry_run=False,
    extra_meta=False,
):
    """Add previously unseen exact FNS users to fns.user_names."""
    source = Path(json_path)
    try:
        entries = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise errors.UserError("fns-config: invalid JSON: {}".format(exc))
    if not isinstance(entries, list):
        raise errors.UserError("fns-config: expected a JSON array")
    if local:
        config_path = find_fns_config(os.getcwd())
        if config_path is None:
            config_path = Path.cwd() / settings.PROJECT_CONFIG_NAME
    else:
        config_path = Path(settings.CONFIG_PATH_DAVO_TOOLS).expanduser()
    try:
        config_text = (
            config_path.read_text(encoding="utf-8")
            if config_path.exists()
            else ""
        )
        contents = yaml.safe_load(config_text) or {}
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
    user_names = fns.setdefault("user_names", {})
    if not isinstance(user_names, dict):
        raise errors.UserError("Invalid fns.user_names: expected a mapping")
    preserved_comments = _existing_user_comments(config_text, user_names)
    seen_users = set()
    metadata = defaultdict(lambda: defaultdict(list))
    changes = []
    for entry in entries:
        try:
            receipt = entry["ticket"]["document"]["receipt"]
            user = str(receipt["user"])
        except (KeyError, TypeError):
            continue
        if not isinstance(receipt, dict) or not user:
            continue
        if extra_meta:
            _add_fns_metadata(metadata, user, receipt)
        if user in seen_users:
            continue
        seen_users.add(user)
        if user in user_names:
            changes.append(("existing", user, user_names[user]))
            continue
        user_name = _normalise_user(user) if normalise else ""
        user_names[user] = user_name
        changes.append(("added", user, user_name))
    if dry_run:
        logger.info("fns-config: would update %s", config_path)
    else:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            _dump_fns_config(
                contents,
                {
                    user: metadata[user]
                    for status, user, _user_name in changes
                    if status == "added" and extra_meta
                },
                preserved_comments,
            ),
            encoding="utf-8",
        )
        logger.info("fns-config: updated %s", config_path)
    if verbose or dry_run:
        for status, user, user_name in changes:
            action = "would add" if dry_run and status == "added" else status
            logger.info("fns-config: %s %s -> %s", action, user, user_name)
            if dry_run and extra_meta and status == "added":
                for comment in _metadata_comments(metadata[user]):
                    logger.info("fns-config: would add %s", comment)


def command_fns_config_show_map():
    user_names, config_path = load_fns_user_names(os.getcwd())
    logger.info("fns-config: %s", config_path or "no project config")
    for source, target in sorted(user_names.items()):
        logger.info("%s: %s", source, target)
