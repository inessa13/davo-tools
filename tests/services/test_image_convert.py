from PIL import Image, ImageFile

from davo.services.photo import utils


def _truncated_panorama(path):
    Image.new("RGB", (7001, 3), "red").save(path)
    path.write_bytes(path.read_bytes()[:-2])


def test_image_convert_dry_run_accepts_truncated_jpeg(tmp_path, monkeypatch):
    source = tmp_path / "panorama.jpg"
    destination = tmp_path / "thumbnail.jpg"
    _truncated_panorama(source)
    source_data = source.read_bytes()
    monkeypatch.setattr(ImageFile, "LOAD_TRUNCATED_IMAGES", False)

    utils.image_convert(
        str(source), str(destination), thumbnail=1600, commit=False
    )

    assert source.read_bytes() == source_data
    assert not destination.exists()
    assert not ImageFile.LOAD_TRUNCATED_IMAGES


def test_image_convert_saves_thumbnail_from_truncated_jpeg(
    tmp_path, monkeypatch
):
    source = tmp_path / "panorama.jpg"
    destination = tmp_path / "thumbnail.jpg"
    _truncated_panorama(source)
    monkeypatch.setattr(ImageFile, "LOAD_TRUNCATED_IMAGES", False)

    utils.image_convert(
        str(source), str(destination), thumbnail=1600, commit=True
    )

    with Image.open(destination) as thumbnail:
        assert thumbnail.size == (1600, 1)
    assert not ImageFile.LOAD_TRUNCATED_IMAGES
