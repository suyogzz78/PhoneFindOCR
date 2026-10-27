"""Turn an uploaded PDF/image into a list of phone numbers."""
import io
import logging
from dataclasses import dataclass
from typing import Callable, Literal

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c
from PIL import Image, ImageOps

from .config import Settings
from .ocr import OcrEngine
from .phones import extract_phones

log = logging.getLogger("ocr.processing")

# on_progress(pages_done, total_pages, phones_found_so_far)
ProgressFn = Callable[[int, int, int], None]


class UploadError(Exception):
    """The upload is not acceptable. The message is safe to show to the user."""


@dataclass
class Inspected:
    kind: Literal["pdf", "image"]
    pages: int


@dataclass
class ExtractResult:
    phones: list[str]
    failed_pages: list[int]


def inspect_upload(content: bytes, settings: Settings) -> Inspected:
    """Cheap validation done *before* a job is queued, so bad files fail instantly.

    We look at the file's real content (not its name or the browser-supplied MIME type).
    """
    if b"%PDF-" in content[:1024]:
        try:
            pdf = pdfium.PdfDocument(content)
        except Exception:
            raise UploadError("Corrupted or invalid PDF file")
        try:
            pages = len(pdf)
        finally:
            pdf.close()
        if pages == 0:
            raise UploadError("The PDF has no pages           ")
        if pages > settings.max_pages:
            raise UploadError(f"PDF has {pages} pages, maximum allowed is {settings.max_pages}")
        return Inspected("pdf", pages)

    try:
        with Image.open(io.BytesIO(content)) as im:
            im.verify()
    except Exception:
        raise UploadError("Unsupported file. Upload a PDF or an image (PNG, JPG, ...)")
    return Inspected("image", 1)


def _prepare_image(img: Image.Image, max_dim: int) -> Image.Image:
    img = ImageOps.exif_transpose(img)  # phone photos are often rotated via EXIF
    img = img.convert("RGB")
    w, h = img.size
    if max(w, h) > max_dim:
        scale = max_dim / max(w, h)
        img = img.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)
    return img


def _page_bands(img: Image.Image, count: int, overlap: int):
    """Yield overlapping horizontal strips, as used by the page recovery script."""
    if count <= 1:
        yield img
        return
    width, height = img.size
    step = max(1, height // count)
    for i in range(count):
        top = max(0, i * step - overlap)
        bottom = height if i == count - 1 else min(height, (i + 1) * step + overlap)
        if bottom > top:
            yield img.crop((0, top, width, bottom))


def extract(
    content: bytes,
    info: Inspected,
    engine: OcrEngine,
    settings: Settings,
    on_progress: ProgressFn,
) -> ExtractResult:
    phones: list[str] = []
    seen: set[str] = set()
    failed_pages: list[int] = []

    def add(new: list[str]) -> None:
        for p in new:
            if p not in seen:
                seen.add(p)
                phones.append(p)

    if info.kind == "image":
        with Image.open(io.BytesIO(content)) as raw:
            img = _prepare_image(raw, settings.max_image_dim)
        add(extract_phones(engine.read_text(img)))
        on_progress(1, 1, len(phones))
        return ExtractResult(phones, failed_pages)

    pdf = pdfium.PdfDocument(content)
    try:
        total = len(pdf)
        for i in range(total):
            page = pdf[i]
            try:
                # FAST PATH: digital PDFs carry real text; reading it takes milliseconds.
                try:
                    digital_text = page.get_textpage().get_text_range()
                except Exception:
                    digital_text = ""
                # Keep embedded text, but do not treat it as complete: mixed PDFs can
                # have a partial text layer over scanned content.
                digital_phones = extract_phones(digital_text)
                add(digital_phones)
                # A usable text layer is the reliable fast path. If it contains
                # no mobile number, render and OCR the page as a scanned/mixed PDF.
                if not digital_phones or any(page.get_objects(filter=[pdfium_c.FPDF_PAGEOBJ_IMAGE])):
                    img = _prepare_image(
                        page.render(scale=settings.pdf_render_scale).to_pil(),
                        settings.max_image_dim,
                    )
                    # Overlapping strips avoid the recognizer's full-page output limit.
                    for band in _page_bands(
                        img, settings.pdf_ocr_bands, settings.pdf_ocr_band_overlap
                    ):
                        add(extract_phones(engine.read_text(band)))
            except Exception:
                # One bad page should not throw away the other 49.
                log.exception("page %d failed", i + 1)
                failed_pages.append(i + 1)
            finally:
                page.close()
            on_progress(i + 1, total, len(phones))
    finally:
        pdf.close()

    if len(failed_pages) == total:
        raise RuntimeError("Could not process any page of the PDF")
    return ExtractResult(phones, failed_pages)
