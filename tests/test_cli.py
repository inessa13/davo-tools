import pytest

from davo import cli
from davo.services.photo import cli as photo_cli


@pytest.mark.parametrize(
    "arguments",
    [
        ["clips", "convert"],
        ["arch", "fns-rename"],
        ["clips", "split", "input.mp4", "00:00:10"],
        ["clips", "trim"],
        ["clips", "web"],
        ["clips", "isweb"],
        ["im", "convert"],
        ["im", "thumbs"],
        ["im", "recover"],
        ["im", "downscale"],
        ["im", "fp", "input.png"],
        ["im", "diff", "first.png", "second.png"],
        ["im", "diff", "first.png", "second.png", "third.png"],
        ["im", "diff", "-r", "images"],
        ["im", "diff", "--recursive", "images"],
        ["im", "diff", "-t", "first.png", "second.png"],
        ["im", "diff", "--table", "first.png", "second.png"],
        ["im", "diff", "-a", "first.png", "second.png"],
        ["im", "diff", "--all", "first.png", "second.png"],
        ["im", "diff", "-f", "first.png", "second.png"],
        ["im", "diff", "--fast", "first.png", "second.png"],
        ["im", "diff", "-g", "first.png", "second.png"],
        ["im", "diff", "--group", "first.png", "second.png"],
    ],
)
def test_parser_accepts_new_command_groups(arguments):
    namespace = cli.init_parser().parse_args(arguments)

    assert callable(namespace.func)


@pytest.mark.parametrize("option", ["-r", "--recursive"])
def test_parser_sets_recursive_for_image_diff(option):
    namespace = cli.init_parser().parse_args(["im", "diff", option, "images"])

    assert namespace.recursive is True


@pytest.mark.parametrize("option", ["-t", "--table"])
def test_parser_sets_table_for_image_diff(option):
    namespace = cli.init_parser().parse_args(
        ["im", "diff", option, "first.png", "second.png"]
    )

    assert namespace.table is True


@pytest.mark.parametrize("option", ["-a", "--all"])
def test_parser_sets_all_for_image_diff(option):
    namespace = cli.init_parser().parse_args(
        ["im", "diff", option, "first.png", "second.png"]
    )

    assert namespace.all is True


@pytest.mark.parametrize("option", ["-f", "--fast"])
def test_parser_sets_fast_for_image_diff(option):
    namespace = cli.init_parser().parse_args(
        ["im", "diff", option, "first.png", "second.png"]
    )

    assert namespace.fast is True


@pytest.mark.parametrize("option", ["-g", "--group"])
def test_parser_sets_group_for_image_diff(option):
    namespace = cli.init_parser().parse_args(
        ["im", "diff", option, "first.png", "second.png"]
    )

    assert namespace.group is True


@pytest.mark.parametrize(
    ("arguments", "show_all", "fast", "group"),
    [
        (["--table", "first.png", "second.png"], False, False, False),
        (["--all", "first.png", "second.png"], True, False, False),
        (["--fast", "first.png", "second.png"], False, True, False),
        (["--group", "first.png", "second.png"], False, False, True),
    ],
)
def test_parser_passes_options_to_image_diff_handler(
    mocker, arguments, show_all, fast, group
):
    handler = mocker.patch.object(
        photo_cli.helpers, "command_fingerprint_diff"
    )
    namespace = cli.init_parser().parse_args(["im", "diff", *arguments])

    namespace.func(namespace)

    handler.assert_called_once_with(
        images=["first.png", "second.png"],
        recursive=False,
        table=arguments[0] == "--table",
        show_all=show_all,
        fast=fast,
        group=group,
    )


@pytest.mark.parametrize(
    "arguments",
    [
        ["file", "clips-convert"],
        ["file", "clips-split", "input.mp4", "00:00:10"],
        ["file", "clips-trim"],
        ["file", "clips-web"],
        ["file", "clips-isweb"],
        ["file", "convert"],
        ["file", "thumbs"],
        ["file", "recover"],
        ["file", "downscale"],
        ["file", "pdf-merge", "input.pdf"],
        ["file", "pdf-rotate", "input.pdf"],
        ["file", "pdf-delete", "input.pdf"],
    ],
)
def test_parser_rejects_removed_file_aliases(arguments):
    with pytest.raises(SystemExit):
        cli.init_parser().parse_args(arguments)


@pytest.mark.parametrize("command", ["merge", "rotate", "delete"])
def test_parser_keeps_pdf_commands(command):
    namespace = cli.init_parser().parse_args(["pdf", command, "input.pdf"])

    assert callable(namespace.func)


@pytest.mark.parametrize(
    ("arguments", "dpi"),
    [
        (["-H"], 400),
        (["-Q"], 300),
        (["-M"], 200),
        (["-l"], 150),
        (["-L"], 96),
        (["--dpi", "800"], 800),
    ],
)
def test_parser_accepts_pdf_form_sizes_and_dpi(arguments, dpi):
    namespace = cli.init_parser().parse_args(
        ["pdf", "form", "-4", *arguments, "input.jpg"]
    )

    assert callable(namespace.func)
    assert namespace.paper_format == "a4"
    assert namespace.dpi == dpi
    assert namespace.inf == ["input.jpg"]


def test_parser_accepts_compact_pdf_form_flags():
    namespace = cli.init_parser().parse_args(
        ["pdf", "form", "-4M", "input.jpg"]
    )

    assert namespace.paper_format == "a4"
    assert namespace.dpi == 200


def test_parser_accepts_pdf_form_quality_and_default():
    default = cli.init_parser().parse_args(["pdf", "form", "-4", "in.jpg"])
    custom = cli.init_parser().parse_args(
        ["pdf", "form", "-4", "-q", "37", "in.jpg"]
    )

    assert default.quality == 80
    assert custom.quality == 37


def test_parser_accepts_pdf_form_debug_fill_and_defaults_to_false():
    default = cli.init_parser().parse_args(["pdf", "form", "-4", "in.jpg"])
    debug = cli.init_parser().parse_args(
        ["pdf", "form", "-4", "--debug-fill", "in.jpg"]
    )

    assert default.debug_fill is False
    assert debug.debug_fill is True


@pytest.mark.parametrize(
    "arguments",
    [
        ["pdf", "form", "input.jpg"],
        ["pdf", "form", "-4", "-5", "input.jpg"],
        ["pdf", "form", "-4", "-M", "--dpi", "200", "input.jpg"],
        ["pdf", "form", "-4", "--dpi", "71", "input.jpg"],
        ["pdf", "form", "-4", "--dpi", "801", "input.jpg"],
    ],
)
def test_parser_rejects_invalid_pdf_form_options(arguments):
    with pytest.raises(SystemExit):
        cli.init_parser().parse_args(arguments)


def test_file_keeps_compare():
    namespace = cli.init_parser().parse_args(["file", "compare"])

    assert callable(namespace.func)


@pytest.mark.parametrize(
    "command",
    [
        "rename",
        "rename-classes",
        "rename-patterns",
        "iphone-clean-live",
        "search-duplicates",
    ],
)
def test_file_keeps_non_image_photo_commands(command):
    namespace = cli.init_parser().parse_args(["file", command])

    assert callable(namespace.func)


def test_photo_cli_keeps_legacy_clip_commands():
    parser = photo_cli.init_parser()[0]

    namespace = parser.parse_args(["clips-convert"])

    assert callable(namespace.func)
