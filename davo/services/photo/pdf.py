import io
import logging
import os
import tempfile
import types
from typing import Any, Iterable, List, Optional, Sequence, Tuple

from davo.utils import format as format_utils

logger = logging.getLogger(__name__)


_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp"}
_EXTRACT_OUTPUT_TYPES = {"jpg", "png"}
_COMPRESS_DPI_PRESETS = {200, 300, 400}
_COMPRESS_JPEG_QUALITY = 75


def _import_fitz(action: str) -> types.ModuleType:
    try:
        import fitz  # noqa pylint: disable=C0415
    except ImportError:
        raise RuntimeError(f"PyMuPDF (fitz) is required for PDF {action}")

    return fitz


def _default_output(input_file: str, suffix: str) -> str:
    base, _ = os.path.splitext(input_file)
    return f"{base}{suffix}.pdf"


def _validate_source_pdf(action: str, input_file: str, verbose: bool) -> bool:
    if not os.path.exists(input_file):
        if verbose:
            logger.warning("pdf.%s: file not found: %s", action, input_file)
        return False

    if os.path.splitext(input_file)[1].lower() != ".pdf":
        if verbose:
            logger.warning("pdf.%s: not a pdf: %s", action, input_file)
        return False

    return True


def _open_pdf(fitz: Any, input_file: str, action: str):
    try:
        return fitz.open(input_file)
    except Exception:  # pragma: no cover - environment dependent
        logger.exception("pdf.%s: failed to open pdf: %s", action, input_file)
        raise


def _parse_rotation_angle(direction: Any) -> int:
    if isinstance(direction, int):
        return direction % 360

    value = str(direction).lower()
    if value in ("cw", "clockwise", "right"):
        return 90
    if value in ("ccw", "counterclockwise", "left"):
        return 270

    try:
        return int(value) % 360
    except Exception as exc:
        raise ValueError(f"unknown rotation direction: {direction!r}") from exc


def _normalize_rotation_pages(
    pages: Optional[Iterable[int]],
    page_count: int,
) -> Sequence[int]:
    if pages is None:
        return range(page_count)

    page_values = list(pages)
    if not page_values:
        return []

    if any(not isinstance(page, int) for page in page_values):
        raise TypeError("pages must be integers")

    non_negative = [page for page in page_values if page >= 0]
    one_based = not non_negative or 0 not in non_negative

    normalized: List[int] = []
    for page in page_values:
        if page < 0:
            idx = page
        elif one_based:
            idx = page - 1
        else:
            idx = page

        if not -page_count <= idx < page_count:
            raise IndexError(f"page index out of range: {page!r}")

        normalized.append(idx)

    seen = set()
    return [idx for idx in normalized if not (idx in seen or seen.add(idx))]


def _normalize_extract_pages(
    pages: Optional[Iterable[int]],
    page_count: int,
) -> Sequence[int]:
    if pages is None:
        return range(page_count)

    page_values = list(pages)
    if not page_values:
        return []

    normalized: List[int] = []
    seen = set()
    for page in page_values:
        if not isinstance(page, int):
            raise TypeError("pages must be integers (1-based)")
        if page < 1 or page > page_count:
            raise IndexError(f"page number out of range: {page!r}")

        idx = page - 1
        if idx not in seen:
            seen.add(idx)
            normalized.append(idx)

    return normalized


def _normalize_extract_type(output_type: Optional[str]) -> str:
    if output_type is None:
        return "jpg"

    normalized = str(output_type).lower().lstrip(".")
    if normalized == "jpeg":
        normalized = "jpg"

    if normalized not in _EXTRACT_OUTPUT_TYPES:
        raise ValueError(f"unsupported image type: {output_type!r}")

    return normalized


def _normalize_compress_dpi(dpi: Any) -> int:
    try:
        normalized = int(dpi)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"unsupported dpi preset: {dpi!r}") from exc

    if normalized not in _COMPRESS_DPI_PRESETS:
        raise ValueError(f"unsupported dpi preset: {dpi!r}")

    return normalized


def _normalize_compress_quality(quality: Any) -> int:
    if quality is None:
        return _COMPRESS_JPEG_QUALITY

    try:
        normalized = int(quality)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"unsupported jpeg quality: {quality!r}") from exc

    if not 0 <= normalized <= 100:
        raise ValueError(f"unsupported jpeg quality: {quality!r}")

    return normalized


def _log_compress_size_report(input_file: str, output_path: str) -> None:
    input_size = os.path.getsize(input_file)
    output_size = os.path.getsize(output_path)

    ratio = 0.0
    if input_size:
        ratio = output_size * 100.0 / float(input_size)

    logger.info(
        "pdf.compress: size %s -> %s (%.2f%%)",
        format_utils.humanize_bytes(input_size),
        format_utils.humanize_bytes(output_size),
        ratio,
    )


def _normalize_output_prefix(
    input_file: str,
    output_path: Optional[str],
) -> str:
    if output_path is None:
        return os.path.splitext(input_file)[0]

    prefix = output_path
    if not os.path.isabs(prefix):
        prefix = os.path.abspath(prefix)

    base, ext = os.path.splitext(prefix)
    if ext.lower() in (".jpg", ".jpeg", ".png"):
        return base
    return prefix


def _list_page_image_xrefs(page: Any) -> List[int]:
    if hasattr(page, "get_images"):
        images = page.get_images(full=True)
    elif hasattr(page, "getImageList"):
        images = page.getImageList(full=True)
    else:
        raise RuntimeError(
            "PyMuPDF page object does not support image listing API"
        )

    xrefs: List[int] = []
    seen = set()
    for image in images:
        if not image:
            continue

        xref = image[0]
        if xref in seen:
            continue

        seen.add(xref)
        xrefs.append(xref)

    return xrefs


def _extract_image_payload(doc: Any, xref: int) -> Tuple[bytes, str]:
    if hasattr(doc, "extract_image"):
        payload = doc.extract_image(xref)
    elif hasattr(doc, "extractImage"):
        payload = doc.extractImage(xref)
    else:
        raise RuntimeError(
            "PyMuPDF document does not support image extraction API"
        )

    image_bytes = payload.get("image")
    image_ext = payload.get("ext")
    if not image_bytes or not image_ext:
        raise RuntimeError(f"invalid extracted image payload for xref {xref}")

    normalized_ext = str(image_ext).lower().lstrip(".")
    if normalized_ext == "jpeg":
        normalized_ext = "jpg"

    return image_bytes, normalized_ext


def _render_page_payload(page: Any, fitz: Any) -> Tuple[bytes, str]:
    if hasattr(page, "get_pixmap"):
        try:
            pixmap = page.get_pixmap(dpi=300)
        except TypeError:
            zoom = 300 / 72
            pixmap = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
    elif hasattr(page, "getPixmap"):
        zoom = 300 / 72
        pixmap = page.getPixmap(matrix=fitz.Matrix(zoom, zoom))
    else:
        raise RuntimeError("PyMuPDF page object does not support pixmap API")

    if hasattr(pixmap, "tobytes"):
        return pixmap.tobytes("png"), "png"

    raise RuntimeError("PyMuPDF pixmap does not support bytes export API")


def _write_extracted_image(
    image_bytes: bytes,
    source_ext: str,
    target_path: str,
    output_type: str,
) -> None:
    if source_ext == output_type:
        with open(target_path, "wb") as f:
            f.write(image_bytes)
        return

    from PIL import Image  # noqa pylint: disable=C0415

    with Image.open(io.BytesIO(image_bytes)) as image:
        save_format = "PNG"
        if output_type == "jpg":
            save_format = "JPEG"
            if image.mode not in ("1", "L", "RGB", "CMYK"):
                image = image.convert("RGBA")
            if image.mode in ("RGBA", "LA"):
                background = Image.new("RGB", image.size, (255, 255, 255))
                alpha = image.getchannel("A")
                background.paste(image, mask=alpha)
                image = background
            elif image.mode not in ("L", "RGB", "CMYK"):
                image = image.convert("RGB")

        image.save(target_path, format=save_format)


def merge_files(
    input_files: Iterable[str],
    output_path: Optional[str],
    verbose: bool = False,
) -> bool:
    fitz = _import_fitz("merge")

    files = list(input_files)
    if not files:
        if verbose:
            logger.warning("pdf.merge: no input files provided")
        return False

    if output_path is None:
        output_path = os.path.join(os.path.dirname(files[0]), "merged.pdf")

    with fitz.open() as result_pdf:
        for file_path in files:
            if not os.path.exists(file_path):
                if verbose:
                    logger.warning("pdf.merge: file not found: %s", file_path)
                continue

            ext = os.path.splitext(file_path)[1].lower()
            if ext == ".pdf":
                with fitz.open(file_path) as doc:
                    result_pdf.insert_pdf(doc)
                continue

            if ext in _IMAGE_EXTENSIONS:
                with fitz.open(file_path) as img_doc:
                    pdf_bytes = img_doc.convert_to_pdf()
                with fitz.open("pdf", pdf_bytes) as img_pdf:
                    result_pdf.insert_pdf(img_pdf)
                continue

            if verbose:
                logger.warning("pdf.merge: file not supported: %s", file_path)

        if result_pdf.page_count == 0:
            return False

        result_pdf.save(output_path)
        return True


def rotate_pages(
    input_file: str,
    output_path: Optional[str],
    direction: Any = "clockwise",
    pages: Optional[Iterable[int]] = None,
    inplace: bool = False,
    verbose: bool = False,
) -> bool:
    fitz = _import_fitz("rotation")

    if not _validate_source_pdf("rotate", input_file, verbose):
        return False

    angle = _parse_rotation_angle(direction)

    replace_when_done = False
    if output_path is None:
        if inplace:
            fd, output_path = tempfile.mkstemp(suffix=".pdf")
            os.close(fd)
            replace_when_done = True
        else:
            output_path = _default_output(input_file, "_rotated")

    with _open_pdf(fitz, input_file, "rotate") as doc:
        page_indices = _normalize_rotation_pages(pages, doc.page_count)

        for idx in page_indices:
            page = doc.load_page(idx)
            if hasattr(page, "set_rotation"):
                page.set_rotation(angle)
            elif hasattr(page, "setRotation"):
                page.setRotation(angle)
            else:
                raise RuntimeError(
                    "PyMuPDF page object does not support rotation API"
                )

        doc.save(output_path)

    if replace_when_done:
        os.replace(output_path, input_file)

    return True


def extract_images(
    input_file: str,
    output_path: Optional[str],
    pages: Optional[Iterable[int]] = None,
    output_type: Optional[str] = None,
    whole_page: bool = False,
    verbose: bool = False,
) -> bool:
    normalized_type = _normalize_extract_type(output_type)
    fitz = _import_fitz("image extraction")

    if not _validate_source_pdf("extract", input_file, verbose):
        return False

    output_prefix = _normalize_output_prefix(input_file, output_path)

    try:
        with _open_pdf(fitz, input_file, "extract") as doc:
            page_indices = _normalize_extract_pages(pages, doc.page_count)
            payloads: List[Tuple[str, Any]] = []
            if whole_page:
                payloads = [("page", page_idx) for page_idx in page_indices]
            else:
                for page_idx in page_indices:
                    page = doc.load_page(page_idx)
                    for xref in _list_page_image_xrefs(page):
                        payloads.append(("image", xref))

            if not payloads:
                if verbose:
                    logger.warning("pdf.extract: no output images found")
                return False

            targets = [
                f"{output_prefix}_{i:03d}.{normalized_type}"
                for i in range(1, len(payloads) + 1)
            ]
            collisions = [path for path in targets if os.path.exists(path)]
            if collisions:
                if verbose:
                    logger.warning(
                        "pdf.extract: target files exist, aborting: %s",
                        collisions,
                    )
                return False

            created: List[str] = []
            try:
                for (payload_type, payload_value), target in zip(
                    payloads, targets
                ):
                    if payload_type == "page":
                        page = doc.load_page(payload_value)
                        image_bytes, source_ext = _render_page_payload(
                            page, fitz
                        )
                    else:
                        image_bytes, source_ext = _extract_image_payload(
                            doc, payload_value
                        )
                    _write_extracted_image(
                        image_bytes,
                        source_ext,
                        target,
                        normalized_type,
                    )
                    created.append(target)
            except (OSError, RuntimeError, ValueError):
                for path in created:
                    try:
                        if os.path.exists(path):
                            os.remove(path)
                    except OSError:
                        pass
                raise
    except (OSError, RuntimeError, ValueError) as exc:
        logger.error("pdf.extract: failed to extract images %s", str(exc))
        return False

    return True


def delete_pages(
    input_file: str,
    output_path: Optional[str],
    pages: Optional[Iterable[int]] = None,
    verbose: bool = False,
) -> bool:
    fitz = _import_fitz("page deletion")

    if not _validate_source_pdf("delete", input_file, verbose):
        return False

    if not pages:
        if verbose:
            logger.warning("pdf.delete: no pages provided")
        return False

    with _open_pdf(fitz, input_file, "delete") as doc:
        page_count = doc.page_count
        indices = []
        for page in pages:
            if not isinstance(page, int):
                raise TypeError("pages must be integers (1-based)")
            if page < 1 or page > page_count:
                raise IndexError(f"page number out of range: {page!r}")
            indices.append(page - 1)

        for idx in sorted(set(indices), reverse=True):
            doc.delete_page(idx)

        if output_path is None:
            output_path = _default_output(input_file, "_deleted")

        doc.save(output_path)

    return True


def _build_split_ranges(
    starts: List[int],
    page_count: int,
) -> List[Tuple[int, int]]:
    ranges: List[Tuple[int, int]] = []
    for i, start in enumerate(starts):
        start_idx = start - 1
        end_idx = page_count - 1
        if i + 1 < len(starts):
            end_idx = starts[i + 1] - 2
        if start_idx <= end_idx:
            ranges.append((start_idx, end_idx))
    return ranges


def split_pages(
    input_file: str,
    output_path: Optional[str],
    pages: Optional[Iterable[int]] = None,
    verbose: bool = False,
) -> bool:
    fitz = _import_fitz("splitting")

    if not _validate_source_pdf("split", input_file, verbose):
        return False

    if not pages:
        if verbose:
            logger.warning("pdf.split: no pages provided")
        return False

    try:
        starts = sorted(set(int(page) for page in pages))
    except Exception as exc:
        raise TypeError(
            "pages must be iterable of integers (1-based)"
        ) from exc

    if starts[0] != 1:
        raise ValueError("pages must include 1 as the first block start")

    with _open_pdf(fitz, input_file, "split") as src:
        page_count = src.page_count
        for page in starts:
            if page < 1 or page > page_count:
                raise IndexError(f"page number out of range: {page!r}")

        ranges = _build_split_ranges(starts, page_count)
        if not ranges:
            if verbose:
                logger.warning("pdf.split: no valid ranges computed")
            return False

        if output_path:
            base, ext = os.path.splitext(output_path)
        else:
            base, ext = os.path.splitext(input_file)

        if not ext:
            ext = ".pdf"

        targets = [f"{base}_{i + 1}{ext}" for i in range(len(ranges))]
        collisions = [path for path in targets if os.path.exists(path)]
        if collisions:
            if verbose:
                logger.warning(
                    "pdf.split: target files exist, aborting: %s",
                    collisions,
                )
            return False

        created: List[str] = []
        try:
            for (start_idx, end_idx), target in zip(ranges, targets):
                with fitz.open() as new_doc:
                    new_doc.insert_pdf(
                        src,
                        from_page=start_idx,
                        to_page=end_idx,
                    )
                    new_doc.save(target)
                created.append(target)
        except (OSError, RuntimeError, ValueError):
            for path in created:
                try:
                    if os.path.exists(path):
                        os.remove(path)
                except OSError:
                    pass
            raise

    return True


def clean_file(
    input_file: str,
    output_path: Optional[str],
    verbose: bool = False,
) -> bool:
    fitz = _import_fitz("cleanup")

    if not _validate_source_pdf("clean", input_file, verbose):
        return False

    if output_path is None:
        output_path = _default_output(input_file, "_cleaned")

    try:
        with _open_pdf(fitz, input_file, "clean") as doc:
            doc.save(output_path, garbage=3, deflate=True, clean=True)
    except (OSError, RuntimeError, ValueError) as exc:
        logger.error("pdf.clean: failed to process pdf %s", str(exc))
        return False

    return True


def compress_file(
    input_file: str,
    output_path: Optional[str],
    dpi: Any,
    quality: Any = None,
    grayscale: bool = False,
    verbose: bool = False,
) -> bool:
    fitz = _import_fitz("compression")

    if not _validate_source_pdf("compress", input_file, verbose):
        return False

    normalized_dpi = _normalize_compress_dpi(dpi)
    normalized_quality = _normalize_compress_quality(quality)

    if output_path is None:
        output_path = _default_output(
            input_file, f"_compressed_{normalized_dpi}dpi"
        )

    try:
        with _open_pdf(fitz, input_file, "compress") as doc:
            if not hasattr(doc, "rewrite_images"):
                raise RuntimeError(
                    "PyMuPDF document does not support image rewrite API"
                )

            doc.rewrite_images(
                dpi_threshold=normalized_dpi + 1,
                dpi_target=normalized_dpi,
                quality=normalized_quality,
                lossy=True,
                lossless=True,
                bitonal=True,
                color=True,
                gray=True,
                set_to_gray=grayscale,
            )
            doc.save(output_path, garbage=3, deflate=True, clean=True)
            _log_compress_size_report(input_file, output_path)
    except (OSError, RuntimeError, ValueError) as exc:
        logger.error("pdf.compress: failed to process pdf %s", str(exc))
        return False

    return True
