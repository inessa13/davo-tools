import json
import logging
from pathlib import Path

import pytest
import yaml

from davo import settings
from davo.services import arch


@pytest.fixture(autouse=True)
def _isolated_davo_user_config(tmp_path, monkeypatch):
    monkeypatch.setattr(
        settings, "CONFIG_PATH_DAVO_TOOLS", str(tmp_path / "user-config.yaml")
    )


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

    arch.command_fns_rename(tmp_path, dry_run=True)

    assert source.exists()
    assert not target.exists()
    assert "would copy receipt.html -> 20260808 REC ozon.ru.html" in (
        caplog.text
    )
    assert str(tmp_path) not in caplog.text


def test_dry_run_only_plans_rename(tmp_path, caplog):
    caplog.set_level(logging.INFO, logger="davo.services.arch")
    source = _write_receipt(tmp_path, "receipt.html")
    target = tmp_path / "20260808 REC ozon.ru.html"

    arch.command_fns_rename(tmp_path, rename=True, dry_run=True)

    assert source.exists()
    assert not target.exists()
    assert "would rename receipt.html -> 20260808 REC ozon.ru.html" in (
        caplog.text
    )


def test_fns_rename_copies_by_default(tmp_path):
    source = _write_receipt(tmp_path, "receipt.html")
    target = tmp_path / "20260808 REC ozon.ru.html"

    arch.command_fns_rename(tmp_path)

    assert source.exists()
    assert target.read_text(encoding="utf-8") == source.read_text(
        encoding="utf-8"
    )


def test_fns_rename_dry_run_reports_collision_without_changing_files(
    tmp_path, caplog
):
    caplog.set_level(logging.INFO, logger="davo.services.arch")
    source = _write_receipt(tmp_path, "receipt.html")
    target = tmp_path / "20260808 REC ozon.ru.html"
    target.write_text("existing", encoding="utf-8")

    arch.command_fns_rename(tmp_path, dry_run=True)

    assert source.exists()
    assert target.read_text(encoding="utf-8") == "existing"
    assert "target already exists: 20260808 REC ozon.ru.html" in caplog.text


def test_commit_copies_unless_rename_requested(tmp_path):
    source = _write_receipt(tmp_path, "receipt.html")
    target = tmp_path / "20260808 REC ozon.ru.html"

    arch.command_fns_rename(tmp_path)

    assert source.exists()
    assert target.read_text(encoding="utf-8") == source.read_text(
        encoding="utf-8"
    )


def test_commit_rename_removes_source(tmp_path):
    source = _write_receipt(tmp_path, "receipt.html")
    target = tmp_path / "20260808 REC ozon.ru.html"

    arch.command_fns_rename(tmp_path, rename=True)

    assert not source.exists()
    assert target.exists()


def test_collision_is_not_overwritten(tmp_path, caplog):
    source = _write_receipt(tmp_path, "receipt.html")
    target = tmp_path / "20260808 REC ozon.ru.html"
    target.write_text("existing", encoding="utf-8")

    arch.command_fns_rename(tmp_path, rename=True)

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
    config = tmp_path / ".davo-tools.yaml"
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
    config = tmp_path / ".davo-tools.yaml"
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


def test_cli_fns_rename_rejects_old_commit_short_option():
    from davo import cli

    with pytest.raises(SystemExit):
        cli.init_parser().parse_args(["arch", "fns-rename", "-c"])


@pytest.mark.parametrize("option", ["-R", "--rename"])
def test_cli_rename_options(option):
    from davo import cli

    namespace = cli.init_parser().parse_args(["arch", "fns-rename", option])

    assert namespace.rename is True


@pytest.mark.parametrize(
    ("old_type", "code"),
    [
        ("check", "REC"),
        ("чек", "REC"),
        ("receipt", "REC"),
        ("R", "REC"),
        ("Ч", "REC"),
        ("purchase", "REC"),
        ("recept", "REC"),
        ("receip", "REC"),
        ("invoice", "INV"),
        ("счет", "INV"),
        ("I", "INV"),
        ("transfer", "TRN"),
        ("ticket", "TCK"),
        ("pass", "TCK"),
        ("voucher", "TCK"),
        ("bp", "BPD"),
        ("посадочные", "BPD"),
        ("fine", "FIN"),
        ("notice", "FIN"),
        ("act", "ACT"),
        ("акт", "ACT"),
        ("claim", "CLM"),
        ("compensation", "CMP"),
        ("warranty", "WRN"),
        ("guaranty", "WRN"),
        ("tax", "TAX"),
        ("выписка", "STM"),
    ],
)
def test_check_norm_converts_legacy_type_and_keeps_detail_and_extension(
    tmp_path, old_type, code
):
    source = tmp_path / "20260129 {} vendor detail.pdf".format(old_type)
    source.write_text("document", encoding="utf-8")

    plan = arch.command_check_norm([tmp_path])

    target = tmp_path / "20260129 {} vendor detail.pdf".format(code)
    assert plan == [arch.ArchiveRename(source, target)]
    assert not source.exists()
    assert target.read_text(encoding="utf-8") == "document"


@pytest.mark.parametrize(
    ("old_name", "new_name", "underscores"),
    [
        (
            "20260727 claim insurance +invoice Golub Chiro.pdf",
            "20260727 CLM +REC Golub Chiro.pdf",
            False,
        ),
        (
            "20260727 compensation insurance 20260804 Golub.pdf",
            "20260727 CMP 20260804 Golub.pdf",
            False,
        ),
        (
            "20260727 claim insurance +invoice Golub Chiro.pdf",
            "20260727_CLM_+REC_Golub_Chiro.pdf",
            True,
        ),
        (
            "20260727 compensation insurance 20260804 Golub.pdf",
            "20260727_CMP_20260804_Golub.pdf",
            True,
        ),
    ],
)
def test_check_norm_normalizes_insurance_claim_detail(
    tmp_path, old_name, new_name, underscores
):
    source = tmp_path / old_name
    source.write_text("document", encoding="utf-8")

    arch.command_check_norm([source], underscores=underscores)

    assert not source.exists()
    assert (tmp_path / new_name).exists()


def test_check_norm_keeps_nonleading_insurance_and_nonmarker_invoice(tmp_path):
    source = tmp_path / "20260727 claim Golub insurance +invoice-copy.pdf"
    source.write_text("document", encoding="utf-8")

    arch.command_check_norm([source])

    assert (
        tmp_path / "20260727 CLM Golub insurance +invoice-copy.pdf"
    ).exists()


def test_check_norm_scans_direct_children_unless_recursive(tmp_path):
    direct = tmp_path / "20260129 check direct.pdf"
    direct.write_text("direct", encoding="utf-8")
    nested = tmp_path / "nested"
    nested.mkdir()
    child = nested / "20260129 invoice child.pdf"
    child.write_text("child", encoding="utf-8")

    arch.command_check_norm([tmp_path])

    assert (tmp_path / "20260129 REC direct.pdf").exists()
    assert child.exists()
    arch.command_check_norm([nested], recursive=True)
    assert (nested / "20260129 INV child.pdf").exists()


def test_check_norm_skips_unknown_and_normalized_names(tmp_path):
    normalized = tmp_path / "20260129 REC vendor.pdf"
    normalized_sidecar = tmp_path / "20260129 REC vendor.drj.json"
    unknown = tmp_path / "20260129 unknown vendor.pdf"
    for path in (normalized, normalized_sidecar, unknown):
        path.write_text("document", encoding="utf-8")

    assert arch.command_check_norm([tmp_path]) == []
    assert all(
        path.exists() for path in (normalized, normalized_sidecar, unknown)
    )


@pytest.mark.parametrize(
    ("old_name", "new_name", "underscores"),
    [
        (
            "20260727 CLM +REC Golub.pdf",
            "20260727_CLM_+REC_Golub.pdf",
            True,
        ),
        (
            "20260727_CMP_Golub.pdf",
            "20260727 CMP Golub.pdf",
            False,
        ),
        (
            "20260727_CLM_+REC_Golub.drj.json",
            "20260727 CLM +REC Golub.drj.json",
            False,
        ),
    ],
)
def test_check_norm_changes_separators_for_normalized_names(
    tmp_path, old_name, new_name, underscores
):
    source = tmp_path / old_name
    source.write_text("document", encoding="utf-8")

    arch.command_check_norm([source], underscores=underscores)

    assert not source.exists()
    assert (tmp_path / new_name).read_text(encoding="utf-8") == "document"


def test_check_norm_skips_normalized_name_in_requested_format(tmp_path):
    source = tmp_path / "20260727_CLM_+REC_Golub.pdf"
    source.write_text("document", encoding="utf-8")

    assert arch.command_check_norm([source], underscores=True) == []
    assert source.exists()


@pytest.mark.parametrize(
    ("old_name", "new_name", "underscores"),
    [
        (
            "20260110 чек.drj.json",
            "20260110 REC.drj.json",
            False,
        ),
        (
            "20260110 чек.drj.json",
            "20260110_REC.drj.json",
            True,
        ),
        (
            "20260727 claim insurance +invoice Golub.drj.json",
            "20260727 CLM +REC Golub.drj.json",
            False,
        ),
        (
            "20260727 compensation insurance Golub.drj.json",
            "20260727_CMP_Golub.drj.json",
            True,
        ),
    ],
)
def test_check_norm_renames_standalone_sidecar(
    tmp_path, old_name, new_name, underscores
):
    source = tmp_path / old_name
    source.write_text("metadata", encoding="utf-8")

    arch.command_check_norm([source], underscores=underscores)

    assert not source.exists()
    assert (tmp_path / new_name).read_text(encoding="utf-8") == "metadata"


def test_check_norm_renames_existing_sidecar_with_document(tmp_path):
    source = tmp_path / "20260129 check vendor.pdf"
    sidecar = tmp_path / "20260129 check vendor.drj.json"
    source.write_text("document", encoding="utf-8")
    sidecar.write_text("metadata", encoding="utf-8")

    plan = arch.command_check_norm([tmp_path])

    assert not source.exists()
    assert not sidecar.exists()
    assert set(plan) == {
        arch.ArchiveRename(
            source, tmp_path / "20260129 REC vendor.pdf"
        ),
        arch.ArchiveRename(
            sidecar, tmp_path / "20260129 REC vendor.drj.json"
        ),
    }
    assert (tmp_path / "20260129 REC vendor.pdf").read_text(
        encoding="utf-8"
    ) == "document"
    assert (tmp_path / "20260129 REC vendor.drj.json").read_text(
        encoding="utf-8"
    ) == "metadata"


def test_check_norm_sidecar_collision_aborts_all_renames(
    tmp_path, caplog, monkeypatch
):
    caplog.set_level(logging.ERROR, logger="davo.services.arch")
    monkeypatch.chdir(tmp_path)
    sidecar = tmp_path / "20260129 check vendor.drj.json"
    target = tmp_path / "20260129 REC vendor.drj.json"
    unaffected = tmp_path / "20260130 invoice utility.pdf"
    sidecar.write_text("metadata", encoding="utf-8")
    target.write_text("existing", encoding="utf-8")
    unaffected.write_text("document", encoding="utf-8")

    arch.command_check_norm([tmp_path])

    assert sidecar.exists()
    assert target.exists()
    assert unaffected.exists()
    assert "20260129 check vendor.drj.json" in caplog.text
    assert "20260129 REC vendor.drj.json" in caplog.text
    assert "target already exists" in caplog.text


def test_check_norm_dry_run_reports_operations_without_changing_files(
    tmp_path, caplog, monkeypatch
):
    caplog.set_level(logging.INFO, logger="davo.services.arch")
    monkeypatch.chdir(tmp_path)
    source = tmp_path / "20260129 check vendor.pdf"
    source.write_text("document", encoding="utf-8")

    arch.command_check_norm([source], dry_run=True)

    target = tmp_path / "20260129 REC vendor.pdf"
    assert source.exists()
    assert not target.exists()
    assert (
        "check-norm: would rename  20260129 check vendor.pdf "
        "-> 20260129 REC vendor.pdf"
    ) in caplog.text


def test_check_norm_collision_aborts_entire_plan_and_reports_paths(
    tmp_path, caplog, monkeypatch
):
    caplog.set_level(logging.ERROR, logger="davo.services.arch")
    monkeypatch.chdir(tmp_path)
    first = tmp_path / "20260129 check vendor.pdf"
    second = tmp_path / "20260129 receipt vendor.pdf"
    first.write_text("first", encoding="utf-8")
    second.write_text("second", encoding="utf-8")

    arch.command_check_norm([tmp_path], dry_run=True)

    target = tmp_path / "20260129 REC vendor.pdf"
    assert first.exists()
    assert second.exists()
    assert not target.exists()
    assert "20260129 check vendor.pdf" in caplog.text
    assert "20260129 receipt vendor.pdf" in caplog.text
    assert "20260129 REC vendor.pdf" in caplog.text
    assert str(tmp_path) not in caplog.text
    assert "multiple sources have the same target" in caplog.text

    caplog.clear()
    arch.command_check_norm([tmp_path])
    assert first.exists()
    assert second.exists()
    assert not target.exists()
    assert "multiple sources have the same target" in caplog.text


def test_check_norm_existing_target_aborts_all_renames(
    tmp_path, caplog, monkeypatch
):
    caplog.set_level(logging.ERROR, logger="davo.services.arch")
    monkeypatch.chdir(tmp_path)
    colliding = tmp_path / "20260129 check vendor.pdf"
    unaffected = tmp_path / "20260130 invoice utility.pdf"
    target = tmp_path / "20260129 REC vendor.pdf"
    colliding.write_text("source", encoding="utf-8")
    unaffected.write_text("source", encoding="utf-8")
    target.write_text("existing", encoding="utf-8")

    arch.command_check_norm([tmp_path])

    assert colliding.exists()
    assert unaffected.exists()
    assert not (tmp_path / "20260130 INV utility.pdf").exists()
    assert "20260129 check vendor.pdf" in caplog.text
    assert "20260129 REC vendor.pdf" in caplog.text
    assert "target already exists" in caplog.text


@pytest.mark.parametrize("option", ["-r", "--recursive"])
def test_cli_check_norm_recursive_option(option):
    from davo import cli

    namespace = cli.init_parser().parse_args(
        ["arch", "check-norm", option, "archive"]
    )

    assert namespace.recursive is True


@pytest.mark.parametrize(
    ("option", "attribute"),
    [
        ("-0", "dry_run"),
        ("--dry-run", "dry_run"),
        ("-u", "underscores"),
        ("--underscores", "underscores"),
    ],
)
def test_cli_check_norm_options(option, attribute):
    from davo import cli

    namespace = cli.init_parser().parse_args(["arch", "check-norm", option])

    assert getattr(namespace, attribute)


@pytest.mark.parametrize("option", ["-t", "--table"])
def test_cli_check_norm_table_option(option):
    from davo import cli

    namespace = cli.init_parser().parse_args(["arch", "check-norm", option])

    assert namespace.table is True


def test_cli_check_norm_forwards_table_option(mocker):
    handler = mocker.patch.object(arch, "command_check_norm")
    from davo import cli

    namespace = cli.init_parser().parse_args(
        ["arch", "check-norm", "-0", "-t", "archive"]
    )
    namespace.func(namespace)

    handler.assert_called_once_with(
        paths=["archive"],
        recursive=False,
        dry_run=True,
        underscores=False,
        table=True,
    )


def test_check_norm_aligns_targets_and_prints_relative_paths(
    tmp_path, caplog, monkeypatch
):
    caplog.set_level(logging.INFO, logger="davo.services.arch")
    monkeypatch.chdir(tmp_path)
    first = tmp_path / "20260129 check short.pdf"
    second = tmp_path / "20260129 invoice longer-vendor-name.pdf"
    first.write_text("first", encoding="utf-8")
    second.write_text("second", encoding="utf-8")

    arch.command_check_norm([tmp_path], dry_run=True)

    messages = [
        record.getMessage()
        for record in caplog.records
        if record.name == "davo.services.arch"
    ]
    assert len(messages) == 2
    assert all(str(tmp_path) not in message for message in messages)
    assert len({message.index(" -> ") for message in messages}) == 1


def test_check_norm_table_includes_relative_paths_and_collisions(
    tmp_path, caplog, monkeypatch
):
    caplog.set_level(logging.ERROR, logger="davo.services.arch")
    monkeypatch.chdir(tmp_path)
    source = tmp_path / "20260129 check vendor.pdf"
    target = tmp_path / "20260129 REC vendor.pdf"
    source.write_text("source", encoding="utf-8")
    target.write_text("existing", encoding="utf-8")

    arch.command_check_norm([tmp_path], dry_run=True, table=True)

    lines = caplog.records[0].getMessage().splitlines()
    assert lines[0] == "check-norm:"
    assert lines[1].startswith("+") and lines[1].endswith("+")
    assert "| Action" in lines[2]
    assert "| Source" in lines[2]
    assert "| Target" in lines[2]
    assert "| Details" in lines[2]
    assert "collision" in caplog.text
    assert "target already exists" in caplog.text
    assert str(tmp_path) not in caplog.text


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


def test_fns_extract_renders_qr_and_numbers_same_store(tmp_path, monkeypatch):
    (tmp_path / ".davo-tools.yaml").write_text(
        "fns:\n  user_names:\n    ozon.ru: ozon.ru\n"
    )
    monkeypatch.chdir(tmp_path)
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


def test_fns_extract_uses_user_alias_without_retail_place(
    tmp_path, monkeypatch
):
    entry = _json_entry(1, 11, user="exact user")
    source = _write_json(tmp_path, [entry])
    config = tmp_path / ".davo-tools.yaml"
    config.write_text("fns:\n  user_names:\n    exact user: Продавец\n")

    monkeypatch.chdir(tmp_path)
    generated = arch.command_fns_extract(source, out_dir=tmp_path)

    assert [path.name for path in generated] == [
        "20260730 REC Продавец autogen.html"
    ]


def test_fns_extract_empty_alias_omits_seller(tmp_path, monkeypatch):
    source = _write_json(tmp_path, [_json_entry(1, 11, user="seller")])
    config = tmp_path / ".davo-tools.yaml"
    config.write_text("fns:\n  user_names:\n    seller: ''\n")

    monkeypatch.chdir(tmp_path)
    generated = arch.command_fns_extract(source, out_dir=tmp_path)

    assert [path.name for path in generated] == ["20260730 REC autogen.html"]


def test_fns_extract_resumes_and_refuses_complete_repeat(
    tmp_path, monkeypatch
):
    (tmp_path / ".davo-tools.yaml").write_text(
        "fns:\n  user_names:\n    ozon.ru: ozon.ru\n"
    )
    monkeypatch.chdir(tmp_path)
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
    config = nested.parent / ".davo-tools.yaml"
    config.write_text(
        "other: retained\nfns:\n  user_names:\n    ozon.ru: Озон\n"
    )
    source = _write_json(nested, [_json_entry(1, 11)])
    monkeypatch.chdir(nested)

    arch.command_fns_extract(source, dry_run=True)

    assert not list(nested.glob("*.html"))
    assert "would create 20260730 REC Озон autogen.html" in caplog.text
    arch.command_fns_config_init_map(source, local=True)
    assert "other: retained" in config.read_text(encoding="utf-8")


def test_fns_extract_writes_valid_receipts_but_reports_invalid_ones(
    tmp_path, monkeypatch
):
    (tmp_path / ".davo-tools.yaml").write_text(
        "fns:\n  user_names:\n    ozon.ru: ozon.ru\n"
    )
    monkeypatch.chdir(tmp_path)
    source = _write_json(tmp_path, [_json_entry(1, 11), {}])

    with pytest.raises(arch.errors.UserError, match="1 invalid receipt"):
        arch.command_fns_extract(source, out_dir=tmp_path)

    assert (tmp_path / "20260730 REC ozon.ru autogen.html").exists()


def test_fns_extract_no_autogen_changes_only_filename(tmp_path, monkeypatch):
    (tmp_path / ".davo-tools.yaml").write_text(
        "fns:\n  user_names:\n    ozon.ru: ozon.ru\n"
    )
    monkeypatch.chdir(tmp_path)
    source = _write_json(tmp_path, [_json_entry(1, 11)])

    generated = arch.command_fns_extract(
        source, out_dir=tmp_path, no_autogen=True
    )

    assert [path.name for path in generated] == ["20260730 REC ozon.ru.html"]
    assert "davo-fns-autogen fiscal-identity" in generated[0].read_text(
        encoding="utf-8"
    )


def test_fns_extract_pdf_stores_identity_and_resumes_by_type(
    tmp_path, monkeypatch
):
    from davo.services.photo import pdf

    (tmp_path / ".davo-tools.yaml").write_text(
        "fns:\n  user_names:\n    ozon.ru: ozon.ru\n"
    )
    monkeypatch.chdir(tmp_path)
    source = _write_json(tmp_path, [_json_entry(1, 11)])
    rendered_html = []

    def render(fitz, input_file, temp_dir):
        rendered_html.append(Path(input_file).read_text(encoding="utf-8"))
        path = Path(temp_dir) / "browser.pdf"
        doc = fitz.open()
        doc.new_page()
        doc.save(path)
        doc.close()
        return str(path)

    monkeypatch.setattr(pdf, "_render_html_to_pdf", render)
    generated = arch.command_fns_extract(
        source, out_dir=tmp_path, output_type="pdf", no_autogen=True
    )

    assert [path.name for path in generated] == ["20260730 REC ozon.ru.pdf"]
    assert rendered_html and "КАССОВЫЙ ЧЕК" in rendered_html[0]
    assert not list(tmp_path.glob("20260730 REC ozon.ru.html"))
    fitz = pdf._import_fitz("test")
    with fitz.open(generated[0]) as document:
        assert (
            "davo-fns-autogen fiscal-identity: fn=123 fd=1 fp=11"
            in (document.metadata["keywords"])
        )
    with pytest.raises(arch.errors.UserError, match="repeated run"):
        arch.command_fns_extract(source, out_dir=tmp_path, output_type="pdf")

    html = arch.command_fns_extract(source, out_dir=tmp_path)
    assert html[0].suffix == ".html"


def test_fns_extract_pdf_dry_run_does_not_render(tmp_path, monkeypatch):
    from davo.services.photo import pdf

    (tmp_path / ".davo-tools.yaml").write_text("fns: {}\n")
    monkeypatch.chdir(tmp_path)
    source = _write_json(tmp_path, [_json_entry(1, 11)])
    monkeypatch.setattr(
        pdf,
        "_render_html_to_pdf",
        lambda *_args: pytest.fail("renderer must not run during dry run"),
    )

    generated = arch.command_fns_extract(
        source, out_dir=tmp_path, output_type="pdf", dry_run=True
    )

    assert [path.name for path in generated] == [
        "20260730 REC ozon.ru autogen.pdf"
    ]
    assert not generated[0].exists()


def test_fns_config_init_map_verbose_reports_added_and_existing(
    tmp_path, caplog, monkeypatch
):
    caplog.set_level(logging.INFO, logger="davo.services.arch")
    config = tmp_path / ".davo-tools.yaml"
    config.write_text("fns:\n  user_names:\n    ozon.ru: Озон\n")
    source = _write_json(
        tmp_path,
        [
            _json_entry(1, 11, user="ozon.ru"),
            _json_entry(2, 22, user="Новый / магазин"),
            _json_entry(3, 33, user="ozon.ru"),
        ],
    )

    monkeypatch.chdir(tmp_path)
    arch.command_fns_config_init_map(source, local=True, verbose=True)

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


def test_fns_config_init_map_normalise_and_dry_run(
    tmp_path, caplog, monkeypatch
):
    caplog.set_level(logging.INFO, logger="davo.services.arch")
    config = tmp_path / ".davo-tools.yaml"
    source = _write_json(
        tmp_path, [_json_entry(1, 11, user="ИП Иванов Иван Иванович")]
    )

    monkeypatch.chdir(config.parent)
    arch.command_fns_config_init_map(
        source, local=True, normalise=True, dry_run=True
    )

    assert not config.exists()
    assert "would add ИП Иванов Иван Иванович -> ИП Иванов" in caplog.text

    arch.command_fns_config_init_map(source, local=True, normalise=True)

    assert yaml.safe_load(config.read_text(encoding="utf-8"))["fns"][
        "user_names"
    ] == {"ИП Иванов Иван Иванович": "ИП Иванов"}


def test_fns_config_init_map_extra_meta_for_new_users_only(
    tmp_path, monkeypatch
):
    config = tmp_path / ".davo-tools.yaml"
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

    monkeypatch.chdir(tmp_path)
    arch.command_fns_config_init_map(source, local=True, extra_meta=True)

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
    tmp_path, caplog, monkeypatch
):
    caplog.set_level(logging.INFO, logger="davo.services.arch")
    config = tmp_path / ".davo-tools.yaml"
    entry = _json_entry(1, 11, user="New seller")
    entry["ticket"]["document"]["receipt"]["retailPlace"] = "shop.example"
    source = _write_json(tmp_path, [entry])

    monkeypatch.chdir(config.parent)
    arch.command_fns_config_init_map(
        source, local=True, dry_run=True, extra_meta=True
    )

    assert not config.exists()
    assert "would add # retailPlace: shop.example" in caplog.text


def test_fns_config_init_map_preserves_existing_user_comments(
    tmp_path, monkeypatch
):
    config = tmp_path / ".davo-tools.yaml"
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

    monkeypatch.chdir(tmp_path)
    arch.command_fns_config_init_map(source, local=True, extra_meta=True)

    contents = config.read_text(encoding="utf-8")
    assert "# retailPlace: first.example" in contents
    assert "# userInn: 111" in contents
    assert "# retailPlace: second.example" in contents
    assert "# userInn: 222" in contents

    arch.command_fns_config_init_map(source, local=True, extra_meta=True)

    contents = config.read_text(encoding="utf-8")
    assert contents.count("# retailPlace: first.example") == 1
    assert contents.count("# retailPlace: second.example") == 1


def test_fns_dedup_finds_html_candidate_in_json_reference(tmp_path, caplog):
    caplog.set_level(logging.INFO, logger="davo.services.arch")
    incoming = tmp_path / "incoming" / "nested"
    archive = tmp_path / "archive" / "nested"
    incoming.mkdir(parents=True)
    archive.mkdir(parents=True)
    candidate = incoming / "receipt.html"
    candidate.write_text(
        "<p>ФН: №123<br>ФД: №1<br>ФПД:#11</p>", encoding="utf-8"
    )
    reference = _write_json(archive, [_json_entry(1, 11)])

    matches = arch.command_fns_dedup([incoming.parent], [archive.parent])

    assert [(item.candidate, item.reference) for item in matches] == [
        (candidate, reference)
    ]
    assert candidate.exists()
    assert "fn=123 fd=1 fp=11" in caplog.text


def test_fns_dedup_scans_autogen_html_and_pdf(tmp_path, monkeypatch):
    incoming = tmp_path / "incoming"
    archive = tmp_path / "archive"
    incoming.mkdir()
    archive.mkdir()
    html = incoming / "receipt.html"
    html.write_text(
        "<!-- davo-fns-autogen fiscal-identity: fn=123 fd=1 fp=11 -->",
        encoding="utf-8",
    )
    pdf = archive / "receipt.pdf"
    pdf.write_bytes(b"not inspected by this test")
    monkeypatch.setattr(
        arch,
        "_pdf_fiscal_identities",
        lambda path: {("123", "1", "11")} if path == pdf else set(),
    )

    matches = arch.command_fns_dedup([incoming], [archive])

    assert len(matches) == 1
    assert matches[0].reference == pdf


def test_fns_dedup_delete_and_dry_run_never_change_references(
    tmp_path, caplog
):
    caplog.set_level(logging.INFO, logger="davo.services.arch")
    incoming = tmp_path / "incoming"
    archive = tmp_path / "archive"
    incoming.mkdir()
    archive.mkdir()
    duplicate = _write_json(incoming, [_json_entry(1, 11)])
    reference = _write_json(archive, [_json_entry(1, 11)])

    arch.command_fns_dedup([incoming], [archive], delete=True, dry_run=True)

    assert duplicate.exists()
    assert reference.exists()
    assert "would delete" in caplog.text
    assert "duplicate" not in caplog.text

    arch.command_fns_dedup([incoming], [archive], delete=True)

    assert not duplicate.exists()
    assert reference.exists()


def test_fns_dedup_keeps_candidate_json_with_unique_receipts(tmp_path, caplog):
    caplog.set_level(logging.INFO, logger="davo.services.arch")
    incoming = tmp_path / "incoming"
    archive = tmp_path / "archive"
    incoming.mkdir()
    archive.mkdir()
    candidate = _write_json(incoming, [_json_entry(1, 11), _json_entry(2, 22)])
    _write_json(archive, [_json_entry(1, 11)])

    arch.command_fns_dedup([incoming], [archive], delete=True)

    assert candidate.exists()
    assert "also contains unique receipts" in caplog.text


def test_fns_dedup_reports_missing_identity_only_when_verbose(
    tmp_path, caplog
):
    caplog.set_level(logging.WARNING, logger="davo.services.arch")
    incoming = tmp_path / "incoming"
    archive = tmp_path / "archive"
    incoming.mkdir()
    archive.mkdir()
    (incoming / "not-a-receipt.html").write_text("<p>other file</p>")

    arch.command_fns_dedup([incoming], [archive])

    assert "no fiscal identity found" not in caplog.text
    arch.command_fns_dedup([incoming], [archive], verbose=True)
    assert "no fiscal identity found" in caplog.text


def test_cli_fns_dedup_options():
    from davo import cli

    namespace = cli.init_parser().parse_args(
        [
            "arch", "fns-dedup", "-d", "one", "two", "-r", "three",
            "-D", "-0", "-v",
        ]
    )

    assert namespace.directories == ["one", "two"]
    assert namespace.reference == ["three"]
    assert namespace.delete is True
    assert namespace.dry_run is True
    assert namespace.verbose is True
