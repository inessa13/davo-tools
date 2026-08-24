import re
from pathlib import Path

import pytest

from davo import errors
from davo.services.photo import clients, helpers

_FILES = [
    "/test_media/a.mp4",  # converted
    "/test_media/b.mp4",  # converted with thumbnail
    "/test_media/b.jpg",  # thumbnail
    "/test_media/c.avi",  # not converted
    "/test_media/short/c.mov",  # not converted
    "/test_media/short/c.3gp",  # not converted
    "/test_media/short/d.jpg",  # image
    "/test_media/short/d.png",  # image
    "/test_media/e.txt",  # no-media format
    "/test_media/short/e.zip",  # no-media format
    "/test_media/single/a.avi",  # video
]

_PB = "[========================================>] 100% {0}/{0} Elapsed: 0.00s"
_PB1 = _PB.format(1)
_PB5 = _PB.format(5)

_OUT_SHORT_P_OK = """
./a.mp4: succeed
./b.mp4: succeed
./b.jpg: succeed
./c.avi: succeed
./e.txt: succeed
"""
_OUT_SHORT_P_DRY = """
./a.mp4: dry-run
./b.mp4: dry-run
./b.jpg: dry-run
./c.avi: dry-run
./e.txt: dry-run
"""
_OUT_SHORT_P_A = """
./a.mp4: already
./b.mp4: already
./b.jpg: already
./c.avi: already
./e.txt: already
"""
_OUT_SHORT_OK = (
    _PB5
    + """
./a.mp4:
    succeed 0.00s
./b.mp4:
    succeed 0.00s
./b.jpg:
    succeed 0.00s
./c.avi:
    succeed 0.00s
./e.txt:
    succeed 0.00s
"""
)
_OUT_SHORT_DRY = (
    _PB5
    + """
./a.mp4:
    dry-run 0.00s
./b.mp4:
    dry-run 0.00s
./b.jpg:
    dry-run 0.00s
./c.avi:
    dry-run 0.00s
./e.txt:
    dry-run 0.00s
"""
)

_OUT_SINGLE_P_OK = "./a.avi: succeed"
_OUT_SINGLE_P_A = "./a.avi: already"
_OUT_SINGLE_P_DRY = "./a.avi: dry-run"
_OUT_SINGLE_OK = (
    _PB1
    + """
./a.avi:
    succeed 0.00s
"""
)
_OUT_SINGLE_FAIL = (
    _PB1
    + """
./a.avi:
    failed 0.00s
"""
)
_OUT_SINGLE_DRY = (
    _PB1
    + """
./a.avi:
    dry-run 0.00s
"""
)
_OUT_SINGLE_DRY_C = (
    _PB1
    + """
./a.avi:
    *cmd*
    dry-run 0.00s
"""
)


class ReprintMock:
    initial_len = 0
    _len = 0
    _out = None

    def __init__(self):
        self._out = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    def append(self, line):
        self._out.append(line)
        self._len += 1

    def __getitem__(self, i):
        if isinstance(i, slice):
            return ["slice"]
        return self._out[i]

    def __setitem__(self, i, o):
        if isinstance(i, slice):
            self._out = self._out[1:] + [o[1]]
        else:
            self._out[i] = o

    def __len__(self):
        return self._len

    def output(self, initial_len=0):
        self.initial_len = initial_len
        if initial_len:
            self._out = [""] * initial_len
        return self

    def assert_out(self, value):
        assert "\n".join(self._out).strip("\n") == value


@pytest.fixture()
def mock_reprint(mocker):
    instance = ReprintMock()
    mocker.patch("davo.services.photo.utils.reprint", instance)
    mocker.patch("davo.utils.prnt.rp_plain", instance.append)
    return instance


@pytest.fixture(autouse=True)
def mock_subproc(mocker):
    mocker.patch("davo.utils.concur.run_subproc", return_value=b"")


@pytest.fixture(autouse=True)
def iter_files(mocker):
    def _iter_files(root_path, recursive=False, **_kw):
        if root_path == "/test_media" or root_path == "/test_media/":
            if recursive:
                return _FILES
            else:
                return [f for f in _FILES if re.match("/test_media/[^/]+$", f)]
        elif root_path.startswith("/test_media/"):
            return [f for f in _FILES if f.startswith(root_path)]
        raise errors.UserError("Invalid path {}".format(root_path))

    mocker.patch("davo.services.photo.utils.iter_files", _iter_files)


def test_run_ffmpeg_uses_path_binary():
    result = clients.run_ffmpeg("/a.avi", "/a-web.avi", commit=False)

    assert result == "ffmpeg -i /a.avi /a-web.avi"


def test_run_ffmpeg_builds_compression_command():
    result = clients.run_ffmpeg(
        "/a.mov",
        "/a_compressed.mp4",
        video_codec="libx264",
        crf=20,
        audio_codec="copy",
        overwrite=True,
        commit=False,
    )

    assert result == (
        "ffmpeg -y -i /a.mov -vcodec libx264 -crf 20 "
        "-acodec copy /a_compressed.mp4"
    )


def test_clips_compress_selects_unique_videos_in_stable_order(mocker):
    mocker.patch.object(
        helpers.os.path,
        "isfile",
        side_effect=lambda path: path in {"one.mov", "one-alias.mov"},
    )
    mocker.patch.object(
        helpers.os.path, "isdir", side_effect=lambda path: path == "videos"
    )
    mocker.patch.object(
        helpers.os.path,
        "abspath",
        side_effect=lambda path: (
            "one.mov" if path == "one-alias.mov" else path
        ),
    )
    mocker.patch.object(
        helpers.utils,
        "iter_files",
        return_value=[
            "videos/a.mp4",
            "videos/a_compressed.mp4",
            "videos/note.txt",
            "videos/z.MKV",
        ],
    )

    assert helpers._clips_compress_inputs(
        ["one.mov", "videos", "one-alias.mov"], recursive=True
    ) == ["one.mov", "videos/a.mp4", "videos/z.MKV"]


def test_clips_compress_dry_run_and_rewrite(mocker, caplog):
    caplog.set_level("INFO")
    mocker.patch.object(
        helpers,
        "_clips_compress_inputs",
        return_value=["one.mov", "two.mkv"],
    )
    mocker.patch.object(helpers.os.path, "exists", return_value=False)
    ffmpeg = mocker.patch.object(
        helpers.clients, "run_ffmpeg", return_value="ffmpeg command"
    )

    helpers.command_clips_compress(
        ["one.mov", "two.mkv"], crf=18, mp4=True, dry_run=True, rewrite=True
    )

    assert ffmpeg.call_count == 2
    assert ffmpeg.call_args_list[0].args == (
        "one.mov",
        "one_compressed.mp4",
    )
    assert ffmpeg.call_args_list[0].kwargs == {
        "video_codec": "libx264",
        "crf": 18,
        "audio_codec": "copy",
        "overwrite": True,
        "timeout": 14400,
        "commit": False,
    }
    assert "ffmpeg command" in caplog.text


def test_clips_compress_skips_existing_output_without_rewrite(mocker):
    mocker.patch.object(
        helpers, "_clips_compress_inputs", return_value=["one.mov"]
    )
    mocker.patch.object(helpers.os.path, "exists", return_value=True)
    ffmpeg = mocker.patch.object(helpers.clients, "run_ffmpeg")

    helpers.command_clips_compress(["one.mov"])

    ffmpeg.assert_not_called()


def test_clips_compress_reports_sizes_and_total(tmp_path, mocker, caplog):
    caplog.set_level("INFO")
    first = tmp_path / "first.mov"
    second = tmp_path / "second.mkv"
    first.write_bytes(b"a" * 100)
    second.write_bytes(b"b" * 200)
    mocker.patch.object(
        helpers,
        "_clips_compress_inputs",
        return_value=[str(first), str(second)],
    )

    def compress(_source, output, **_kwargs):
        Path(output).write_bytes(b"x" * (50 if "first" in output else 300))
        return True

    mocker.patch.object(helpers.clients, "run_ffmpeg", side_effect=compress)

    helpers.command_clips_compress([str(first), str(second)])

    assert "first.mov:" in caplog.text
    assert "(50.00% reduction)" in caplog.text
    assert "second.mkv:" in caplog.text
    assert "(-50.00% reduction)" in caplog.text
    assert "total:" in caplog.text
    assert "(-16.67% reduction)" in caplog.text
    assert "_compressed" not in caplog.text


def test_clips_compress_does_not_report_total_for_one_success(
    tmp_path, mocker, caplog
):
    caplog.set_level("INFO")
    source = tmp_path / "movie.mov"
    source.write_bytes(b"a" * 100)
    mocker.patch.object(
        helpers, "_clips_compress_inputs", return_value=[str(source)]
    )

    def compress(_source, output, **_kwargs):
        Path(output).write_bytes(b"x" * 50)
        return True

    mocker.patch.object(helpers.clients, "run_ffmpeg", side_effect=compress)

    helpers.command_clips_compress([str(source)])

    assert "total:" not in caplog.text


def test_clips_compress_replace_source_after_success(tmp_path, mocker):
    source = tmp_path / "movie.mov"
    source.write_bytes(b"a" * 100)
    mocker.patch.object(
        helpers, "_clips_compress_inputs", return_value=[str(source)]
    )

    def compress(_source, output, **_kwargs):
        Path(output).write_bytes(b"compressed")
        return True

    mocker.patch.object(helpers.clients, "run_ffmpeg", side_effect=compress)

    helpers.command_clips_compress([str(source)], replace_source=True)

    assert source.read_bytes() == b"compressed"
    assert not (tmp_path / "movie_compressed.mov").exists()


def test_clips_compress_replace_source_keeps_source_after_failure(
    tmp_path, mocker
):
    source = tmp_path / "movie.mov"
    source.write_bytes(b"original")
    mocker.patch.object(
        helpers, "_clips_compress_inputs", return_value=[str(source)]
    )
    mocker.patch.object(helpers.clients, "run_ffmpeg", return_value=False)

    helpers.command_clips_compress([str(source)], replace_source=True)

    assert source.read_bytes() == b"original"


def test_clips_compress_replace_source_mp4(tmp_path, mocker):
    source = tmp_path / "movie.mov"
    target = tmp_path / "movie.mp4"
    source.write_bytes(b"original")
    mocker.patch.object(
        helpers, "_clips_compress_inputs", return_value=[str(source)]
    )

    def compress(_source, output, **_kwargs):
        Path(output).write_bytes(b"compressed")
        return True

    mocker.patch.object(helpers.clients, "run_ffmpeg", side_effect=compress)

    helpers.command_clips_compress(
        [str(source)], mp4=True, replace_source=True
    )

    assert not source.exists()
    assert target.read_bytes() == b"compressed"
    assert not (tmp_path / "movie_compressed.mp4").exists()


def test_clips_compress_replace_source_existing_mp4(tmp_path, mocker):
    source = tmp_path / "movie.mp4"
    source.write_bytes(b"original")
    mocker.patch.object(
        helpers, "_clips_compress_inputs", return_value=[str(source)]
    )

    def compress(_source, output, **_kwargs):
        Path(output).write_bytes(b"compressed")
        return True

    mocker.patch.object(helpers.clients, "run_ffmpeg", side_effect=compress)

    helpers.command_clips_compress(
        [str(source)], mp4=True, replace_source=True
    )

    assert source.read_bytes() == b"compressed"
    assert not (tmp_path / "movie_compressed.mp4").exists()


def test_clips_compress_replace_source_mp4_skips_existing_target(
    tmp_path, mocker, caplog
):
    caplog.set_level("ERROR")
    source = tmp_path / "movie.mov"
    target = tmp_path / "movie.mp4"
    source.write_bytes(b"original")
    target.write_bytes(b"keep")
    mocker.patch.object(
        helpers, "_clips_compress_inputs", return_value=[str(source)]
    )
    ffmpeg = mocker.patch.object(helpers.clients, "run_ffmpeg")

    helpers.command_clips_compress(
        [str(source)], mp4=True, replace_source=True, rewrite=True
    )

    ffmpeg.assert_not_called()
    assert source.read_bytes() == b"original"
    assert target.read_bytes() == b"keep"
    assert "target exists" in caplog.text


@pytest.mark.parametrize(
    ["path", "stream"],
    [
        ("/a.mp3", "a"),
        ("/a.avi", "v"),
    ],
)
def test_check_ffmpeg_faststart_uses_path_binary(
    mocker, path, stream
):
    run_subproc = mocker.patch(
        "davo.services.photo.clients.concur.run_subproc",
        return_value=b"pos=501",
    )

    assert clients.check_ffmpeg_faststart(path) is True
    cmd = run_subproc.call_args.args[0]
    assert cmd[0] == "ffprobe"
    assert cmd[cmd.index("-select_streams") + 1] == stream
    assert run_subproc.call_args.kwargs == {"quiet": False, "pipe": True}


@pytest.mark.skip
@pytest.mark.parametrize("path", ("/test_media", "/test_media/short"))
@pytest.mark.parametrize("points", ("00:10", "00:10 00:15", "00:00.00.1234"))
@pytest.mark.parametrize("ext", ("mp4", "webm", "jpg", "png"))
@pytest.mark.parametrize("recursive", (True, False))
@pytest.mark.parametrize("verbose", (True, False))
@pytest.mark.parametrize("silent", (True, False))
@pytest.mark.parametrize("commit", (True, False))
def _test_smoke_command_clips_split(
    path, points, ext, recursive, silent, verbose, commit
):
    helpers.command_clips_split(
        root=path,
        points=points,
        ext=ext,
        recursive=recursive,
        verbose=verbose,
        silent=silent,
        commit=commit,
    )


@pytest.mark.parametrize("verbose", (True, False))
@pytest.mark.parametrize("silent", (True, False))
@pytest.mark.parametrize("commit", (True, False))
def test_smoke_command_clips_web(silent, verbose, commit):
    helpers.command_clips_web(
        root="/test_media",
        recursive=False,
        verbose=verbose,
        silent=silent,
        commit=commit,
    )


@pytest.mark.parametrize(
    ["verbose", "silent", "commit", "check", "result"],
    [
        (True, True, True, False, _OUT_SINGLE_P_OK),
        (True, True, True, True, _OUT_SINGLE_P_A),
        (True, True, False, True, _OUT_SINGLE_P_A),
        (False, True, True, False, _OUT_SINGLE_P_OK),
        (True, False, True, False, _OUT_SINGLE_OK),
        (False, True, False, False, _OUT_SINGLE_P_DRY),
    ],
)
def test_r_command_clips_web(
    mocker, mock_reprint, silent, verbose, commit, check, result
):
    mocker.patch(
        "davo.services.photo.clients.check_ffmpeg_faststart",
        return_value=check,
    )
    mocker.patch(
        "davo.services.photo.clients.run_ffmpeg_pref", return_value=True
    )
    helpers.command_clips_web(
        root="/test_media/single",
        recursive=False,
        verbose=verbose,
        silent=silent,
        commit=commit,
    )
    mock_reprint.assert_out(result.strip())


@pytest.mark.parametrize(
    ["verbose", "commit", "ok", "result"],
    [
        (True, True, True, _OUT_SINGLE_OK),
        (True, True, False, _OUT_SINGLE_FAIL),
        (
            True,
            False,
            True,
            _OUT_SINGLE_DRY_C.replace(
                "*cmd*",
                "ffmpeg -i /a.avi -movflags +faststart "
                "-c copy /a-web.avi",
            ),
        ),
        (False, False, True, _OUT_SINGLE_DRY),
        (
            True,
            False,
            False,
            _OUT_SINGLE_DRY_C.replace(
                "*cmd*",
                "ffmpeg -i /a.avi -movflags +faststart "
                "-c copy /a-web.avi",
            ),
        ),
    ],
)
def test_r2_command_clips_web(
    mocker, mock_reprint, verbose, commit, ok, result
):
    mocker.patch(
        "davo.services.photo.clients.check_ffmpeg_faststart",
        return_value=False,
    )
    mocker.patch("os.path.isfile", return_value=ok)
    mocker.patch("os.path.getatime")
    mocker.patch("os.path.getmtime")
    mocker.patch("os.utime")
    helpers.command_clips_web(
        root="/test_media/single",
        recursive=False,
        verbose=verbose,
        silent=False,
        commit=commit,
    )
    mock_reprint.assert_out(result.strip())


@pytest.mark.parametrize(
    ["ss", "to", "verbose", "silent", "commit", "result"],
    [
        ("10", "10", True, False, True, _OUT_SINGLE_OK),
        ("10", "", True, False, True, _OUT_SINGLE_OK),
        ("", "10", True, False, True, _OUT_SINGLE_OK),
        ("10", "", True, True, True, _OUT_SINGLE_P_OK),
        ("10", "", False, False, False, _OUT_SINGLE_DRY),
        (
            "10",
            "",
            True,
            False,
            False,
            _OUT_SINGLE_DRY_C.replace(
                "*cmd*",
                "ffmpeg -ss 10 -i /a.avi -movflags +faststart "
                "/a-trimmed.avi",
            ),
        ),
    ],
)
def test_r_command_clips_trim(
    mocker, ss, to, mock_reprint, silent, verbose, commit, result
):
    mocker.patch("os.path.isfile", return_value=True)
    mocker.patch("os.path.getatime")
    mocker.patch("os.path.getmtime")
    mocker.patch("os.utime")
    helpers.command_clips_trim(
        root="/test_media/single",
        ss=ss,
        to=to,
        verbose=verbose,
        silent=silent,
        commit=commit,
    )
    mock_reprint.assert_out(result.strip())
