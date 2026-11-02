import csv
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from davo import errors
from davo.services import pa, revolut


def _page(text, words):
    def get_text(kind=None, sort=False):
        del sort
        return words if kind == "words" else text

    return SimpleNamespace(get_text=get_text)


class _PdfDocument(list):
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        del exc_type, exc_value, traceback


def _word(x, y, value):
    return (x, y, 0, 0, value, 0, 0, 0)


def _words(x, y, value):
    result = []
    for item in value.split():
        result.append(_word(x, y, item))
        x += len(item) * 5 + 3
    return result


def _mock_pdf(mocker, pages):
    fitz = SimpleNamespace(
        open=mocker.Mock(return_value=_PdfDocument(pages))
    )
    mocker.patch.dict("sys.modules", {"fitz": fitz})


def _summary_words(language, values):
    product = (
        "Счет (текущий счет)"
        if language == "ru"
        else "Account (Current Account)"
    )
    total = "Итого" if language == "ru" else "Total"
    words = _words(10, 100, product)
    words.extend(_word(x, 100, value) for x, value in zip(
        (220, 310, 400, 500), values
    ))
    words.extend(_words(10, 120, total))
    words.extend(_word(x, 120, value) for x, value in zip(
        (220, 310, 400, 500), values
    ))
    return words


def _header_words(language):
    if language == "ru":
        return [
            _word(10, 200, "Дата"),
            _word(120, 200, "Описание"),
            _word(300, 200, "Списания"),
            _word(390, 200, "Пополнения"),
            _word(500, 200, "Остаток"),
        ]
    return [
        _word(10, 200, "Date"),
        _word(120, 200, "Description"),
        _word(300, 200, "Money"),
        _word(340, 200, "out"),
        _word(390, 200, "Money"),
        _word(430, 200, "in"),
        _word(500, 200, "Balance"),
    ]


def _row(date, description, *, money_out="", money_in="", balance, y):
    words = _words(10, y, date)
    words.extend(_words(120, y, description))
    if money_out:
        words.append(_word(300, y, money_out))
    if money_in:
        words.append(_word(390, y, money_in))
    words.append(_word(500, y, balance))
    return words


def _first_page(language, summary, rows, details=()):
    if language == "ru":
        text = (
            "Выписка для EUR\nСведения о балансе\n"
            "Операции по счету"
        )
    else:
        text = "EUR Statement\nBalance summary\nAccount transactions"
    words = _summary_words(language, summary) + _header_words(language)
    for row in rows:
        words.extend(row)
    for y, detail in details:
        words.extend(_words(120, y, detail))
    return _page(text, words)


def _continuation_page(language, rows, details=()):
    words = _header_words(language)
    for row in rows:
        words.extend(row)
    for y, detail in details:
        words.extend(_words(120, y, detail))
    return _page("", words)


def test_revolut_parses_russian_multpage_statement(mocker):
    first = _first_page(
        "ru",
        ("1 000,00€", "35,50€", "100,00€", "1 064,50€"),
        [
            _row(
                "2 янв. 2026г.",
                "Магазин, \"У дома\"",
                money_out="25,50€",
                balance="974,50€",
                y=220,
            ),
            _row(
                "3 февраля 2026г.",
                "Перевод, отправитель: TEST USER",
                money_in="100,00€",
                balance="1 074,50€",
                y=250,
            ),
        ],
        details=[(228, "Карта: 1234")],
    )
    second = _continuation_page(
        "ru",
        [
            _row(
                "4 мар. 2026г.",
                "Неизвестная операция",
                money_out="10,00€",
                balance="1 064,50€",
                y=220,
            )
        ],
    )
    _mock_pdf(mocker, [first, second])

    rows = revolut.parse_statement("statement.pdf")

    assert [row[0] for row in rows] == [
        "Платеж по карте",
        "Переводы",
        "",
    ]
    assert rows[0] == (
        "Платеж по карте",
        "Текущий",
        "2026-01-02 00:00:00",
        "2026-01-02 00:00:00",
        "Магазин, \"У дома\"",
        "-25.50",
        "0.00",
        "EUR",
        "ВЫПОЛНЕНО",
        "974.50",
    )
    assert rows[1][2] == "2026-02-03 00:00:00"
    assert rows[1][5] == "100.00"
    assert rows[2][2] == "2026-03-04 00:00:00"


def test_revolut_parses_english_months_and_decimal_points(mocker):
    page = _first_page(
        "en",
        ("€1,000.00", "€6.00", "€10.25", "€1,004.25"),
        [
            _row(
                "September 1, 2026",
                "Transfer from TEST USER",
                money_in="€10.25",
                balance="€1,010.25",
                y=220,
            ),
            _row(
                "Oct 2, 2026",
                "Coffee Shop",
                money_out="€6.00",
                balance="€1,004.25",
                y=250,
            ),
        ],
        details=[(258, "Card: 1234")],
    )
    _mock_pdf(mocker, [page])

    rows = revolut.parse_statement("statement.pdf")

    assert [row[0] for row in rows] == ["Переводы", "Платеж по карте"]
    assert [row[4] for row in rows] == [
        "Transfer from TEST USER",
        "Coffee Shop",
    ]
    assert [row[5] for row in rows] == ["10.25", "-6.00"]


@pytest.mark.parametrize(
    ("summary", "row_balance", "message"),
    [
        (
            ("100,00€", "10,00€", "0,00€", "90,00€"),
            "91,00€",
            "transaction balance mismatch",
        ),
        (
            ("100,00€", "11,00€", "0,00€", "89,00€"),
            "90,00€",
            "transaction totals mismatch",
        ),
    ],
)
def test_revolut_rejects_balance_and_total_mismatches(
    mocker, summary, row_balance, message
):
    page = _first_page(
        "ru",
        summary,
        [
            _row(
                "1 окт. 2026г.",
                "Покупка",
                money_out="10,00€",
                balance=row_balance,
                y=220,
            )
        ],
    )
    _mock_pdf(mocker, [page])

    with pytest.raises(pa.errors.UserError, match=message):
        revolut.parse_statement("statement.pdf")


def test_revolut_rejects_unsupported_structure(mocker):
    _mock_pdf(mocker, [_page("Some other PDF", [])])

    with pytest.raises(pa.errors.UserError, match="Not a supported"):
        revolut.parse_statement("statement.pdf")


def test_revolut_rejects_opening_and_closing_balance_mismatch(mocker):
    page = _first_page(
        "en",
        ("€100.00", "€10.00", "€0.00", "€91.00"),
        [
            _row(
                "Oct 1, 2026",
                "Card payment",
                money_out="€10.00",
                balance="€90.00",
                y=220,
            )
        ],
    )
    _mock_pdf(mocker, [page])

    with pytest.raises(pa.errors.UserError, match="opening and closing"):
        revolut.parse_statement("statement.pdf")


def _valid_row(description="Description, with \"quotes\""):
    return (
        "",
        "Текущий",
        "2026-01-01 00:00:00",
        "2026-01-01 00:00:00",
        description,
        "1.00",
        "0.00",
        "EUR",
        "ВЫПОЛНЕНО",
        "1.00",
    )


def test_revo2csv_writes_exact_utf8_schema_and_quoted_values(
    mocker, tmp_path
):
    source = tmp_path / "statement.pdf"
    target = tmp_path / "statement.csv"
    source.touch()
    mocker.patch.object(
        revolut, "parse_statement", return_value=[_valid_row()]
    )

    pa.command_revo2csv([source])

    raw = target.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    with target.open(encoding="utf-8", newline="") as file:
        assert list(csv.reader(file)) == [
            list(revolut.CSV_HEADER),
            list(_valid_row()),
        ]
    assert b'"Description, with ""quotes"""' in raw


def test_revo2csv_rejects_entire_batch_before_writing(mocker, tmp_path):
    first = tmp_path / "first.pdf"
    second = tmp_path / "second.pdf"
    first.touch()
    second.touch()

    def parse(path):
        if path == second:
            raise pa.errors.UserError("Revolut transaction totals mismatch")
        return [_valid_row()]

    mocker.patch.object(revolut, "parse_statement", side_effect=parse)

    with pytest.raises(pa.errors.UserError, match="totals mismatch"):
        pa.command_revo2csv([first, second])

    assert not first.with_suffix(".csv").exists()
    assert not second.with_suffix(".csv").exists()


def test_revo2csv_rolls_back_whole_batch_if_commit_fails(mocker, tmp_path):
    first = tmp_path / "first.pdf"
    second = tmp_path / "second.pdf"
    first_target = first.with_suffix(".csv")
    second_target = second.with_suffix(".csv")
    first.touch()
    second.touch()
    first_target.write_text("original", encoding="utf-8")
    mocker.patch.object(
        revolut, "parse_statement", return_value=[_valid_row()]
    )
    original_replace = Path.replace

    def replace(path, target):
        if path.suffix == ".tmp" and Path(target) == second_target:
            raise OSError("simulated commit failure")
        return original_replace(path, target)

    mocker.patch.object(Path, "replace", replace)

    with pytest.raises(pa.errors.UserError, match="Cannot write"):
        pa.command_revo2csv([first, second], rewrite=True)

    assert first_target.read_text(encoding="utf-8") == "original"
    assert not second_target.exists()
    assert not list(tmp_path.glob(".*.tmp"))
    assert not list(tmp_path.glob(".*.backup"))


def test_revo2csv_dry_run_validates_batch_without_writing(
    mocker, tmp_path, capsys
):
    source = tmp_path / "statement.pdf"
    source.touch()
    mocker.patch.object(
        revolut, "parse_statement", return_value=[_valid_row()]
    )

    pa.command_revo2csv([source], dry_run=True)

    assert capsys.readouterr().out.strip() == str(source.with_suffix(".csv"))
    assert not source.with_suffix(".csv").exists()


def test_revo2csv_rewrite_only_applies_to_automatic_target(mocker, tmp_path):
    source = tmp_path / "statement.pdf"
    automatic = source.with_suffix(".csv")
    explicit = tmp_path / "explicit.csv"
    source.touch()
    automatic.write_text("old", encoding="utf-8")
    explicit.write_text("old", encoding="utf-8")
    mocker.patch.object(
        revolut, "parse_statement", return_value=[_valid_row()]
    )

    pa.command_revo2csv([source], rewrite=True)
    assert automatic.read_text(encoding="utf-8") != "old"

    with pytest.raises(pa.errors.UserError, match="already exists"):
        pa.command_revo2csv(
            [source], out_path=explicit, rewrite=True
        )
    assert explicit.read_text(encoding="utf-8") == "old"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("15 нояб. 2026г.", (2026, 11, 15)),
        ("2 ноября 2026", (2026, 11, 2)),
        ("1 сент. 2026", (2026, 9, 1)),
        ("3 февр. 2026", (2026, 2, 3)),
        ("4 мар. 2026", (2026, 3, 4)),
        ("5 мая 2026", (2026, 5, 5)),
        ("6 май 2026", (2026, 5, 6)),
        ("7 июн. 2026", (2026, 6, 7)),
        ("8 июл. 2026", (2026, 7, 8)),
        ("Sept 9, 2026", (2026, 9, 9)),
        ("September 10, 2026", (2026, 9, 10)),
        ("Oct 11, 2026", (2026, 10, 11)),
        ("12 Dec 2026", (2026, 12, 12)),
    ],
)
def test_revolut_parses_month_name_variants(value, expected):
    parsed = revolut._date(value)  # pylint: disable=protected-access
    assert parsed == datetime(*expected)


def test_revolut_rejects_unknown_month():
    with pytest.raises(errors.UserError, match="Unsupported Revolut"):
        revolut._date("1 xyz 2026")  # pylint: disable=protected-access
