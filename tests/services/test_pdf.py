import types

import pytest

from davo.services.photo import pdf


class FakePage:
    def __init__(
        self,
        use_legacy=False,
        with_rotation=True,
        images=None,
        rendered_bytes=None,
    ):
        self.rotation = []
        self.rotation_legacy = []
        self.images = images or []
        self.rendered_bytes = rendered_bytes or b"rendered-page"
        self.pixmap_calls = []
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


@pytest.fixture(autouse=True)
def fake_paths(monkeypatch):
    monkeypatch.setattr(pdf.os.path, "exists", lambda path: True)
    monkeypatch.setattr(pdf.os.path, "getsize", lambda _path: 1024)


@pytest.fixture()
def fake_fitz(mocker):
    docs = {}

    def _open(*args):
        if len(args) == 0:
            return FakeDoc(page_count=0)
        key = args[0]
        if key not in docs:
            docs[key] = FakeDoc(page_count=3)
        return docs[key]

    fitz_mod = types.SimpleNamespace(
        open=_open,
        Matrix=lambda x, y: (x, y),
    )
    mocker.patch("davo.services.photo.pdf._import_fitz", return_value=fitz_mod)
    return docs


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


def test_split_pages_returns_false_on_collision(monkeypatch, fake_fitz):
    def _exists(path):
        if path == "/a_1.pdf":
            return True
        return True

    monkeypatch.setattr(pdf.os.path, "exists", _exists)
    fake_fitz["/a.pdf"] = FakeDoc(page_count=4)

    status = pdf.split_pages("/a.pdf", None, pages=[1, 3], verbose=True)

    assert status is False


def test_clean_file_uses_default_output_and_save_options(fake_fitz):
    fake_fitz["/a.pdf"] = FakeDoc(page_count=2)

    status = pdf.clean_file("/a.pdf", None)

    assert status is True
    assert fake_fitz["/a.pdf"].saved == [
        ("/a_cleaned.pdf", {"garbage": 3, "deflate": True, "clean": True})
    ]


def test_compress_file_rewrites_images_and_saves(fake_fitz):
    fake_fitz["/a.pdf"] = FakeDoc(page_count=2)

    status = pdf.compress_file("/a.pdf", "/out.pdf", 300)

    assert status is True
    assert fake_fitz["/a.pdf"].rewritten == [
        {
            "dpi_threshold": 301,
            "dpi_target": 300,
            "quality": 75,
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
        lambda image_bytes, source_ext, target_path, output_type: written.append(
            (image_bytes, source_ext, target_path, output_type)
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
        lambda image_bytes, source_ext, target_path, output_type: written.append(
            (image_bytes, source_ext, target_path, output_type)
        ),
    )

    status = pdf.extract_images("/a.pdf", "/tmp/out.png", pages=[2, 1], output_type="png")

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

    status = pdf.extract_images("/a.pdf", None, verbose=True)

    assert status is False


def test_extract_images_rejects_invalid_type():
    with pytest.raises(ValueError, match="unsupported image type"):
        pdf.extract_images("/a.pdf", None, output_type="gif")


def test_extract_images_returns_false_on_output_collision(
    monkeypatch, fake_fitz
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

    status = pdf.extract_images("/a.pdf", None, verbose=True)

    assert status is False


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
        lambda image_bytes, source_ext, target_path, output_type: written.append(
            (image_bytes, source_ext, target_path, output_type)
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
