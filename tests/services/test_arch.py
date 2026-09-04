import json
import logging

import pytest
import yaml

from davo.services import arch


def _receipt(date="08.08.26 12.10", user="ozon.ru"):
    return """<html><body>
        <td>Пользователь: {}</td>
        <td>Дата: {}</td>
    </body></html>""".format(user, date)


def _write_receipt(root, name, **kwargs):
    path = root / name
    path.write_text(_receipt(**kwargs), encoding="utf-8")
    return path


def test_extract_fns_name_uses_normalised_user(tmp_path):
    receipt = _write_receipt(
        tmp_path,
        "receipt.html",
        date="09.08.26 04.51",
        user="  ООО «ozon.ru» /  ",
    )

    assert arch.extract_fns_name(receipt) == "20260809 REC ozon.ru.html"


def test_plan_numbers_duplicate_names_in_sort_order(tmp_path):
    _write_receipt(tmp_path, "b.html")
    _write_receipt(tmp_path, "a.html")

    plan = arch.plan_fns_rename(tmp_path)

    assert [(item.source.name, item.target.name) for item in plan] == [
        ("a.html", "20260808 REC ozon.ru 1.html"),
        ("b.html", "20260808 REC ozon.ru 2.html"),
    ]


def test_plan_uses_single_digit_numbers_for_nine_duplicates(tmp_path):
    for index in range(9):
        _write_receipt(tmp_path, "receipt-{}.html".format(index))

    names = [item.target.name for item in arch.plan_fns_rename(tmp_path)]

    assert names[0] == "20260808 REC ozon.ru 1.html"
    assert names[-1] == "20260808 REC ozon.ru 9.html"


def test_plan_uses_two_digit_numbers_for_ten_duplicates(tmp_path):
    for index in range(10):
        _write_receipt(tmp_path, "receipt-{}.html".format(index))

    names = [item.target.name for item in arch.plan_fns_rename(tmp_path)]

    assert names[0] == "20260808 REC ozon.ru 01.html"
    assert names[-1] == "20260808 REC ozon.ru 10.html"


def test_dry_run_only_plans_copy(tmp_path, caplog):
    caplog.set_level(logging.INFO, logger="davo.services.arch")
    source = _write_receipt(tmp_path, "receipt.html")
    target = tmp_path / "20260808 REC ozon.ru.html"

    arch.command_fns_rename(tmp_path)

    assert source.exists()
    assert not target.exists()
    assert "copy receipt.html -> 20260808 REC ozon.ru.html" in caplog.text
    assert str(tmp_path) not in caplog.text


def test_commit_copies_unless_rename_requested(tmp_path):
    source = _write_receipt(tmp_path, "receipt.html")
    target = tmp_path / "20260808 REC ozon.ru.html"

    arch.command_fns_rename(tmp_path, commit=True)

    assert source.exists()
    assert target.read_text(encoding="utf-8") == source.read_text(
        encoding="utf-8"
    )


def test_commit_rename_removes_source(tmp_path):
    source = _write_receipt(tmp_path, "receipt.html")
    target = tmp_path / "20260808 REC ozon.ru.html"

    arch.command_fns_rename(tmp_path, commit=True, rename=True)

    assert not source.exists()
    assert target.exists()


def test_collision_is_not_overwritten(tmp_path, caplog):
    source = _write_receipt(tmp_path, "receipt.html")
    target = tmp_path / "20260808 REC ozon.ru.html"
    target.write_text("existing", encoding="utf-8")

    arch.command_fns_rename(tmp_path, commit=True, rename=True)

    assert source.exists()
    assert target.read_text(encoding="utf-8") == "existing"
    assert "target already exists: 20260808 REC ozon.ru.html" in caplog.text
    assert str(tmp_path) not in caplog.text


def test_invalid_and_nested_html_are_skipped(tmp_path, caplog):
    (tmp_path / "invalid.html").write_text("<html></html>", encoding="utf-8")
    nested = tmp_path / "nested"
    nested.mkdir()
    _write_receipt(nested, "receipt.html")
    (tmp_path / "readme.txt").write_text("ignored", encoding="utf-8")

    plan = arch.plan_fns_rename(tmp_path)

    assert plan == []
    assert "receipt date is missing" in caplog.text


def test_rename_uses_exact_user_alias_and_does_not_require_place(tmp_path):
    config = tmp_path / ".dtconf"
    config.write_text("fns:\n  user_names:\n    exact user: Продавец\n")
    receipt = tmp_path / "receipt.html"
    receipt.write_text(
        "<td>Пользователь: exact user</td><td>Дата: 08.08.26</td>",
        encoding="utf-8",
    )

    assert arch.extract_fns_name(receipt, {"exact user": "Продавец"}) == (
        "20260808 REC Продавец.html"
    )


def test_rename_empty_alias_omits_seller_and_numbers(tmp_path):
    config = tmp_path / ".dtconf"
    config.write_text("fns:\n  user_names:\n    seller: ''\n")
    _write_receipt(tmp_path, "a.html", user="seller")
    _write_receipt(tmp_path, "b.html", user="seller")

    assert [item.target.name for item in arch.plan_fns_rename(tmp_path)] == [
        "20260808 REC 1.html",
        "20260808 REC 2.html",
    ]


@pytest.mark.parametrize(
    ("user", "expected"),
    [
        ("ООО «Магазин»", "Магазин"),
        ("Магазин, ООО", "Магазин"),
        ("ИП Иванов Иван Иванович", "ИП Иванов"),
        ("Иванов И. И.", "ИП Иванов"),
        ("СОСНОВСКИХ МАРИНА ВИКТОРОВНА", "ИП СОСНОВСКИХ"),
    ],
)
def test_normalise_user_removes_legal_forms_quotes_and_recognises_fio(
    user, expected
):
    assert arch._normalise_user(user) == expected


@pytest.mark.parametrize("option", ["-c", "--commit"])
def test_cli_commit_options(option):
    from davo import cli

    namespace = cli.init_parser().parse_args(["arch", "fns-rename", option])

    assert namespace.commit is True


@pytest.mark.parametrize("option", ["-R", "--rename"])
def test_cli_rename_options(option):
    from davo import cli

    namespace = cli.init_parser().parse_args(["arch", "fns-rename", option])

    assert namespace.rename is True


def _json_entry(number, sign, date="2026-07-30T11:58:00", user="ozon.ru"):
    return {
        "ticket": {
            "document": {
                "receipt": {
                    "dateTime": date,
                    "user": user,
                    "totalSum": 10000,
                    "fiscalDriveNumber": "123",
                    "fiscalDocumentNumber": number,
                    "fiscalSign": sign,
                    "operationType": 1,
                    "items": [
                        {
                            "name": "<item>",
                            "price": 10000,
                            "sum": 10000,
                            "quantity": 1,
                        }
                    ],
                    "ecashTotalSum": 10000,
                }
            }
        },
    }


def _write_json(root, entries):
    path = root / "export.json"
    path.write_text(json.dumps(entries), encoding="utf-8")
    return path


def test_fns_extract_renders_qr_and_numbers_same_store(tmp_path):
    source = _write_json(tmp_path, [_json_entry(1, 11), _json_entry(2, 22)])

    generated = arch.command_fns_extract(source, out_dir=tmp_path)

    assert [path.name for path in generated] == [
        "20260730 REC ozon.ru autogen 1.html",
        "20260730 REC ozon.ru autogen 2.html",
    ]
    contents = generated[0].read_text(encoding="utf-8")
    assert "&lt;item&gt;" in contents
    assert "data:image/png;base64,iVBOR" in contents
    assert "fn=123 fd=1 fp=11" in contents
    assert arch._qr_payload(
        _json_entry(1, 11)["ticket"]["document"]["receipt"]
    ) == ("t=20260730T1158&s=100.00&fn=123&fd=1&fp=11&n=1")


def test_fns_extract_uses_user_alias_without_retail_place(tmp_path):
    entry = _json_entry(1, 11, user="exact user")
    source = _write_json(tmp_path, [entry])
    config = tmp_path / ".dtconf"
    config.write_text("fns:\n  user_names:\n    exact user: Продавец\n")

    generated = arch.command_fns_extract(
        source, out_dir=tmp_path, config=config
    )

    assert [path.name for path in generated] == [
        "20260730 REC Продавец autogen.html"
    ]


def test_fns_extract_empty_alias_omits_seller(tmp_path):
    source = _write_json(tmp_path, [_json_entry(1, 11, user="seller")])
    config = tmp_path / ".dtconf"
    config.write_text("fns:\n  user_names:\n    seller: ''\n")

    generated = arch.command_fns_extract(
        source, out_dir=tmp_path, config=config
    )

    assert [path.name for path in generated] == ["20260730 REC autogen.html"]


def test_fns_extract_resumes_and_refuses_complete_repeat(tmp_path):
    entries = [_json_entry(1, 11), _json_entry(2, 22)]
    source = _write_json(tmp_path, entries)
    first = arch.command_fns_extract(source, out_dir=tmp_path)
    first[1].unlink()

    generated = arch.command_fns_extract(source, out_dir=tmp_path)

    assert [path.name for path in generated] == [
        "20260730 REC ozon.ru autogen 2.html"
    ]
    with pytest.raises(arch.errors.UserError, match="repeated run"):
        arch.command_fns_extract(source, out_dir=tmp_path)


def test_fns_extract_dry_run_and_config_map(tmp_path, caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger="davo.services.arch")
    nested = tmp_path / "project" / "nested"
    nested.mkdir(parents=True)
    config = nested.parent / ".dtconf"
    config.write_text(
        "other: retained\nfns:\n  user_names:\n    ozon.ru: Озон\n"
    )
    source = _write_json(nested, [_json_entry(1, 11)])
    monkeypatch.chdir(nested)

    arch.command_fns_extract(source, dry_run=True)

    assert not list(nested.glob("*.html"))
    assert "would create 20260730 REC Озон autogen.html" in caplog.text
    arch.command_fns_config_init_map(source)
    assert "other: retained" in config.read_text(encoding="utf-8")


def test_fns_extract_writes_valid_receipts_but_reports_invalid_ones(tmp_path):
    source = _write_json(tmp_path, [_json_entry(1, 11), {}])

    with pytest.raises(arch.errors.UserError, match="1 invalid receipt"):
        arch.command_fns_extract(source, out_dir=tmp_path)

    assert (tmp_path / "20260730 REC ozon.ru autogen.html").exists()


def test_fns_config_init_map_verbose_reports_added_and_existing(
    tmp_path, caplog
):
    caplog.set_level(logging.INFO, logger="davo.services.arch")
    config = tmp_path / ".dtconf"
    config.write_text("fns:\n  user_names:\n    ozon.ru: Озон\n")
    source = _write_json(
        tmp_path,
        [
            _json_entry(1, 11, user="ozon.ru"),
            _json_entry(2, 22, user="Новый / магазин"),
            _json_entry(3, 33, user="ozon.ru"),
        ],
    )

    arch.command_fns_config_init_map(source, config=config, verbose=True)

    contents = config.read_text(encoding="utf-8")
    assert "Новый / магазин: ''" in contents
    assert "existing ozon.ru -> Озон" in caplog.text
    assert "added Новый / магазин ->" in caplog.text
    assert caplog.text.count("existing ozon.ru") == 1


@pytest.mark.parametrize("option", ["-v", "--verbose"])
def test_cli_fns_config_init_map_verbose_options(option):
    from davo import cli

    namespace = cli.init_parser().parse_args(
        ["arch", "fns-config", "init-map", option, "export.json"]
    )

    assert namespace.verbose is True


@pytest.mark.parametrize(
    ("option", "attribute"),
    [
        ("--normalise", "normalise"),
        ("-n", "normalise"),
        ("--dry-run", "dry_run"),
        ("-0", "dry_run"),
        ("--extra-meta", "extra_meta"),
        ("-e", "extra_meta"),
    ],
)
def test_cli_fns_config_init_map_new_options(option, attribute):
    from davo import cli

    namespace = cli.init_parser().parse_args(
        ["arch", "fns-config", "init-map", option, "export.json"]
    )

    assert getattr(namespace, attribute) is True


def test_fns_config_init_map_normalise_and_dry_run(tmp_path, caplog):
    caplog.set_level(logging.INFO, logger="davo.services.arch")
    config = tmp_path / "new-project" / ".dtconf"
    source = _write_json(
        tmp_path, [_json_entry(1, 11, user="ИП Иванов Иван Иванович")]
    )

    arch.command_fns_config_init_map(
        source, config=config, normalise=True, dry_run=True
    )

    assert not config.parent.exists()
    assert "would add ИП Иванов Иван Иванович -> ИП Иванов" in caplog.text

    arch.command_fns_config_init_map(source, config=config, normalise=True)

    assert yaml.safe_load(config.read_text(encoding="utf-8"))["fns"][
        "user_names"
    ] == {"ИП Иванов Иван Иванович": "ИП Иванов"}


def test_fns_config_init_map_extra_meta_for_new_users_only(tmp_path):
    config = tmp_path / ".dtconf"
    config.write_text("fns:\n  user_names:\n    Existing: Alias\n")
    first = _json_entry(1, 11, user="New seller")
    first["ticket"]["document"]["receipt"].update(
        {
            "retailPlace": "shop.example",
            "userInn": "123  ",
            "retailPlaceAddress": "Address one",
            "sellerAddress": "seller@example.test",
        }
    )
    second = _json_entry(2, 22, user="New seller")
    second["ticket"]["document"]["receipt"].update(
        {
            "retailPlace": "other.example",
            "userInn": "123",
            "retailPlaceAddress": "Address two",
        }
    )
    existing = _json_entry(3, 33, user="Existing")
    existing["ticket"]["document"]["receipt"]["retailPlace"] = "ignored"
    source = _write_json(tmp_path, [first, second, existing])

    arch.command_fns_config_init_map(source, config=config, extra_meta=True)

    contents = config.read_text(encoding="utf-8")
    assert "# retailPlace: shop.example; other.example" in contents
    assert "# userInn: 123" in contents
    assert "# retailPlaceAddress: Address one; Address two" in contents
    assert "# sellerAddress: seller@example.test" in contents
    assert contents.index("# retailPlace: shop.example") < contents.index(
        "New seller: ''"
    )
    assert "ignored" not in contents


def test_fns_config_init_map_extra_meta_dry_run_logs_without_writing(
    tmp_path, caplog
):
    caplog.set_level(logging.INFO, logger="davo.services.arch")
    config = tmp_path / "new-project" / ".dtconf"
    entry = _json_entry(1, 11, user="New seller")
    entry["ticket"]["document"]["receipt"]["retailPlace"] = "shop.example"
    source = _write_json(tmp_path, [entry])

    arch.command_fns_config_init_map(
        source, config=config, dry_run=True, extra_meta=True
    )

    assert not config.parent.exists()
    assert "would add # retailPlace: shop.example" in caplog.text


def test_fns_config_init_map_preserves_existing_user_comments(tmp_path):
    config = tmp_path / ".dtconf"
    config.write_text(
        "fns:\n"
        "  user_names:\n"
        "    # retailPlace: first.example\n"
        "    # userInn: 111\n"
        "    First seller: ''\n",
        encoding="utf-8",
    )
    first = _json_entry(1, 11, user="First seller")
    second = _json_entry(2, 22, user="Second seller")
    second["ticket"]["document"]["receipt"].update(
        {"retailPlace": "second.example", "userInn": "222"}
    )
    source = _write_json(tmp_path, [first, second])

    arch.command_fns_config_init_map(source, config=config, extra_meta=True)

    contents = config.read_text(encoding="utf-8")
    assert "# retailPlace: first.example" in contents
    assert "# userInn: 111" in contents
    assert "# retailPlace: second.example" in contents
    assert "# userInn: 222" in contents

    arch.command_fns_config_init_map(source, config=config, extra_meta=True)

    contents = config.read_text(encoding="utf-8")
    assert contents.count("# retailPlace: first.example") == 1
    assert contents.count("# retailPlace: second.example") == 1
