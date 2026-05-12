import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

fitz: Any = None
try:
    import fitz
except ImportError:
    logger.warning("PyMuPDF is not installed")
    fitz = None


def merge_files(input_files, output_path, verbose=False):
    if fitz is None:
        raise RuntimeError("PyMuPDF (fitz) is required for PDF rotation")

    # Создаем новый пустой PDF-документ
    result_pdf = fitz.open()

    for file_path in input_files:
        if not os.path.exists(file_path):
            if verbose:
                logger.warning("pdf: file not found: %s", file_path)
            continue

        ext = os.path.splitext(file_path)[1].lower()

        if ext == ".pdf":
            # Если это PDF, открываем и добавляем все его страницы
            with fitz.open(file_path) as doc:
                result_pdf.insert_pdf(doc)

        elif ext in [".jpg", ".jpeg", ".png", ".bmp"]:
            # Если это картинка, конвертируем её в PDF-байты
            # и открываем как документ.
            img_doc = fitz.open(file_path)
            # Конвертируем в PDF в памяти
            pdf_bytes = img_doc.convert_to_pdf()
            # Открываем полученный PDF из байтов
            with fitz.open("pdf", pdf_bytes) as temp_img_pdf:
                result_pdf.insert_pdf(temp_img_pdf)
            img_doc.close()

        else:
            if verbose:
                logger.warning("pdf: file not supported: %s", file_path)

    # Сохраняем финальный файл
    success = False
    if len(result_pdf) > 0:
        result_pdf.save(output_path)
        success = True

    result_pdf.close()
    return success


def rotate_pages(
    input_file: str,
    output_path: str,
    direction="clockwise",
    pages=None,
    inplace=False,
    verbose=False,
):
    """
    Rotate pages in a PDF file.

    Parameters
    - file_path: path to input PDF file (must exist and be a .pdf)
    - direction: 'clockwise'|'ccw'|'counterclockwise'|'left'|'right'
      or an int angle
    - pages: iterable of page indices to rotate. Accepts 0-based indices, but
      will also accept 1-based indices when numbers exceed page_count-1.
      If None, all pages are rotated.
    - output_path: path to write rotated PDF. If None and inplace is True,
      the original file is overwritten (via atomic replace). If None and
      inplace is False, the function will save to '<original>_rotated.pdf'.
    - inplace: if True and output_path is None, overwrite the original file.
    - verbose: if True, log additional warnings.

    Returns True on success, False otherwise.
    """
    # Ensure dependency is available
    if fitz is None:
        raise RuntimeError("PyMuPDF (fitz) is required for PDF rotation")

    # Basic checks
    if not os.path.exists(input_file):
        if verbose:
            logger.warning("pdf.rotate: file not found: %s", input_file)
        return False

    ext = os.path.splitext(input_file)[1].lower()
    if ext != ".pdf":
        if verbose:
            logger.warning("pdf.rotate: not a pdf: %s", input_file)
        return False

    try:
        doc = fitz.open(input_file)
    except Exception:  # pragma: no cover - environment dependent
        logger.exception("pdf.rotate: failed to open pdf: %s", input_file)
        raise

    try:
        # Resolve rotation angle
        if isinstance(direction, int):
            angle = direction % 360
        else:
            d = str(direction).lower()
            if d in ("cw", "clockwise", "right"):
                angle = 90
            elif d in ("ccw", "counterclockwise", "left"):
                angle = 270
            else:
                # try to parse integer-like strings
                try:
                    angle = int(d) % 360
                except Exception:
                    doc.close()
                    raise ValueError(
                        "unknown rotation direction: %r" % (direction,)
                    )

        page_count = doc.page_count

        # Normalize requested pages
        if pages is None:
            page_indices = range(page_count)
        else:
            # Accept iterable of ints; normalize 1-based -> 0-based if needed
            normalized = []
            for p in pages:
                if not isinstance(p, int):
                    raise TypeError("pages must be integers")
                if p < 0:
                    # allow negative indexing
                    idx = p
                elif p > page_count - 1 and p <= page_count:
                    # probable 1-based index -> convert
                    idx = p - 1
                else:
                    idx = p
                if not (-page_count <= idx < page_count):
                    raise IndexError("page index out of range: %r" % (p,))
                normalized.append(idx)
            # remove duplicates while preserving order
            seen = set()
            page_indices = [
                x for x in normalized if not (x in seen or seen.add(x))
            ]

        # Rotate requested pages
        for idx in page_indices:
            try:
                page = doc.load_page(idx)
            except Exception:
                # fallback for older doc API
                page = doc[idx]

            # Try modern method name, fallback to older Variant
            if hasattr(page, "set_rotation"):
                page.set_rotation(angle)
            elif hasattr(page, "setRotation"):
                # older camelCase API
                page.setRotation(angle)
            else:
                # As a last resort, apply rotation via transform matrix
                mat = fitz.Matrix(1, 1).pre_rotate(angle)
                # create a pixmap and replace page contents with rotated image
                pix = page.get_pixmap(matrix=mat)
                img_pdf_bytes = fitz.open("pdf", pix.tobytes())
                # replace page with the single-page pdf of rotated image
                doc.delete_page(idx)
                doc.insert_pdf(img_pdf_bytes)

        # Decide output path
        if output_path is None:
            if inplace:
                # write to temp and replace
                import tempfile

                fd, tmp_path = tempfile.mkstemp(suffix=".pdf")
                os.close(fd)
                out_path = tmp_path
                replace_when_done = True
            else:
                base, _ = os.path.splitext(input_file)
                out_path = base + "_rotated.pdf"
                replace_when_done = False
        else:
            out_path = output_path
            replace_when_done = False

        doc.save(out_path)
        doc.close()

        if replace_when_done:
            os.replace(out_path, input_file)

        return True
    except Exception:
        try:
            doc.close()
        except Exception:
            pass
        raise


def delete_pages(
    input_file: str,
    output_path: str,
    pages=None,
    verbose=False,
):
    """
    Delete pages from a PDF file.

    Parameters
    - input_file: path to the source PDF
    - pages: iterable of 1-based page numbers to remove (required)
    - output_path: path to write the result. If None, saves to
      '<original>_deleted.pdf'.
    - verbose: if True, log additional warnings.

    Returns True on success, False on benign failures.
    """
    # Ensure dependency is available
    if fitz is None:
        raise RuntimeError("PyMuPDF (fitz) is required for PDF page deletion")

    if not os.path.exists(input_file):
        if verbose:
            logger.warning("pdf.delete: file not found: %s", input_file)
        return False

    if os.path.splitext(input_file)[1].lower() != ".pdf":
        if verbose:
            logger.warning("pdf.delete: not a pdf: %s", input_file)
        return False

    if not pages:
        if verbose:
            logger.warning("pdf.delete: no pages provided")
        return False

    try:
        doc = fitz.open(input_file)
    except Exception:  # pragma: no cover - environment dependent
        logger.exception("pdf.delete: failed to open pdf: %s", input_file)
        raise

    page_count = doc.page_count
    try:
        # Validate and convert 1-based page numbers to 0-based indices
        indices = []
        for p in pages:
            if not isinstance(p, int):
                doc.close()
                raise TypeError("pages must be integers (1-based)")
            if p < 1 or p > page_count:
                doc.close()
                raise IndexError("page number out of range: %r" % (p,))
            indices.append(p - 1)

        # Remove duplicates and sort descending to avoid shifting indices
        indices = sorted(set(indices), reverse=True)

        for idx in indices:
            doc.delete_page(idx)

        # Decide output path
        if output_path is None:
            base, _ = os.path.splitext(input_file)
            out_path = base + "_deleted.pdf"
        else:
            out_path = output_path

        doc.save(out_path)
        doc.close()
        return True
    except Exception:
        try:
            doc.close()
        except Exception:
            pass
        raise


def split_pages(
    input_file: str,
    output_path: str,
    pages=None,
    verbose=False,
):
    """
    Split `input_file` PDF into multiple PDFs.

    - `pages` is an iterable of 1-based page numbers indicating the
      first page of each output block. The list MUST include 1.
    - `output_path` is the base path for outputs (e.g. 'out.pdf') and
      outputs will be named 'out_1.pdf', 'out_2.pdf', ... placed next
      to the provided path. If `output_path` is None, the input file's
      basename is used.
    - If any target filename already exists, the function will NOT start
      saving and will return False.

    Returns True on success, False on benign failures.
    """
    # Ensure dependency is available
    if fitz is None:
        raise RuntimeError("PyMuPDF (fitz) is required for PDF splitting")

    if not os.path.exists(input_file):
        if verbose:
            logger.warning("pdf.split: file not found: %s", input_file)
        return False

    if os.path.splitext(input_file)[1].lower() != ".pdf":
        if verbose:
            logger.warning("pdf.split: not a pdf: %s", input_file)
        return False

    if not pages:
        if verbose:
            logger.warning("pdf.split: no pages provided")
        return False

    # Normalize and validate pages (1-based)
    try:
        starts = sorted(set(int(p) for p in pages))
    except Exception:
        raise TypeError("pages must be iterable of integers (1-based)")

    # pages must include 1 as the first block start
    if starts[0] != 1:
        raise ValueError("pages must include 1 as the first block start")

    # Open source doc
    try:
        src = fitz.open(input_file)
    except Exception:  # pragma: no cover - environment dependent
        logger.exception("pdf.split: failed to open pdf: %s", input_file)
        raise

    page_count = src.page_count

    # Validate ranges
    for p in starts:
        if p < 1 or p > page_count:
            src.close()
            raise IndexError("page number out of range: %r" % (p,))

    # Compute block ranges (0-based inclusive)
    ranges = []
    for i, s in enumerate(starts):
        start_idx = s - 1
        if i + 1 < len(starts):
            end_idx = starts[i + 1] - 2
        else:
            end_idx = page_count - 1
        if start_idx <= end_idx:
            ranges.append((start_idx, end_idx))

    if not ranges:
        src.close()
        if verbose:
            logger.warning("pdf.split: no valid ranges computed")
        return False

    # Prepare output filenames and check collisions
    if output_path:
        base, ext = os.path.splitext(output_path)
    else:
        base, ext = os.path.splitext(input_file)

    if not ext:
        ext = ".pdf"

    targets = [f"{base}_{i + 1}{ext}" for i in range(len(ranges))]

    # If any target exists, don't start saving
    collisions = [p for p in targets if os.path.exists(p)]
    if collisions:
        if verbose:
            logger.warning(
                "pdf.split: target files exist, aborting: %s", collisions
            )
        src.close()
        return False

    created = []
    try:
        for (start_idx, end_idx), out in zip(ranges, targets):
            new_doc = fitz.open()
            # insert_pdf takes 0-based from_page,to_page
            new_doc.insert_pdf(src, from_page=start_idx, to_page=end_idx)
            new_doc.save(out)
            new_doc.close()
            created.append(out)

        src.close()
        return True
    except Exception:
        # on error, try to cleanup any files we created
        for f in created:
            try:
                if os.path.exists(f):
                    os.remove(f)
            except Exception:
                pass
        try:
            src.close()
        except Exception:
            pass
        raise


def clean_file(
    input_file: str,
    output_path: str,
    verbose=False,
):
    # Ensure dependency is available
    if fitz is None:
        raise RuntimeError("PyMuPDF (fitz) is required for PDF splitting")

    if not os.path.exists(input_file):
        if verbose:
            logger.warning("pdf.split: file not found: %s", input_file)
        return False

    if os.path.splitext(input_file)[1].lower() != ".pdf":
        if verbose:
            logger.warning("pdf.split: not a pdf: %s", input_file)
        return False

    try:
        doc = fitz.open(input_file)
    except Exception as exc:
        logger.exception("pdf.split: failed to open pdf: %s", str(exc))
        return False

    try:
        # Опция garbage=3 удаляет лишние объекты.
        # clean=True пытается восстановить структуру.
        doc.save(output_path, garbage=3, deflate=True, clean=True)
        doc.close()
        return True
    except Exception as exc:
        logger.error("pdf.split: failed to process pdf %s", str(exc))
        return False
