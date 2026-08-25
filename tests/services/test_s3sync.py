import hashlib
import os
from types import SimpleNamespace

import pytest

from davo import constants
from davo import utils as davo_utils
from davo.services.s3sync import cache, cli, conf, handlers, utils


def test_cli_command_with_mapping():
    assert cli._command("diff", {"diff": "d"}) == "d"


def test_cli_command_with_non_mapping():
    assert cli._command("diff", ["diff"]) == "diff"


def test_file_path_info_absolute_project_root(monkeypatch):
    path, key = utils.file_path_info(
        "/repo",
        project_root="/repo",
        current_root="/repo",
    )
    assert path == "/repo"
    assert key == ""


def test_file_path_info_relative_from_project_root(monkeypatch):
    path, key = utils.file_path_info(
        "a/b.txt",
        project_root="/repo",
        current_root="/repo",
    )
    assert path == "/repo/a/b.txt"
    assert key == "a/b.txt"


def test_file_path_info_relative_from_nested_current_root(monkeypatch):
    path, key = utils.file_path_info(
        "child/file.txt",
        project_root="/repo",
        current_root="/repo/sub",
    )
    assert path == "/repo/sub/child/file.txt"
    assert key == "sub/child/file.txt"


def test_check_file_type_allow_list():
    assert utils.check_file_type("photo.JPG", "jpg,png") is True
    assert utils.check_file_type("video.mp4", "jpg,png") is False


def test_check_file_type_exclude_list():
    assert utils.check_file_type("photo.jpg", "^jpg,png") is False
    assert utils.check_file_type("video.mp4", "^jpg,png") is True


def test_is_excluded_matches_substring_rule():
    assert davo_utils.path.is_excluded("photos/audio/song.mp3", ("audio",))
    assert not davo_utils.path.is_excluded("photos/image.jpg", ("audio",))


def test_is_excluded_matches_regex_rule():
    assert davo_utils.path.is_excluded(
        "photo/2019/image.jpg", ("^photo/201[0-9]",)
    )
    assert not davo_utils.path.is_excluded(
        "archive/photo/2019/image.jpg", ("^photo/201[0-9]",)
    )


def _diff_file(state, comment=None):
    return {"state": state, "comment": comment or []}


def _on_diff_with_etag(tmp_path, monkeypatch, etag, content="local", **kwargs):
    local_file = tmp_path / "local.txt"
    local_file.write_text(content, encoding="utf-8")
    remote_file = SimpleNamespace(
        name="local.txt",
        size=local_file.stat().st_size,
        last_modified="2026-01-01T00:00:00.000Z",
        etag=etag,
    )

    def iter_local_path(**_kwargs):
        return [str(local_file)]

    def file_key(_path):
        return "local.txt"

    def iter_remote_path(*_args, **_kwargs):
        return iter([remote_file])

    def connect_bucket():
        return object()

    monkeypatch.setattr(conf, "init", lambda: None)
    monkeypatch.setattr(utils, "connect_bucket", connect_bucket)
    monkeypatch.setattr(utils, "iter_local_path", iter_local_path)
    monkeypatch.setattr(utils, "file_key", file_key)
    monkeypatch.setattr(utils, "iter_remote_path", iter_remote_path)

    options = {
        "all": False,
        "modes": constants.STATES_DIFF_ALL,
        "path": str(tmp_path),
        "recursive": True,
        "depth": None,
        "file_types": None,
        "ignore_case": False,
        "no_cache": True,
        "md5": True,
        "force_upload": False,
        "force_download": False,
        "brief": True,
        "verbose": False,
    }
    options.update(kwargs)
    namespace = SimpleNamespace(**options)
    return handlers.on_diff(namespace, print_details=False)


@pytest.mark.parametrize("quoted", (False, True))
def test_on_diff_md5_accepts_matching_s3_etag(tmp_path, monkeypatch, quoted):
    md5 = hashlib.md5(b"local").hexdigest()
    etag = '"{}"'.format(md5.upper()) if quoted else md5.upper()

    _bucket, diff = _on_diff_with_etag(
        tmp_path, monkeypatch, etag, modes=constants.STATES_ALL
    )

    assert diff["local.txt"]["state"] == constants.STATE_EQUAL


def test_on_diff_md5_shows_both_hashes_in_verbose_output(
    tmp_path, monkeypatch
):
    remote_md5 = hashlib.md5(b"other").hexdigest()

    _bucket, diff = _on_diff_with_etag(
        tmp_path, monkeypatch, '"{}"'.format(remote_md5), verbose=True
    )

    assert diff["local.txt"]["state"] != constants.STATE_EQUAL
    assert "md5: local {}, remote {}".format(
        hashlib.md5(b"local").hexdigest(), remote_md5
    ) in handlers._diff_display_lines(  # pylint: disable=protected-access
        diff, diff, verbose=True
    )[0]


def test_on_diff_md5_skips_multipart_etag(tmp_path, monkeypatch, caplog):
    _bucket, diff = _on_diff_with_etag(
        tmp_path, monkeypatch, '"0123456789abcdef0123456789abcdef-2"'
    )

    assert diff == {}
    assert "not a single-part MD5" in caplog.text


def test_on_diff_md5_verbose_omits_matching_files(tmp_path, monkeypatch):
    md5 = hashlib.md5(b"local").hexdigest()

    _bucket, diff = _on_diff_with_etag(
        tmp_path, monkeypatch, md5, verbose=True
    )

    assert diff == {}


def test_diff_display_lines_collapses_wholly_missing_folders():
    files = {
        "local/a.txt": _diff_file(constants.STATE_LOCAL_NEW),
        "local/nested/b.txt": _diff_file(constants.STATE_LOCAL_NEW),
        "remote/a.txt": _diff_file(constants.STATE_LOCAL_MISSING),
        "remote/nested/b.txt": _diff_file(constants.STATE_LOCAL_MISSING),
    }

    assert handlers._diff_display_lines(files, files) == [  # pylint: disable=protected-access
        "+ local/ (2 files)",
        "- remote/ (2 files)",
    ]


def test_diff_display_lines_verbose_keeps_individual_files():
    files = {
        "local/z.txt": _diff_file(constants.STATE_LOCAL_NEW),
        "local/a.txt": _diff_file(constants.STATE_LOCAL_NEW, ["size: 1%"]),
    }

    assert handlers._diff_display_lines(  # pylint: disable=protected-access
        files, files, verbose=True
    ) == [
        "+ local/z.txt ",
        "+ local/a.txt size: 1%",
    ]


def test_diff_display_lines_sorts_non_verbose_output_by_path():
    files = {
        "z.txt": _diff_file(constants.STATE_LOCAL_NEW),
        "a.txt": _diff_file(constants.STATE_LOCAL_MISSING),
        "m.txt": _diff_file(constants.STATE_LOCAL_NEWER, ["size: 1%"]),
    }

    assert handlers._diff_display_lines(files, files) == [  # pylint: disable=protected-access
        "- a.txt ",
        "> m.txt size: 1%",
        "+ z.txt ",
    ]


def test_diff_display_lines_does_not_collapse_selected_root():
    files = {
        "photo/200x/2008/08/15-22 _g/DSCN0667.JPG": _diff_file(
            constants.STATE_LOCAL_MISSING
        ),
        "photo/200x/2008/08/15-22 _g/DSCN0670.jpg": _diff_file(
            constants.STATE_LOCAL_MISSING
        ),
    }

    assert handlers._diff_display_lines(  # pylint: disable=protected-access
        files, files, root_key="photo/200x/2008/08/15-22 _g"
    ) == [
        "- photo/200x/2008/08/15-22 _g/DSCN0667.JPG ",
        "- photo/200x/2008/08/15-22 _g/DSCN0670.jpg ",
    ]


def test_diff_display_lines_only_collapses_complete_nested_trees():
    all_files = {
        "root/exists.txt": _diff_file(constants.STATE_EQUAL),
        "root/new/a.txt": _diff_file(constants.STATE_LOCAL_NEW),
        "root/new/b.txt": _diff_file(constants.STATE_LOCAL_NEW),
        "root/a.txt": _diff_file(constants.STATE_LOCAL_NEW),
        "root/b.txt": _diff_file(constants.STATE_LOCAL_NEW),
    }
    files = {
        key: data
        for key, data in all_files.items()
        if data["state"] != constants.STATE_EQUAL
    }

    assert handlers._diff_display_lines(  # pylint: disable=protected-access
        files, all_files, root_key="root"
    ) == [
        "+ root/a.txt ",
        "+ root/b.txt ",
        "+ root/new/ (2 files)",
    ]


@pytest.mark.parametrize("no_cache", (False, True))
def test_on_diff_excludes_ignored_remote_keys(tmp_path, monkeypatch, no_cache):
    local_file = tmp_path / "local.txt"
    local_file.write_text("local", encoding="utf-8")
    remote_files = [
        SimpleNamespace(
            name="audio/song.mp3",
            size=1,
            last_modified="2026-01-01T00:00:00.000Z",
            etag='"ignored"',
        ),
        SimpleNamespace(
            name="keep.txt",
            size=1,
            last_modified="2026-01-01T00:00:00.000Z",
            etag='"kept"',
        ),
    ]
    cached_values = []

    monkeypatch.setattr(conf, "init", lambda: None)
    monkeypatch.setattr(utils, "connect_bucket", lambda: object())
    monkeypatch.setattr(
        utils, "iter_local_path", lambda **_kwargs: [str(local_file)]
    )
    monkeypatch.setattr(utils, "file_key", lambda _path: "local.txt")

    def iter_remote(*_args, **kwargs):
        cached_values.append(kwargs["cached"])
        return iter(remote_files)

    monkeypatch.setattr(utils, "iter_remote_path", iter_remote)
    monkeypatch.setattr(cache.cache, "init", lambda: None)
    monkeypatch.setattr(cache.cache, "total", lambda: 1)
    monkeypatch.setitem(conf._CONFIG, "IGNORE", ("audio",))

    namespace = SimpleNamespace(
        all=False,
        modes=constants.STATES_DIFF_ALL,
        path=str(tmp_path),
        recursive=True,
        depth=None,
        file_types=None,
        ignore_case=False,
        no_cache=no_cache,
        md5=False,
        force_upload=False,
        force_download=False,
        brief=True,
    )

    _bucket, diff = handlers.on_diff(namespace, print_details=False)

    assert "audio/song.mp3" not in diff
    assert "keep.txt" in diff
    assert cached_values == [not no_cache]


def test_load_config_tree_merges_global_and_local(monkeypatch):
    local_root = "/repo"
    global_path = "/global.yaml"

    local_config = {
        "GLOBAL_CONFIG": global_path,
        "LOAD_SECRETS": False,
        "BUCKET": "local",
    }
    global_config = {"BUCKET": "global", "ACCESS_KEY": "k"}

    def fake_load_config(path, **kwargs):
        if path == os.path.join(local_root, "s3sync.yaml"):
            return local_config
        if path == global_path:
            return global_config
        raise AssertionError(path)

    monkeypatch.setattr(
        conf.settings, "CONFIG_PATH_S3SYNC_LOCAL", "s3sync.yaml"
    )
    monkeypatch.setattr(conf, "load_config", fake_load_config)
    monkeypatch.setattr(conf.os.path, "exists", lambda p: p == global_path)

    cfg = conf.load_config_tree(local_root, "/unused.yaml")

    assert cfg["PROJECT_ROOT"] == local_root
    assert cfg["LOCAL_CONFIG"] == os.path.join(local_root, "s3sync.yaml")
    # local must override global on conflict
    assert cfg["BUCKET"] == "local"
    assert cfg["ACCESS_KEY"] == "k"


def test_load_config_tree_without_global_file(monkeypatch):
    local_root = "/repo"

    local_config = {
        "GLOBAL_CONFIG": "/missing.yaml",
        "BUCKET": "local",
    }

    monkeypatch.setattr(
        conf.settings, "CONFIG_PATH_S3SYNC_LOCAL", "s3sync.yaml"
    )
    monkeypatch.setattr(
        conf,
        "load_config",
        lambda path, **kwargs: local_config,
    )
    monkeypatch.setattr(conf.os.path, "exists", lambda _p: False)

    cfg = conf.load_config_tree(local_root, "/unused.yaml")

    assert cfg["BUCKET"] == "local"


def test_cache_select_exact_file_prefix_with_delimiter(tmp_path, monkeypatch):
    monkeypatch.setattr(
        conf,
        "_CONFIG",
        {
            **conf._CONFIG,
            "PROJECT_ROOT": str(tmp_path),
            "CACHE_FILE_NAME": ".s3cache-test.db",
        },
    )

    db = cache.Cache()
    db.init()
    try:
        db.update(
            "AGENTS.md",
            {
                "name": "AGENTS.md",
                "size": 1,
                "last_modified": "2026-05-13T00:00:00.000Z",
                "etag": "e1",
            },
        )
        db.flush()

        rows = list(db.select(prefix="AGENTS.md", delimiter="/"))
    finally:
        db.close()

    assert [row["name"] for row in rows] == ["AGENTS.md"]


def test_cache_select_directory_prefix_with_delimiter(tmp_path, monkeypatch):
    monkeypatch.setattr(
        conf,
        "_CONFIG",
        {
            **conf._CONFIG,
            "PROJECT_ROOT": str(tmp_path),
            "CACHE_FILE_NAME": ".s3cache-test.db",
        },
    )

    db = cache.Cache()
    db.init()
    try:
        db.update(
            "docs/one.md",
            {
                "name": "docs/one.md",
                "size": 1,
                "last_modified": "2026-05-13T00:00:00.000Z",
                "etag": "e1",
            },
        )
        db.update(
            "docs/sub/two.md",
            {
                "name": "docs/sub/two.md",
                "size": 1,
                "last_modified": "2026-05-13T00:00:00.000Z",
                "etag": "e2",
            },
        )
        db.flush()

        rows = list(db.select(prefix="docs/", delimiter="/"))
    finally:
        db.close()

    assert [row["name"] for row in rows] == ["docs/one.md"]
