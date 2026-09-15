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
        recursive=kwargs.get("recursive", False),
        thumbnail=kwargs.get("thumbnail"),
        skip_no_exif=False,
        drop_alpha=False,
        dry_run=kwargs.get("dry_run", False),
        rewrite=kwargs.get("rewrite", False),
        separate_dir=kwargs.get("separate_dir", False),
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


def test_command_convert_logs_relative_destination(
    tmp_path, monkeypatch, caplog
):
    monkeypatch.chdir(tmp_path)
    source = tmp_path / "photo.jpg"
    Image.new("RGB", (8, 8), "red").save(source)
    caplog.set_level("INFO")

    _convert(source, dry_run=True)
    default_line = next(
        record.getMessage()
        for record in caplog.records
        if record.getMessage().startswith("photo.jpg")
    )
    assert default_line.split()[-1] == "photo_converted.jpg"
    assert str(tmp_path) not in default_line

    caplog.clear()
    _convert(source, dry_run=True, separate_dir=True)
    separate_line = next(
        record.getMessage()
        for record in caplog.records
        if record.getMessage().startswith("photo.jpg")
    )
    assert separate_line.split()[-1] == "davo_im_convert/photo.jpg"
    assert str(tmp_path) not in separate_line


def test_command_convert_separate_dir_writes_original_name(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    source = tmp_path / "photo.jpg"
    Image.new("RGB", (8, 8), "red").save(source)
    source_data = source.read_bytes()

    _convert(source, separate_dir=True)

    output = tmp_path / "davo_im_convert" / "photo.jpg"
    assert output.read_bytes() == source_data
    assert not (tmp_path / "photo_converted.jpg").exists()
    assert source.read_bytes() == source_data


def test_command_convert_separate_dir_mirrors_relative_path(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    source = tmp_path / "photos" / "a.jpg"
    source.parent.mkdir()
    Image.new("RGB", (8, 8), "red").save(source)

    _convert(source, separate_dir=True)

    output = tmp_path / "davo_im_convert" / "photos" / "a.jpg"
    assert output.exists()
    assert not (tmp_path / "photos" / "a_converted.jpg").exists()


def test_command_convert_separate_dir_dry_run_does_not_create_dir(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    source = tmp_path / "photo.jpg"
    Image.new("RGB", (8, 8), "red").save(source)

    _convert(source, separate_dir=True, dry_run=True)

    assert not (tmp_path / "davo_im_convert").exists()
    assert not (tmp_path / "photo_converted.jpg").exists()


def test_command_convert_separate_dir_skips_existing_without_rewrite(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    source = tmp_path / "photo.jpg"
    Image.new("RGB", (8, 8), "red").save(source)
    output = tmp_path / "davo_im_convert" / "photo.jpg"
    output.parent.mkdir()
    output.write_bytes(b"existing")

    _convert(source, separate_dir=True)

    assert output.read_bytes() == b"existing"


def test_command_convert_separate_dir_rewrite_replaces_output(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    source = tmp_path / "photo.jpg"
    Image.new("RGB", (8, 8), "blue").save(source)
    output = tmp_path / "davo_im_convert" / "photo.jpg"
    output.parent.mkdir()
    output.write_bytes(b"existing")

    _convert(source, separate_dir=True, rewrite=True)

    assert output.read_bytes() == source.read_bytes()
    assert output.read_bytes() != b"existing"


def test_command_convert_separate_dir_skips_files_in_output_dir(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    output_dir = tmp_path / "davo_im_convert"
    output_dir.mkdir()
    inside = output_dir / "photo.jpg"
    Image.new("RGB", (8, 8), "red").save(inside)
    inside_data = inside.read_bytes()

    _convert(inside, separate_dir=True)
    _convert(output_dir, separate_dir=True, recursive=True)

    assert inside.read_bytes() == inside_data
    assert list(output_dir.iterdir()) == [inside]
