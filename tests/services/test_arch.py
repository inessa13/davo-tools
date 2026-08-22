import logging

import pytest

from davo.services import arch


def _receipt(date="08.08.26 12.10", place="ozon.ru"):
    return """<html><body>
        <td>Место расчета: {}</td>
        <td>Дата: {}</td>
    </body></html>""".format(place, date)


def _write_receipt(root, name, **kwargs):
    path = root / name
    path.write_text(_receipt(**kwargs), encoding="utf-8")
    return path


def test_extract_fns_name_normalises_store(tmp_path):
    receipt = _write_receipt(
        tmp_path,
        "receipt.html",
        date="09.08.26 04.51",
        place="  ozon.ru/  ",
    )

    assert arch.extract_fns_name(receipt) == "20260809 Ч ozon.ru.html"


def test_plan_numbers_duplicate_names_in_sort_order(tmp_path):
    _write_receipt(tmp_path, "b.html")
    _write_receipt(tmp_path, "a.html")

    plan = arch.plan_fns_rename(tmp_path)

    assert [(item.source.name, item.target.name) for item in plan] == [
        ("a.html", "20260808 Ч ozon.ru 1.html"),
        ("b.html", "20260808 Ч ozon.ru 2.html"),
    ]


def test_plan_uses_single_digit_numbers_for_nine_duplicates(tmp_path):
    for index in range(9):
        _write_receipt(tmp_path, "receipt-{}.html".format(index))

    names = [item.target.name for item in arch.plan_fns_rename(tmp_path)]

    assert names[0] == "20260808 Ч ozon.ru 1.html"
    assert names[-1] == "20260808 Ч ozon.ru 9.html"


def test_plan_uses_two_digit_numbers_for_ten_duplicates(tmp_path):
    for index in range(10):
        _write_receipt(tmp_path, "receipt-{}.html".format(index))

    names = [item.target.name for item in arch.plan_fns_rename(tmp_path)]

    assert names[0] == "20260808 Ч ozon.ru 01.html"
    assert names[-1] == "20260808 Ч ozon.ru 10.html"


def test_dry_run_only_plans_copy(tmp_path, caplog):
    caplog.set_level(logging.INFO, logger="davo.services.arch")
    source = _write_receipt(tmp_path, "receipt.html")
    target = tmp_path / "20260808 Ч ozon.ru.html"

    arch.command_fns_rename(tmp_path)

    assert source.exists()
    assert not target.exists()
    assert "copy receipt.html -> 20260808 Ч ozon.ru.html" in caplog.text
    assert str(tmp_path) not in caplog.text


def test_commit_copies_unless_rename_requested(tmp_path):
    source = _write_receipt(tmp_path, "receipt.html")
    target = tmp_path / "20260808 Ч ozon.ru.html"

    arch.command_fns_rename(tmp_path, commit=True)

    assert source.exists()
    assert target.read_text(encoding="utf-8") == source.read_text(
        encoding="utf-8"
    )


def test_commit_rename_removes_source(tmp_path):
    source = _write_receipt(tmp_path, "receipt.html")
    target = tmp_path / "20260808 Ч ozon.ru.html"

    arch.command_fns_rename(tmp_path, commit=True, rename=True)

    assert not source.exists()
    assert target.exists()


def test_collision_is_not_overwritten(tmp_path, caplog):
    source = _write_receipt(tmp_path, "receipt.html")
    target = tmp_path / "20260808 Ч ozon.ru.html"
    target.write_text("existing", encoding="utf-8")

    arch.command_fns_rename(tmp_path, commit=True, rename=True)

    assert source.exists()
    assert target.read_text(encoding="utf-8") == "existing"
    assert "target already exists: 20260808 Ч ozon.ru.html" in caplog.text
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
