# pylint: disable=too-many-lines
import argparse
import io
import types

import pytest
from PIL import Image

from davo.services.photo import cli as photo_cli
from davo.services.photo import helpers, pdf


class FakeRect:
    def __init__(self, width, height, x0=0, y0=0):
        self.x0 = x0
        self.y0 = y0
        self.width = width
        self.height = height
        self.x1 = x0 + width
        self.y1 = y0 + height

    def as_tuple(self):
        return (self.x0, self.y0, self.x1, self.y1)


class FakeOutputPage:
    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.shown = []
        self.inserted = []
        self.drawn = []
        self.operations = []

    def draw_rect(self, rect, color=None, fill=None, overlay=True):
        self.drawn.append((rect, color, fill, overlay))
        self.operations.append("draw_rect")

    def show_pdf_page(
        self, rect, doc, page_idx, keep_proportion=True
    ):
        self.shown.append((rect, doc, page_idx, keep_proportion))
        self.operations.append("show_pdf_page")

    def insert_image(self, rect, stream, keep_proportion=True):
        self.inserted.append((rect, stream, keep_proportion))
        self.operations.append("insert_image")

    def insertImage(self, rect, stream):
        self.inserted.append((rect, stream, True))
        self.operations.append("insertImage")


class FakePage:
    def __init__(
        self,
        use_legacy=False,
        with_rotation=True,
        images=None,
        rendered_bytes=None,
        text="",
        drawings=None,
        image_rects=None,
        rect=None,
    ):
        self.rotation = []
        self.rotation_legacy = []
        self.images = images or []
        self.rendered_bytes = rendered_bytes or b"rendered-page"
        self.pixmap_calls = []
        self.text = text
        self.drawings = drawings or []
        self.image_rects = image_rects or {}
        self.rect = rect or FakeRect(595, 842)
        if with_rotation:
            if use_legacy:
                self.setRotation = self._set_rotation_legacy
            else:
                self.set_rotation = self._set_rotation

    def _set_rotation(self, value):
        self.rotation.append(value)

    def _set_rotation_legacy(self, value):
        self.rotation_legacy.append(value)

    def get_images(self, full=True):
        return list(self.images)

    def get_text(self, output="text"):
        assert output == "text"
        return self.text

    def getText(self, output="text"):
        return self.get_text(output)

    def get_drawings(self):
        return list(self.drawings)

    def getDrawings(self):
        return self.get_drawings()

    def get_image_rects(self, xref):
        return list(self.image_rects.get(xref, []))

    def get_pixmap(self, **kwargs):
        self.pixmap_calls.append(kwargs)
        return FakePixmap(self.rendered_bytes)


class FakePixmap:
    def __init__(self, image_bytes):
        self.image_bytes = image_bytes

    def tobytes(self, output="png"):
        assert output == "png"
        return self.image_bytes


class FakeDoc:
    def __init__(self, page_count=1, pages=None, extracted_images=None):
        self.page_count = page_count
        self.pages = pages
        self.extracted_images = extracted_images or {}
        if self.pages is None:
            self.pages = [FakePage() for _ in range(page_count)]
        self.saved = []
        self.deleted = []
        self.inserted = []
        self.rewritten = []
        self.new_pages = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False

    def load_page(self, idx):
        return self.pages[idx]

    def save(self, path, **kwargs):
        self.saved.append((path, kwargs))

    def delete_page(self, idx):
        self.deleted.append(idx)

    def insert_pdf(self, doc, from_page=None, to_page=None):
        self.inserted.append((doc, from_page, to_page))

    def extract_image(self, xref):
        return self.extracted_images[xref]

    def rewrite_images(self, **kwargs):
        self.rewritten.append(kwargs)

    def new_page(self, width, height):
        page = FakeOutputPage(width, height)
        self.new_pages.append(page)
        return page


@pytest.fixture(autouse=True)
def fake_paths(monkeypatch):
    input_paths = {
        "/a.pdf",
        "/a.txt",
        "/a_1.pdf",
        "/b.pdf",
        "/docs/merged.pdf",
        "/landscape.pdf",
        "/multi.pdf",
        "/scan.pdf",
    }
    monkeypatch.setattr(
        pdf.os.path,
        "exists",
        lambda path: path in input_paths,
    )
    monkeypatch.setattr(pdf.os.path, "getsize", lambda _path: 1024)


@pytest.fixture()
def fake_fitz(mocker):
    docs = {"__created__": []}

    def _open(*args):
        if len(args) == 0:
            doc = FakeDoc(page_count=0)
            docs["__created__"].append(doc)
            return doc
        key = args[0]
        if key not in docs:
            docs[key] = FakeDoc(page_count=3)
        return docs[key]

    fitz_mod = types.SimpleNamespace(
        open=_open,
        Matrix=lambda x, y: (x, y),
        Rect=lambda x0, y0, x1, y1: (x0, y0, x1, y1),
    )
    mocker.patch("davo.services.photo.pdf._import_fitz", return_value=fitz_mod)
    return docs


def make_png_bytes(size=(8, 8), color=(255, 0, 0)):
    image = Image.new("RGB", size, color)
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def test_rotate_pages_sets_rotation_and_saves(fake_fitz):
    fake_fitz["/a.pdf"] = FakeDoc(page_count=2, pages=[FakePage(), FakePage()])

    status = pdf.rotate_pages("/a.pdf", "/out.pdf", direction="right")

    assert status is True
    assert fake_fitz["/a.pdf"].saved == [("/out.pdf", {})]
    assert fake_fitz["/a.pdf"].pages[0].rotation == [90]
    assert fake_fitz["/a.pdf"].pages[1].rotation == [90]


def test_rotate_pages_supports_legacy_api(fake_fitz):
    fake_fitz["/a.pdf"] = FakeDoc(
        page_count=1,
        pages=[FakePage(use_legacy=True)],
    )

    status = pdf.rotate_pages("/a.pdf", "/out.pdf", direction="left")

    assert status is True
    assert fake_fitz["/a.pdf"].pages[0].rotation_legacy == [270]


def test_rotate_pages_raises_without_rotation_api(fake_fitz):
    fake_fitz["/a.pdf"] = FakeDoc(
        page_count=1,
        pages=[FakePage(with_rotation=False)],
    )

    with pytest.raises(RuntimeError, match="does not support rotation"):
        pdf.rotate_pages("/a.pdf", "/out.pdf", direction="right")


def test_rotate_pages_inplace_uses_temp_file(monkeypatch, fake_fitz):
    replaced = []
    closed = []
    monkeypatch.setattr(
        pdf.tempfile,
        "mkstemp",
        lambda suffix: (42, "/tmp/rot.pdf"),
    )
    monkeypatch.setattr(pdf.os, "close", lambda fd: closed.append(fd))
    monkeypatch.setattr(
        pdf.os,
        "replace",
        lambda src, dst: replaced.append((src, dst)),
    )

    status = pdf.rotate_pages("/a.pdf", None, direction="right", inplace=True)

    assert status is True
    assert closed == [42]
    assert replaced == [("/tmp/rot.pdf", "/a.pdf")]
    assert fake_fitz["/a.pdf"].saved == [("/tmp/rot.pdf", {})]


def test_delete_pages_uses_one_based_and_descending(fake_fitz):
    fake_fitz["/a.pdf"] = FakeDoc(page_count=5)

    status = pdf.delete_pages("/a.pdf", None, pages=[1, 5, 3, 3])

    assert status is True
    assert fake_fitz["/a.pdf"].deleted == [4, 2, 0]
    assert fake_fitz["/a.pdf"].saved == [("/a_deleted.pdf", {})]


def test_split_pages_overwrites_collision_with_warning(
    monkeypatch, fake_fitz, caplog
):
    monkeypatch.setattr(pdf.os.path, "exists", lambda _path: True)
    fake_fitz["/a.pdf"] = FakeDoc(page_count=4)

    status = pdf.split_pages(
        "/a.pdf",
        None,
        pages=[1, 3],
        verbose=True,
        rewrite=True,
    )

    assert status is True
    assert "overwriting existing output file: /a_1.pdf" in caplog.text
    assert "overwriting existing output file: /a_2.pdf" in caplog.text


def test_clean_file_uses_default_output_and_save_options(fake_fitz):
    fake_fitz["/a.pdf"] = FakeDoc(page_count=2)

    status = pdf.clean_file("/a.pdf", None)

    assert status is True
    assert fake_fitz["/a.pdf"].saved == [
        ("/a_cleaned.pdf", {"garbage": 3, "deflate": True, "clean": True})
    ]


@pytest.mark.parametrize(
    ("operation", "args", "kwargs"),
    [
        (pdf.scale_file, ("/a.pdf", "/a.pdf"), {}),
        (pdf.merge_files, (["/a.pdf", "/b.pdf"], "/b.pdf"), {}),
        (pdf.rotate_pages, ("/a.pdf", "/a.pdf"), {}),
        (pdf.delete_pages, ("/a.pdf", "/a.pdf"), {"pages": [1]}),
        (pdf.clean_file, ("/a.pdf", "/a.pdf"), {}),
        (pdf.compress_file, ("/a.pdf", "/a.pdf", 96), {}),
    ],
)
def test_pdf_operations_refuse_to_overwrite_input(
    fake_fitz, caplog, operation, args, kwargs
):
    fake_fitz["/a.pdf"] = FakeDoc(page_count=2)

    status = operation(*args, **kwargs)

    assert status is False
    assert "refusing to overwrite input file" in caplog.text
    assert fake_fitz["/a.pdf"].saved == []


def test_rewrite_flag_never_allows_overwriting_input(fake_fitz, caplog):
    fake_fitz["/a.pdf"] = FakeDoc(page_count=1)

    status = pdf.clean_file("/a.pdf", "/a.pdf", rewrite=True)

    assert status is False
    assert "refusing to overwrite input file" in caplog.text
    assert fake_fitz["/a.pdf"].saved == []


def test_existing_output_requires_rewrite_flag(
    monkeypatch, fake_fitz, caplog
):
    monkeypatch.setattr(
        pdf.os.path,
        "exists",
        lambda path: path in {"/a.pdf", "/out.pdf"},
    )
    fake_fitz["/a.pdf"] = FakeDoc(page_count=1)

    status = pdf.clean_file("/a.pdf", "/out.pdf")

    assert status is False
    assert "use -W/--rewrite to overwrite" in caplog.text
    assert fake_fitz["/a.pdf"].saved == []

    status = pdf.clean_file("/a.pdf", "/out.pdf", rewrite=True)

    assert status is True
    assert "overwriting existing output file: /out.pdf" in caplog.text
    assert fake_fitz["/a.pdf"].saved == [
        ("/out.pdf", {"garbage": 3, "deflate": True, "clean": True})
    ]


def test_merge_refuses_automatic_output_that_is_an_input(fake_fitz, caplog):
    fake_fitz["/docs/merged.pdf"] = FakeDoc(page_count=1)

    status = pdf.merge_files(["/docs/merged.pdf"], None)

    assert status is False
    assert "refusing to overwrite input file" in caplog.text


def test_split_refuses_computed_target_that_is_input(fake_fitz, caplog):
    fake_fitz["/a_1.pdf"] = FakeDoc(page_count=2)

    status = pdf.split_pages(
        "/a_1.pdf",
        "/a.pdf",
        pages=[1],
    )

    assert status is False
    assert "refusing to overwrite input file: /a_1.pdf" in caplog.text


def test_output_guard_recognizes_relative_and_absolute_input(
    monkeypatch, tmp_path, caplog, fake_fitz
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(pdf.os.path, "exists", lambda _path: True)
    fake_fitz["input.pdf"] = FakeDoc(page_count=1)

    status = pdf.clean_file(
        "input.pdf",
        str(tmp_path / "input.pdf"),
    )

    assert status is False
    assert "refusing to overwrite input file" in caplog.text


def test_compress_file_rewrites_images_and_saves(fake_fitz):
    fake_fitz["/a.pdf"] = FakeDoc(page_count=2)

    status = pdf.compress_file("/a.pdf", "/out.pdf", 300)

    assert status is True
    assert fake_fitz["/a.pdf"].rewritten == [
        {
            "dpi_threshold": 301,
            "dpi_target": 300,
            "quality": 80,
            "lossy": True,
            "lossless": True,
            "bitonal": True,
            "color": True,
            "gray": True,
            "set_to_gray": False,
        }
    ]
    assert fake_fitz["/a.pdf"].saved == [
        ("/out.pdf", {"garbage": 3, "deflate": True, "clean": True})
    ]


def test_form_files_places_pdf_pages_without_enlarging(fake_fitz):
    fake_fitz["/multi.pdf"] = FakeDoc(
        page_count=2,
        pages=[
            FakePage(rect=FakeRect(100, 200)),
            FakePage(rect=FakeRect(400, 200)),
        ],
    )

    status = pdf.form_files(
        ["/multi.pdf"],
        "/out.pdf",
        paper_format="a6",
    )

    assert status is True
    result = fake_fitz["__created__"][0]
    portrait, landscape = result.new_pages
    a6_width, a6_height = pdf._PAPER_FORMATS["a6"]
    assert (portrait.width, portrait.height) == (a6_width, a6_height)
    assert (landscape.width, landscape.height) == (a6_height, a6_width)
    first_rect = portrait.shown[0][0]
    assert first_rect == pytest.approx(
        ((a6_width - 100) / 2, (a6_height - 200) / 2,
         (a6_width + 100) / 2, (a6_height + 200) / 2)
    )
    second_rect = landscape.shown[0][0]
    assert second_rect == pytest.approx(
        (
            (a6_height - 400) / 2,
            (a6_width - 200) / 2,
            (a6_height + 400) / 2,
            (a6_width + 200) / 2,
        )
    )
    assert result.saved == [
        ("/out.pdf", {"garbage": 3, "deflate": True, "clean": True})
    ]


def test_form_files_debug_fill_precedes_pdf_placement(fake_fitz):
    fake_fitz["/multi.pdf"] = FakeDoc(
        pages=[FakePage(rect=FakeRect(100, 200))]
    )

    status = pdf.form_files(
        ["/multi.pdf"], "/out.pdf", paper_format="a6", debug_fill=True
    )

    assert status is True
    page = fake_fitz["__created__"][0].new_pages[0]
    a6_width, a6_height = pdf._PAPER_FORMATS["a6"]
    assert page.drawn == [
        ((0, 0, a6_width, a6_height), None, (1, 0, 1), False)
    ]
    assert page.operations == ["draw_rect", "show_pdf_page"]


def test_form_files_debug_fill_precedes_raster_placement(
    fake_fitz, monkeypatch, tmp_path
):
    source = tmp_path / "input.png"
    Image.new("RGBA", (100, 50), (255, 0, 0, 0)).save(source)
    monkeypatch.setattr(
        pdf.os.path, "exists", lambda path: path == str(source)
    )
    status = pdf.form_files(
        [str(source)], str(tmp_path / "out.pdf"), paper_format="a6",
        debug_fill=True,
    )

    assert status is True
    page = fake_fitz["__created__"][0].new_pages[0]
    a6_width, a6_height = pdf._PAPER_FORMATS["a6"]
    assert page.drawn == [
        ((0, 0, a6_height, a6_width), None, (1, 0, 1), False)
    ]
    assert page.operations == ["draw_rect", "insert_image"]


def test_form_files_does_not_draw_debug_fill_by_default(fake_fitz):
    fake_fitz["/multi.pdf"] = FakeDoc(
        pages=[FakePage(rect=FakeRect(100, 200))]
    )

    assert pdf.form_files(["/multi.pdf"], "/out.pdf", paper_format="a6")

    assert fake_fitz["__created__"][0].new_pages[0].drawn == []


def test_form_files_rejects_unsupported_source_before_creating_result(
    fake_fitz,
):
    status = pdf.form_files(
        ["/a.txt"], "/out.pdf", paper_format="a4"
    )

    assert status is False
    assert fake_fitz["__created__"] == []


def test_form_image_bytes_downsamples_jpeg_to_placed_dpi(tmp_path):
    source = tmp_path / "wide.jpg"
    Image.new("RGB", (2000, 1000), "red").save(source, quality=95)

    payload = pdf._form_image_bytes(  # pylint: disable=W0212
        str(source), FakeRect(144, 72), dpi=200, quality=37
    )

    with Image.open(io.BytesIO(payload)) as image:
        assert image.format == "JPEG"
        assert image.size == (400, 200)


def test_form_image_bytes_does_not_enlarge_and_preserves_png_alpha(tmp_path):
    source = tmp_path / "transparent.png"
    Image.new("RGBA", (10, 20), (255, 0, 0, 100)).save(source)

    payload = pdf._form_image_bytes(  # pylint: disable=W0212
        str(source), FakeRect(144, 288), dpi=200, quality=80
    )

    with Image.open(io.BytesIO(payload)) as image:
        assert image.format == "PNG"
        assert image.size == (10, 20)
        assert image.mode == "RGBA"
        assert image.getpixel((0, 0))[3] == 100


@pytest.mark.parametrize("dpi", [72, 96])
def test_compress_file_supports_low_dpi_presets(fake_fitz, dpi):
    fake_fitz["/a.pdf"] = FakeDoc(page_count=1)

    status = pdf.compress_file("/a.pdf", "/out.pdf", dpi)

    assert status is True
    rewrite = fake_fitz["/a.pdf"].rewritten[0]
    assert rewrite["dpi_threshold"] == dpi + 1
    assert rewrite["dpi_target"] == dpi


def test_compress_file_uses_default_output_name(fake_fitz):
    fake_fitz["/a.pdf"] = FakeDoc(page_count=2)

    status = pdf.compress_file("/a.pdf", None, 200)

    assert status is True
    assert fake_fitz["/a.pdf"].saved == [
        (
            "/a_compressed_200dpi.pdf",
            {"garbage": 3, "deflate": True, "clean": True},
        )
    ]


def test_compress_file_supports_quality_override_and_grayscale(fake_fitz):
    fake_fitz["/a.pdf"] = FakeDoc(page_count=1)

    status = pdf.compress_file(
        "/a.pdf",
        "/out.pdf",
        400,
        quality=55,
        grayscale=True,
    )

    assert status is True
    assert fake_fitz["/a.pdf"].rewritten == [
        {
            "dpi_threshold": 401,
            "dpi_target": 400,
            "quality": 55,
            "lossy": True,
            "lossless": True,
            "bitonal": True,
            "color": True,
            "gray": True,
            "set_to_gray": True,
        }
    ]


def test_compress_file_logs_size_report(monkeypatch, fake_fitz):
    fake_fitz["/a.pdf"] = FakeDoc(page_count=1)
    size_map = {"/a.pdf": 2048, "/out.pdf": 1024}
    logged = []

    monkeypatch.setattr(pdf.os.path, "getsize", lambda path: size_map[path])
    monkeypatch.setattr(
        pdf.logger,
        "info",
        lambda msg, *args: logged.append((msg, args)),
    )

    status = pdf.compress_file("/a.pdf", "/out.pdf", 300)

    assert status is True
    assert logged == [
        (
            "pdf.compress: size %s -> %s (%.2f%%)",
            ("   2.00 K", "1024.00  ", 50.0),
        )
    ]


def test_compress_file_returns_false_for_missing_input(monkeypatch, fake_fitz):
    monkeypatch.setattr(pdf.os.path, "exists", lambda _path: False)

    status = pdf.compress_file("/missing.pdf", "/out.pdf", 300, verbose=True)

    assert status is False
    assert "/missing.pdf" not in fake_fitz


def test_compress_file_returns_false_for_non_pdf(fake_fitz):
    fake_fitz["/a.txt"] = FakeDoc(page_count=1)

    status = pdf.compress_file("/a.txt", "/out.pdf", 400, verbose=True)

    assert status is False
    assert fake_fitz["/a.txt"].rewritten == []


def test_merge_files_returns_false_when_nothing_added(monkeypatch, fake_fitz):
    monkeypatch.setattr(pdf.os.path, "exists", lambda _path: False)

    status = pdf.merge_files(["/missing.pdf"], "/out.pdf", verbose=True)

    assert status is False


def test_extract_images_uses_default_prefix_and_global_counter(
    monkeypatch, fake_fitz
):
    monkeypatch.setattr(
        pdf.os.path,
        "exists",
        lambda path: path == "/a.pdf",
    )
    fake_fitz["/a.pdf"] = FakeDoc(
        page_count=3,
        pages=[
            FakePage(images=[(11,), (12,)]),
            FakePage(images=[]),
            FakePage(images=[(31,)]),
        ],
        extracted_images={
            11: {"image": b"img-11", "ext": "png"},
            12: {"image": b"img-12", "ext": "jpeg"},
            31: {"image": b"img-31", "ext": "png"},
        },
    )
    written = []
    monkeypatch.setattr(
        pdf,
        "_write_extracted_image",
        lambda image_bytes, source_ext, target_path, output_type: (
            written.append(
                (image_bytes, source_ext, target_path, output_type)
            )
        ),
    )

    status = pdf.extract_images("/a.pdf", None)

    assert status is True
    assert written == [
        (b"img-11", "png", "/a_001.jpg", "jpg"),
        (b"img-12", "jpg", "/a_002.jpg", "jpg"),
        (b"img-31", "png", "/a_003.jpg", "jpg"),
    ]


def test_extract_images_respects_selected_page_order_and_output_type(
    monkeypatch, fake_fitz
):
    monkeypatch.setattr(
        pdf.os.path,
        "exists",
        lambda path: path == "/a.pdf",
    )
    fake_fitz["/a.pdf"] = FakeDoc(
        page_count=3,
        pages=[
            FakePage(images=[(11,)]),
            FakePage(images=[(22,), (23,)]),
            FakePage(images=[(33,)]),
        ],
        extracted_images={
            11: {"image": b"img-11", "ext": "png"},
            22: {"image": b"img-22", "ext": "png"},
            23: {"image": b"img-23", "ext": "png"},
            33: {"image": b"img-33", "ext": "png"},
        },
    )
    written = []
    monkeypatch.setattr(
        pdf,
        "_write_extracted_image",
        lambda image_bytes, source_ext, target_path, output_type: (
            written.append(
                (image_bytes, source_ext, target_path, output_type)
            )
        ),
    )

    status = pdf.extract_images(
        "/a.pdf",
        "/tmp/out.png",
        pages=[2, 1],
        output_type="png",
    )

    assert status is True
    assert written == [
        (b"img-22", "png", "/tmp/out_001.png", "png"),
        (b"img-23", "png", "/tmp/out_002.png", "png"),
        (b"img-11", "png", "/tmp/out_003.png", "png"),
    ]


def test_extract_images_returns_false_when_no_embedded_images(
    monkeypatch, fake_fitz
):
    monkeypatch.setattr(
        pdf.os.path,
        "exists",
        lambda path: path == "/a.pdf",
    )
    fake_fitz["/a.pdf"] = FakeDoc(
        page_count=2,
        pages=[FakePage(images=[]), FakePage(images=[])],
    )

    status = pdf.extract_images(
        "/a.pdf",
        None,
        verbose=True,
        rewrite=True,
    )

    assert status is False


def test_extract_images_rejects_invalid_type():
    with pytest.raises(ValueError, match="unsupported image type"):
        pdf.extract_images("/a.pdf", None, output_type="gif")


def test_extract_images_overwrites_collision_with_warning(
    monkeypatch, fake_fitz, caplog
):
    monkeypatch.setattr(
        pdf.os.path,
        "exists",
        lambda path: path in {"/a.pdf", "/a_001.jpg"},
    )
    fake_fitz["/a.pdf"] = FakeDoc(
        page_count=1,
        pages=[FakePage(images=[(11,)])],
        extracted_images={11: {"image": b"img-11", "ext": "png"}},
    )
    written = []
    monkeypatch.setattr(
        pdf,
        "_write_extracted_image",
        lambda *args: written.append(args),
    )

    status = pdf.extract_images(
        "/a.pdf",
        None,
        verbose=True,
        rewrite=True,
    )

    assert status is True
    assert written
    assert "overwriting existing output file: /a_001.jpg" in caplog.text


def test_extract_images_whole_page_mode_renders_selected_pages(
    monkeypatch, fake_fitz
):
    monkeypatch.setattr(
        pdf.os.path,
        "exists",
        lambda path: path == "/a.pdf",
    )
    fake_fitz["/a.pdf"] = FakeDoc(
        page_count=3,
        pages=[
            FakePage(images=[], rendered_bytes=b"page-1"),
            FakePage(images=[], rendered_bytes=b"page-2"),
            FakePage(images=[(31,)], rendered_bytes=b"page-3"),
        ],
        extracted_images={31: {"image": b"img-31", "ext": "png"}},
    )
    written = []
    monkeypatch.setattr(
        pdf,
        "_write_extracted_image",
        lambda image_bytes, source_ext, target_path, output_type: (
            written.append(
                (image_bytes, source_ext, target_path, output_type)
            )
        ),
    )

    status = pdf.extract_images(
        "/a.pdf",
        None,
        pages=[2, 1],
        output_type="png",
        whole_page=True,
    )

    assert status is True
    assert written == [
        (b"page-2", "png", "/a_001.png", "png"),
        (b"page-1", "png", "/a_002.png", "png"),
    ]
    assert fake_fitz["/a.pdf"].pages[1].pixmap_calls == [{"dpi": 300}]
    assert fake_fitz["/a.pdf"].pages[0].pixmap_calls == [{"dpi": 300}]


@pytest.mark.parametrize(
    ("arguments", "expected"),
    [
        (
            ["merge", "cover.pdf", "/tmp/body.pdf", "-o", "all.pdf"],
            {"inf": ["cover.pdf", "/tmp/body.pdf"], "out": "all.pdf"},
        ),
        (
            ["rotate", "scan.pdf", "-o", "/tmp/out.pdf", "-d", "left"],
            {"inf": "scan.pdf", "out": "/tmp/out.pdf", "dir": "left"},
        ),
        (
            ["delete", "scan.pdf", "-o", "out.pdf", "-p", "2", "4"],
            {"inf": "scan.pdf", "out": "out.pdf", "pages": [2, 4]},
        ),
        (
            ["split", "scan.pdf", "-o", "out.pdf", "-p", "3", "7"],
            {"inf": "scan.pdf", "out": "out.pdf", "pages": [3, 7]},
        ),
        (
            ["clean", "/tmp/scan.pdf", "-o", "clean.pdf"],
            {"inf": "/tmp/scan.pdf", "out": "clean.pdf"},
        ),
        (
            [
                "compress",
                "scan.pdf",
                "-o",
                "small.pdf",
                "--dpi",
                "200",
                "--quality",
                "60",
                "--grayscale",
            ],
            {
                "inf": "scan.pdf",
                "out": "small.pdf",
                "dpi": 200,
                "quality": 60,
                "grayscale": True,
            },
        ),
        (
            [
                "extract",
                "scan.pdf",
                "-o",
                "/tmp/page.png",
                "-p",
                "1",
                "3",
                "-t",
                "png",
                "-w",
            ],
            {
                "inf": "scan.pdf",
                "out": "/tmp/page.png",
                "pages": [1, 3],
                "type": "png",
                "whole_page": True,
            },
        ),
        (
            ["info", "/documents/scan.pdf", "-p", "2", "1"],
            {"inf": "/documents/scan.pdf", "pages": [2, 1]},
        ),
        (
            [
                "scale",
                "scan.pdf",
                "-o",
                "out.pdf",
                "-p",
                "2",
                "1",
                "--format",
                "a5",
            ],
            {
                "inf": "scan.pdf",
                "out": "out.pdf",
                "pages": [2, 1],
                "paper_format": "a5",
            },
        ),
    ],
)
def test_init_parser_pdf_accepts_positional_inputs_and_options(
    arguments, expected
):
    parser = argparse.ArgumentParser()
    photo_cli.init_parser_pdf(parser)

    namespace = parser.parse_args(arguments)

    for name, value in expected.items():
        assert getattr(namespace, name) == value
    assert not hasattr(namespace, "path")
    assert callable(namespace.func)


@pytest.mark.parametrize(
    "command",
    [
        "merge",
        "rotate",
        "delete",
        "split",
        "clean",
        "compress",
        "extract",
        "info",
        "scale",
    ],
)
def test_init_parser_pdf_requires_input(command):
    parser = argparse.ArgumentParser()
    photo_cli.init_parser_pdf(parser)

    with pytest.raises(SystemExit):
        parser.parse_args([command])


@pytest.mark.parametrize("dpi", [72, 96])
def test_init_parser_pdf_accepts_low_compress_dpi(dpi):
    parser = argparse.ArgumentParser()
    photo_cli.init_parser_pdf(parser)

    namespace = parser.parse_args(
        ["compress", "scan.pdf", "--dpi", str(dpi)]
    )

    assert namespace.dpi == dpi


def test_init_parser_pdf_compress_defaults():
    parser = argparse.ArgumentParser()
    photo_cli.init_parser_pdf(parser)

    namespace = parser.parse_args(["compress", "scan.pdf"])

    assert namespace.dpi == 300
    assert namespace.quality == 80
    assert not hasattr(namespace, "rebuild")


def test_init_parser_pdf_rejects_removed_rebuild_flag():
    parser = argparse.ArgumentParser()
    photo_cli.init_parser_pdf(parser)

    with pytest.raises(SystemExit):
        parser.parse_args(["compress", "scan.pdf", "--rebuild"])


@pytest.mark.parametrize(
    ("command", "arguments"),
    [
        ("merge", ["first.pdf", "second.pdf"]),
        ("rotate", ["scan.pdf"]),
        ("delete", ["scan.pdf", "-p", "1"]),
        ("split", ["scan.pdf", "-p", "1"]),
        ("clean", ["scan.pdf"]),
        ("compress", ["scan.pdf"]),
        ("extract", ["scan.pdf"]),
        ("scale", ["scan.pdf"]),
    ],
)
def test_init_parser_pdf_accepts_rewrite_flag(command, arguments):
    parser = argparse.ArgumentParser()
    photo_cli.init_parser_pdf(parser)

    namespace = parser.parse_args([command, *arguments, "--rewrite"])

    assert namespace.rewrite is True


def test_init_parser_pdf_info_rejects_rewrite_flag():
    parser = argparse.ArgumentParser()
    photo_cli.init_parser_pdf(parser)

    with pytest.raises(SystemExit):
        parser.parse_args(["info", "scan.pdf", "--rewrite"])


@pytest.mark.parametrize("input_option", ["-i", "--inf"])
def test_init_parser_pdf_rejects_removed_input_options(input_option):
    parser = argparse.ArgumentParser()
    photo_cli.init_parser_pdf(parser)

    with pytest.raises(SystemExit):
        parser.parse_args(["info", input_option, "a.pdf"])


def test_init_parser_pdf_rejects_removed_root_option():
    parser = argparse.ArgumentParser()
    photo_cli.init_parser_pdf(parser)

    with pytest.raises(SystemExit):
        parser.parse_args(["info", "a.pdf", "--root", "/documents"])


@pytest.mark.parametrize("command", ["merge", "rotate", "delete"])
def test_init_parser_pdf_preserves_legacy_alias_arguments(command):
    parser = argparse.ArgumentParser()
    photo_cli.init_parser_pdf(
        parser,
        prefix="pdf-",
        commands=(command,),
        legacy=True,
    )
    input_files = ["a.pdf", "b.pdf"] if command == "merge" else ["a.pdf"]

    namespace = parser.parse_args(
        [f"pdf-{command}", "/documents", "-i", *input_files, "-W"]
    )

    assert namespace.path == "/documents"
    expected_input = input_files if command == "merge" else "a.pdf"
    assert namespace.inf == expected_input
    assert namespace.rewrite is True


@pytest.mark.parametrize("command", ["info", "merge"])
def test_init_parser_pdf_help_documents_positional_input(
    command, capsys
):
    parser = argparse.ArgumentParser()
    photo_cli.init_parser_pdf(parser)

    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args([command, "--help"])

    assert exc_info.value.code == 0
    help_text = capsys.readouterr().out
    assert "INPUT" in help_text
    assert "--inf" not in help_text
    assert "--root" not in help_text


@pytest.mark.parametrize(
    ("command", "arguments", "expected_input"),
    [
        ("merge", ["first.pdf", "second.pdf"], ["first.pdf", "second.pdf"]),
        ("rotate", ["scan.pdf"], "scan.pdf"),
        ("delete", ["scan.pdf", "-p", "1"], "scan.pdf"),
        ("split", ["scan.pdf", "-p", "1"], "scan.pdf"),
        ("clean", ["scan.pdf"], "scan.pdf"),
        ("compress", ["scan.pdf"], "scan.pdf"),
        ("extract", ["scan.pdf"], "scan.pdf"),
        ("scale", ["scan.pdf"], "scan.pdf"),
    ],
)
def test_init_parser_pdf_passes_direct_input_and_no_output(
    monkeypatch, command, arguments, expected_input
):
    calls = []
    monkeypatch.setattr(
        helpers,
        f"command_pdf_{command}",
        lambda **kwargs: calls.append(kwargs),
    )
    parser = argparse.ArgumentParser()
    photo_cli.init_parser_pdf(parser)

    namespace = parser.parse_args([command, *arguments])
    namespace.func(namespace)

    assert calls[0]["root"] is None
    assert calls[0]["inf"] == expected_input
    assert calls[0]["out"] is None
    assert calls[0]["rewrite"] is False


def test_command_pdf_merge_preserves_direct_paths_and_omitted_output(
    monkeypatch,
):
    calls = []
    monkeypatch.setattr(
        pdf,
        "merge_files",
        lambda input_files, output_path, **kwargs: calls.append(
            (input_files, output_path, kwargs)
        )
        or True,
    )

    helpers.command_pdf_merge(
        None,
        None,
        ["body.pdf", "/documents/appendix.pdf"],
        verbose=True,
    )

    assert calls == [
        (
            ["body.pdf", "/documents/appendix.pdf"],
            None,
            {"rewrite": False, "verbose": True},
        )
    ]


def test_command_pdf_clean_preserves_direct_paths_and_omitted_output(
    monkeypatch,
):
    calls = []
    monkeypatch.setattr(
        pdf,
        "clean_file",
        lambda input_file, output_path, **kwargs: calls.append(
            (input_file, output_path, kwargs)
        )
        or True,
    )

    helpers.command_pdf_clean(
        None,
        None,
        "scan.pdf",
        verbose=True,
        rewrite=True,
    )

    assert calls == [
        ("scan.pdf", None, {"rewrite": True, "verbose": True})
    ]


def test_inspect_pages_classifies_text_vector_empty_and_mixed(fake_fitz):
    fake_fitz["/a.pdf"] = FakeDoc(
        page_count=4,
        pages=[
            FakePage(text="hello"),
            FakePage(drawings=[object()]),
            FakePage(),
            FakePage(
                text="caption",
                images=[(41,)],
                image_rects={41: [FakeRect(100, 100)]},
            ),
        ],
        extracted_images={
            41: {"width": 400, "height": 400},
        },
    )

    rows = pdf.inspect_pages("/a.pdf")

    assert [row["type"] for row in rows] == [
        "text",
        "vector",
        "empty",
        "mixed",
    ]
    assert [row["resolution"] for row in rows[:3]] == ["-", "-", "-"]
    assert [row["image_size_px"] for row in rows[:3]] == ["-", "-", "-"]


def test_inspect_pages_classifies_raster_and_formats_metadata(fake_fitz):
    page_rect = FakeRect(595, 842)
    fake_fitz["/scan.pdf"] = FakeDoc(
        page_count=1,
        pages=[
            FakePage(
                images=[(11,)],
                image_rects={11: [page_rect]},
                rect=page_rect,
            )
        ],
        extracted_images={
            11: {"width": 2480, "height": 3508},
        },
    )

    rows = pdf.inspect_pages("/scan.pdf")

    assert rows == [
        {
            "page": 1,
            "type": "raster",
            "resolution": "300 dpi",
            "image_size_px": "2480x3508 px",
            "orientation": "portrait",
            "page_size": "a4",
        }
    ]


def test_inspect_pages_classifies_single_partial_image_as_raster(fake_fitz):
    fake_fitz["/scan.pdf"] = FakeDoc(
        page_count=1,
        pages=[
            FakePage(
                images=[(11,)],
                image_rects={11: [FakeRect(100, 100, x0=20, y0=20)]},
            )
        ],
        extracted_images={11: {"width": 400, "height": 400}},
    )

    assert pdf.inspect_pages("/scan.pdf")[0]["type"] == "raster"


def test_inspect_pages_formats_different_dpi_per_axis(fake_fitz):
    page_rect = FakeRect(72, 72)
    fake_fitz["/scan.pdf"] = FakeDoc(
        page_count=1,
        pages=[
            FakePage(
                images=[(11,)], image_rects={11: [page_rect]}, rect=page_rect
            )
        ],
        extracted_images={11: {"width": 300, "height": 200}},
    )

    rows = pdf.inspect_pages("/scan.pdf")

    assert rows[0]["resolution"] == "300x200 dpi"


def test_inspect_pages_uses_visible_bbox_and_reused_xref_for_multi_raster(
    fake_fitz,
):
    fake_fitz["/multi.pdf"] = FakeDoc(
        page_count=1,
        pages=[
            FakePage(
                images=[(11,)],
                image_rects={
                    11: [FakeRect(100, 100), FakeRect(360, 360)],
                },
            )
        ],
        extracted_images={
            11: {"width": 1500, "height": 1500},
        },
    )

    rows = pdf.inspect_pages("/multi.pdf")

    assert rows == [
        {
            "page": 1,
            "type": "multi-raster",
            "resolution": "300 dpi",
            "image_size_px": "1500x1500 px",
            "orientation": "portrait",
            "page_size": "a4",
        }
    ]


def test_command_pdf_info_prints_report(monkeypatch, capsys):
    monkeypatch.setattr(
        pdf,
        "inspect_pages",
        lambda *_args, **_kwargs: [
            {
                "page": 1,
                "type": "empty",
                "resolution": "-",
                "image_size_px": "-",
                "orientation": "portrait",
                "page_size": "210x297 mm",
            }
        ],
    )

    helpers.command_pdf_info("/root", "a.pdf")

    output = capsys.readouterr().out
    assert "Page" in output
    assert "ImageSizePx" in output
    assert "empty" in output
    assert "210x297 mm" in output
    assert "XResolution" not in output
    assert "YResolution" not in output


@pytest.mark.parametrize(
    ("width_mm", "height_mm", "expected"),
    [
        (297, 420, "a3"),
        (420, 297, "a3"),
        (210, 297, "a4"),
        (297, 210, "a4"),
        (148, 210, "a5"),
        (210, 148, "a5"),
        (105, 148, "a6"),
        (148, 105, "a6"),
        (212, 297, "212x297 mm"),
    ],
)
def test_format_page_size_recognizes_iso_sizes_in_both_orientations(
    width_mm, height_mm, expected
):
    rect = FakeRect(width_mm * 72.0 / 25.4, height_mm * 72.0 / 25.4)

    assert pdf._format_page_size(rect) == expected  # pylint: disable=W0212
    if expected.startswith("a"):
        assert pdf._format_page_size(rect, pt=True) == expected  # pylint: disable=W0212


def test_format_page_info_report_supports_points_and_ascii_table():
    rows = [
        {
            "page": 2,
            "type": "raster",
            "resolution": "300x200 dpi",
            "image_size_px": "100x200 px",
            "orientation": "portrait",
            "page_size": "612x792 pt",
        }
    ]

    report = pdf.format_page_info_report(rows, table=True)

    assert report.splitlines()[0].startswith("+")
    assert "| Page" in report
    assert "300x200 dpi" in report
    assert "XResolution" not in report
    assert report.splitlines()[-1] == report.splitlines()[0]


def test_init_parser_pdf_info_passes_display_options(monkeypatch):
    calls = []
    monkeypatch.setattr(
        helpers, "command_pdf_info", lambda **kwargs: calls.append(kwargs)
    )
    parser = argparse.ArgumentParser()
    photo_cli.init_parser_pdf(parser)

    namespace = parser.parse_args(["info", "scan.pdf", "--pt", "-t"])
    namespace.func(namespace)

    assert calls == [
        {
            "root": None,
            "inf": "scan.pdf",
            "pages": None,
            "verbose": False,
            "pt": True,
            "table": True,
        }
    ]


@pytest.mark.parametrize(
    ("out", "expected_output"),
    [
        ("formed.pdf", "/root/formed.pdf"),
        (None, "/root/scan_formed.pdf"),
    ],
)
def test_command_pdf_form_reports_actual_output_after_success(
    monkeypatch, out, expected_output
):
    monkeypatch.setattr(pdf, "form_files", lambda *_args, **_kwargs: True)
    calls = []
    monkeypatch.setattr(
        helpers, "command_pdf_info", lambda root, inf, **kwargs: calls.append(
            (root, inf, kwargs)
        )
    )

    helpers.command_pdf_form("/root", out, ["scan.pdf"], paper_format="a4")

    assert calls == [(None, expected_output, {"verbose": False})]


def test_command_pdf_form_does_not_report_failed_output(monkeypatch):
    monkeypatch.setattr(pdf, "form_files", lambda *_args, **_kwargs: False)
    calls = []
    monkeypatch.setattr(
        helpers, "command_pdf_info", lambda *_args, **_kwargs: calls.append(1)
    )

    helpers.command_pdf_form(
        "/root", "formed.pdf", ["scan.pdf"], paper_format="a4"
    )

    assert calls == []


def test_command_pdf_form_forwards_quality(monkeypatch):
    calls = []
    monkeypatch.setattr(
        pdf,
        "form_files",
        lambda *args, **kwargs: calls.append((args, kwargs)) or False,
    )

    helpers.command_pdf_form(
        "/root", "formed.pdf", ["scan.pdf"], paper_format="a4", quality=37
    )

    assert calls[0][1]["quality"] == 37


def test_command_pdf_form_forwards_debug_fill(monkeypatch):
    calls = []
    monkeypatch.setattr(
        pdf,
        "form_files",
        lambda *args, **kwargs: calls.append((args, kwargs)) or False,
    )

    helpers.command_pdf_form(
        "/root", "formed.pdf", ["scan.pdf"], paper_format="a4",
        debug_fill=True,
    )

    assert calls[0][1]["debug_fill"] is True


def test_scale_file_uses_default_output_name_and_a4_portrait(fake_fitz):
    fake_fitz["/a.pdf"] = FakeDoc(
        page_count=1,
        pages=[FakePage(rect=FakeRect(200, 400))],
    )

    status = pdf.scale_file("/a.pdf", None, paper_format="a4")

    assert status is True
    created = fake_fitz["__created__"][0]
    assert created.saved == [
        (
            "/a_scaled_a4.pdf",
            {"garbage": 3, "deflate": True, "clean": True},
        )
    ]
    assert len(created.new_pages) == 1
    new_page = created.new_pages[0]
    assert round(new_page.width, 3) == round(210.0 * 72.0 / 25.4, 3)
    assert round(new_page.height, 3) == round(297.0 * 72.0 / 25.4, 3)
    shown_rect, shown_doc, shown_idx, keep_proportion = new_page.shown[0]
    assert shown_doc is fake_fitz["/a.pdf"]
    assert shown_idx == 0
    assert keep_proportion is True
    a4_width = 210.0 * 72.0 / 25.4
    a4_height = 297.0 * 72.0 / 25.4
    scale = min(a4_width / 200.0, a4_height / 400.0)
    fitted_width = 200.0 * scale
    assert shown_rect == pytest.approx(
        (
            (a4_width - fitted_width) / 2.0,
            0.0,
            (a4_width + fitted_width) / 2.0,
            a4_height,
        )
    )


def test_scale_file_supports_a5_landscape(fake_fitz):
    fake_fitz["/landscape.pdf"] = FakeDoc(
        page_count=1,
        pages=[FakePage(rect=FakeRect(400, 200))],
    )

    status = pdf.scale_file("/landscape.pdf", "/out.pdf", paper_format="a5")

    assert status is True
    created = fake_fitz["__created__"][0]
    assert created.saved == [
        ("/out.pdf", {"garbage": 3, "deflate": True, "clean": True})
    ]
    new_page = created.new_pages[0]
    assert round(new_page.width, 3) == round(210.0 * 72.0 / 25.4, 3)
    assert round(new_page.height, 3) == round(148.0 * 72.0 / 25.4, 3)
    shown_rect = new_page.shown[0][0]
    a5_width = 210.0 * 72.0 / 25.4
    a5_height = 148.0 * 72.0 / 25.4
    scale = min(a5_width / 400.0, a5_height / 200.0)
    fitted_height = 200.0 * scale
    assert shown_rect == pytest.approx(
        (
            0.0,
            (a5_height - fitted_height) / 2.0,
            a5_width,
            (a5_height + fitted_height) / 2.0,
        )
    )


def test_scale_file_respects_page_selection_order(fake_fitz):
    fake_fitz["/a.pdf"] = FakeDoc(
        page_count=3,
        pages=[
            FakePage(rect=FakeRect(200, 400)),
            FakePage(rect=FakeRect(400, 200)),
            FakePage(rect=FakeRect(300, 300)),
        ],
    )

    status = pdf.scale_file("/a.pdf", "/out.pdf", pages=[2, 1])

    assert status is True
    created = fake_fitz["__created__"][0]
    assert [page.shown[0][2] for page in created.new_pages] == [1, 0]


def test_command_pdf_scale_passes_paths_and_format(monkeypatch):
    calls = []
    monkeypatch.setattr(
        pdf,
        "scale_file",
        lambda input_file, output_path, **kwargs: calls.append(
            (input_file, output_path, kwargs)
        )
        or True,
    )

    helpers.command_pdf_scale(
        "/root",
        "out.pdf",
        "a.pdf",
        pages=[2, 1],
        paper_format="a5",
        verbose=True,
    )

    assert calls == [
        (
            "/root/a.pdf",
            "/root/out.pdf",
            {
                "pages": [2, 1],
                "paper_format": "a5",
                "rewrite": False,
                "verbose": True,
            },
        )
    ]


def test_compress_file_rebuild_renders_pages_and_inserts_full_page_images(
    fake_fitz,
):
    png_bytes = make_png_bytes()
    fake_fitz["/a.pdf"] = FakeDoc(
        page_count=2,
        pages=[
            FakePage(rect=FakeRect(595, 842), rendered_bytes=png_bytes),
            FakePage(rect=FakeRect(400, 200), rendered_bytes=png_bytes),
        ],
    )

    status = pdf.compress_file(
        "/a.pdf",
        "/out.pdf",
        200,
        rebuild=True,
    )

    assert status is True
    assert fake_fitz["/a.pdf"].rewritten == []
    assert fake_fitz["/a.pdf"].pages[0].pixmap_calls == [{"dpi": 200}]
    assert fake_fitz["/a.pdf"].pages[1].pixmap_calls == [{"dpi": 200}]
    created = fake_fitz["__created__"][0]
    assert created.saved == [
        ("/out.pdf", {"garbage": 3, "deflate": True, "clean": True})
    ]
    assert [
        (page.width, page.height) for page in created.new_pages
    ] == [(595, 842), (400, 200)]
    assert created.new_pages[0].inserted[0][0] == (0.0, 0.0, 595.0, 842.0)
    assert created.new_pages[1].inserted[0][0] == (0.0, 0.0, 400.0, 200.0)
    assert created.new_pages[0].inserted[0][2] is False
    assert created.new_pages[1].inserted[0][2] is False
    assert created.new_pages[0].inserted[0][1]
    assert created.new_pages[1].inserted[0][1]


def test_compress_file_rebuild_uses_default_output_name(fake_fitz):
    fake_fitz["/a.pdf"] = FakeDoc(
        page_count=1,
        pages=[
            FakePage(
                rect=FakeRect(595, 842),
                rendered_bytes=make_png_bytes(),
            )
        ],
    )

    status = pdf.compress_file("/a.pdf", None, 200, rebuild=True)

    assert status is True
    created = fake_fitz["__created__"][0]
    assert created.saved == [
        (
            "/a_compressed_200dpi.pdf",
            {"garbage": 3, "deflate": True, "clean": True},
        )
    ]


def test_command_pdf_compress_rebuilds_by_default(monkeypatch):
    calls = []
    monkeypatch.setattr(
        pdf,
        "compress_file",
        lambda input_file, output_path, dpi, **kwargs: calls.append(
            (input_file, output_path, dpi, kwargs)
        )
        or True,
    )

    helpers.command_pdf_compress(
        "/root",
        "out.pdf",
        "a.pdf",
        200,
        55,
        grayscale=True,
        verbose=True,
    )

    assert calls == [
        (
            "/root/a.pdf",
            "/root/out.pdf",
            200,
            {
                "quality": 55,
                "grayscale": True,
                "rebuild": True,
                "rewrite": False,
                "verbose": True,
            },
        )
    ]
