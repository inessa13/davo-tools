import pytest

from davo import cli, errors, settings
from davo.services import arch
from davo.utils import conf


def test_load_davo_config_deep_merges_and_resolves_each_layer(tmp_path):
    user = tmp_path / "user" / "davo-tools.yaml"
    project = tmp_path / "project" / settings.PROJECT_CONFIG_NAME
    user.parent.mkdir()
    project.parent.mkdir()
    user.write_text(
        "fns:\n  user_names:\n    global: Global\n"
        "s3:\n  IGNORE: [one]\n"
        "vpn:\n  accounts:\n    main:\n"
        "      url: ./global.ovpn\n      handler: openvpn\n",
        encoding="utf-8",
    )
    project.write_text(
        "fns:\n  user_names:\n    local: Local\n"
        "s3:\n  IGNORE: [two]\n"
        "vpn:\n  accounts:\n    main:\n      url: ./local.ovpn\n"
        "    work:\n      handler: openconnect\n",
        encoding="utf-8",
    )

    result, user_path, project_path = conf.load_davo_config(
        project.parent, user_path=user
    )

    assert user_path == user
    assert project_path == project
    assert result["fns"]["user_names"] == {
        "global": "Global",
        "local": "Local",
    }
    assert result["s3"]["IGNORE"] == ["two"]
    assert result["vpn"]["accounts"]["main"] == {
        "url": str(project.parent / "local.ovpn"), "handler": "openvpn"
    }
    assert result["vpn"]["accounts"]["work"] == {"handler": "openconnect"}


@pytest.mark.parametrize(
    "contents", ["- item\n", "key: [unterminated\n"]
)
def test_load_davo_config_rejects_invalid_yaml_or_non_mapping(
    tmp_path, contents
):
    user = tmp_path / "davo-tools.yaml"
    user.write_text(contents, encoding="utf-8")

    with pytest.raises(errors.UserError, match="Invalid config"):
        conf.load_davo_config(tmp_path, user_path=user)


@pytest.mark.parametrize(
    "arguments",
    [
        ["arch", "fns-rename", "--config", "config.yaml"],
        ["arch", "fns-extract", "--config", "config.yaml"],
        [
            "arch", "fns-config", "init-map", "--config", "config.yaml",
            "in.json",
        ],
        ["arch", "fns-config", "show-map", "--config", "config.yaml"],
    ],
)
def test_fns_cli_rejects_removed_config_option(arguments):
    with pytest.raises(SystemExit):
        cli.init_parser().parse_args(arguments)


def test_fns_init_map_writes_user_or_local_config(tmp_path, monkeypatch):
    user = tmp_path / "user.yaml"
    source = tmp_path / "in.json"
    source.write_text(
        '[{"ticket": {"document": {"receipt": {"user": "Shop"}}}}]',
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "CONFIG_PATH_DAVO_TOOLS", str(user))
    monkeypatch.chdir(tmp_path)

    arch.command_fns_config_init_map(source)

    assert "Shop: ''" in user.read_text(encoding="utf-8")
    arch.command_fns_config_init_map(source, local=True)
    assert "Shop: ''" in (tmp_path / settings.PROJECT_CONFIG_NAME).read_text(
        encoding="utf-8"
    )
