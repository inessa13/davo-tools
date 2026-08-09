import pytest

from davo import cli
from davo.services.photo import cli as photo_cli


@pytest.mark.parametrize(
    "arguments",
    [
        ["clips", "convert"],
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
    ],
)
def test_parser_accepts_new_command_groups(arguments):
    namespace = cli.init_parser().parse_args(arguments)

    assert callable(namespace.func)


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
