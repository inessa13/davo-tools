# pylint: disable=too-many-lines

import csv
from types import SimpleNamespace

import pytest

from davo.services import pa


def _rules(*items):
    return [
        (pa.re.compile(item["pattern"]), item["action"], item.get("value", ""))
        for item in items
    ]


_TAIL_RULE = _rules(
    {"pattern": r"\.\s*Операция по (?:карте|счету)\b.*$", "action": "remove"}
)


class _PdfPage:  # pylint: disable=too-few-public-methods
    def __init__(self, text, words):
        self.text = text
        self.words = words

    def get_text(self, kind=None, sort=False):
        del sort
        return self.words if kind == "words" else self.text


class _PdfDocument:
    def __init__(self, pages):
        self.pages = pages

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        del exc_type, exc_value, traceback

    def __getitem__(self, index):
        return self.pages[index]

    def __iter__(self):
        return iter(self.pages)


def _mock_pdf(mocker, pages):
    fitz = SimpleNamespace(
        open=mocker.Mock(return_value=_PdfDocument(pages))
    )
    mocker.patch.dict("sys.modules", {"fitz": fitz})


_OzonPage = _PdfPage
_TBankPage = _PdfPage


def _ozon_word(x, y, value):
    return (x, y, 0, 0, value, 0, 0, 0)


def _tbank_word(x, y, value):
    return (x, y, 0, 0, value, 0, 0, 0)


def _sber_word(x, y, value):
    return (x, y, 0, 0, value, 0, 0, 0)


def _sber_total_words(income, expense):
    return [
        _sber_word(350, 15, "Пополнение"),
        _sber_word(480, 15, income),
        _sber_word(350, 30, "Списание"),
        _sber_word(480, 30, expense),
    ]


def _sber_account_page(
    rows, *, continuation=False, totals=None, title="Выписка по счёту"
):
    heading = _sber_word(
        50,
        50 if continuation else 40,
        "ДАТА" if continuation else "Расшифровка",
    )
    words = [heading]
    if totals is not None:
        words.extend(_sber_total_words(*totals))
    for date, description, amount, y_position in rows:
        words.extend(
            [
                _sber_word(50, y_position, date),
                _sber_word(150, y_position, description),
                _sber_word(450, y_position, amount),
            ]
        )
    return _PdfPage("" if continuation else title, words)


def _sber_card_page(
    rows,
    *,
    totals,
    title="Выписка по платёжному счёту",
    footer=None,
):
    words = [
        _sber_word(50, 40, "Расшифровка"),
        *_sber_total_words(*totals),
    ]
    for date, time, code, description_lines, amount, y_position in rows:
        words.extend(
            [
                _sber_word(50, y_position, date),
                _sber_word(50, y_position + 8, time),
                _sber_word(50, y_position + 16, code),
                _sber_word(400, y_position, amount),
            ]
        )
        words.extend(
            _sber_word(150, y_position + index * 8, line)
            for index, line in enumerate(description_lines)
        )
    if footer is not None:
        words.append(_sber_word(50, footer[0], footer[1]))
    return _PdfPage(title, words)


def _sber_debit_page():
    return _sber_card_page(
        [
            (
                "03.09.2026",
                "10:00",
                "199029",
                [
                    "Перевод на карту",
                    "SBOL. Операция по счету ****0460",
                ],
                "+1 000,00",
                100,
            ),
            (
                "02.09.2026",
                "11:00",
                "835435",
                [
                    "Перевод на карту",
                    "SBOL. Операция по счету ****0460",
                ],
                "+2 000,00",
                160,
            ),
            (
                "01.09.2026",
                "12:00",
                "151502",
                [
                    "Прочие операции",
                    "BRANCH KARTA-CREDIT. Операция по счету ****0460",
                ],
                "-500,00",
                220,
            ),
        ],
        totals=("3 000,00", "500,00"),
    )


def _sber_transfer_page():
    return _sber_card_page(
        [
            (
                "25.07.2026",
                "15:20",
                "887429",
                [
                    "Перевод с карты",
                    "Перевод для Г. Галина Алексеевна.",
                    "Операция по счету ****8546",
                ],
                "-498,00",
                100,
            ),
        ],
        totals=("0,00", "498,00"),
    )


def test_ozon2csv_collects_multiline_purposes_and_first_amount_column():
    page = _OzonPage(
        "",
        [
            _ozon_word(55, 100, "01.02.2026"),
            _ozon_word(102, 100, "10:20:30"),
            _ozon_word(160, 100, "123"),
            _ozon_word(225, 100, "Payment"),
            _ozon_word(225, 115, "purpose"),
            _ozon_word(380, 100, "- RUR 10.50"),
            _ozon_word(484, 100, "- RUR 10.50"),
            _ozon_word(55, 140, "02.02.2026"),
            _ozon_word(102, 140, "11:20:30"),
            _ozon_word(160, 140, "456"),
            _ozon_word(225, 140, "Refund"),
            _ozon_word(380, 140, "+ RUR 1.25"),
        ],
    )

    assert pa._ozon_page_rows(page) == [  # pylint: disable=protected-access
        (
            "01.02.2026 10:20:30",
            "123",
            "Payment purpose",
            pa.Decimal("-10.50"),
        ),
        ("02.02.2026 11:20:30", "456", "Refund", pa.Decimal("1.25")),
    ]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("- RUR 2 728.52", pa.Decimal("-2728.52")),
        ("+ RUR 10.50", pa.Decimal("10.50")),
        ("- 931.37 ₽", pa.Decimal("-931.37")),
        ("+ 5 000.00 ₽", pa.Decimal("5000.00")),
    ],
)
def test_ozon2csv_parses_english_and_russian_amounts(value, expected):
    assert pa._ozon_amount(value) == expected  # pylint: disable=protected-access


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("-97 000.00 ₽", pa.Decimal("97000.00")),
        ("+5 000.00 ₽", pa.Decimal("-5000.00")),
        ("-5 000.00", pa.Decimal("5000.00")),
    ],
)
def test_tbank2csv_parses_english_and_russian_amounts(value, expected):
    assert (
        pa._tbank_normalised_amount(  # pylint: disable=protected-access
            value
        )
        == expected
    )


def test_ozon2csv_extracts_statement_totals():
    page = _OzonPage(
        "Total deposits for the period: RUR 1 000.25\n"
        "Total withdrawals for the period: RUR 999.00",
        [],
    )

    assert pa._ozon_totals(page) == (  # pylint: disable=protected-access
        pa.Decimal("1000.25"), pa.Decimal("999.00")
    )


def test_ozon2csv_extracts_russian_statement_totals():
    page = _OzonPage(
        "Итого зачислений за период: 1 000.00 ₽\n"
        "Итого списаний за период: 500.00 ₽",
        [],
    )

    assert pa._ozon_totals(page) == (  # pylint: disable=protected-access
        pa.Decimal("1000.00"), pa.Decimal("500.00")
    )


def test_ozon2csv_extracts_russian_account_number():
    page = _OzonPage(
        "Номер лицевого счёта: № 00000000000000000000, открыт 01.01.2020",
        [],
    )

    assert pa._ozon_account(page) == (  # pylint: disable=protected-access
        "00000000000000000000"
    )


def test_ozon2csv_extracts_russian_contract_number():
    page = _OzonPage(
        "Номер договора: № 2026-08-12-KK-00000000000000000000 "
        "от 12.08.2026",
        [],
    )

    assert pa._ozon_account(page) == (  # pylint: disable=protected-access
        "2026-08-12-KK-00000000000000000000"
    )


def test_ozon2csv_parses_russian_credit_statement(mocker):
    page = _OzonPage(
        "Справка о движении средств\n"
        "Номер договора: № credit-account от 01.01.2026\n"
        "Итого зачислений за период: 70.18 ₽\n"
        "Итого списаний за период: 129.00 ₽",
        [
            _ozon_word(160, 50, "Документ"),
            _ozon_word(55, 70, "01.02.2026"),
            _ozon_word(102, 70, "10:20:30"),
            _ozon_word(160, 70, "14681921570"),
            _ozon_word(225, 70, "Credit repayment"),
            _ozon_word(380, 70, "+ 70.18 ₽"),
            _ozon_word(55, 100, "02.02.2026"),
            _ozon_word(102, 100, "11:20:30"),
            _ozon_word(160, 100, "14681921571"),
            _ozon_word(225, 100, "Purchase"),
            _ozon_word(380, 100, "- 129.00 ₽"),
        ],
    )
    _mock_pdf(mocker, [page])

    rows = pa._parse_ozon_statement(  # pylint: disable=protected-access
        "statement.pdf", []
    )

    assert len(rows) == 2
    assert rows[0][1] == "Ocredit-account_14681921570"
    amounts = [pa.Decimal(row[6].replace(" ", "")) for row in rows]
    assert sum((amount for amount in amounts if amount > 0), pa.Decimal()) == (
        pa.Decimal("70.18")
    )
    withdrawals = sum(
        (-amount for amount in amounts if amount < 0), pa.Decimal()
    )
    assert withdrawals == pa.Decimal("129.00")


@pytest.mark.parametrize(
    ("title", "account_line", "account"),
    [
        (
            "Operations Statement",
            "Account number: № english-account, dated 01.01.2026",
            "english-account",
        ),
        (
            "Справка о движении средств",
            "Номер лицевого счёта: № russian-account, открыт 01.01.2026",
            "russian-account",
        ),
    ],
)
def test_ozon2csv_builds_ids_for_english_and_russian_statements(
    mocker, title, account_line, account
):
    page = _OzonPage(
        "{}\n{}\nTotal deposits for the period: RUR 10.00\n"
        "Total withdrawals for the period: RUR 0.00".format(
            title, account_line
        ),
        [
            _ozon_word(160, 50, "Document"),
            _ozon_word(55, 70, "01.02.2026"),
            _ozon_word(102, 70, "10:20:30"),
            _ozon_word(160, 70, "123"),
            _ozon_word(225, 70, "Transfer"),
            _ozon_word(380, 70, "+ RUR 10.00"),
        ],
    )
    _mock_pdf(mocker, [page])

    rows = pa._parse_ozon_statement(  # pylint: disable=protected-access
        "statement.pdf", []
    )

    assert rows[0][1] == "O{}_123".format(account)


def test_ozon2csv_table_start_ignores_stray_date_above_heading():
    page = _OzonPage(
        "",
        [
            # A metadata line (e.g. "Период выписки: ...") whose date
            # happens to fall in the date column's x-range, above the
            # real table heading - must not be mistaken for a row.
            _ozon_word(144.9, 268.3, "14.08.2026"),
            _ozon_word(159.7, 348.5, "Документ"),
            _ozon_word(54.7, 383.4, "01.02.2026"),
            _ozon_word(102.3, 383.4, "10:20:30"),
            _ozon_word(159.7, 383.4, "123"),
            _ozon_word(225, 383.4, "Payment"),
            _ozon_word(380, 383.4, "- RUR 10.50"),
        ],
    )

    assert pa._ozon_page_rows(page) == [  # pylint: disable=protected-access
        ("01.02.2026 10:20:30", "123", "Payment", pa.Decimal("-10.50")),
    ]


def test_tbank2csv_table_start_skips_metadata_date_heading():
    words = [
        # e.g. "Дата заключения договора:" above the real table
        _tbank_word(56, 212, "Дата"),
        _tbank_word(56, 296, "Дата"),
    ]

    assert (
        pa._tbank_table_start(  # pylint: disable=protected-access
            words, russian=True
        )
        == 321.0
    )


def test_tbank2csv_parses_russian_page_rows():
    page = _TBankPage(
        "",
        [
            _tbank_word(56, 296, "Дата"),
            _tbank_word(56, 323, "21.09.2026"),
            _tbank_word(56, 334, "14:15"),
            # settlement-date column, must be ignored
            _tbank_word(126, 323, "21.09.2026"),
            _tbank_word(126, 334, "14:16"),
            _tbank_word(199, 323, "-1 000,00 ₽"),
            _tbank_word(389, 323, "Тестовая операция"),
        ],
    )

    assert pa._tbank_page_rows(  # pylint: disable=protected-access
        page, russian=True
    ) == [
        ("21.09.2026 14:15:00", "Тестовая операция", pa.Decimal("1000.00")),
    ]


def test_tbank2csv_totals_parses_russian_labels():
    page = _TBankPage(
        "",
        [
            _tbank_word(56, 21.3, "Пополнения:"),
            _tbank_word(126, 21.3, "1 000,00 ₽"),
            _tbank_word(56, 36.3, "Расходы:"),
            _tbank_word(126, 36.3, "500,00 ₽"),
        ],
    )

    assert pa._tbank_totals(page) == (  # pylint: disable=protected-access
        pa.Decimal("1000.00"), pa.Decimal("500.00")
    )


def test_tbank2csv_account_parses_russian_label():
    page = _TBankPage(
        "Номер лицевого счета:  00000000000000000000", []
    )

    assert pa._tbank_account(page) == (  # pylint: disable=protected-access
        "00000000000000000000"
    )


def test_tbank2csv_parses_english_statement(mocker):
    page = _TBankPage(
        "Bank Statement TBANK\n"
        "Personal account number: 40817810200142781910",
        [
            _tbank_word(56, 20, "Replenishment:"),
            _tbank_word(126, 20, "5 000,00"),
            _tbank_word(56, 35, "Expenses:"),
            _tbank_word(126, 35, "597,00"),
            _tbank_word(56, 310, "Date"),
            _tbank_word(56, 340, "07.09.2026"),
            _tbank_word(56, 350, "21:01"),
            _tbank_word(199, 340, "+5 000.00"),
            _tbank_word(389, 340, "Replenishment with a partner ATM"),
            _tbank_word(56, 380, "08.09.2026"),
            _tbank_word(56, 390, "12:00"),
            _tbank_word(199, 380, "-597.00"),
            _tbank_word(389, 380, "Cash withdrawal in ATM"),
        ],
    )
    _mock_pdf(mocker, [page])

    rows = pa._parse_tbank_statement(  # pylint: disable=protected-access
        "statement.pdf", _TAIL_RULE, original_comment=True
    )

    assert len(rows) == 2
    assert rows[0] == (
        "07.09.2026 21:01:00",
        "",
        "",
        "Replenishment with a partner ATM",
        "",
        "",
        "-5 000.00",
        "Replenishment with a partner ATM",
    )
    assert rows[1][3] == "Cash withdrawal in ATM"
    assert sum(
        -pa.Decimal(row[6].replace(" ", ""))
        for row in rows
        if row[6].startswith("-")
    ) == pa.Decimal("5000.00")
    assert sum(
        pa.Decimal(row[6].replace(" ", ""))
        for row in rows
        if not row[6].startswith("-")
    ) == pa.Decimal("597.00")


@pytest.mark.parametrize("original_comment", [False, True])
def test_tbank2csv_writes_original_only_with_original_comment_flag(
    mocker, tmp_path, original_comment
):
    source = tmp_path / "statement.pdf"
    target = tmp_path / "result.csv"
    source.touch()
    row = (
        "01.02.2026 10:20:00",
        "",
        "",
        "Payment",
        "",
        "",
        "10.00",
    ) + (("Original bank description",) if original_comment else ())
    mocker.patch.object(pa, "_load_tbank2csv_config", return_value=[])
    mocker.patch.object(pa, "_parse_tbank_statement", return_value=[row])

    pa.command_tbank2csv(
        [source], out_path=target, original_comment=original_comment
    )

    with target.open(encoding="utf-8-sig", newline="") as file:
        written = list(csv.reader(file))
    expected_header = pa._CSV_HEADER + (  # pylint: disable=protected-access
        ("Оригинал",) if original_comment else ()
    )
    assert written == [list(expected_header), list(row)]


@pytest.mark.parametrize("original_comment", [False, True])
def test_sber2csv_writes_original_in_own_column(
    mocker, tmp_path, original_comment
):
    source = tmp_path / "statement.pdf"
    target = tmp_path / "result.csv"
    source.touch()
    row = ("01.02.2026 10:20:00", "", "", "Payment", "", "raw", "10.00")
    mocker.patch.object(pa, "_load_sber2csv_config", return_value=[])
    mocker.patch.object(pa, "_parse_statement", return_value=[row])

    pa.command_sber2csv(
        [source], out_path=target, original_comment=original_comment
    )

    with target.open(encoding="utf-8-sig", newline="") as file:
        written = list(csv.reader(file))
    expected = ["01.02.2026 10:20:00", "", "", "Payment", "", "", "10.00"]
    if original_comment:
        expected.append("raw")
    assert written == [
        list(
            pa._CSV_HEADER  # pylint: disable=protected-access
            + (("Оригинал",) if original_comment else ())
        ),
        expected,
    ]


@pytest.mark.parametrize("original_comment", [False, True])
def test_ozon2csv_writes_original_only_with_original_comment_flag(
    mocker, tmp_path, original_comment
):
    source = tmp_path / "statement.pdf"
    target = tmp_path / "result.csv"
    source.touch()
    raw = "Original bank description"
    row = (
        "01.02.2026 10:20:30",
        "O123_456",
        "",
        "Payment",
        "",
        "",
        "10.00",
    ) + ((raw,) if original_comment else ())
    mocker.patch.object(pa, "_load_ozon2csv_config", return_value=[])
    mocker.patch.object(pa, "_parse_ozon_statement", return_value=[row])

    pa.command_ozon2csv(
        [source], out_path=target, original_comment=original_comment
    )

    with target.open(encoding="utf-8-sig", newline="") as file:
        written = list(csv.reader(file))
    expected_header = pa._CSV_HEADER + (  # pylint: disable=protected-access
        ("Оригинал",) if original_comment else ()
    )
    assert written == [list(expected_header), list(row)]
    assert written[1][5] == ""


@pytest.mark.parametrize(
    ("command", "loader_name", "parser_name"),
    [
        (
            pa.command_sber2csv,
            "_load_sber2csv_config",
            "_parse_statement",
        ),
        (
            pa.command_tbank2csv,
            "_load_tbank2csv_config",
            "_parse_tbank_statement",
        ),
        (
            pa.command_ozon2csv,
            "_load_ozon2csv_config",
            "_parse_ozon_statement",
        ),
    ],
)
@pytest.mark.parametrize("operation", ["", " \t"])
@pytest.mark.parametrize("dry_run", [False, True])
def test_bank_commands_reject_empty_operations_before_output(  # pylint: disable=too-many-positional-arguments
    mocker,
    tmp_path,
    capsys,
    command,
    loader_name,
    parser_name,
    operation,
    dry_run,
):
    source = tmp_path / "statement.pdf"
    target = tmp_path / "result.csv"
    source.touch()
    row = (
        "01.02.2026 10:20:00",
        "test-id",
        "",
        operation,
        "",
        "",
        "10.00",
    )
    mocker.patch.object(pa, loader_name, return_value=[])
    mocker.patch.object(pa, parser_name, return_value=[row])

    with pytest.raises(pa.errors.UserError) as exc_info:
        command([source], out_path=target, dry_run=dry_run)

    message = str(exc_info.value)
    assert "Empty operations are not allowed" in message
    assert "date='01.02.2026 10:20:00'" in message
    assert "external_id='test-id'" in message
    assert str(source) in message
    assert not target.exists()
    assert capsys.readouterr().out == ""


def test_ozon2csv_rejects_whole_batch_before_rewriting_or_creating(
    mocker, tmp_path
):
    valid_source = tmp_path / "a-valid.pdf"
    invalid_source = tmp_path / "b-invalid.pdf"
    valid_target = tmp_path / "a-valid.csv"
    invalid_target = tmp_path / "b-invalid.csv"
    valid_source.touch()
    invalid_source.touch()
    valid_target.write_text("existing output", encoding="utf-8")
    valid_row = (
        "01.02.2026 10:20:00",
        "Oaccount_1",
        "",
        "Payment",
        "",
        "",
        "10.00",
    )
    invalid_rows = [
        (
            "02.02.2026 10:20:00",
            "Oaccount_2",
            "",
            "",
            "",
            "",
            "20.00",
        ),
        (
            "03.02.2026 10:20:00",
            "Oaccount_3",
            "",
            " ",
            "",
            "",
            "30.00",
        ),
    ]

    def parse_statement(path, _rules, original_comment=False):
        del original_comment
        return [valid_row] if path == valid_source else invalid_rows

    mocker.patch.object(pa, "_load_ozon2csv_config", return_value=[])
    mocker.patch.object(pa, "_parse_ozon_statement", parse_statement)

    with pytest.raises(pa.errors.UserError) as exc_info:
        pa.command_ozon2csv(
            [valid_source, invalid_source],
            rewrite=True,
        )

    message = str(exc_info.value)
    assert "external_id='Oaccount_2'" in message
    assert "external_id='Oaccount_3'" in message
    assert str(invalid_source) in message
    assert valid_target.read_text(encoding="utf-8") == "existing output"
    assert not invalid_target.exists()


def test_sber2csv_removes_footer_and_normalises_operation_spaces():
    assert pa._apply_rules(  # pylint: disable=protected-access
        "  SHOP   NAME. Операция по карте ****1234  ", _TAIL_RULE
    ) == ("", "", "SHOP NAME")


def test_rules_replace_all_matches_and_expand_named_groups():
    rules = _rules(
        {
            "pattern": r"(?P<word>first|second)",
            "action": "replace",
            "value": r"[\g<word>]",
        },
    )

    assert pa._apply_rules(  # pylint: disable=protected-access
        "first second", rules
    ) == ("", "", "[first] [second]")


def test_ozon2csv_rules_normalise_marketplace_purchase_and_sbp_transfer():
    rules = _rules(
        {
            "pattern": r"Payment for goods/services on Platform Ozon",
            "action": "replace",
            "value": "ozon.ru",
        },
        {
            "pattern": (
                r"^Refund of payment for goods/services purchased on Platform "
                r"Ozon, order (?P<order>.+)\.$"
            ),
            "action": "replace",
            "value": r"Refund ozon.ru, order \g<order>",
        },
        {
            "pattern": (
                r"^Loan repayment (?:according to contract|under agreement) "
                r"No\. .*$"
            ),
            "action": "replace",
            "value": "repayment",
        },
        {
            "pattern": (
                r"^Credit repayment (?:under|according to) "
                r"(?:agreement|contract)(?: No\.?\s*)?.*$"
            ),
            "action": "replace",
            "value": "Credit repayment",
        },
        {"pattern": "№", "action": "replace", "value": ""},
        {
            "pattern": (
                r"^Transfer .*?through SBP\. Sender: "
                r"(?P<sender>.+?)\. VAT not applicable\.$"
            ),
            "action": "replace",
            "value": r"Transfer from \g<sender>.",
        },
        {"pattern": r"VAT not applicable\.", "action": "replace", "value": ""},
        {
            "pattern": r"(?=^Transfer from\b)",
            "action": "place",
            "value": "СБП",
        },
    )

    assert pa._apply_rules(  # pylint: disable=protected-access
        "Payment for goods/services on Platform Ozon, order №70987310-0055. "
        "VAT not applicable.",
        rules,
    ) == ("", "", "ozon.ru, order 70987310-0055.")
    assert pa._apply_rules(  # pylint: disable=protected-access
        "Transfer to a bank account through SBP. Sender: David ZHoraevich D. "
        "VAT not applicable.",
        rules,
    ) == ("СБП", "", "Transfer from David ZHoraevich D.")
    assert pa._apply_rules(  # pylint: disable=protected-access
        "Refund of payment for goods/services purchased on Platform Ozon, "
        "order 70987310- 0061.",
        rules,
    ) == ("", "", "Refund ozon.ru, order 70987310- 0061")
    assert pa._apply_rules(  # pylint: disable=protected-access
        "Loan repayment according to contract No. 2026-08-12- "
        "KK-036637684858053463 50, Dzhanyan David ZHoraevich",
        rules,
    ) == ("", "", "repayment")
    assert pa._apply_rules(  # pylint: disable=protected-access
        "Loan repayment under agreement No. 2026-08- 12- "
        "KK-036637684858053463 50, Dzhanyan David ZHoraevich",
        rules,
    ) == ("", "", "repayment")
    for description in (
        "Credit repayment under agreement 2026-08-12- "
        "KK-036637684858053463 50, Dzhanyan David ZHoraevich",
        "Credit repayment under agreement No.2026-08- 12- "
        "KK-036637684858053463 50, Dzhanyan David ZHoraevich",
        "Credit repayment under agreement No. 2026-08- 12- "
        "KK-036637684858053463 50, Dzhanyan David ZHoraevich",
        "Credit repayment under contract No. 2026-08-12- "
        "KK-036637684858053463 50, Dzhanyan David ZHoraevich",
        "Credit repayment according to contract No. 2026-08-12- "
        "KK-036637684858053463 50, Dzhanyan David ZHoraevich",
    ):
        assert pa._apply_rules(  # pylint: disable=protected-access
            description, rules
        ) == ("", "", "Credit repayment")


@pytest.mark.parametrize(
    ("description", "place", "operation"),
    [
        ("SHOP _P_QR", "СБП-QR", "SHOP"),
        ("SHOP _SBP", "СБП", "SHOP"),
        ("SHOP SBOL", "SBOL", "SHOP"),
    ],
)
def test_sber2csv_moves_sbp_and_sbol_markers_to_place(
    description, place, operation
):
    rules = _rules(
        {
            "pattern": r"(?:_P?_QR\b|Покупка по СБП)",
            "action": "place",
            "value": "СБП-QR",
        },
        {"pattern": r"(?:_SBP\b|\bСБП\b)", "action": "place", "value": "СБП"},
        {"pattern": r"\bSBOL\b", "action": "place", "value": "SBOL"},
    )

    assert pa._apply_rules(description, rules) == (  # pylint: disable=protected-access
        place,
        "",
        operation,
    )


@pytest.mark.parametrize(
    ("title", "card"),
    [
        ("Выписка по счёту", False),
        ("Выписка по платёжному счёту", True),
        ("Выписка по счёту дебетовой карты", True),
        ("Выписка по счёту кредитной карты", True),
    ],
)
def test_sber2csv_supports_statement_templates(mocker, title, card):
    if card:
        page = _sber_card_page(
            [
                (
                    "01.02.2026",
                    "10:20",
                    "123456",
                    ["Purchase"],
                    "-10,00",
                    100,
                )
            ],
            totals=("0,00", "10,00"),
            title=title,
        )
    else:
        page = _sber_account_page(
            [("01.02.2026", "Transfer", "-10,00", 100)],
            totals=("0,00", "10,00"),
            title=title,
        )
    _mock_pdf(mocker, [page])

    rows = pa._parse_statement(  # pylint: disable=protected-access
        "statement.pdf", _TAIL_RULE
    )

    assert len(rows) == 1


def test_sber2csv_parses_card_statement(mocker):
    _mock_pdf(mocker, [_sber_transfer_page()])

    rows = pa._parse_statement(  # pylint: disable=protected-access
        "statement.pdf", _TAIL_RULE
    )

    assert len(rows) == 1
    assert rows[0] == (
        "25.07.2026 15:20:00",
        "887429",
        "",
        "Перевод с карты Перевод для Г. Галина Алексеевна",
        "",
        (
            "Перевод с карты Перевод для Г. Галина Алексеевна. "
            "Операция по счету ****8546"
        ),
        "498.00",
    )


def test_sber2csv_falls_back_to_card_category_after_rules(mocker):
    page = _sber_card_page(
        [
            (
                "25.07.2026",
                "15:20",
                "887429",
                [
                    "Перевод с карты",
                    "SBOL. Операция по счету ****8546",
                ],
                "-498,00",
                100,
            )
        ],
        totals=("0,00", "498,00"),
    )
    _mock_pdf(mocker, [page])

    rows = pa._parse_statement(  # pylint: disable=protected-access
        "statement.pdf",
        _rules(
            {
                "pattern": r"\.\s*Операция по (?:карте|счету)\b.*$",
                "action": "remove",
            },
            {
                "pattern": r"^Перевод с карты\s*",
                "action": "category",
                "value": "__tr__",
            },
            {
                "pattern": r"\bSBOL\b\.?",
                "action": "place",
                "value": "SBOL",
            },
        ),
    )

    assert rows[0][2:5] == ("SBOL", "Перевод с карты", "__tr__")


def test_sber2csv_writes_compact_continuation_page(mocker, tmp_path):
    source = tmp_path / "statement.pdf"
    target = tmp_path / "statement.csv"
    source.touch()
    first_page_rows = [
        ("14.09.2026", "Income", "+16 175,11", 100),
        ("13.09.2026", "Expense", "-498 175,11", 150),
    ]
    first_page_rows.extend(
        ("12.09.2026", "Expense", "-1 000,00", 200 + index * 50)
        for index in range(8)
    )
    first_page = _sber_account_page(
        first_page_rows,
        totals=("16 175,11", "516 175,11"),
    )
    second_page = _sber_account_page(
        [("04.09.2026", "Expense", "-10 000,00", 80)],
        continuation=True,
    )
    _mock_pdf(mocker, [first_page, second_page])
    mocker.patch.object(pa, "_load_sber2csv_config", return_value=_TAIL_RULE)

    pa.command_sber2csv([source], out_path=target)

    with target.open(encoding="utf-8-sig", newline="") as file:
        written = list(csv.reader(file))
    assert written[0] == list(
        pa._CSV_HEADER  # pylint: disable=protected-access
    )
    rows = written[1:]
    assert len(rows) == 11
    amounts = [pa.Decimal(row[6].replace(" ", "")) for row in rows]
    income = sum(
        (-amount for amount in amounts if amount < 0), pa.Decimal()
    )
    expense = sum(
        (amount for amount in amounts if amount > 0), pa.Decimal()
    )
    assert income == pa.Decimal("16175.11")
    assert expense == pa.Decimal("516175.11")
    assert rows[-1][0] == "04.09.2026 00:00:00"
    assert rows[-1][6] == "10 000.00"


def test_sber2csv_uses_pdf_category_for_empty_incoming_transfers(mocker):
    _mock_pdf(mocker, [_sber_debit_page()])

    rows = pa._parse_statement(  # pylint: disable=protected-access
        "statement.pdf",
        _rules(
            {
                "pattern": r"\.\s*Операция по (?:карте|счету)\b.*$",
                "action": "remove",
            },
            {
                "pattern": (
                    r"^(?:Перевод на карту|Прочие операции|"
                    r"Оплата по QR–коду|Транспорт)\s*"
                ),
                "action": "remove",
            },
            {
                "pattern": r"\bSBOL\b\.?",
                "action": "place",
                "value": "SBOL",
            },
        ),
    )

    assert len(rows) == 3
    by_code = {row[1]: row for row in rows}
    for code in ("199029", "835435"):
        assert by_code[code][2:4] == ("SBOL", "Перевод на карту")
    assert by_code["151502"][3] == "BRANCH KARTA-CREDIT"
    assert by_code["199029"][5] == (
        "Перевод на карту SBOL. Операция по счету ****0460"
    )
    assert by_code["151502"][5] == (
        "Прочие операции BRANCH KARTA-CREDIT. "
        "Операция по счету ****0460"
    )
    amounts = [pa.Decimal(row[6].replace(" ", "")) for row in rows]
    income = sum(
        (-amount for amount in amounts if amount < 0), pa.Decimal()
    )
    assert income == pa.Decimal("3000.00")
    assert sum((amount for amount in amounts if amount > 0), pa.Decimal()) == (
        pa.Decimal("500.00")
    )


def test_sber2csv_uses_pdf_category_for_empty_card_operations(mocker):
    _mock_pdf(mocker, [_sber_debit_page()])

    rows = pa._parse_statement(  # pylint: disable=protected-access
        "statement.pdf",
        _rules({"pattern": r".*", "action": "remove"}),
    )

    by_code = {row[1]: row for row in rows}
    assert by_code["199029"][3] == "Перевод на карту"
    assert by_code["151502"][3] == "Прочие операции"


def test_sber2csv_rejects_empty_account_operation_without_fallback(
    mocker, tmp_path
):
    source = tmp_path / "statement.pdf"
    target = tmp_path / "statement.csv"
    source.touch()
    page = _sber_account_page(
        [("01.02.2026", "Transfer", "-10,00", 100)],
        totals=("0,00", "10,00"),
    )
    _mock_pdf(mocker, [page])
    mocker.patch.object(
        pa,
        "_load_sber2csv_config",
        return_value=_rules({"pattern": r".*", "action": "remove"}),
    )

    with pytest.raises(pa.errors.UserError) as exc_info:
        pa.command_sber2csv([source])

    message = str(exc_info.value)
    assert "Empty operations are not allowed" in message
    assert "date='01.02.2026 00:00:00'" in message
    assert "external_id=''" in message
    assert str(source) in message
    assert not target.exists()


def test_sber2csv_excludes_page_footer_from_original_comment():
    page = _sber_card_page(
        [
            (
                "25.07.2026",
                "15:20",
                "975922",
                ["Purchase", "Операция по счету ****8546"],
                "-10,00",
                100,
            )
        ],
        totals=("0,00", "10,00"),
        footer=(150, "Продолжение на следующей странице"),
    )

    rows = pa._card_rows(page)  # pylint: disable=protected-access

    comment = rows[0][4]
    assert "Продолжение на следующей странице" not in comment
    assert comment.endswith("Операция по счету ****8546")


def test_sber2csv_rules_can_remove_card_description_first_line(mocker):
    _mock_pdf(mocker, [_sber_transfer_page()])

    rows = pa._parse_statement(  # pylint: disable=protected-access
        "statement.pdf",
        _rules(
            {
                "pattern": r"\.\s*Операция по (?:карте|счету)\b.*$",
                "action": "remove",
            },
            {"pattern": r"^Перевод с карты\s*", "action": "remove"},
        ),
    )

    first = rows[0]
    assert first[3] == "Перевод для Г. Галина Алексеевна"
    assert first[5] == (
        "Перевод с карты Перевод для Г. Галина Алексеевна. "
        "Операция по счету ****8546"
    )


def test_sber2csv_place_rule_can_use_card_description_first_line(mocker):
    _mock_pdf(mocker, [_sber_transfer_page()])

    rows = pa._parse_statement(  # pylint: disable=protected-access
        "statement.pdf",
        _rules(
            {
                "pattern": r"\.\s*Операция по (?:карте|счету)\b.*$",
                "action": "remove",
            },
            {
                "pattern": r"^Перевод с карты\s*",
                "action": "place",
                "value": "Перевод с карты",
            },
        ),
    )

    assert rows[0][2:4] == (
        "Перевод с карты",
        "Перевод для Г. Галина Алексеевна",
    )


def test_sber2csv_category_rule_writes_category_column(mocker):
    _mock_pdf(mocker, [_sber_transfer_page()])

    rows = pa._parse_statement(  # pylint: disable=protected-access
        "statement.pdf",
        _rules(
            {
                "pattern": r"\.\s*Операция по (?:карте|счету)\b.*$",
                "action": "remove",
            },
            {
                "pattern": r"^Перевод с карты\s*",
                "action": "category",
                "value": "Переводы",
            },
        ),
    )

    assert rows[0][3:6] == (
        "Перевод для Г. Галина Алексеевна",
        "Переводы",
        "Перевод с карты Перевод для Г. Галина Алексеевна. "
        "Операция по счету ****8546",
    )


def test_sber2csv_preserves_original_comment_after_rules(mocker):
    page = _sber_card_page(
        [
            (
                "25.07.2026",
                "15:20",
                "913142",
                [
                    "Прочие расходы",
                    "SBERPRIME MOSCOW RUS.",
                    "Операция по карте ****5640",
                ],
                "-10,00",
                100,
            )
        ],
        totals=("0,00", "10,00"),
    )
    _mock_pdf(mocker, [page])

    rows = pa._parse_statement(  # pylint: disable=protected-access
        "statement.pdf",
        _rules(
            {
                "pattern": r"\.\s*Операция по (?:карте|счету)\b.*$",
                "action": "remove",
            },
            {"pattern": r"^Прочие расходы\s+", "action": "remove"},
            {
                "pattern": r"\s+(?P<place>MOSCOW RUS)$",
                "action": "place",
                "value": r"\g<place>",
            },
        ),
    )

    row = next(row for row in rows if row[1] == "913142")
    assert row[3] == "SBERPRIME"
    assert row[2] == "MOSCOW RUS"
    assert row[5] == (
        "Прочие расходы SBERPRIME MOSCOW RUS. Операция по карте ****5640"
    )


@pytest.mark.parametrize(
    ("description", "place", "operation"),
    [
        ("SBERPRIME MOSCOW RUS", "MOSCOW RUS", "SBERPRIME"),
        ("SHOP MOSKVA RUS", "MOSKVA RUS", "SHOP"),
        ("MOSCOW YANDEX", "MOSCOW", "YANDEX"),
    ],
)
def test_sber2csv_extracts_place_from_rules(description, place, operation):
    rules = _rules(
        {
            "pattern": r"\s+(?P<place>MOSCOW RUS|MOSKVA RUS)$",
            "action": "place",
            "value": r"\g<place>",
        },
        {
            "pattern": r"^(?P<place>MOSCOW)\s+",
            "action": "place",
            "value": r"\g<place>",
        },
    )

    assert pa._apply_rules(description, rules) == (  # pylint: disable=protected-access
        place,
        "",
        operation,
    )


def test_sber2csv_uses_first_place_rule_and_all_remove_rules():
    rules = _rules(
        {"pattern": r"^first\s+", "action": "place", "value": "first"},
        {"pattern": r"second\s+", "action": "place", "value": "second"},
        {"pattern": r"shop", "action": "remove"},
        {"pattern": r"\s+", "action": "remove"},
    )

    assert pa._apply_rules("first second shop", rules) == (  # pylint: disable=protected-access
        "first",
        "",
        "second",
    )


def test_sber2csv_extracts_category_from_rule():
    rules = _rules(
        {
            "pattern": r"\s+\[(?P<category>Subscriptions)\]$",
            "action": "category",
            "value": r"\g<category>",
        },
    )

    assert pa._apply_rules(  # pylint: disable=protected-access
        "STREAMING SERVICE [Subscriptions]", rules
    ) == ("", "Subscriptions", "STREAMING SERVICE")


def test_sber2csv_extracts_place_and_category_independently():
    rules = _rules(
        {
            "pattern": r"\s+(?P<place>MOSCOW RUS)$",
            "action": "place",
            "value": r"\g<place>",
        },
        {
            "pattern": r"^\[(?P<category>Food)\]\s+",
            "action": "category",
            "value": r"\g<category>",
        },
    )

    assert pa._apply_rules(  # pylint: disable=protected-access
        "[Food] SHOP MOSCOW RUS", rules
    ) == ("MOSCOW RUS", "Food", "SHOP")


def test_sber2csv_uses_first_category_rule_and_all_remove_rules():
    rules = _rules(
        {
            "pattern": r"^\[(?P<category>Food)\]\s+",
            "action": "category",
            "value": r"\g<category>",
        },
        {
            "pattern": r"\[(?P<category>Ignored)\]\s+",
            "action": "category",
            "value": r"\g<category>",
        },
        {"pattern": r"\s+SHOP$", "action": "remove"},
    )

    assert pa._apply_rules(  # pylint: disable=protected-access
        "[Food] [Ignored] SHOP", rules
    ) == ("", "Food", "[Ignored]")


@pytest.mark.parametrize(
    "rules",
    [
        "not-a-list",
        [{}],
        [{"pattern": "[", "action": "remove"}],
        [{"pattern": "shop", "action": "unknown"}],
        [{"pattern": "shop", "action": "replace"}],
        [{"pattern": "shop", "action": "replace", "value": r"\g<missing>"}],
        [{"pattern": "shop", "action": "place"}],
        [{"pattern": "shop", "action": "place", "value": r"\g<missing>"}],
        [{"pattern": "shop", "action": "category"}],
        [
            {
                "pattern": "shop",
                "action": "category",
                "value": r"\g<missing>",
            }
        ],
    ],
)
def test_sber2csv_rejects_invalid_rules_before_writing(
    mocker, tmp_path, rules
):
    mocker.patch.object(
        pa.conf,
        "load_davo_config",
        return_value=(
            {"pa": {"sber2csv": {"rules": rules}}},
            None,
            None,
        ),
    )
    source = tmp_path / "statement.pdf"
    source.touch()

    with pytest.raises(pa.errors.UserError):
        pa.command_sber2csv([source], out_path=tmp_path / "result.csv")

    assert not (tmp_path / "result.csv").exists()
