import types

import pytest

from davo.services.photo import pdf


class FakePage:
    def __init__(self, use_legacy=False, with_rotation=True):
        self.rotation = []
        self.rotation_legacy = []
        if with_rotation:
            if use_legacy:
                self.setRotation = self._set_rotation_legacy
            else:
                self.set_rotation = self._set_rotation

    def _set_rotation(self, value):
        self.rotation.append(value)

    def _set_rotation_legacy(self, value):
        self.rotation_legacy.append(value)


class FakeDoc:
    def __init__(self, page_count=1, pages=None):
        self.page_count = page_count
        self.pages = pages
        if self.pages is None:
            self.pages = [FakePage() for _ in range(page_count)]
        self.saved = []
        self.deleted = []
        self.inserted = []

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


@pytest.fixture(autouse=True)
def fake_paths(monkeypatch):
    monkeypatch.setattr(pdf.os.path, "exists", lambda path: True)


@pytest.fixture()
def fake_fitz(monkeypatch):
    docs = {}

    def _open(*args):
        if len(args) == 0:
            return FakeDoc(page_count=0)
        key = args[0]
        if key not in docs:
            docs[key] = FakeDoc(page_count=3)
        return docs[key]

    fitz_mod = types.SimpleNamespace(open=_open)
    monkeypatch.setattr(pdf, "fitz", fitz_mod)
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


def test_merge_files_returns_false_when_nothing_added(monkeypatch, fake_fitz):
    monkeypatch.setattr(pdf.os.path, "exists", lambda _path: False)

    status = pdf.merge_files(["/missing.pdf"], "/out.pdf", verbose=True)

    assert status is False
