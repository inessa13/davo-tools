import io
import logging
import os
import tempfile
import types
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from davo.utils import format as format_utils

logger = logging.getLogger(__name__)


_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp"}
_EXTRACT_OUTPUT_TYPES = {"jpg", "png"}
_COMPRESS_DPI_PRESETS = {72, 96, 150, 200, 300, 400}
_COMPRESS_JPEG_QUALITY = 80
_ISO_PAGE_FORMATS_MM = {
    "a3": (297.0, 420.0),
    "a4": (210.0, 297.0),
    "a5": (148.0, 210.0),
    "a6": (105.0, 148.0),
}
_PAPER_FORMATS = {
    "a4": (210.0 * 72.0 / 25.4, 297.0 * 72.0 / 25.4),
    "a5": (148.0 * 72.0 / 25.4, 210.0 * 72.0 / 25.4),
    "a6": (105.0 * 72.0 / 25.4, 148.0 * 72.0 / 25.4),
}


def _import_fitz(action: str) -> types.ModuleType:
    try:
        import fitz  # noqa pylint: disable=C0415
    except ImportError:
        raise RuntimeError(f"PyMuPDF (fitz) is required for PDF {action}")

    return fitz


def _default_output(input_file: str, suffix: str) -> str:
    base, _ = os.path.splitext(input_file)
    return f"{base}{suffix}.pdf"


def _paths_refer_to_same_file(path_a: str, path_b: str) -> bool:
    normalized_a = os.path.normcase(os.path.realpath(os.path.abspath(path_a)))
    normalized_b = os.path.normcase(os.path.realpath(os.path.abspath(path_b)))
    if normalized_a == normalized_b:
        return True

    try:
        return os.path.samefile(path_a, path_b)
    except OSError:
        return False


def _allow_output_targets(
    action: str,
    input_files: Iterable[str],
    output_files: Iterable[str],
    rewrite: bool = False,
) -> bool:
    inputs = list(input_files)
    outputs = list(output_files)
    for output_file in outputs:
        if any(
            _paths_refer_to_same_file(input_file, output_file)
            for input_file in inputs
        ):
            logger.error(
                "pdf.%s: refusing to overwrite input file: %s",
                action,
                output_file,
            )
            return False

    existing = [
        output_file for output_file in outputs if os.path.exists(output_file)
    ]
    if existing and not rewrite:
        logger.error(
            "pdf.%s: output files already exist: %s; "
            "use -W/--rewrite to overwrite",
            action,
            existing,
        )
        return False

    for output_file in existing:
        if rewrite:
            logger.warning(
                "pdf.%s: overwriting existing output file: %s",
                action,
                output_file,
            )
    return True


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


def _render_page_payload(
    page: Any,
    fitz: Any,
    dpi: int = 300,
) -> Tuple[bytes, str]:
    if hasattr(page, "get_pixmap"):
        try:
            pixmap = page.get_pixmap(dpi=dpi)
        except TypeError:
            zoom = dpi / 72
            pixmap = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
    elif hasattr(page, "getPixmap"):
        zoom = dpi / 72
        pixmap = page.getPixmap(matrix=fitz.Matrix(zoom, zoom))
    else:
        raise RuntimeError("PyMuPDF page object does not support pixmap API")

    if hasattr(pixmap, "tobytes"):
        return pixmap.tobytes("png"), "png"

    raise RuntimeError("PyMuPDF pixmap does not support bytes export API")


def _get_page_text(page: Any) -> str:
    if hasattr(page, "get_text"):
        return page.get_text("text")
    if hasattr(page, "getText"):
        return page.getText("text")
    raise RuntimeError("PyMuPDF page object does not support text API")


def _get_page_drawings(page: Any) -> List[Any]:
    if hasattr(page, "get_drawings"):
        return list(page.get_drawings())
    if hasattr(page, "getDrawings"):
        return list(page.getDrawings())
    raise RuntimeError("PyMuPDF page object does not support drawings API")


def _get_page_rect(page: Any) -> Any:
    rect = getattr(page, "rect", None)
    if rect is not None:
        return rect
    if hasattr(page, "bound"):
        return page.bound()
    raise RuntimeError("PyMuPDF page object does not expose page bounds")


def _rect_dimensions(rect: Any) -> Tuple[float, float]:
    width = getattr(rect, "width", None)
    height = getattr(rect, "height", None)
    if width is not None and height is not None:
        return float(width), float(height)

    if isinstance(rect, (list, tuple)) and len(rect) >= 4:
        return float(rect[2] - rect[0]), float(rect[3] - rect[1])

    raise RuntimeError(f"unsupported rect representation: {rect!r}")


def _rect_area(rect: Any) -> float:
    width, height = _rect_dimensions(rect)
    return max(width, 0.0) * max(height, 0.0)


def _get_page_image_rects(page: Any, xref: int) -> List[Any]:
    if hasattr(page, "get_image_rects"):
        rects = page.get_image_rects(xref)
    elif hasattr(page, "getImageRects"):
        rects = page.getImageRects(xref)
    else:
        raise RuntimeError(
            "PyMuPDF page object does not support image rect listing API"
        )
    return list(rects or [])


def _extract_image_dimensions(doc: Any, xref: int) -> Tuple[int, int]:
    if hasattr(doc, "extract_image"):
        payload = doc.extract_image(xref)
    elif hasattr(doc, "extractImage"):
        payload = doc.extractImage(xref)
    else:
        raise RuntimeError(
            "PyMuPDF document does not support image extraction API"
        )

    width = payload.get("width")
    height = payload.get("height")
    if width and height:
        return int(width), int(height)

    image_bytes = payload.get("image")
    if not image_bytes:
        raise RuntimeError(f"invalid extracted image payload for xref {xref}")

    from PIL import Image  # noqa pylint: disable=C0415

    with Image.open(io.BytesIO(image_bytes)) as image:
        return int(image.width), int(image.height)


def _inspect_page_raster_placements(
    doc: Any,
    page: Any,
) -> List[Dict[str, Any]]:
    placements: List[Dict[str, Any]] = []
    for xref in _list_page_image_xrefs(page):
        width_px, height_px = _extract_image_dimensions(doc, xref)
        for rect in _get_page_image_rects(page, xref):
            width_pt, height_pt = _rect_dimensions(rect)
            if width_pt <= 0 or height_pt <= 0:
                continue

            width_in = width_pt / 72.0
            height_in = height_pt / 72.0
            if width_in <= 0 or height_in <= 0:
                continue

            placements.append(
                {
                    "xref": xref,
                    "width_px": width_px,
                    "height_px": height_px,
                    "width_pt": width_pt,
                    "height_pt": height_pt,
                    "area_pt": width_pt * height_pt,
                    "x_dpi": width_px / width_in,
                    "y_dpi": height_px / height_in,
                }
            )
    return placements


def _classify_page_type(
    has_text: bool,
    has_vector: bool,
    raster_placements: Sequence[Dict[str, Any]],
    page_area: float,
    raster_coverage_threshold: float,
) -> str:
    raster_count = len(raster_placements)
    if not has_text and not has_vector and raster_count == 0:
        return "empty"
    if has_text and not has_vector and raster_count == 0:
        return "text"
    if has_vector and not has_text and raster_count == 0:
        return "vector"
    if not has_text and not has_vector and raster_count > 1:
        return "multi-raster"
    if not has_text and not has_vector and raster_count == 1:
        dominant_area = raster_placements[0]["area_pt"]
        coverage = 0.0
        if page_area > 0:
            coverage = dominant_area / page_area
        if coverage >= raster_coverage_threshold:
            return "raster"
    return "mixed"


def _format_page_size(rect: Any, pt: bool = False) -> str:
    """Format a page size, preferring a recognized ISO A paper name."""
    width_pt, height_pt = _rect_dimensions(rect)
    width_mm = width_pt * 25.4 / 72.0
    height_mm = height_pt * 25.4 / 72.0

    for paper_format, (paper_width_mm, paper_height_mm) in (
        _ISO_PAGE_FORMATS_MM.items()
    ):
        if (
            abs(width_mm - paper_width_mm) <= 1
            and abs(height_mm - paper_height_mm) <= 1
        ) or (
            abs(width_mm - paper_height_mm) <= 1
            and abs(height_mm - paper_width_mm) <= 1
        ):
            return paper_format

    if pt:
        return f"{int(round(width_pt))}x{int(round(height_pt))} pt"
    return f"{int(round(width_mm))}x{int(round(height_mm))} mm"


def inspect_pages(
    input_file: str,
    pages: Optional[Iterable[int]] = None,
    verbose: bool = False,
    raster_coverage_threshold: float = 0.9,
    pt: bool = False,
) -> Optional[List[Dict[str, Any]]]:
    fitz = _import_fitz("page inspection")

    if not _validate_source_pdf("info", input_file, verbose):
        return None

    try:
        with _open_pdf(fitz, input_file, "info") as doc:
            page_indices = _normalize_extract_pages(pages, doc.page_count)
            rows: List[Dict[str, Any]] = []
            for page_idx in page_indices:
                page = doc.load_page(page_idx)
                page_rect = _get_page_rect(page)
                page_area = _rect_area(page_rect)
                has_text = bool(_get_page_text(page).strip())
                has_vector = bool(_get_page_drawings(page))
                raster_placements = _inspect_page_raster_placements(doc, page)
                dominant = None
                if raster_placements:
                    dominant = max(
                        raster_placements,
                        key=lambda item: item["area_pt"],
                    )

                page_type = _classify_page_type(
                    has_text,
                    has_vector,
                    raster_placements,
                    page_area,
                    raster_coverage_threshold,
                )
                x_resolution = None
                y_resolution = None
                resolution = "-"
                image_size_px = "-"
                if dominant is not None:
                    x_resolution = int(round(dominant["x_dpi"]))
                    y_resolution = int(round(dominant["y_dpi"]))
                    if x_resolution == y_resolution:
                        resolution = f"{x_resolution} dpi"
                    else:
                        resolution = f"{x_resolution}x{y_resolution} dpi"
                    image_size_px = (
                        f'{dominant["width_px"]}x{dominant["height_px"]} px'
                    )

                width_pt, height_pt = _rect_dimensions(page_rect)
                if abs(width_pt - height_pt) < 0.01:
                    orientation = "square"
                elif width_pt > height_pt:
                    orientation = "landscape"
                else:
                    orientation = "portrait"

                rows.append(
                    {
                        "page": page_idx + 1,
                        "type": page_type,
                        "resolution": resolution,
                        "image_size_px": image_size_px,
                        "orientation": orientation,
                        "page_size": _format_page_size(page_rect, pt=pt),
                    }
                )
    except (OSError, RuntimeError, ValueError) as exc:
        logger.error("pdf.info: failed to inspect pdf %s", str(exc))
        return None

    return rows


def format_page_info_report(
    rows: Sequence[Dict[str, Any]], table: bool = False
) -> str:
    headers = [
        "Page",
        "Type",
        "Resolution",
        "ImageSizePx",
        "Orientation",
        "PageSize",
    ]
    table_rows = [
        [
            str(row["page"]),
            row["type"],
            row["resolution"],
            row["image_size_px"],
            row["orientation"],
            row["page_size"],
        ]
        for row in rows
    ]

    widths = [len(header) for header in headers]
    for row in table_rows:
        for idx, value in enumerate(row):
            widths[idx] = max(widths[idx], len(value))

    if table:
        border = "+{}+".format(
            "+".join("-" * (width + 2) for width in widths)
        )

        def format_row(row: Sequence[str]) -> str:
            return "| {} |".format(
                " | ".join(
                    value.rjust(widths[index]) if index == 0
                    else value.ljust(widths[index])
                    for index, value in enumerate(row)
                )
            )

        return "\n".join(
            (border, format_row(headers), border,
             *(format_row(row) for row in table_rows), border)
        )

    rendered_rows = [
        "  ".join(
            header.ljust(widths[idx]) for idx, header in enumerate(headers)
        )
    ]
    for row in table_rows:
        rendered_rows.append(
            "  ".join(
                value.ljust(widths[idx]) for idx, value in enumerate(row)
            )
        )
    return "\n".join(rendered_rows)


def _normalize_scale_format(paper_format: Optional[str]) -> str:
    normalized = str(paper_format or "a4").lower()
    if normalized not in _PAPER_FORMATS:
        raise ValueError(f"unsupported paper format: {paper_format!r}")
    return normalized


def _resolve_target_page_size(
    paper_format: str,
    source_rect: Any,
) -> Tuple[float, float]:
    width_pt, height_pt = _PAPER_FORMATS[paper_format]
    source_width, source_height = _rect_dimensions(source_rect)
    if source_width > source_height:
        return height_pt, width_pt
    return width_pt, height_pt


def _build_rect(
    fitz: Any,
    x0: float,
    y0: float,
    x1: float,
    y1: float,
) -> Any:
    if hasattr(fitz, "Rect"):
        return fitz.Rect(x0, y0, x1, y1)
    return (x0, y0, x1, y1)


def _fit_rect_within(
    fitz: Any,
    source_rect: Any,
    target_width: float,
    target_height: float,
) -> Any:
    source_width, source_height = _rect_dimensions(source_rect)
    if source_width <= 0 or source_height <= 0:
        raise RuntimeError("source page has invalid bounds")

    scale = min(target_width / source_width, target_height / source_height)
    fitted_width = source_width * scale
    fitted_height = source_height * scale
    x0 = (target_width - fitted_width) / 2.0
    y0 = (target_height - fitted_height) / 2.0
    return _build_rect(
        fitz,
        x0,
        y0,
        x0 + fitted_width,
        y0 + fitted_height,
    )


def _fit_dimensions_within(
    fitz: Any,
    source_width: float,
    source_height: float,
    target_width: float,
    target_height: float,
    allow_upscale: bool = False,
) -> Any:
    """Return a centered rectangle preserving the source aspect ratio."""
    if source_width <= 0 or source_height <= 0:
        raise RuntimeError("source has invalid bounds")

    scale = min(target_width / source_width, target_height / source_height)
    if not allow_upscale:
        scale = min(scale, 1.0)
    fitted_width = source_width * scale
    fitted_height = source_height * scale
    x0 = (target_width - fitted_width) / 2.0
    y0 = (target_height - fitted_height) / 2.0
    return _build_rect(
        fitz, x0, y0, x0 + fitted_width, y0 + fitted_height
    )


def _resolve_form_page_size(
    page_size: Tuple[float, float],
    source_width: float,
    source_height: float,
) -> Tuple[float, float]:
    width, height = page_size
    if source_width > source_height:
        return height, width
    return width, height


def _image_source_dimensions(
    input_file: str,
) -> Tuple[int, int, Optional[Tuple[float, float]]]:
    """Return image pixels and its physical DPI when it is trustworthy."""
    from PIL import Image  # noqa pylint: disable=C0415

    with Image.open(input_file) as image:
        width, height = image.size
        dpi = image.info.get("dpi")
        if not dpi or len(dpi) < 2:
            return width, height, None
        x_dpi, y_dpi = dpi[:2]
        if x_dpi <= 0 or y_dpi <= 0:
            return width, height, None
        return width, height, (float(x_dpi), float(y_dpi))


def _validate_form_sources(
    fitz: Any,
    input_files: Sequence[str],
    verbose: bool,
) -> bool:
    """Check every source before a result document can be created."""
    from PIL import Image  # noqa pylint: disable=C0415

    for input_file in input_files:
        if not os.path.exists(input_file):
            if verbose:
                logger.warning("pdf.form: file not found: %s", input_file)
            return False

        ext = os.path.splitext(input_file)[1].lower()
        if ext == ".pdf":
            try:
                with _open_pdf(fitz, input_file, "form"):
                    pass
            except (OSError, RuntimeError, ValueError):
                logger.error("pdf.form: failed to open pdf: %s", input_file)
                return False
        elif ext in _IMAGE_EXTENSIONS:
            try:
                with Image.open(input_file) as image:
                    image.verify()
            except (OSError, ValueError):
                logger.error("pdf.form: invalid image: %s", input_file)
                return False
        else:
            if verbose:
                logger.warning("pdf.form: file not supported: %s", input_file)
            return False
    return True


def _document_has_images_over_dpi(doc: Any, dpi: int) -> bool:
    for page_idx in range(doc.page_count):
        page = doc.load_page(page_idx)
        for placement in _inspect_page_raster_placements(doc, page):
            if max(placement["x_dpi"], placement["y_dpi"]) > dpi:
                return True
    return False


def form_files(
    input_files: Iterable[str],
    output_path: Optional[str],
    page_size: Optional[Tuple[float, float]] = None,
    paper_format: Optional[str] = None,
    dpi: Any = 300,
    verbose: bool = False,
    rewrite: bool = False,
) -> bool:
    """Place PDF pages and images on consistently sized, oriented sheets."""
    files = list(input_files)
    if not files:
        if verbose:
            logger.warning("pdf.form: no input files provided")
        return False

    try:
        normalized_dpi = int(dpi)
        if not 72 <= normalized_dpi <= 800:
            raise ValueError("dpi must be between 72 and 800")
        if page_size is None:
            normalized_format = _normalize_scale_format(paper_format)
            page_size = _PAPER_FORMATS[normalized_format]
        base_width, base_height = page_size
        if base_width <= 0 or base_height <= 0:
            raise ValueError("page size must be positive")
    except (TypeError, ValueError) as exc:
        logger.error("pdf.form: invalid option: %s", exc)
        return False

    if output_path is None:
        output_path = _default_output(files[0], "_formed")
    if not _allow_output_targets(
        "form", files, [output_path], rewrite=rewrite
    ):
        return False

    fitz = _import_fitz("form creation")
    if not _validate_form_sources(fitz, files, verbose):
        return False

    try:
        with fitz.open() as out_doc:
            for input_file in files:
                ext = os.path.splitext(input_file)[1].lower()
                if ext == ".pdf":
                    with _open_pdf(fitz, input_file, "form") as src:
                        for page_idx in range(src.page_count):
                            source_page = src.load_page(page_idx)
                            source_rect = _get_page_rect(source_page)
                            source_width, source_height = _rect_dimensions(
                                source_rect
                            )
                            target_size = _resolve_form_page_size(
                                (base_width, base_height),
                                source_width,
                                source_height,
                            )
                            target_width, target_height = target_size
                            dest_page = out_doc.new_page(
                                width=target_width, height=target_height
                            )
                            dest_rect = _fit_dimensions_within(
                                fitz,
                                source_width,
                                source_height,
                                target_width,
                                target_height,
                            )
                            if hasattr(dest_page, "show_pdf_page"):
                                dest_page.show_pdf_page(
                                    dest_rect, src, page_idx,
                                    keep_proportion=True,
                                )
                            elif hasattr(dest_page, "showPDFpage"):
                                dest_page.showPDFpage(dest_rect, src, page_idx)
                            else:
                                raise RuntimeError(
                                    "PyMuPDF page object does not support "
                                    "page placement API"
                                )
                    continue

                width_px, height_px, image_dpi = _image_source_dimensions(
                    input_file
                )
                target_width, target_height = _resolve_form_page_size(
                    (base_width, base_height), width_px, height_px
                )
                if image_dpi is None:
                    # Pixels have no physical size in this case, so fitting is
                    # the useful default rather than treating them as 72 DPI.
                    source_width, source_height = width_px, height_px
                    allow_upscale = True
                else:
                    x_dpi, y_dpi = image_dpi
                    source_width = width_px * 72.0 / x_dpi
                    source_height = height_px * 72.0 / y_dpi
                    allow_upscale = False
                dest_page = out_doc.new_page(
                    width=target_width, height=target_height
                )
                dest_rect = _fit_dimensions_within(
                    fitz, source_width, source_height,
                    target_width, target_height, allow_upscale=allow_upscale,
                )
                if hasattr(dest_page, "insert_image"):
                    dest_page.insert_image(
                        dest_rect, filename=input_file, keep_proportion=False
                    )
                elif hasattr(dest_page, "insertImage"):
                    dest_page.insertImage(dest_rect, filename=input_file)
                else:
                    raise RuntimeError(
                        "PyMuPDF page object does not support image "
                        "insertion API"
                    )

            if _document_has_images_over_dpi(out_doc, normalized_dpi):
                if not hasattr(out_doc, "rewrite_images"):
                    raise RuntimeError(
                        "PyMuPDF document does not support image rewrite API"
                    )
                out_doc.rewrite_images(
                    dpi_threshold=normalized_dpi + 1,
                    dpi_target=normalized_dpi,
                    quality=_COMPRESS_JPEG_QUALITY,
                    lossy=True,
                    lossless=True,
                    bitonal=True,
                    color=True,
                    gray=True,
                    set_to_gray=False,
                )
            out_doc.save(output_path, garbage=3, deflate=True, clean=True)
    except (OSError, RuntimeError, ValueError) as exc:
        logger.error("pdf.form: failed to form pdf %s", str(exc))
        return False

    return True


def _render_page_jpeg_bytes(
    page: Any,
    fitz: Any,
    dpi: int,
    quality: int,
    grayscale: bool = False,
) -> bytes:
    image_bytes, _ = _render_page_payload(page, fitz, dpi=dpi)

    from PIL import Image  # noqa pylint: disable=C0415

    with Image.open(io.BytesIO(image_bytes)) as image:
        if grayscale:
            image = image.convert("L")
        else:
            if image.mode not in ("1", "L", "RGB", "CMYK"):
                image = image.convert("RGBA")
            if image.mode in ("RGBA", "LA"):
                background = Image.new("RGB", image.size, (255, 255, 255))
                alpha = image.getchannel("A")
                background.paste(image, mask=alpha)
                image = background
            elif image.mode not in ("L", "RGB", "CMYK"):
                image = image.convert("RGB")

        output = io.BytesIO()
        image.save(output, format="JPEG", quality=quality)
        return output.getvalue()


def _rebuild_pdf_pages(
    src: Any,
    fitz: Any,
    output_path: str,
    dpi: int,
    quality: int,
    grayscale: bool = False,
) -> None:
    with fitz.open() as out_doc:
        for page_idx in range(src.page_count):
            page = src.load_page(page_idx)
            page_rect = _get_page_rect(page)
            width_pt, height_pt = _rect_dimensions(page_rect)
            image_bytes = _render_page_jpeg_bytes(
                page,
                fitz,
                dpi=dpi,
                quality=quality,
                grayscale=grayscale,
            )
            out_page = out_doc.new_page(width=width_pt, height=height_pt)
            target_rect = _build_rect(fitz, 0.0, 0.0, width_pt, height_pt)
            if hasattr(out_page, "insert_image"):
                out_page.insert_image(
                    target_rect,
                    stream=image_bytes,
                    keep_proportion=False,
                )
            elif hasattr(out_page, "insertImage"):
                out_page.insertImage(target_rect, stream=image_bytes)
            else:
                raise RuntimeError(
                    "PyMuPDF page object does not support image insertion API"
                )

        out_doc.save(output_path, garbage=3, deflate=True, clean=True)


def scale_file(
    input_file: str,
    output_path: Optional[str],
    pages: Optional[Iterable[int]] = None,
    paper_format: Optional[str] = None,
    verbose: bool = False,
    rewrite: bool = False,
) -> bool:
    fitz = _import_fitz("scaling")

    if not _validate_source_pdf("scale", input_file, verbose):
        return False

    normalized_format = _normalize_scale_format(paper_format)
    if output_path is None:
        output_path = _default_output(
            input_file,
            f"_scaled_{normalized_format}",
        )
    if not _allow_output_targets(
        "scale", [input_file], [output_path], rewrite=rewrite
    ):
        return False

    try:
        with _open_pdf(fitz, input_file, "scale") as src:
            page_indices = _normalize_extract_pages(pages, src.page_count)
            if not page_indices:
                if verbose:
                    logger.warning("pdf.scale: no pages selected")
                return False

            with fitz.open() as out_doc:
                for page_idx in page_indices:
                    page = src.load_page(page_idx)
                    page_rect = _get_page_rect(page)
                    target_width, target_height = _resolve_target_page_size(
                        normalized_format,
                        page_rect,
                    )
                    dest_page = out_doc.new_page(
                        width=target_width,
                        height=target_height,
                    )
                    dest_rect = _fit_rect_within(
                        fitz,
                        page_rect,
                        target_width,
                        target_height,
                    )
                    if hasattr(dest_page, "show_pdf_page"):
                        dest_page.show_pdf_page(
                            dest_rect,
                            src,
                            page_idx,
                            keep_proportion=True,
                        )
                    elif hasattr(dest_page, "showPDFpage"):
                        dest_page.showPDFpage(dest_rect, src, page_idx)
                    else:
                        raise RuntimeError(
                            "PyMuPDF page object does not support page "
                            "placement API"
                        )

                out_doc.save(output_path, garbage=3, deflate=True, clean=True)
    except (OSError, RuntimeError, ValueError) as exc:
        logger.error("pdf.scale: failed to scale pdf %s", str(exc))
        return False

    return True


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
    rewrite: bool = False,
) -> bool:
    fitz = _import_fitz("merge")

    files = list(input_files)
    if not files:
        if verbose:
            logger.warning("pdf.merge: no input files provided")
        return False

    if output_path is None:
        output_path = os.path.join(os.path.dirname(files[0]), "merged.pdf")
    if not _allow_output_targets(
        "merge", files, [output_path], rewrite=rewrite
    ):
        return False

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
    rewrite: bool = False,
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
    if not replace_when_done and not _allow_output_targets(
        "rotate", [input_file], [output_path], rewrite=rewrite
    ):
        return False

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
    rewrite: bool = False,
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
            if not _allow_output_targets(
                "extract", [input_file], targets, rewrite=rewrite
            ):
                return False

            preexisting = {
                path for path in targets if os.path.exists(path)
            }
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
                        if path not in preexisting and os.path.exists(path):
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
    rewrite: bool = False,
) -> bool:
    fitz = _import_fitz("page deletion")

    if not _validate_source_pdf("delete", input_file, verbose):
        return False

    if not pages:
        if verbose:
            logger.warning("pdf.delete: no pages provided")
        return False

    if output_path is None:
        output_path = _default_output(input_file, "_deleted")
    if not _allow_output_targets(
        "delete", [input_file], [output_path], rewrite=rewrite
    ):
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
    rewrite: bool = False,
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
        if not _allow_output_targets(
            "split", [input_file], targets, rewrite=rewrite
        ):
            return False

        preexisting = {path for path in targets if os.path.exists(path)}
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
                    if path not in preexisting and os.path.exists(path):
                        os.remove(path)
                except OSError:
                    pass
            raise

    return True


def clean_file(
    input_file: str,
    output_path: Optional[str],
    verbose: bool = False,
    rewrite: bool = False,
) -> bool:
    fitz = _import_fitz("cleanup")

    if not _validate_source_pdf("clean", input_file, verbose):
        return False

    if output_path is None:
        output_path = _default_output(input_file, "_cleaned")
    if not _allow_output_targets(
        "clean", [input_file], [output_path], rewrite=rewrite
    ):
        return False

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
    rebuild: bool = False,
    verbose: bool = False,
    rewrite: bool = False,
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
    if not _allow_output_targets(
        "compress", [input_file], [output_path], rewrite=rewrite
    ):
        return False

    try:
        with _open_pdf(fitz, input_file, "compress") as doc:
            if rebuild:
                _rebuild_pdf_pages(
                    doc,
                    fitz,
                    output_path,
                    dpi=normalized_dpi,
                    quality=normalized_quality,
                    grayscale=grayscale,
                )
            else:
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
