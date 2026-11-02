"""Revolut PDF statement parsing and CSV conversion."""

import csv
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from davo import errors

from . import pa_common

CSV_HEADER = (
    "Тип",
    "Продукт",
    "Дата начала",
    "Дата выполнения",
    "Описание",
    "Сумма",
    "Комиссия",
    "Валюта",
    "State",
    "Остаток средств",
)

_LANGUAGES = {
    "ru": {
        "title": "Выписка для",
        "summary": "Сведения о балансе",
        "transactions": "Операции по счету",
        "date": "Дата",
        "description": "Описание",
        "out": "Списания",
        "in": "Пополнения",
        "balance": "Остаток",
        "product": "Счет (текущий счет)",
        "total": "Итого",
    },
    "en": {
        "title": "Statement",
        "summary": "Balance summary",
        "transactions": "Account transactions",
        "date": "Date",
        "description": "Description",
        "out": "Money out",
        "in": "Money in",
        "balance": "Balance",
        "product": "Account (Current Account)",
        "total": "Total",
    },
}
_MONTH_STEMS = (
    ("jan", "янв"),
    ("feb", "фев"),
    ("mar", "мар"),
    ("apr", "апр"),
    ("may", "ма[йя]"),
    ("jun", "июн"),
    ("jul", "июл"),
    ("aug", "авг"),
    ("sep", "сен"),
    ("oct", "окт"),
    ("nov", "ноя"),
    ("dec", "дек"),
)
_MONEY_RE = re.compile(
    r"[+-]?(?:\d{1,3}(?:[ \u00a0\u202f.,]\d{3})+|\d+)"
    r"[.,]\d{2}"
)


@dataclass(frozen=True)
class _PdfLine:
    y: float
    words: tuple

    @property
    def text(self):
        return " ".join(word[4] for word in self.words)


@dataclass(frozen=True)
class _Transaction:
    date: datetime
    description: str
    amount: Decimal
    balance: Decimal
    kind: str


def _pdf_lines(words):
    lines = []
    for word in sorted(words, key=lambda item: (item[1], item[0])):
        if not lines or abs(word[1] - lines[-1][0]) > 2:
            lines.append([word[1], [word]])
        else:
            lines[-1][1].append(word)
    return [
        _PdfLine(y, tuple(sorted(items, key=lambda item: item[0])))
        for y, items in lines
    ]


def _normalise_space(value):
    return " ".join(value.replace("\u00a0", " ").split())


def _language(text):
    normalised = _normalise_space(text).casefold()
    matches = []
    for language, labels in _LANGUAGES.items():
        required = (
            labels["title"],
            labels["summary"],
            labels["transactions"],
        )
        if all(item.casefold() in normalised for item in required):
            matches.append(language)
    if len(matches) != 1:
        raise errors.UserError("Not a supported Revolut statement template")
    return matches[0]


def _currency(text, language):
    if language == "ru":
        pattern = r"Выписка\s+для\s+([A-Z]{3})\b"
    else:
        pattern = r"\b([A-Z]{3})\s+Statement\b"
    match = re.search(pattern, text, re.IGNORECASE)
    if match is None:
        raise errors.UserError("Missing Revolut statement currency")
    return match.group(1).upper()


def _decimal(value):
    match = _MONEY_RE.search(value)
    if match is None:
        raise errors.UserError("Invalid Revolut amount: {}".format(value))
    raw = match.group().replace(" ", "").replace("\u00a0", "")
    raw = raw.replace("\u202f", "")
    comma = raw.rfind(",")
    point = raw.rfind(".")
    decimal_separator = "," if comma > point else "."
    thousands_separator = "." if decimal_separator == "," else ","
    raw = raw.replace(thousands_separator, "")
    raw = raw.replace(decimal_separator, ".")
    try:
        return Decimal(raw)
    except InvalidOperation as exc:
        raise errors.UserError(
            "Invalid Revolut amount: {}".format(value)
        ) from exc


def _line_amounts(line):
    return [_decimal(match.group()) for match in _MONEY_RE.finditer(line.text)]


def _summary(lines, language):
    labels = _LANGUAGES[language]
    product_lines = [
        line
        for line in lines
        if line.text.casefold().startswith(labels["product"].casefold())
    ]
    total_lines = [
        line
        for line in lines
        if line.text.casefold().startswith(labels["total"].casefold())
    ]
    if len(product_lines) != 1 or len(total_lines) != 1:
        raise errors.UserError("Unsupported Revolut balance summary")
    account = _line_amounts(product_lines[0])
    total = _line_amounts(total_lines[0])
    if len(account) != 4 or len(total) != 4 or account != total:
        raise errors.UserError("Invalid Revolut balance summary totals")
    opening, money_out, money_in, closing = account
    if opening - money_out + money_in != closing:
        raise errors.UserError("Revolut opening and closing balances mismatch")
    return opening, money_out, money_in, closing


def _month(value):
    key = value.casefold().rstrip(".").replace("ё", "е")
    for number, stems in enumerate(_MONTH_STEMS, start=1):
        if any(re.match(stem, key) for stem in stems):
            return number
    raise errors.UserError(
        "Unsupported Revolut statement month: {}".format(value)
    )


def _date(value):
    cleaned = _normalise_space(value)
    cleaned = re.sub(r"(?i)(\d{4})\s*г\.?$", r"\1", cleaned)
    day_first = re.fullmatch(
        r"(\d{1,2})\s+([A-Za-zА-Яа-яЁё.]+),?\s+(\d{4})",
        cleaned,
    )
    month_first = re.fullmatch(
        r"([A-Za-z.]+)\s+(\d{1,2}),?\s+(\d{4})",
        cleaned,
    )
    if day_first is not None:
        day, month_name, year = day_first.groups()
    elif month_first is not None:
        month_name, day, year = month_first.groups()
    else:
        return None
    try:
        return datetime(
            int(year),
            _month(month_name),
            int(day),
        )
    except ValueError as exc:
        raise errors.UserError(
            "Invalid Revolut statement date: {}".format(value)
        ) from exc


def _word_x(lines, value, header_y, minimum_x=0):
    candidates = [
        word[0]
        for line in lines
        if abs(line.y - header_y) < 12
        for word in line.words
        if word[0] >= minimum_x and word[4].casefold() == value.casefold()
    ]
    return min(candidates) if candidates else None


def _columns(lines, language):
    labels = _LANGUAGES[language]
    headers = []
    for line in lines:
        values = [word[4].casefold() for word in line.words]
        if (
            labels["date"].casefold() in values
            and labels["description"].casefold() in values
        ):
            headers.append(line)
    if len(headers) != 1:
        raise errors.UserError("Unsupported Revolut transaction table")
    header = headers[0]
    date_x = _word_x(lines, labels["date"], header.y)
    description_x = _word_x(lines, labels["description"], header.y)
    balance_x = _word_x(lines, labels["balance"], header.y, description_x)
    if language == "ru":
        out_x = _word_x(lines, labels["out"], header.y, description_x)
        in_x = _word_x(lines, labels["in"], header.y, out_x)
    else:
        money_x = sorted(
            word[0]
            for line in lines
            if abs(line.y - header.y) < 3
            for word in line.words
            if word[0] > description_x and word[4].casefold() == "money"
        )
        out_x, in_x = money_x if len(money_x) == 2 else (None, None)
    columns = (date_x, description_x, out_x, in_x, balance_x)
    if None in columns or list(columns) != sorted(columns):
        raise errors.UserError("Unsupported Revolut transaction columns")
    return header.y, columns


def _cell(line, start, end=None):
    return " ".join(
        word[4]
        for word in line.words
        if word[0] >= start and (end is None or word[0] < end)
    )


def _transaction_kind(description, details):
    description_lower = description.casefold()
    details_lower = details.casefold()
    if (
        "card:" in details_lower
        or "карта:" in details_lower
        or description_lower.startswith(
            ("card payment", "платеж по карте", "оплата картой")
        )
    ):
        return "Платеж по карте"
    if description_lower.startswith(("transfer ", "перевод")):
        return "Переводы"
    return ""


def _page_transactions(page, language):
    words = page.get_text("words", sort=True)
    lines = _pdf_lines(words)
    header_y, columns = _columns(lines, language)
    _date_x, description_x, out_x, in_x, balance_x = columns
    dated_lines = []
    for line in lines:
        if line.y <= header_y:
            continue
        parsed = _date(_cell(line, 0, description_x))
        if parsed is not None:
            dated_lines.append((line, parsed))
    result = []
    for index, (line, parsed_date) in enumerate(dated_lines):
        description = _normalise_space(_cell(line, description_x, out_x))
        if not description:
            raise errors.UserError("Missing Revolut transaction description")
        out_value = _cell(line, out_x, in_x)
        in_value = _cell(line, in_x, balance_x)
        balance_value = _cell(line, balance_x)
        has_out = _MONEY_RE.search(out_value) is not None
        has_in = _MONEY_RE.search(in_value) is not None
        if has_out == has_in or _MONEY_RE.search(balance_value) is None:
            raise errors.UserError("Invalid Revolut transaction amounts")
        amount = -_decimal(out_value) if has_out else _decimal(in_value)
        balance = _decimal(balance_value)
        end_y = (
            dated_lines[index + 1][0].y
            if index + 1 < len(dated_lines)
            else float("inf")
        )
        details = " ".join(
            item.text
            for item in lines
            if line.y <= item.y < end_y
        )
        result.append(
            _Transaction(
                parsed_date,
                description,
                amount,
                balance,
                _transaction_kind(description, details),
            )
        )
    return result


def _validate(transactions, summary):
    opening, expected_out, expected_in, expected_closing = summary
    actual_out = sum(
        (-item.amount for item in transactions if item.amount < 0),
        Decimal(),
    )
    actual_in = sum(
        (item.amount for item in transactions if item.amount > 0),
        Decimal(),
    )
    if actual_out != expected_out or actual_in != expected_in:
        raise errors.UserError("Revolut transaction totals mismatch")
    balance = opening
    for item in transactions:
        balance += item.amount
        if balance != item.balance:
            raise errors.UserError(
                "Revolut transaction balance mismatch on {}".format(
                    item.date.strftime("%Y-%m-%d")
                )
            )
    if balance != expected_closing:
        raise errors.UserError("Revolut closing balance mismatch")


def _format(value):
    return format(value, ".2f")


def parse_statement(path):
    """Parse and fully reconcile one Russian or English Revolut PDF."""
    try:
        import fitz  # pylint: disable=import-outside-toplevel
    except ImportError as exc:
        raise errors.UserError(
            "PyMuPDF is required for Revolut PDF statements"
        ) from exc
    try:
        document = fitz.open(path)
    except (OSError, ValueError, RuntimeError) as exc:
        raise errors.UserError("Cannot open PDF: {}".format(path)) from exc
    with document:
        pages = list(document)
        if not pages:
            raise errors.UserError("Empty PDF: {}".format(path))
        first_words = pages[0].get_text("words", sort=True)
        first_text = "{}\n{}".format(
            pages[0].get_text(),
            " ".join(word[4] for word in first_words),
        )
        language = _language(first_text)
        currency = _currency(first_text, language)
        summary = _summary(_pdf_lines(first_words), language)
        transactions = []
        for page in pages:
            transactions.extend(_page_transactions(page, language))
    if not transactions:
        raise errors.UserError(
            "No operations found in Revolut statement: {}".format(path)
        )
    _validate(transactions, summary)
    result = []
    for item in transactions:
        date = item.date.strftime("%Y-%m-%d 00:00:00")
        result.append(
            (
                item.kind,
                "Текущий",
                date,
                date,
                item.description,
                _format(item.amount),
                "0.00",
                currency,
                "ВЫПОЛНЕНО",
                _format(item.balance),
            )
        )
    return result


def _remove_files(paths):
    for path in paths:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


def _stage_csv_files(plan):
    staged = []
    try:
        for target, rows in plan:
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                newline="",
                prefix=".{}-".format(target.name),
                suffix=".tmp",
                dir=target.parent,
                delete=False,
            ) as file:
                staged.append((target, Path(file.name)))
                writer = csv.writer(file)
                writer.writerow(CSV_HEADER)
                writer.writerows(rows)
    except Exception:
        _remove_files(temporary for _target, temporary in staged)
        raise
    return staged


def _commit_csv_files(staged):
    backups = {}
    committed = set()
    try:
        for target, _temporary in staged:
            if not target.exists():
                continue
            with tempfile.NamedTemporaryFile(
                prefix=".{}-".format(target.name),
                suffix=".backup",
                dir=target.parent,
                delete=False,
            ) as file:
                backup = Path(file.name)
            backup.unlink()
            target.replace(backup)
            backups[target] = backup
        for target, temporary in staged:
            temporary.replace(target)
            committed.add(target)
    except OSError as exc:
        _remove_files(target for target in committed)
        for target, backup in backups.items():
            if backup.exists():
                backup.replace(target)
        _remove_files(temporary for _target, temporary in staged)
        raise errors.UserError("Cannot write Revolut CSV output") from exc
    _remove_files(backups.values())


def command(paths, out_path=None, dry_run=False, verbose=False, rewrite=False):
    """Convert supported statements after validating the complete batch."""
    inputs = pa_common.input_pdfs(paths)
    if out_path and len(inputs) != 1:
        raise errors.UserError("-o/--out requires exactly one PDF input")
    options = {
        "out_path": out_path,
        "rewrite": rewrite,
        "verbose": verbose,
        "parser": parse_statement,
    }
    parsed = pa_common.conversion_plan(inputs, paths, **options)
    plan = [(target, rows) for _source, target, rows in parsed]
    if not plan:
        raise errors.UserError("No supported Revolut statements found")
    if dry_run:
        for target, _rows in plan:
            print(target)
        return
    try:
        staged = _stage_csv_files(plan)
    except OSError as exc:
        raise errors.UserError("Cannot write Revolut CSV output") from exc
    _commit_csv_files(staged)
