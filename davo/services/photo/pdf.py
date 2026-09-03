import io
import logging
import math
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import textwrap
import time
import types
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from davo.services.photo import image_info
from davo.utils import format as format_utils

logger = logging.getLogger(__name__)


_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp"}
_TEXT_EXTENSIONS = {".txt"}
_HTML_EXTENSIONS = {".html", ".htm"}
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
_TEXT_FONT_SIZE = 10.0
_TEXT_LINE_HEIGHT = 12.0
_TEXT_MARGIN = 72.0 / 2.54
_CROP_VALUE_RE = re.compile(
    r"^([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)(%|px)?$"
)
_HTML_RENDER_TIMEOUT_SECONDS = 10
_HTML_RENDER_TERMINATION_GRACE_SECONDS = 1
_HTML_BROWSER_CAPTURE_TIMEOUT_MILLISECONDS = 5000
_HTML_BROWSER_LOG_TAIL_BYTES = 8192
_HTML_RENDER_POLL_SECONDS = 0.1
_HTML_BROWSER_COMMANDS = (
    "google-chrome",
    "google-chrome-stable",
    "chromium",
    "chromium-browser",
    "chrome",
)
_HTML_BROWSER_MACOS_PATHS = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
)


class HtmlRenderError(RuntimeError):
    """HTML could not be printed to a usable browser PDF."""


def _find_html_browser() -> Optional[str]:
    """Return a system Chrome/Chromium executable, if one is available."""
    for command in _HTML_BROWSER_COMMANDS:
        executable = shutil.which(command)
        if executable:
            return executable
    for executable in _HTML_BROWSER_MACOS_PATHS:
        if os.path.isfile(executable) and os.access(executable, os.X_OK):
            return executable
    return None


def _stop_html_browser_process(process: Any) -> Tuple[Any, Any, str]:
    """Stop a timed-out browser and all processes in its process group."""
    if os.name == "posix":
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    else:  # pragma: no cover - exercised only on Windows
        process.terminate()

    try:
        stdout, stderr = process.communicate(
            timeout=_HTML_RENDER_TERMINATION_GRACE_SECONDS
        )
        return stdout, stderr, "Chrome process stopped after SIGTERM"
    except subprocess.TimeoutExpired:
        pass

    if os.name == "posix":
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    else:  # pragma: no cover - exercised only on Windows
        process.kill()

    try:
        stdout, stderr = process.communicate(
            timeout=_HTML_RENDER_TERMINATION_GRACE_SECONDS
        )
        return stdout, stderr, "Chrome process stopped after SIGKILL"
    except subprocess.TimeoutExpired as exc:  # pragma: no cover - defensive
        logger.warning("pdf.html: browser process did not stop after SIGKILL")
        return (
            exc.output or b"",
            exc.stderr or b"",
            "Chrome process remained running after SIGKILL",
        )


def _html_browser_error(
    message: str,
    command: Sequence[str],
    stderr: Any,
    verbose: bool,
    process_state: Optional[str] = None,
) -> HtmlRenderError:
    """Build a concise browser error, with diagnostics for verbose callers."""
    if not verbose:
        return HtmlRenderError(message)

    if isinstance(stderr, bytes):
        stderr_text = stderr.decode("utf-8", errors="replace")
    else:
        stderr_text = str(stderr or "")
    stderr_tail = stderr_text[-_HTML_BROWSER_LOG_TAIL_BYTES:]
    diagnostics = [f"Chrome command: {shlex.join(command)}"]
    if process_state:
        diagnostics.append(process_state)
    if stderr_tail:
        diagnostics.append(
            "Chrome stderr (last "
            f"{_HTML_BROWSER_LOG_TAIL_BYTES} bytes):\n{stderr_tail}"
        )
    else:
        diagnostics.append("Chrome stderr: (no output)")
    return HtmlRenderError(f"{message}\n" + "\n".join(diagnostics))


def _html_browser_log_tail(log_file: Any) -> bytes:
    """Read the useful end of a Chrome log redirected away from a pipe."""
    log_file.flush()
    log_file.seek(0, os.SEEK_END)
    size = log_file.tell()
    log_file.seek(max(0, size - _HTML_BROWSER_LOG_TAIL_BYTES))
    return log_file.read()


def _html_pdf_is_valid(fitz: Any, output_path: str) -> bool:
    """Return whether a fully written browser PDF has at least one page."""
    try:
        with _open_pdf(fitz, output_path, "HTML rendering") as rendered:
            return rendered.page_count > 0
    except Exception:  # A PDF can still be being written by Chrome.
        return False


def _render_html_to_pdf(
    fitz: Any,
    input_file: str,
    temp_dir: str,
    verbose: bool = False,
) -> str:
    """Print local HTML through Chrome/Chromium into a checked PDF."""
    if not os.path.isfile(input_file):
        raise HtmlRenderError("HTML file not found")
    browser = _find_html_browser()
    if browser is None:
        raise HtmlRenderError(
            "Chrome or Chromium is required to render HTML; install Chromium"
        )

    source_uri = Path(input_file).resolve().as_uri()
    output_path = os.path.join(
        temp_dir, f"html-{len(os.listdir(temp_dir))}.pdf"
    )
    profile_dir = tempfile.mkdtemp(prefix="chrome-profile-", dir=temp_dir)
    command = [
        browser,
        "--headless",
        "--disable-gpu",
        "--allow-file-access-from-files",
        "--no-pdf-header-footer",
        f"--timeout={_HTML_BROWSER_CAPTURE_TIMEOUT_MILLISECONDS}",
        f"--user-data-dir={profile_dir}",
        f"--print-to-pdf={output_path}",
    ]
    if sys.platform == "darwin":
        command.extend(
            (
                "--use-mock-keychain",
                "--disable-features=DialMediaRouteProvider",
                "--no-first-run",
                "--no-default-browser-check",
            )
        )
    if verbose:
        command.append("--enable-logging=stderr")
    command.append(source_uri)

    stdout_log = tempfile.TemporaryFile(dir=temp_dir)
    stderr_log = tempfile.TemporaryFile(dir=temp_dir)
    popen_kwargs: Dict[str, Any] = {
        "stdout": stdout_log,
        "stderr": stderr_log,
    }
    if os.name == "posix":
        popen_kwargs["start_new_session"] = True
    else:  # pragma: no cover - exercised only on Windows
        popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP

    process = None
    stderr = b""
    try:
        # Keep the process available to terminate its whole group after a PDF
        # is ready, or on timeout.
        process = subprocess.Popen(  # pylint: disable=consider-using-with
            command, **popen_kwargs
        )
        deadline = time.monotonic() + _HTML_RENDER_TIMEOUT_SECONDS
        previous_size = None
        while time.monotonic() < deadline:
            if os.path.isfile(output_path):
                size = os.path.getsize(output_path)
                if size > 0 and size == previous_size:
                    if _html_pdf_is_valid(fitz, output_path):
                        _stop_html_browser_process(process)
                        return output_path
                previous_size = size

            if process.poll() is not None:
                break
            time.sleep(_HTML_RENDER_POLL_SECONDS)
        else:
            _stdout, _stderr, process_state = _stop_html_browser_process(
                process
            )
            stderr = _html_browser_log_tail(stderr_log)
            raise _html_browser_error(
                "browser timed out while rendering HTML after "
                f"{_HTML_RENDER_TIMEOUT_SECONDS} seconds",
                command,
                stderr,
                verbose,
                process_state,
            )
        stderr = _html_browser_log_tail(stderr_log)
    except OSError as exc:
        raise _html_browser_error(
            f"browser failed to render HTML: {exc}", command, b"", verbose
        ) from exc
    finally:
        stdout_log.close()
        stderr_log.close()
        shutil.rmtree(profile_dir, ignore_errors=True)

    if process.returncode != 0:
        raise _html_browser_error(
            f"browser failed to render HTML (exit {process.returncode})",
            command,
            stderr,
            verbose,
        )
    if not os.path.isfile(output_path) or os.path.getsize(output_path) == 0:
        raise _html_browser_error(
            "browser did not create a PDF", command, stderr, verbose
        )
    try:
        with _open_pdf(fitz, output_path, "HTML rendering") as rendered:
            if rendered.page_count == 0:
                raise _html_browser_error(
                    "browser created an empty PDF", command, stderr, verbose
                )
    except HtmlRenderError:
        raise
    except Exception as exc:
        raise _html_browser_error(
            "browser created an invalid PDF", command, stderr, verbose
        ) from exc
    raise _html_browser_error(
        "browser exited before creating a stable PDF", command, stderr, verbose
    )


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


def _extract_image_info(
    doc: Any,
    xref: int,
) -> Tuple[int, int, Optional[bytes], Optional[str]]:
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
    image_bytes = payload.get("image")
    image_format = payload.get("ext")
    if width and height:
        return int(width), int(height), image_bytes, image_format

    if not image_bytes:
        raise RuntimeError(f"invalid extracted image payload for xref {xref}")

    from PIL import Image  # noqa pylint: disable=C0415

    with Image.open(io.BytesIO(image_bytes)) as image:
        return int(image.width), int(image.height), image_bytes, image_format


def _extract_image_dimensions(doc: Any, xref: int) -> Tuple[int, int]:
    """Return an extracted image's dimensions (legacy inspection helper)."""
    width, height, _, _ = _extract_image_info(doc, xref)
    return width, height


def _estimate_jpeg_quality(
    image_bytes: Optional[bytes],
    image_format: Optional[str],
) -> str:
    """Estimate JPEG quality from quantization tables, or return ``-``.

    JPEG quality is encoder-specific metadata in practice, so custom tables are
    reported as the closest table set generated by Pillow's standard encoder.
    """
    if not image_bytes:
        return "-"
    if image_format and str(image_format).lower() not in {"jpg", "jpeg"}:
        return "-"

    try:
        from PIL import Image  # noqa pylint: disable=C0415

        with Image.open(io.BytesIO(image_bytes)) as image:
            return image_info.estimate_jpeg_quality(image)
    except (AttributeError, KeyError, OSError, TypeError, ValueError):
        return "-"


def _inspect_page_raster_placements(
    doc: Any,
    page: Any,
) -> List[Dict[str, Any]]:
    placements: List[Dict[str, Any]] = []
    for xref in _list_page_image_xrefs(page):
        width_px, height_px, image_bytes, image_format = _extract_image_info(
            doc, xref
        )
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
                    "image_bytes": image_bytes,
                    "image_format": image_format,
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
        # Margins around a single scan do not make the page mixed.
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
                quality = "-"
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
                    quality = _estimate_jpeg_quality(
                        dominant["image_bytes"], dominant["image_format"]
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
                        "total_pages": doc.page_count,
                        "type": page_type,
                        "resolution": resolution,
                        "image_size_px": image_size_px,
                        "quality": quality,
                        "orientation": orientation,
                        "page_size": _format_page_size(page_rect, pt=pt),
                    }
                )
    except (OSError, RuntimeError, ValueError) as exc:
        logger.error("pdf.info: failed to inspect pdf %s", str(exc))
        return None

    return rows


def format_page_info_report(
    rows: Sequence[Dict[str, Any]],
    table: bool = False,
    compact: bool = False,
    page_number_width: Optional[int] = None,
) -> str:
    headers = [
        "Page",
        "Type",
        "Resolution",
        "ImageSizePx",
        "Quality",
        "Orientation",
        "PageSize",
    ]
    table_rows = []
    for row in rows:
        if compact:
            total_pages = row["total_pages"]
            width = page_number_width or len(str(total_pages))
            page = f'{row["page"]:0{width}d}/{total_pages:0{width}d}'
        else:
            page = str(row["page"])
        table_rows.append(
            [
                page,
                row["type"],
                row["resolution"],
                row["image_size_px"],
                row.get("quality", "-"),
                row["orientation"],
                row["page_size"],
            ]
        )

    widths = [0 if compact else len(header) for header in headers]
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

        if compact:
            return "\n".join(
                (border, *(format_row(row) for row in table_rows), border)
            )
        return "\n".join(
            (border, format_row(headers), border,
             *(format_row(row) for row in table_rows), border)
        )

    rendered_rows = []
    if not compact:
        rendered_rows.append(
            "  ".join(
                header.ljust(widths[idx]) for idx, header in enumerate(headers)
            )
        )
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
    force_orientation: Optional[str] = None,
) -> Tuple[float, float]:
    if force_orientation == "landscape":
        return max(page_size), min(page_size)
    if force_orientation == "portrait":
        return min(page_size), max(page_size)
    width, height = page_size
    if source_width > source_height:
        return height, width
    return width, height


def _resolve_text_page_size(
    page_size: Tuple[float, float],
    force_orientation: Optional[str],
) -> Tuple[float, float]:
    """Use the selected text sheet size, applying an explicit orientation."""
    if force_orientation == "landscape":
        return max(page_size), min(page_size)
    if force_orientation == "portrait":
        return min(page_size), max(page_size)
    return page_size


def _normalize_crop(crop: Optional[Sequence[Any]]):
    """Parse TOP RIGHT BOTTOM LEFT crop values into amounts and units."""
    if crop is None:
        return None
    if isinstance(crop, str) or len(crop) != 4:
        raise ValueError(
            "crop must contain exactly four values: TOP RIGHT BOTTOM LEFT"
        )

    normalized = []
    for value in crop:
        match = _CROP_VALUE_RE.fullmatch(str(value))
        if match is None:
            raise ValueError(
                "crop values must be non-negative numbers followed by % or px"
            )
        amount = float(match.group(1))
        unit = match.group(2)
        if not math.isfinite(amount) or amount < 0:
            raise ValueError("crop values must be finite and non-negative")
        if unit is None and amount != 0:
            raise ValueError("crop values must use % or px (except zero)")
        normalized.append((amount, unit))
    return tuple(normalized)


def _crop_margins(
    crop, width: float, height: float
) -> Tuple[float, float, float, float]:
    """Resolve a normalized crop to top, right, bottom, left dimensions."""
    if crop is None:
        return (0.0, 0.0, 0.0, 0.0)

    dimensions = (height, width, height, width)
    margins = tuple(
        amount * dimension / 100.0 if unit == "%" else amount
        for (amount, unit), dimension in zip(crop, dimensions)
    )
    top, right, bottom, left = margins
    if width - left - right <= 0 or height - top - bottom <= 0:
        raise ValueError("crop leaves no visible source area")
    return margins


def _cropped_rect(fitz: Any, source_rect: Any, crop) -> Any:
    """Return the visible source rectangle after applying ``crop``."""
    width, height = _rect_dimensions(source_rect)
    top, right, bottom, left = _crop_margins(crop, width, height)
    if hasattr(source_rect, "x0"):
        x0, y0 = source_rect.x0, source_rect.y0
    else:
        x0, y0 = source_rect[0], source_rect[1]
    return _build_rect(
        fitz,
        x0 + left,
        y0 + top,
        x0 + width - right,
        y0 + height - bottom,
    )


def _crop_image(image: Any, crop) -> Any:
    """Crop a Pillow image before it is sized for its destination."""
    if crop is None:
        return image
    width, height = image.size
    top, right, bottom, left = _crop_margins(crop, width, height)
    cropped = image.crop((left, top, width - right, height - bottom))
    if not all(cropped.size):
        raise ValueError("crop leaves no visible source area")
    return cropped


def _image_source_dimensions(
    input_file: str,
    crop=None,
) -> Tuple[int, int, Optional[Tuple[float, float]]]:
    """Return image pixels and its physical DPI when it is trustworthy."""
    from PIL import Image  # noqa pylint: disable=C0415

    with Image.open(input_file) as image:
        image = _crop_image(image, crop)
        width, height = image.size
        dpi = image.info.get("dpi")
        if not dpi or len(dpi) < 2:
            return width, height, None
        x_dpi, y_dpi = dpi[:2]
        if x_dpi <= 0 or y_dpi <= 0:
            return width, height, None
        return width, height, (float(x_dpi), float(y_dpi))


def _form_image_bytes(
    input_file: str,
    dest_rect: Any,
    dpi: int,
    quality: int,
    crop=None,
) -> bytes:
    """Encode an image no larger than its placed size at ``dpi``."""
    from PIL import Image  # noqa pylint: disable=C0415

    width_pt, height_pt = _rect_dimensions(dest_rect)
    max_width = max(1, int(width_pt * dpi / 72.0))
    max_height = max(1, int(height_pt * dpi / 72.0))
    ext = os.path.splitext(input_file)[1].lower()

    with Image.open(input_file) as source:
        image = _crop_image(source, crop).copy()
        source_width, source_height = image.size
        scale = min(
            1.0,
            max_width / float(source_width),
            max_height / float(source_height),
        )
        target_size = (
            max(1, int(source_width * scale)),
            max(1, int(source_height * scale)),
        )
        if target_size != image.size:
            try:
                resample = Image.Resampling.LANCZOS
            except AttributeError:  # pragma: no cover - old Pillow
                resample = Image.LANCZOS
            image = image.resize(target_size, resample=resample)

        output = io.BytesIO()
        if ext in (".jpg", ".jpeg"):
            if image.mode not in ("RGB", "L", "CMYK"):
                image = image.convert("RGB")
            image.save(output, format="JPEG", quality=quality)
        else:
            # PNG encoding retains alpha for transparent PNG inputs.
            image.save(output, format="PNG")
        return output.getvalue()


def _read_text_file(input_file: str) -> str:
    """Read a supported text file, preferring UTF-8 over Windows-1251."""
    with open(input_file, "rb") as source:
        payload = source.read()

    try:
        text = payload.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = payload.decode("cp1251")

    return (
        text.replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\t", "    ")
    )


def _load_form_text_sources(
    input_files: Iterable[str], verbose: bool
) -> Optional[Dict[str, str]]:
    """Decode every TXT source before form output can be created."""
    text_sources = {}
    for input_file in input_files:
        if os.path.splitext(input_file)[1].lower() not in _TEXT_EXTENSIONS:
            continue
        try:
            text_sources[input_file] = _read_text_file(input_file)
        except (OSError, UnicodeDecodeError) as exc:
            if verbose:
                logger.warning(
                    "pdf.form: failed to read text file %s: %s",
                    input_file,
                    exc,
                )
            else:
                logger.error(
                    "pdf.form: failed to read text file: %s", input_file
                )
            return None
    return text_sources


def _wrap_text_lines(text: str, available_width: float) -> List[str]:
    """Wrap normalized text while retaining blank input lines."""
    chars_per_line = max(1, int(available_width / (_TEXT_FONT_SIZE * 0.6)))
    wrapper = textwrap.TextWrapper(
        width=chars_per_line,
        expand_tabs=False,
        replace_whitespace=False,
        drop_whitespace=False,
        break_long_words=True,
        break_on_hyphens=False,
    )
    lines = []
    for source_line in text.split("\n"):
        lines.extend(wrapper.wrap(source_line) or [""])
    return lines


def _pdf_text(value: str) -> str:
    """Replace values that cannot be represented as Unicode PDF text."""
    return "".join(
        "?" if 0xD800 <= ord(char) <= 0xDFFF or ord(char) in (0xFFFE, 0xFFFF)
        else char
        for char in value
    )


def _render_text_pages(
    fitz: Any,
    out_doc: Any,
    text: str,
    page_size: Tuple[float, float],
    debug_fill: bool = False,
) -> int:
    """Add selectable Courier text pages to ``out_doc``."""
    width, height = page_size
    lines = _wrap_text_lines(text, width - 2 * _TEXT_MARGIN)
    lines_per_page = max(
        1, int((height - 2 * _TEXT_MARGIN) / _TEXT_LINE_HEIGHT)
    )
    font = fitz.Font(fontname="cour")

    pages_added = 0
    for start in range(0, len(lines), lines_per_page):
        page = out_doc.new_page(width=width, height=height)
        if debug_fill:
            _draw_form_debug_fill(fitz, page, width, height)
        writer = fitz.TextWriter(_build_rect(fitz, 0, 0, width, height))
        page_lines = lines[start:start + lines_per_page]
        for line_number, line in enumerate(page_lines):
            point = (
                _TEXT_MARGIN,
                _TEXT_MARGIN
                + _TEXT_FONT_SIZE
                + line_number * _TEXT_LINE_HEIGHT,
            )
            try:
                writer.append(
                    point, _pdf_text(line), font=font, fontsize=_TEXT_FONT_SIZE
                )
            except (RuntimeError, ValueError):
                # PyMuPDF's automatic fallback covers normal Unicode. If it
                # cannot find a glyph, retain the layout with an ASCII marker.
                writer.append(
                    point,
                    "?" * len(line),
                    font=font,
                    fontsize=_TEXT_FONT_SIZE,
                )
        writer.write_text(page)
        pages_added += 1
    return pages_added


def _validate_form_sources(
    fitz: Any,
    input_files: Sequence[str],
    verbose: bool,
    crop=None,
    rendered_html_sources: Optional[Dict[str, str]] = None,
) -> bool:
    """Check every source before a result document can be created."""
    from PIL import Image  # noqa pylint: disable=C0415

    for input_file in input_files:
        if not os.path.exists(input_file):
            if verbose:
                logger.warning("pdf.form: file not found: %s", input_file)
            return False

        ext = os.path.splitext(input_file)[1].lower()
        if ext == ".pdf" or ext in _HTML_EXTENSIONS:
            if crop is not None and any(unit == "px" for _, unit in crop):
                logger.error(
                    "pdf.form: px crop is not supported for PDF or HTML: %s",
                    input_file,
                )
                return False
            try:
                source_path = input_file
                if ext in _HTML_EXTENSIONS:
                    source_path = rendered_html_sources[input_file]
                with _open_pdf(fitz, source_path, "form") as doc:
                    for page_idx in range(doc.page_count):
                        page_rect = _get_page_rect(doc.load_page(page_idx))
                        _cropped_rect(fitz, page_rect, crop)
            except (OSError, RuntimeError, ValueError):
                logger.error("pdf.form: failed to open pdf: %s", input_file)
                return False
        elif ext in _IMAGE_EXTENSIONS:
            try:
                with Image.open(input_file) as image:
                    _crop_margins(crop, *image.size)
                    image.verify()
            except (OSError, RuntimeError, ValueError):
                logger.error("pdf.form: invalid image: %s", input_file)
                return False
        elif ext in _TEXT_EXTENSIONS:
            # TXT files were decoded by _load_form_text_sources before this
            # validation pass, so no result document can exist on failure.
            continue
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


def _processed_form_path(input_file: str) -> str:
    """Return the name used to mark a form source as processed."""
    stem, ext = os.path.splitext(input_file)
    return f"{stem}_processed{ext}"


def _plan_form_processed_renames(
    input_files: Iterable[str], output_path: str
) -> Optional[List[Tuple[str, str]]]:
    """Validate and de-duplicate form source renames before saving output."""
    planned = []
    seen_sources = set()
    for input_file in input_files:
        source_key = os.path.normcase(
            os.path.realpath(os.path.abspath(input_file))
        )
        if source_key in seen_sources:
            continue
        seen_sources.add(source_key)

        stem, _ = os.path.splitext(input_file)
        if stem.endswith("_processed"):
            logger.error(
                "pdf.form: source is already marked as processed: %s",
                input_file,
            )
            return None

        processed_path = _processed_form_path(input_file)
        if os.path.exists(processed_path):
            logger.error(
                "pdf.form: processed target already exists: %s",
                processed_path,
            )
            return None
        if _paths_refer_to_same_file(processed_path, output_path):
            logger.error(
                "pdf.form: processed target conflicts with output: %s",
                processed_path,
            )
            return None
        planned.append((input_file, processed_path))
    return planned


def _rename_processed_form_sources(
    renames: Iterable[Tuple[str, str]]
) -> bool:
    """Atomically claim every processed name without overwriting it."""
    for source_path, processed_path in renames:
        try:
            os.link(source_path, processed_path)
            os.unlink(source_path)
        except OSError as exc:
            logger.error(
                "pdf.form: failed to rename processed source %s to %s: %s",
                source_path,
                processed_path,
                exc,
            )
            return False
    return True


def form_files(
    input_files: Iterable[str],
    output_path: Optional[str],
    page_size: Optional[Tuple[float, float]] = None,
    paper_format: Optional[str] = None,
    dpi: Any = 300,
    quality: Any = None,
    debug_fill: bool = False,
    rename_processed: bool = False,
    verbose: bool = False,
    rewrite: bool = False,
    force_orientation: Optional[str] = None,
    crop: Optional[Sequence[Any]] = None,
) -> bool:
    """Place PDF, image, TXT, and HTML pages on consistently sized sheets."""
    files = list(input_files)
    if not files:
        if verbose:
            logger.warning("pdf.form: no input files provided")
        return False

    try:
        normalized_dpi = int(dpi)
        if not 72 <= normalized_dpi <= 800:
            raise ValueError("dpi must be between 72 and 800")
        normalized_quality = _normalize_compress_quality(quality)
        if page_size is None:
            normalized_format = _normalize_scale_format(paper_format)
            page_size = _PAPER_FORMATS[normalized_format]
        base_width, base_height = page_size
        if base_width <= 0 or base_height <= 0:
            raise ValueError("page size must be positive")
        if force_orientation not in (None, "landscape", "portrait"):
            raise ValueError(
                "force orientation must be landscape or portrait"
            )
        normalized_crop = _normalize_crop(crop)
    except (TypeError, ValueError) as exc:
        logger.error("pdf.form: invalid option: %s", exc)
        return False

    if output_path is None:
        output_path = _default_output(files[0], "_formed")
    if not _allow_output_targets(
        "form", files, [output_path], rewrite=rewrite
    ):
        return False

    renames = []
    if rename_processed:
        renames = _plan_form_processed_renames(files, output_path)
        if renames is None:
            return False

    fitz = _import_fitz("form creation")
    text_sources = _load_form_text_sources(files, verbose)
    if text_sources is None:
        return False

    # HTML is rendered before source validation and before the output document
    # exists: unlike merge, form must leave no partial output on a failure.
    with tempfile.TemporaryDirectory(prefix="davo-html-") as html_temp_dir:
        rendered_html_sources = {}
        for input_file in files:
            if os.path.splitext(input_file)[1].lower() not in _HTML_EXTENSIONS:
                continue
            try:
                rendered_html_sources[input_file] = _render_html_to_pdf(
                    fitz, input_file, html_temp_dir, verbose=verbose
                )
            except HtmlRenderError as exc:
                logger.error(
                    "pdf.form: failed to render HTML %s: %s", input_file, exc
                )
                return False
        if not _validate_form_sources(
            fitz, files, verbose, normalized_crop, rendered_html_sources
        ):
            return False

        try:
            out_doc = fitz.open()
            for input_file in files:
                ext = os.path.splitext(input_file)[1].lower()
                if ext == ".pdf" or ext in _HTML_EXTENSIONS:
                    source_path = rendered_html_sources.get(
                        input_file, input_file
                    )
                    with _open_pdf(fitz, source_path, "form") as src:
                        for page_idx in range(src.page_count):
                            source_page = src.load_page(page_idx)
                            source_rect = _get_page_rect(source_page)
                            crop_rect = _cropped_rect(
                                fitz, source_rect, normalized_crop
                            )
                            source_width, source_height = _rect_dimensions(
                                crop_rect
                            )
                            target_size = _resolve_form_page_size(
                                (base_width, base_height),
                                source_width,
                                source_height,
                                force_orientation=force_orientation,
                            )
                            target_width, target_height = target_size
                            dest_page = out_doc.new_page(
                                width=target_width, height=target_height
                            )
                            if debug_fill:
                                _draw_form_debug_fill(
                                    fitz, dest_page,
                                    target_width, target_height,
                                )
                            dest_rect = _fit_dimensions_within(
                                fitz,
                                source_width,
                                source_height,
                                target_width,
                                target_height,
                                allow_upscale=normalized_crop is not None,
                            )
                            if hasattr(dest_page, "show_pdf_page"):
                                if normalized_crop is None:
                                    dest_page.show_pdf_page(
                                        dest_rect, src, page_idx,
                                        keep_proportion=True,
                                    )
                                else:
                                    dest_page.show_pdf_page(
                                        dest_rect, src, page_idx,
                                        keep_proportion=True, clip=crop_rect,
                                    )
                            elif hasattr(dest_page, "showPDFpage"):
                                if normalized_crop is None:
                                    dest_page.showPDFpage(
                                        dest_rect, src, page_idx
                                    )
                                else:
                                    dest_page.showPDFpage(
                                        dest_rect, src, page_idx,
                                        clip=crop_rect,
                                    )
                            else:
                                raise RuntimeError(
                                    "PyMuPDF page object does not support "
                                    "page placement API"
                                )
                    continue

                if ext in _TEXT_EXTENSIONS:
                    target_size = _resolve_text_page_size(
                        (base_width, base_height), force_orientation
                    )
                    _render_text_pages(
                        fitz,
                        out_doc,
                        text_sources[input_file],
                        target_size,
                        debug_fill=debug_fill,
                    )
                    continue

                width_px, height_px, image_dpi = _image_source_dimensions(
                    input_file, normalized_crop
                )
                target_width, target_height = _resolve_form_page_size(
                    (base_width, base_height), width_px, height_px,
                    force_orientation=force_orientation,
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
                    allow_upscale = normalized_crop is not None
                dest_page = out_doc.new_page(
                    width=target_width, height=target_height
                )
                if debug_fill:
                    _draw_form_debug_fill(
                        fitz, dest_page, target_width, target_height
                    )
                dest_rect = _fit_dimensions_within(
                    fitz, source_width, source_height,
                    target_width, target_height, allow_upscale=allow_upscale,
                )
                if hasattr(dest_page, "insert_image"):
                    dest_page.insert_image(
                        dest_rect,
                        stream=_form_image_bytes(
                            input_file, dest_rect, normalized_dpi,
                            normalized_quality, normalized_crop,
                        ),
                        keep_proportion=False,
                    )
                elif hasattr(dest_page, "insertImage"):
                    dest_page.insertImage(
                        dest_rect,
                        stream=_form_image_bytes(
                            input_file, dest_rect, normalized_dpi,
                            normalized_quality, normalized_crop,
                        ),
                    )
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
                    quality=normalized_quality,
                    lossy=True,
                    lossless=True,
                    bitonal=True,
                    color=True,
                    gray=True,
                    set_to_gray=False,
                )
            out_doc.save(output_path, garbage=3, deflate=True, clean=True)
            if hasattr(out_doc, "close"):
                out_doc.close()
        except (OSError, RuntimeError, ValueError) as exc:
            logger.error("pdf.form: failed to form pdf %s", str(exc))
            return False

    if rename_processed and not _rename_processed_form_sources(renames):
        return False

    return True


def _draw_form_debug_fill(
    fitz: Any, page: Any, width: float, height: float
) -> None:
    """Paint the debug background beneath the placed source content."""
    if not hasattr(page, "draw_rect"):
        raise RuntimeError(
            "PyMuPDF page object does not support drawing API"
        )
    page.draw_rect(
        fitz.Rect(0, 0, width, height),
        color=None,
        fill=(1, 0, 1),
        overlay=False,
    )


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

    with tempfile.TemporaryDirectory(prefix="davo-html-") as html_temp_dir:
        with fitz.open() as result_pdf:
            rendered_generated_pages = 0
            for file_path in files:
                if not os.path.exists(file_path):
                    if verbose:
                        logger.warning(
                            "pdf.merge: file not found: %s", file_path
                        )
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

                if ext in _TEXT_EXTENSIONS:
                    try:
                        text = _read_text_file(file_path)
                        rendered_generated_pages += _render_text_pages(
                            fitz,
                            result_pdf,
                            text,
                            _PAPER_FORMATS["a4"],
                        )
                    except (
                        OSError, RuntimeError, UnicodeDecodeError, ValueError
                    ):
                        if verbose:
                            logger.warning(
                                "pdf.merge: failed to read text file: %s",
                                file_path,
                            )
                    continue

                if ext in _HTML_EXTENSIONS:
                    try:
                        rendered_path = _render_html_to_pdf(
                            fitz, file_path, html_temp_dir, verbose=verbose
                        )
                        with _open_pdf(
                            fitz, rendered_path, "merge"
                        ) as html_pdf:
                            for page_idx in range(html_pdf.page_count):
                                source_page = html_pdf.load_page(page_idx)
                                dest_page = result_pdf.new_page(
                                    width=_PAPER_FORMATS["a4"][0],
                                    height=_PAPER_FORMATS["a4"][1],
                                )
                                dest_rect = _fit_rect_within(
                                    fitz,
                                    _get_page_rect(source_page),
                                    *_PAPER_FORMATS["a4"],
                                )
                                if hasattr(dest_page, "show_pdf_page"):
                                    dest_page.show_pdf_page(
                                        dest_rect, html_pdf, page_idx,
                                        keep_proportion=True,
                                    )
                                elif hasattr(dest_page, "showPDFpage"):
                                    dest_page.showPDFpage(
                                        dest_rect, html_pdf, page_idx
                                    )
                                else:
                                    raise RuntimeError(
                                        "PyMuPDF page object does not support "
                                        "page placement API"
                                    )
                                rendered_generated_pages += 1
                    except (
                        HtmlRenderError, OSError, RuntimeError, ValueError
                    ):
                        if verbose:
                            logger.warning(
                                "pdf.merge: failed to render HTML: %s",
                                file_path,
                            )
                    continue

                if verbose:
                    logger.warning(
                        "pdf.merge: file not supported: %s", file_path
                    )

            if result_pdf.page_count == 0 and rendered_generated_pages == 0:
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
