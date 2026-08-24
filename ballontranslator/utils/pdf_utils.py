"""PDF page extraction and re-assembly helpers.

The app pipeline only understands a directory of raster images, so PDF support is
implemented as a pre/post-processing pair around that existing contract:

* :func:`extract_pdf_pages` rasterises a PDF into a sibling working directory and
  writes ``pdf_source.json``, recording the original page geometry.
* :func:`export_translated_pdf` reads that manifest back and rebuilds a PDF whose
  pages keep the original point sizes, so a translated comic stays a PDF with the
  same page format as the input.

PyMuPDF is an optional dependency. Every entry point raises :class:`PdfSupportError`
with an install hint instead of failing at import time, so the app keeps working
without it.

>>> osp.basename(pdf_workdir_for('/tmp/comic.pdf'))
'comic_translate'
>>> is_pdf_path('/tmp/comic.PDF'), is_pdf_path('/tmp/comic.png')
(True, False)
"""

from __future__ import annotations

import json
import os
import os.path as osp
from typing import Callable, Dict, List, Optional, Tuple

from .logger import logger as LOGGER

PDF_EXT = ['.pdf']

PDF_MANIFEST_NAME = 'pdf_source.json'
PDF_MANIFEST_VERSION = 1

DEFAULT_PDF_DPI = 300
MIN_PDF_DPI = 72
MAX_PDF_DPI = 900

# PyMuPDF decodes these directly from disk; anything else is transcoded in memory.
_FITZ_READABLE_EXT = {'.png', '.jpg', '.jpeg', '.webp', '.bmp'}

_PDF_INSTALL_HINT = 'PDF support requires PyMuPDF. Install it with: pip install pymupdf'


class PdfSupportError(Exception):
    """Raised when PDF work cannot proceed (missing backend or unusable file)."""


def _load_pymupdf():
    """Import PyMuPDF lazily so a missing optional dependency stays recoverable."""
    try:
        import pymupdf  # noqa: F401  modern package name
        return pymupdf
    except ImportError:
        pass
    try:
        import fitz  # legacy package name shipped by older PyMuPDF wheels
        return fitz
    except ImportError as e:
        raise PdfSupportError(_PDF_INSTALL_HINT) from e


def pdf_support_available() -> bool:
    """Return whether PDF import/export can run in this environment."""
    try:
        _load_pymupdf()
    except PdfSupportError:
        return False
    return True


def pdf_install_hint() -> str:
    return _PDF_INSTALL_HINT


def is_pdf_path(path: str) -> bool:
    return isinstance(path, str) and osp.splitext(path)[1].lower() in PDF_EXT


def find_pdf_files(path: str, recursive: bool = False, exclude_dirs=None) -> List[str]:
    """Return the PDF files under *path*, or the single file when *path* is a PDF.

    Directories are scanned non-recursively by default so a folder of PDFs behaves
    like a folder of images: each PDF becomes one pipeline queue item. With
    ``recursive`` the scan descends into subdirectories, skipping generated
    ``*_translate`` working dirs so re-scanning a parent never re-imports output.
    Callers may pass ``exclude_dirs`` to also skip user-configured directory names.

    >>> find_pdf_files('/nonexistent/dir')
    []
    """
    if isinstance(path, str) and osp.isfile(path):
        return [path] if is_pdf_path(path) else []
    if not isinstance(path, str) or not osp.isdir(path):
        return []

    if not recursive:
        return [
            osp.join(path, name)
            for name in sorted(os.listdir(path))
            if is_pdf_path(name)
        ]

    if exclude_dirs is None:
        exclude_dirs = set()
    else:
        exclude_dirs = set(exclude_dirs)

    pdfs: List[str] = []
    for root, dirs, files in os.walk(path):
        dirs[:] = sorted(
            d for d in dirs
            if d not in exclude_dirs and not d.endswith('_translate')
        )
        for name in sorted(files):
            if is_pdf_path(name):
                pdfs.append(osp.join(root, name))
    return pdfs


def clamp_pdf_dpi(dpi) -> int:
    try:
        dpi = int(dpi)
    except (TypeError, ValueError):
        LOGGER.warning(f'invalid pdf dpi {dpi!r}, falling back to {DEFAULT_PDF_DPI}')
        return DEFAULT_PDF_DPI
    return max(MIN_PDF_DPI, min(MAX_PDF_DPI, dpi))


def pdf_workdir_for(pdf_path: str) -> str:
    """Return the image working directory used for *pdf_path*."""
    base = osp.splitext(osp.basename(pdf_path))[0]
    return osp.join(osp.dirname(osp.abspath(pdf_path)), base + '_translate')


def manifest_path(directory: str) -> str:
    return osp.join(directory, PDF_MANIFEST_NAME)


def extract_pdf_pages(
    pdf_path: str,
    out_dir: Optional[str] = None,
    dpi: Optional[int] = None,
    reuse_existing: bool = True,
    progress_cb: Optional[Callable[[int, int], None]] = None,
) -> str:
    """Rasterise *pdf_path* into a working directory and return that directory.

    Existing page images are reused when ``reuse_existing`` is set, which keeps a
    re-opened project from discarding user edits or re-rendering a long document.
    """
    pymupdf = _load_pymupdf()
    if not osp.isfile(pdf_path):
        raise PdfSupportError(f'PDF not found: {pdf_path}')

    dpi = clamp_pdf_dpi(DEFAULT_PDF_DPI if dpi is None else dpi)
    if out_dir is None:
        out_dir = pdf_workdir_for(pdf_path)
    os.makedirs(out_dir, exist_ok=True)

    zoom = dpi / 72.0
    pages: List[Dict] = []
    try:
        doc = pymupdf.open(pdf_path)
    except Exception as e:
        raise PdfSupportError(f'Failed to open PDF: {pdf_path}') from e

    try:
        total = doc.page_count
        if total == 0:
            raise PdfSupportError(f'PDF has no pages: {pdf_path}')
        matrix = pymupdf.Matrix(zoom, zoom)
        for index in range(total):
            page = doc.load_page(index)
            img_name = f'{index + 1:04d}.png'
            img_path = osp.join(out_dir, img_name)
            if not (reuse_existing and osp.exists(img_path)):
                # alpha=False keeps pages opaque so inpainting has no stray transparency.
                pix = page.get_pixmap(matrix=matrix, alpha=False)
                pix.save(img_path)
            rect = page.rect
            pages.append({
                'index': index,
                'image': img_name,
                'width': float(rect.width),
                'height': float(rect.height),
            })
            if progress_cb is not None:
                progress_cb(index + 1, total)
    finally:
        doc.close()

    _write_manifest(out_dir, {
        'version': PDF_MANIFEST_VERSION,
        'source_pdf': osp.abspath(pdf_path),
        'dpi': dpi,
        'pages': pages,
    })
    return out_dir


def _write_manifest(directory: str, manifest: Dict) -> None:
    with open(manifest_path(directory), 'w', encoding='utf8') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)


def read_pdf_manifest(directory: str) -> Optional[Dict]:
    """Return the PDF manifest for *directory*, or ``None`` when it is not a PDF project.

    Loading stays permissive: malformed page entries are dropped with a warning so a
    partially damaged manifest never blocks opening the project.
    """
    if not isinstance(directory, str) or not directory:
        return None
    mpath = manifest_path(directory)
    if not osp.exists(mpath):
        return None
    try:
        with open(mpath, 'r', encoding='utf8') as f:
            raw = json.load(f)
    except Exception as e:
        LOGGER.warning(f'failed to read {mpath}: {e}')
        return None
    if not isinstance(raw, dict):
        LOGGER.warning(f'unexpected content in {mpath}, ignoring pdf metadata')
        return None

    pages = []
    for entry in raw.get('pages') or []:
        if not isinstance(entry, dict):
            LOGGER.warning(f'discarding non-dict page entry in {mpath}')
            continue
        image = entry.get('image')
        if not isinstance(image, str) or not image:
            LOGGER.warning(f'discarding page entry without image name in {mpath}')
            continue
        try:
            width = float(entry.get('width', 0) or 0)
            height = float(entry.get('height', 0) or 0)
        except (TypeError, ValueError):
            width = height = 0.0
        pages.append({
            'index': len(pages),
            'image': image,
            'width': width if width > 0 else 0.0,
            'height': height if height > 0 else 0.0,
        })

    source_pdf = raw.get('source_pdf')
    return {
        'version': raw.get('version', PDF_MANIFEST_VERSION),
        'source_pdf': source_pdf if isinstance(source_pdf, str) else '',
        'dpi': clamp_pdf_dpi(raw.get('dpi', DEFAULT_PDF_DPI)),
        'pages': pages,
    }


def is_pdf_project(directory: str) -> bool:
    """Return whether *directory* was produced by :func:`extract_pdf_pages`."""
    manifest = read_pdf_manifest(directory)
    return bool(manifest and manifest['pages'])


def translated_pdf_path(directory: str, manifest: Optional[Dict] = None) -> Optional[str]:
    """Return the default output path for the translated PDF of *directory*."""
    if manifest is None:
        manifest = read_pdf_manifest(directory)
    if not manifest:
        return None
    source = manifest.get('source_pdf') or ''
    if source:
        stem = osp.splitext(osp.basename(source))[0]
        out_dir = osp.dirname(source) if osp.isdir(osp.dirname(source)) else directory
    else:
        stem = osp.basename(osp.abspath(directory))
        out_dir = directory
    return osp.join(out_dir, stem + '_translated.pdf')


def _resolve_page_image(
    directory: str, result_dir: Optional[str], image_name: str
) -> Tuple[Optional[str], bool]:
    """Resolve a page image, preferring the rendered result over the source render.

    Returns ``(path, from_result_dir)`` so callers can report pages that were not
    rendered yet without re-deriving the lookup order.
    """
    from .io_utils import IMG_EXT

    stem = osp.splitext(image_name)[0]
    if result_dir and osp.isdir(result_dir):
        for ext in IMG_EXT:
            candidate = osp.join(result_dir, stem + ext)
            if osp.exists(candidate):
                return candidate, True
    src = osp.join(directory, image_name)
    if osp.exists(src):
        return src, False
    return None, False


def _insert_page_image(page, rect, img_path: str) -> None:
    ext = osp.splitext(img_path)[1].lower()
    if ext in _FITZ_READABLE_EXT:
        page.insert_image(rect, filename=img_path)
        return
    # Formats such as .jxl are only decodable by the app's own readers.
    import cv2
    from .io_utils import imread

    img = imread(img_path)
    if img is None:
        raise PdfSupportError(f'Failed to read page image: {img_path}')
    ok, buf = cv2.imencode('.png', img)
    if not ok:
        raise PdfSupportError(f'Failed to encode page image: {img_path}')
    page.insert_image(rect, stream=buf.tobytes())


def export_translated_pdf(
    directory: str,
    result_dir: Optional[str] = None,
    save_path: Optional[str] = None,
    progress_cb: Optional[Callable[[int, int], None]] = None,
) -> Tuple[str, List[str]]:
    """Rebuild a PDF from the translated page images of a PDF-backed project.

    Returns ``(save_path, missing_pages)``. Page sizes come from the manifest so the
    output keeps the original PDF page geometry; pages whose result image is missing
    fall back to the untranslated source render and are reported in ``missing_pages``.
    """
    pymupdf = _load_pymupdf()
    manifest = read_pdf_manifest(directory)
    if not manifest or not manifest['pages']:
        raise PdfSupportError(f'{directory} is not a PDF-backed project')

    if save_path is None:
        save_path = translated_pdf_path(directory, manifest)
    if not save_path:
        raise PdfSupportError('Could not determine a PDF output path')

    dpi = manifest['dpi']
    pages = manifest['pages']
    missing: List[str] = []
    out = pymupdf.open()
    try:
        for ii, entry in enumerate(pages):
            image_name = entry['image']
            img_path, from_result = _resolve_page_image(directory, result_dir, image_name)
            if img_path is None:
                LOGGER.warning(f'skipping page without image: {image_name}')
                missing.append(image_name)
                continue
            if not from_result:
                # Page was never rendered: keep the original render so page count matches.
                missing.append(image_name)

            width, height = entry['width'], entry['height']
            if width <= 0 or height <= 0:
                # No recorded geometry: derive points from the render dpi.
                from .io_utils import imread
                img = imread(img_path)
                if img is None:
                    raise PdfSupportError(f'Failed to read page image: {img_path}')
                h, w = img.shape[:2]
                width, height = w * 72.0 / dpi, h * 72.0 / dpi

            page = out.new_page(width=width, height=height)
            _insert_page_image(page, page.rect, img_path)
            if progress_cb is not None:
                progress_cb(ii + 1, len(pages))

        if out.page_count == 0:
            raise PdfSupportError('No page images available to export')
        os.makedirs(osp.dirname(osp.abspath(save_path)), exist_ok=True)
        out.save(save_path, deflate=True, garbage=3)
    finally:
        out.close()

    return save_path, missing
