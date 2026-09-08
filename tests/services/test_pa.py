from pathlib import Path

import pytest

from davo.services import pa

_STATEMENTS = Path(__file__).parents[2] / "examples" / "stmt"


def _rules(*items):
    return [
        (pa.re.compile(item["pattern"]), item["action"], item.get("value", ""))
        for item in items
    ]


_TAIL_RULE = _rules(
    {"pattern": r"\.\s*Операция по (?:карте|счету)\b.*$", "action": "remove"}
)


def test_sber2csv_removes_footer_and_normalises_operation_spaces():
    assert pa._apply_rules(  # pylint: disable=protected-access
        "  SHOP   NAME. Операция по карте ****1234  ", _TAIL_RULE
    ) == ("", "", "SHOP NAME")


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
