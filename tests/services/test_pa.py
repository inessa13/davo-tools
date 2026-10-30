import csv
from pathlib import Path

import pytest

from davo.services import pa

_STATEMENTS = Path(__file__).parents[2] / "examples" / "stmt"
_TBANK_STATEMENT = (
    Path(__file__).parents[2] / "examples" / "20260909 tbank golub dd.pdf"
)
_OZON_RUSSIAN_CREDIT_STATEMENT = (
    Path(__file__).parents[2]
    / "examples"
    / "20261030"
    / "20261030 ozon dzd cc.pdf"
)
_OZON_ENGLISH_STATEMENT = (
    Path(__file__).parents[2]
    / "examples"
    / "20261002"
    / (
        "ozon Джанян_Д_Ж_о_движении_денежных_средств_"
        "ozonbank_document_36799119.pdf"
    )
)
_OZON_RUSSIAN_DEBIT_STATEMENT = (
    Path(__file__).parents[2]
    / "examples"
    / "20261002"
    / (
        "ozon Джанян_Д_Ж_о_движении_денежных_средств_"
        "ozonbank_document_36799152.pdf"
    )
)


def _rules(*items):
    return [
        (pa.re.compile(item["pattern"]), item["action"], item.get("value", ""))
        for item in items
    ]


_TAIL_RULE = _rules(
    {"pattern": r"\.\s*Операция по (?:карте|счету)\b.*$", "action": "remove"}
)


class _OzonPage:  # pylint: disable=too-few-public-methods
    def __init__(self, text, words):
        self.text = text
        self.words = words

    def get_text(self, kind=None, sort=False):
        del sort
        return self.words if kind == "words" else self.text


def _ozon_word(x, y, value):
    return (x, y, 0, 0, value, 0, 0, 0)


class _TBankPage:  # pylint: disable=too-few-public-methods
    def __init__(self, text, words):
        self.text = text
        self.words = words

    def get_text(self, kind=None, sort=False):
        del sort
        return self.words if kind == "words" else self.text


def _tbank_word(x, y, value):
    return (x, y, 0, 0, value, 0, 0, 0)


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


def test_ozon2csv_parses_known_russian_credit_statement():
    rows = pa._parse_ozon_statement(  # pylint: disable=protected-access
        _OZON_RUSSIAN_CREDIT_STATEMENT, []
    )

    assert len(rows) == 50
    assert rows[0][1] == (
        "O2026-08-12-KK-03663768485805346350_14681921570"
    )
    amounts = [pa.Decimal(row[6].replace(" ", "")) for row in rows]
    assert sum((amount for amount in amounts if amount > 0), pa.Decimal()) == (
        pa.Decimal("70692.18")
    )
    withdrawals = sum(
        (-amount for amount in amounts if amount < 0), pa.Decimal()
    )
    assert withdrawals == pa.Decimal("129005.00")


def test_ozon2csv_preserves_existing_english_and_russian_debit_ids():
    english_rows = pa._parse_ozon_statement(  # pylint: disable=protected-access
        _OZON_ENGLISH_STATEMENT, []
    )
    russian_debit_rows = pa._parse_ozon_statement(  # pylint: disable=protected-access
        _OZON_RUSSIAN_DEBIT_STATEMENT, []
    )

    assert english_rows[0][1] == (
        "O2026-08-12-KK-03663768485805346350_13897200662"
    )
    assert russian_debit_rows[0][1] == "O40817810511113506970_13523345386"


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


def test_tbank2csv_parses_known_english_statement():
    rows = pa._parse_tbank_statement(  # pylint: disable=protected-access
        _TBANK_STATEMENT, _TAIL_RULE, original_comment=True
    )

    import fitz  # pylint: disable=import-outside-toplevel

    with fitz.open(_TBANK_STATEMENT) as document:
        account = pa._tbank_account(  # pylint: disable=protected-access
            document[0]
        )
    assert account == "40817810200142781910"
    assert len(rows) == 13
    assert rows[0] == (
        "07.09.2026 21:01:00",
        "",
        "",
        "Replenishment with a partner ATM T-Bank Moscow RU",
        "",
        "",
        "-5 000.00",
        "Replenishment with a partner ATM T-Bank Moscow RU",
    )
    assert rows[1][3] == "Cash withdrawal in ATM.T- BANK MOSCOW RUS"
    assert sum(
        -pa.Decimal(row[6].replace(" ", ""))
        for row in rows
        if row[6].startswith("-")
    ) == pa.Decimal("41800.00")
    assert sum(
        pa.Decimal(row[6].replace(" ", ""))
        for row in rows
        if not row[6].startswith("-")
    ) == pa.Decimal("5597.00")


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
    ("name", "operations"),
    [
        ("Выписка по вкладу или счёту.pdf", 5),
        ("Выписка по счёту дебетовой карты.pdf", 44),
        ("Выписка по счёту кредитной карты.pdf", 21),
        ("Выписка по счёту дебетовой карты(1).pdf", 52),
    ],
)
def test_sber2csv_supports_statement_templates(name, operations):
    rows = pa._parse_statement(  # pylint: disable=protected-access
        _STATEMENTS / name, _TAIL_RULE
    )

    assert len(rows) == operations


def test_sber2csv_parses_known_visa_statement():
    rows = pa._parse_statement(  # pylint: disable=protected-access
        _STATEMENTS / "sber golub dt visa 20260724.pdf", _TAIL_RULE
    )

    assert len(rows) == 18
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
    assert rows[4][1] == "052769"
    assert rows[2][-1] == "-442 500.00"


@pytest.mark.parametrize("code", ["975922", "128219"])
def test_sber2csv_excludes_page_footer_from_original_comment(code):
    rows = pa._parse_statement(  # pylint: disable=protected-access
        _STATEMENTS / "sber golub dt visa 20260724.pdf", _TAIL_RULE
    )

    comment = next(row[5] for row in rows if row[1] == code)
    assert "Продолжение на следующей странице" not in comment
    assert "лицензия Банка России" not in comment
    assert comment.endswith("Операция по счету ****8546")


def test_sber2csv_rules_can_remove_card_description_first_line():
    rows = pa._parse_statement(  # pylint: disable=protected-access
        _STATEMENTS / "sber golub dt visa 20260724.pdf",
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


def test_sber2csv_place_rule_can_use_card_description_first_line():
    rows = pa._parse_statement(  # pylint: disable=protected-access
        _STATEMENTS / "sber golub dt visa 20260724.pdf",
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


def test_sber2csv_category_rule_writes_category_column():
    rows = pa._parse_statement(  # pylint: disable=protected-access
        _STATEMENTS / "sber golub dt visa 20260724.pdf",
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


def test_sber2csv_preserves_original_comment_after_rules():
    rows = pa._parse_statement(  # pylint: disable=protected-access
        _STATEMENTS / "sber golub dt visa 20260724.pdf",
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
