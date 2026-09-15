from PIL import Image, ImageFile

from davo.services.photo import helpers, utils

_DEFAULT_REPLACE = "[source]_converted.[Ext]"


def _truncated_panorama(path):
    Image.new("RGB", (7001, 3), "red").save(path)
    path.write_bytes(path.read_bytes()[:-2])


def _convert(path, **kwargs):
    helpers.command_convert(
        root=str(path),
        replace=kwargs.get("replace", _DEFAULT_REPLACE),
        recursive=False,
        thumbnail=kwargs.get("thumbnail"),
        skip_no_exif=False,
        drop_alpha=False,
        dry_run=kwargs.get("dry_run", False),
        rewrite=kwargs.get("rewrite", False),
    )


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


def test_command_convert_writes_converted_copy_by_default(tmp_path):
    source = tmp_path / "photo.jpg"
    Image.new("RGB", (8, 8), "red").save(source)
    source_data = source.read_bytes()

    _convert(source)

    output = tmp_path / "photo_converted.jpg"
    assert output.read_bytes() == source_data
    assert source.read_bytes() == source_data


def test_command_convert_dry_run_does_not_write(tmp_path):
    source = tmp_path / "photo.jpg"
    Image.new("RGB", (8, 8), "red").save(source)

    _convert(source, dry_run=True)

    assert source.exists()
    assert not (tmp_path / "photo_converted.jpg").exists()


def test_command_convert_skips_existing_output_without_rewrite(tmp_path):
    source = tmp_path / "photo.jpg"
    Image.new("RGB", (8, 8), "red").save(source)
    output = tmp_path / "photo_converted.jpg"
    output.write_bytes(b"existing")

    _convert(source)

    assert output.read_bytes() == b"existing"


def test_command_convert_rewrite_replaces_default_output(tmp_path):
    source = tmp_path / "photo.jpg"
    Image.new("RGB", (8, 8), "blue").save(source)
    output = tmp_path / "photo_converted.jpg"
    output.write_bytes(b"existing")

    _convert(source, rewrite=True)

    assert output.read_bytes() == source.read_bytes()
    assert output.read_bytes() != b"existing"


def test_command_convert_never_rewrites_custom_pattern(tmp_path):
    source = tmp_path / "photo.jpg"
    Image.new("RGB", (8, 8), "green").save(source)
    output = tmp_path / "photo_copy.jpg"
    output.write_bytes(b"existing")

    _convert(source, replace="[source]_copy.[Ext]", rewrite=True)

    assert output.read_bytes() == b"existing"
