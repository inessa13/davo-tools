"""Personal-accounting commands."""

import csv
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

from davo import errors
from davo.utils import conf

_DATE_RE = re.compile(r"^\d{2}\.\d{2}\.\d{4}$")
_TIME_RE = re.compile(r"^\d{2}:\d{2}$")
_AMOUNT_RE = re.compile(r"[+-]?(?:\d{1,3}(?:[ \u00a0]\d{3})*|\d+),\d{2}")
_FOOTER_MARKERS = (
    "дата формирования документа",
    "продолжение на следующей странице",
    "лицензия банка россии",
)
_CSV_HEADER = (
    "Дата",
    "external_id",
    "место",
    "Операция",
    "Статья",
    "Комент",
    "Сумма",
)
_OZON_CSV_HEADER = _CSV_HEADER + ("Оригинал",)
_OZON_DATE_TIME_RE = re.compile(r"^\d{2}\.\d{2}\.\d{4}\s+\d{2}:\d{2}:\d{2}$")
_OZON_ACCOUNT_RE = re.compile(
    r"Account number:\s*№\s*(.+?)(?:,|\s+dated\s|\n)"
)
_OZON_TOTAL_RE = re.compile(
    r"Total (deposits|withdrawals) for the period:\s*RUR\s*([\d ]+\.\d{2})"
)


def _join_words(words):
    """Join PDF words in visual reading order, preserving line boundaries."""
    lines = []
    for word in sorted(words, key=lambda item: (round(item[1], 1), item[0])):
        if not lines or abs(word[1] - lines[-1][0]) > 2:
            lines.append((word[1], [word[4]]))
        else:
            lines[-1][1].append(word[4])
    return "\n".join(" ".join(line) for _y, line in lines)


def _amount(value):
    match = _AMOUNT_RE.search(value.replace("\u202f", "\u00a0"))
    if match is None:
        raise errors.UserError("Missing operation amount: {}".format(value))
    raw = (
        match.group().replace("\u00a0", "").replace(" ", "").replace(",", ".")
    )
    try:
        return Decimal(raw)
    except InvalidOperation as exc:
        raise errors.UserError(
            "Invalid operation amount: {}".format(value)
        ) from exc


def _normalised_amount(value):
    """Return an expense-import amount (credits are negative)."""
    return (
        -abs(_amount(value))
        if value.lstrip().startswith("+")
        else abs(_amount(value))
    )


def _line_words(words, y, x0=470):
    return _join_words(
        [word for word in words if x0 <= word[0] and abs(word[1] - y) < 4]
    )


def _statement_totals(page):
    words = page.get_text("words", sort=True)
    totals = {}
    for label in ("Пополнение", "Списание"):
        candidates = [
            word for word in words if word[4] == label and word[0] > 300
        ]
        if len(candidates) != 1:
            raise errors.UserError(
                "Missing {} total in statement".format(label)
            )
        value = _line_words(words, candidates[0][1])
        totals[label] = abs(_amount(value))
    return totals["Пополнение"], totals["Списание"]


def _date_starts(words, y_min):
    starts = []
    for word in words:
        if (
            word[0] < 140
            and y_min <= word[1] < 800
            and _DATE_RE.match(word[4])
        ):
            if not starts or word[1] - starts[-1] > 20:
                starts.append(word[1])
    return starts


def _table_start(words):
    """Find the first operation line on a first or continuation page."""
    captions = [word[1] for word in words if word[4] == "Расшифровка"]
    if captions:
        return max(captions) + 40
    headings = [
        word[1] for word in words if word[4] == "ДАТА" and word[0] < 100
    ]
    return max(headings) + 40 if headings else None


def _table_end(words, table_start):
    """Return the first recognised page footer after the operations table."""
    footer_starts = []
    line_starts = {word[1] for word in words if table_start <= word[1] < 800}
    for line_start in line_starts:
        line = _join_words(
            [word for word in words if abs(word[1] - line_start) < 2]
        ).casefold()
        if any(marker in line for marker in _FOOTER_MARKERS):
            footer_starts.append(line_start)
    return min(footer_starts, default=800)


def _card_rows(page):
    words = page.get_text("words", sort=True)
    table_start = _table_start(words)
    if table_start is None:
        return []
    starts = _date_starts(words, table_start)
    table_end = _table_end(words, table_start)
    rows = []
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else table_end
        left = [
            word
            for word in words
            if 40 <= word[0] < 145 and start - 1 <= word[1] < end
        ]
        dates = [word[4] for word in left if _DATE_RE.match(word[4])]
        times = [word[4] for word in left if _TIME_RE.match(word[4])]
        codes = [word[4] for word in left if re.match(r"^\d{6}$", word[4])]
        descriptions = [
            word
            for word in words
            if 145 <= word[0] < 390 and start - 1 <= word[1] < end
        ]
        if not dates or not descriptions:
            raise errors.UserError("Incomplete card operation in PDF")
        raw = _join_words(descriptions).replace("\n", " ")
        amount_words = [
            word
            for word in words
            if 390 <= word[0] < 480 and start - 1 <= word[1] < end
        ]
        rows.append(
            (
                dates[0],
                times[0] if times else "00:00",
                codes[0] if codes else "",
                raw,
                _normalised_amount(_join_words(amount_words)),
            )
        )
    return rows


def _account_rows(page):
    words = page.get_text("words", sort=True)
    table_start = _table_start(words)
    if table_start is None:
        return []
    starts = _date_starts(words, table_start)
    table_end = _table_end(words, table_start)
    rows = []
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else table_end
        operation_words = [
            word
            for word in words
            if 40 <= word[0] < 245
            and start - 1 <= word[1] < end
            and not _DATE_RE.match(word[4])
        ]
        amount_words = [
            word
            for word in words
            if 425 <= word[0] < 490 and start - 1 <= word[1] < end
        ]
        if not operation_words or not amount_words:
            raise errors.UserError("Incomplete account operation in PDF")
        raw = _join_words(operation_words).replace("\n", " ")
        rows.append(
            (
                next(
                    word[4]
                    for word in words
                    if word[0] < 140
                    and abs(word[1] - start) < 2
                    and _DATE_RE.match(word[4])
                ),
                "00:00",
                "",
                raw,
                _normalised_amount(_join_words(amount_words)),
            )
        )
    return rows


def _load_rules_config(start, name):
    """Load and validate bank conversion rules before processing PDFs."""
    contents, _user_path, _project_path = conf.load_davo_config(start)
    try:
        settings = contents.get("pa", {}).get(name, {})
        rules = settings.get("rules", [])
    except AttributeError as exc:
        raise errors.UserError(
            "Invalid pa.{} configuration".format(name)
        ) from exc
    if not isinstance(rules, list):
        raise errors.UserError(
            "Invalid pa.{}.rules: expected a list".format(name)
        )
    result = []
    for rule in rules:
        if not isinstance(rule, dict) or set(rule) - {
            "pattern",
            "action",
            "value",
        }:
            raise errors.UserError("Invalid pa.{} rule".format(name))
        if not all(
            isinstance(rule.get(key), str) for key in ("pattern", "action")
        ) or rule["action"] not in {
            "remove",
            "replace",
            "place",
            "category",
        }:
            raise errors.UserError("Invalid pa.{} rule".format(name))
        requires_value = rule["action"] in {
            "replace",
            "place",
            "category",
        }
        if requires_value and not isinstance(rule.get("value"), str):
            raise errors.UserError("Invalid pa.{} rule".format(name))
        try:
            pattern = re.compile(rule["pattern"])
        except re.error as exc:
            raise errors.UserError(
                "Invalid pa.{} rule pattern: {}".format(name, exc)
            ) from exc
        value = rule.get("value", "")
        if rule["action"] in {"replace", "place", "category"}:
            try:
                # re.sub validates all numeric and named group references.
                pattern.sub(value, "")
            except (re.error, IndexError) as exc:
                raise errors.UserError(
                    "Invalid pa.{} rule value: {}".format(name, exc)
                ) from exc
        result.append((pattern, rule["action"], value))
    return result


def _load_sber2csv_config(start):
    """Load and validate Sber conversion rules before processing PDFs."""
    return _load_rules_config(start, "sber2csv")


def _load_ozon2csv_config(start):
    """Load and validate Ozon conversion rules before processing PDFs."""
    return _load_rules_config(start, "ozon2csv")


def _apply_rules(operation, rules):
    """Normalise an operation and extract its place and category."""
    place = ""
    category = ""
    category_found = False
    for pattern, action, value in rules:
        if action == "remove":
            operation = pattern.sub("", operation)
        elif action == "replace":
            operation = pattern.sub(value, operation)
        elif action == "place" and not place:
            match = pattern.search(operation)
            if match:
                place = match.expand(value)
                operation = pattern.sub("", operation, count=1)
        elif action == "category" and not category_found:
            match = pattern.search(operation)
            if match:
                category = match.expand(value)
                category_found = True
                operation = pattern.sub("", operation, count=1)
    return place, category, " ".join(operation.split())


def _parse_statement(path, rules, original_comment=True):
    try:
        import fitz  # pylint: disable=import-outside-toplevel
    except ImportError as exc:
        raise errors.UserError(
            "Missing PyMuPDF; install davo-tools[full]"
        ) from exc
    try:
        document = fitz.open(path)
    except (
        Exception
    ) as exc:  # PyMuPDF exposes several document-specific errors.
        raise errors.UserError(
            "Cannot read PDF {}: {}".format(path, exc)
        ) from exc
    with document:
        first_text = document[0].get_text()
        card = any(
            title in first_text
            for title in (
                "Выписка по платёжному счёту",
                "Выписка по счёту дебетовой карты",
                "Выписка по счёту кредитной карты",
            )
        )
        account = "Выписка по счёту" in first_text and not card
        if not card and not account:
            raise errors.UserError(
                "Not a supported Sber statement: {}".format(path)
            )
        income, expense = _statement_totals(document[0])
        parsed = []
        for page in document:
            parsed.extend(_card_rows(page) if card else _account_rows(page))
    if not parsed:
        raise errors.UserError(
            "No operations found in statement: {}".format(path)
        )
    actual_income = sum(
        (abs(amount) for *_rest, amount in parsed if amount < 0), Decimal()
    )
    actual_expense = sum(
        (amount for *_rest, amount in parsed if amount > 0), Decimal()
    )
    if actual_income != income or actual_expense != expense:
        message = "Totals do not match {} (income {} != {}, "
        message += "expense {} != {})"
        raise errors.UserError(
            message.format(
                path,
                actual_income,
                income,
                actual_expense,
                expense,
            )
        )
    result = []
    for date, time, code, raw, amount in parsed:
        place, category, operation = _apply_rules(raw, rules)
        result.append(
            (
                "{} {}:00".format(date, time),
                code,
                place,
                operation,
                category,
                raw if original_comment else "",
                _format_amount(amount),
            )
        )
    return result


def _format_amount(value):
    return "{:,.2f}".format(value).replace(",", " ")


def _ozon_amount(value):
    """Parse an Ozon amount such as ``- RUR 2 728.52``."""
    match = re.search(r"([+-])\s*RUR\s*([\d ]+\.\d{2})", value)
    if match is None:
        raise errors.UserError(
            "Missing Ozon operation amount: {}".format(value)
        )
    return Decimal(match.group(2).replace(" ", "")) * (
        1 if match.group(1) == "+" else -1
    )


def _ozon_account(page):
    match = _OZON_ACCOUNT_RE.search(page.get_text())
    if match is None:
        raise errors.UserError("Missing account number in Ozon statement")
    return match.group(1).strip()


def _ozon_page_rows(page):
    """Extract Ozon table rows, using its fixed four-column layout."""
    words = page.get_text("words", sort=True)
    starts = [
        word[1]
        for word in words
        if word[0] < 145 and _DATE_RE.match(word[4])
    ]
    rows = []
    total_positions = [
        word[1] for word in words if word[4] == "Total" and word[0] < 150
    ]
    table_end = min(total_positions, default=float("inf"))
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else table_end
        row_words = [
            word for word in words if start - 1 <= word[1] < end
        ]
        date_words = [word[4] for word in row_words if word[0] < 145]
        if len(date_words) < 2 or not _DATE_RE.match(date_words[0]):
            raise errors.UserError("Incomplete Ozon operation in PDF")
        date_time = "{} {}".format(date_words[0], date_words[1])
        if not _OZON_DATE_TIME_RE.match(date_time):
            raise errors.UserError(
                "Invalid Ozon operation date: {}".format(date_time)
            )
        document = _join_words(
            [word for word in row_words if 145 <= word[0] < 220]
        ).replace("\n", " ")
        document = "".join(document.split())
        purpose = _join_words(
            [word for word in row_words if 220 <= word[0] < 340]
        ).replace("\n", " ")
        amount = _join_words(
            [word for word in row_words if 340 <= word[0] < 452]
        ).replace("\n", " ")
        if not document or not purpose or not amount:
            raise errors.UserError("Incomplete Ozon operation in PDF")
        rows.append((date_time, document, purpose, _ozon_amount(amount)))
    return rows


def _ozon_totals(page):
    values = {
        kind: Decimal(amount.replace(" ", ""))
        for kind, amount in _OZON_TOTAL_RE.findall(page.get_text())
    }
    if not values:
        return None
    if set(values) != {"deposits", "withdrawals"}:
        raise errors.UserError("Incomplete totals in Ozon statement")
    return values["deposits"], values["withdrawals"]


def _parse_ozon_statement(path, rules, original_comment=False):
    """Parse all Ozon Operations Statements contained in one PDF."""
    try:
        import fitz  # pylint: disable=import-outside-toplevel
    except ImportError as exc:
        raise errors.UserError(
            "Missing PyMuPDF; install davo-tools[full]"
        ) from exc
    try:
        document = fitz.open(path)
    except Exception as exc:  # PyMuPDF exposes document-specific errors.
        raise errors.UserError(
            "Cannot read PDF {}: {}".format(path, exc)
        ) from exc
    result = []
    active_account = None
    statement_rows = []
    found = False
    with document:
        for page in document:
            text = page.get_text()
            if "Operations Statement" in text:
                if active_account is not None:
                    raise errors.UserError("Missing totals in Ozon statement")
                active_account = _ozon_account(page)
                found = True
            if active_account is None:
                continue
            statement_rows.extend(_ozon_page_rows(page))
            totals = _ozon_totals(page)
            if totals is None:
                continue
            if not statement_rows:
                raise errors.UserError("No operations found in Ozon statement")
            deposits = sum(
                (amount for *_rest, amount in statement_rows if amount > 0),
                Decimal(),
            )
            withdrawals = sum(
                (-amount for *_rest, amount in statement_rows if amount < 0),
                Decimal(),
            )
            if (deposits, withdrawals) != totals:
                raise errors.UserError(
                    "Totals do not match {} (deposits {} != {}, withdrawals "
                    "{} != {})".format(
                        path, deposits, totals[0], withdrawals, totals[1]
                    )
                )
            for date_time, number, raw, amount in statement_rows:
                place, category, operation = _apply_rules(raw, rules)
                result.append(
                    (
                        date_time,
                        "O{}_{}".format(active_account, number),
                        place,
                        operation,
                        category,
                        "",
                        _format_amount(amount),
                    )
                    + ((raw,) if original_comment else ())
                )
            active_account = None
            statement_rows = []
    if not found:
        raise errors.UserError(
            "Not a supported Ozon statement: {}".format(path)
        )
    if active_account is not None:
        raise errors.UserError("Missing totals in Ozon statement")
    if not result:
        raise errors.UserError(
            "No operations found in statement: {}".format(path)
        )
    return result


def _input_pdfs(paths):
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


def command_sber2csv(  # pylint: disable=too-many-positional-arguments
    paths,
    out_path=None,
    dry_run=False,
    verbose=False,
    rewrite=False,
    original_comment=False,
):
    """Convert supported Sber PDF statements, validating all output first."""
    inputs = _input_pdfs(paths)
    if out_path and len(inputs) != 1:
        raise errors.UserError("-o/--out requires exactly one PDF input")
    rules = _load_sber2csv_config(Path.cwd())
    plan = []
    targets = set()
    explicit = Path(out_path).expanduser() if out_path else None
    requested = {Path(value).expanduser() for value in paths}
    for source in inputs:
        try:
            rows = _parse_statement(
                source,
                rules,
                original_comment=original_comment,
            )
        except errors.UserError as exc:
            if source in requested or not str(exc).startswith(
                "Not a supported"
            ):
                raise
            if verbose:
                print("skip unsupported PDF: {}".format(source))
            continue
        target = explicit or source.with_name(source.stem + ".csv")
        if target in targets:
            raise errors.UserError(
                "Duplicate output target: {}".format(target)
            )
        if target.exists() and (explicit or not rewrite):
            raise errors.UserError("Output already exists: {}".format(target))
        plan.append((target, rows))
        targets.add(target)
    if not plan:
        raise errors.UserError("No supported Sber statements found")
    if dry_run:
        for target, _rows in plan:
            print(target)
        return
    for target, rows in plan:
        with target.open("w", encoding="utf-8-sig", newline="") as file:
            writer = csv.writer(file)
            writer.writerow(_CSV_HEADER)
            writer.writerows(rows)


def command_ozon2csv(  # pylint: disable=too-many-positional-arguments
    paths, out_path=None, dry_run=False, verbose=False, rewrite=False,
    original_comment=False,
):
    """Convert Ozon Bank Operations Statements to expense CSV."""
    inputs = _input_pdfs(paths)
    if out_path and len(inputs) != 1:
        raise errors.UserError("-o/--out requires exactly one PDF input")
    rules = _load_ozon2csv_config(Path.cwd())
    plan = []
    targets = set()
    explicit = Path(out_path).expanduser() if out_path else None
    requested = {Path(value).expanduser() for value in paths}
    for source in inputs:
        try:
            rows = _parse_ozon_statement(
                source, rules, original_comment=original_comment
            )
        except errors.UserError as exc:
            if source in requested or not str(exc).startswith(
                "Not a supported"
            ):
                raise
            if verbose:
                print("skip unsupported PDF: {}".format(source))
            continue
        target = explicit or source.with_name(source.stem + ".csv")
        if target in targets:
            raise errors.UserError(
                "Duplicate output target: {}".format(target)
            )
        if target.exists() and (explicit or not rewrite):
            raise errors.UserError("Output already exists: {}".format(target))
        plan.append((target, rows))
        targets.add(target)
    if not plan:
        raise errors.UserError("No supported Ozon statements found")
    if dry_run:
        for target, _rows in plan:
            print(target)
        return
    for target, rows in plan:
        with target.open("w", encoding="utf-8-sig", newline="") as file:
            writer = csv.writer(file)
            writer.writerow(
                _OZON_CSV_HEADER if original_comment else _CSV_HEADER
            )
            writer.writerows(rows)
