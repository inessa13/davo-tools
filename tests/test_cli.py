import pytest

from davo import cli
from davo.services.photo import cli as photo_cli


@pytest.mark.parametrize(
    "arguments",
    [
        ["vid", "convert"],
        ["arch", "fns-rename"],
        ["vid", "split", "input.mp4", "00:00:10"],
        ["vid", "trim"],
        ["vid", "web"],
        ["vid", "isweb"],
        ["vid", "compress", "input.mp4"],
        ["im", "convert"],
        ["im", "thumbs"],
        ["im", "recover"],
        ["im", "downscale"],
        ["im", "fp", "input.png"],
        ["im", "diff", "first.png", "second.png"],
        ["im", "merge", "-V", "first.png", "second.png"],
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


@pytest.mark.parametrize("option", ["-O", "--original-comment"])
def test_parser_accepts_sber_original_comment_option(option):
    namespace = cli.init_parser().parse_args(
        ["pa", "sber2csv", option, "statement.pdf"]
    )

    assert namespace.original_comment is True


@pytest.mark.parametrize("option", ["-0", "--dry-run"])
def test_parser_accepts_ozon2csv_options(option):
    namespace = cli.init_parser().parse_args(
        ["pa", "ozon2csv", option, "statement.pdf"]
    )

    assert namespace.dry_run is True
    assert callable(namespace.func)


@pytest.mark.parametrize("option", ["-O", "--original-comment"])
def test_parser_accepts_ozon_original_comment_option(option):
    namespace = cli.init_parser().parse_args(
        ["pa", "ozon2csv", option, "statement.pdf"]
    )

    assert namespace.original_comment is True


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


def test_parser_passes_options_to_image_merge_handler(mocker):
    handler = mocker.patch.object(photo_cli.helpers, "command_image_merge")
    namespace = cli.init_parser().parse_args(
        [
            "im", "merge", "--horizontal", "--debug-fill", "--smart",
            "-o", "merged.png", "first.png", "second.png",
        ]
    )

    namespace.func(namespace)

    handler.assert_called_once_with(
        images=["first.png", "second.png"],
        vertical=False,
        out="merged.png",
        debug_fill=True,
        smart=True,
    )


@pytest.mark.parametrize("smart_option", ["-S", "--smart"])
def test_parser_accepts_each_smart_merge_option(mocker, smart_option):
    handler = mocker.patch.object(photo_cli.helpers, "command_image_merge")
    namespace = cli.init_parser().parse_args(
        ["im", "merge", "-V", smart_option, "first.png", "second.png"]
    )

    namespace.func(namespace)

    assert handler.call_args.kwargs["smart"] is True


@pytest.mark.parametrize(
    "arguments",
    [
        ["im", "merge", "first.png", "second.png"],
        ["im", "merge", "-V", "-H", "first.png", "second.png"],
    ],
)
def test_parser_rejects_invalid_image_merge_direction(arguments):
    with pytest.raises(SystemExit):
        cli.init_parser().parse_args(arguments)


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
        (["-d", "800"], 800),
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


def test_parser_accepts_pdf_form_crop_in_css_order():
    namespace = cli.init_parser().parse_args(
        ["pdf", "form", "-4", "--crop", "5%", "20px", "0", "1.5%", "in.jpg"]
    )

    assert namespace.crop == ["5%", "20px", "0", "1.5%"]


@pytest.mark.parametrize(
    ("option", "orientation"),
    [
        ("--force-landscape", "landscape"),
        ("--force-portrait", "portrait"),
    ],
)
def test_parser_accepts_pdf_form_forced_orientation(option, orientation):
    default = cli.init_parser().parse_args(["pdf", "form", "-4", "in.jpg"])
    forced = cli.init_parser().parse_args(
        ["pdf", "form", "-4", option, "in.jpg"]
    )

    assert default.force_orientation is None
    assert forced.force_orientation == orientation


@pytest.mark.parametrize("option", ["-R", "--rename-processed"])
def test_parser_accepts_pdf_form_rename_processed(option):
    default = cli.init_parser().parse_args(["pdf", "form", "-4", "in.jpg"])
    renamed = cli.init_parser().parse_args(
        ["pdf", "form", "-4", option, "in.jpg"]
    )

    assert default.rename_processed is False
    assert renamed.rename_processed is True


@pytest.mark.parametrize(
    "arguments",
    [
        ["pdf", "form", "input.jpg"],
        ["pdf", "form", "-4", "-5", "input.jpg"],
        [
            "pdf", "form", "-4", "--force-landscape",
            "--force-portrait", "input.jpg",
        ],
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
    "arguments",
    [
        ["arch", "fns-extract", "-0", "export.json"],
        ["arch", "fns-extract", "--dry-run", "export.json"],
        ["arch", "fns-rename", "-0"],
        ["arch", "fns-rename", "--dry-run"],
        ["vid", "compress", "-0", "movie.mov"],
    ],
)
def test_parser_accepts_dry_run_short_option(arguments):
    namespace = cli.init_parser().parse_args(arguments)

    assert namespace.dry_run is True


def test_fns_extract_parser_output_options():
    namespace = cli.init_parser().parse_args(
        ["arch", "fns-extract", "-A", "-t", "pdf", "export.json"]
    )

    assert namespace.no_autogen is True
    assert namespace.type == "pdf"


def test_fns_extract_parser_defaults_to_html():
    namespace = cli.init_parser().parse_args(
        ["arch", "fns-extract", "export.json"]
    )

    assert namespace.no_autogen is False
    assert namespace.type == "html"


@pytest.mark.parametrize(
    "arguments",
    [
        ["file", "rename", "-C"],
        ["file", "iphone-clean-live", "-C"],
        ["file", "compare", "-C"],
        ["vid", "convert", "-C"],
        ["vid", "split", "-C", "input.mp4", "00:00:10"],
        ["vid", "trim", "-C"],
        ["vid", "web", "-C"],
        ["im", "convert", "-C"],
        ["im", "recover", "-C"],
        ["im", "downscale", "-C"],
    ],
)
def test_parser_uses_uppercase_short_option_for_commit(arguments):
    namespace = cli.init_parser().parse_args(arguments)

    assert namespace.commit is True


@pytest.mark.parametrize(
    "arguments",
    [
        ["file", "rename", "-c"],
        ["im", "convert", "-c"],
    ],
)
def test_parser_uses_lowercase_short_option_for_copy(arguments):
    namespace = cli.init_parser().parse_args(arguments)

    assert namespace.copy is True
    assert namespace.commit is False


@pytest.mark.parametrize(
    ("arguments", "handler_name"),
    [
        (["file", "rename", "-c", "-C"], "command_regexp"),
        (["im", "convert", "-c", "-C"], "command_convert"),
    ],
)
def test_parser_forwards_copy_and_commit_options(
    mocker, arguments, handler_name
):
    handler = mocker.patch.object(photo_cli.helpers, handler_name)
    namespace = cli.init_parser().parse_args(arguments)

    namespace.func(namespace)

    assert handler.call_args.kwargs["copy"] is True
    assert handler.call_args.kwargs["commit"] is True


@pytest.mark.parametrize(
    "arguments",
    [
        ["pdf", "info", "-c"],
        ["pdf", "info", "--compact"],
    ],
)
def test_parser_accepts_compact_pdf_info_option(arguments):
    namespace = cli.init_parser().parse_args(arguments)

    assert namespace.compact is True


@pytest.mark.parametrize("option", ["-a", "--all"])
def test_cit_parser_accepts_all_short_option(option):
    namespace = cli.init_parser().parse_args(["cit", option])

    assert namespace.all is True


@pytest.mark.parametrize(
    "arguments",
    [
        ["arch", "fns-rename", "-c"],
        ["vid", "convert", "-c"],
        ["vid", "split", "-c", "input.mp4", "00:00:10"],
        ["vid", "trim", "-c"],
        ["vid", "web", "-c"],
        ["im", "recover", "-c"],
        ["im", "downscale", "-c"],
        ["cit", "-A"],
    ],
)
def test_parser_rejects_removed_conflicting_short_options(arguments):
    with pytest.raises(SystemExit):
        cli.init_parser().parse_args(arguments)


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


def test_photo_cli_rejects_legacy_clip_convert():
    parser = photo_cli.init_parser()[0]

    with pytest.raises(SystemExit):
        parser.parse_args(["clips-convert"])


def test_parser_rejects_removed_clips_group():
    with pytest.raises(SystemExit):
        cli.init_parser().parse_args(["clips", "info", "movie.mp4"])


@pytest.mark.parametrize(
    "arguments",
    [
        ["clips-info", "movie.mp4"],
        ["clips-convert"],
        ["clips-split", "movie.mp4", "00:00:10"],
        ["clips-trim"],
        ["clips-web"],
        ["clips-isweb"],
        ["clips-compress", "movie.mp4"],
    ],
)
def test_photo_cli_rejects_legacy_clip_commands(arguments):
    with pytest.raises(SystemExit):
        photo_cli.init_parser()[0].parse_args(arguments)


def test_vid_compress_cli_forwards_options(mocker):
    handler = mocker.patch.object(photo_cli.helpers, "command_clips_compress")
    namespace = cli.init_parser().parse_args(
        [
            "vid",
            "compress",
            "--crf",
            "20",
            "-H",
            "721",
            "--mp4",
            "--replace-source",
            "--dry-run",
            "-W",
            "-r",
            "one.mov",
            "two.mkv",
        ]
    )

    namespace.func(namespace)

    assert handler.call_args.kwargs == {
        "inputs": ["one.mov", "two.mkv"],
        "crf": 20,
        "height": 720,
        "mp4": True,
        "replace_source": True,
        "dry_run": True,
        "rewrite": True,
        "recursive": True,
    }


@pytest.mark.parametrize("height", ["144", "2160"])
def test_vid_compress_cli_accepts_height_limits(height):
    namespace = cli.init_parser().parse_args(
        ["vid", "compress", "-H", height, "movie.mov"]
    )

    assert namespace.height == int(height)


@pytest.mark.parametrize("height", ["143", "2161", "720p"])
def test_vid_compress_cli_rejects_invalid_height(height):
    with pytest.raises(SystemExit):
        cli.init_parser().parse_args(
            ["vid", "compress", "-H", height, "movie.mov"]
        )
