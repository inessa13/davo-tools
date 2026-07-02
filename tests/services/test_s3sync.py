import os

from davo.services.s3sync import cache, cli, conf, utils


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
