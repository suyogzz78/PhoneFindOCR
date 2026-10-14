import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

def _int(name: str, default: int) -> int:
    return int(os.environ.get(name, default))


@dataclass(frozen=True)
class Settings:
    # Path to the model snapshot folder (the one that contains indic_ocr.py).
    # If empty we try the local Hugging Face cache instead.
    model_path: str = os.environ.get("MODEL_PATH", "")
    # OCR_STUB=1 swaps the real model for a fake one for testing purposes. The stub returna a fixed string for every page, so you can test the API without downloading the model.
    use_stub: bool = os.environ.get("OCR_STUB", "") == "1"

    max_upload_mb: int = _int("MAX_UPLOAD_MB", 50)
    max_pages: int = _int("MAX_PAGES", 50)
    max_queued_jobs: int = _int("MAX_QUEUED_JOBS", 20)
    job_ttl_seconds: int = _int("JOB_TTL_SECONDS", 3600)

    # OCR tuning (same values the original project used)
    # Match the settings that recovered the full text in debug_page.py. Keep these
    # configurable because larger pages and token limits use more memory/time.
    max_image_dim: int = _int("MAX_IMAGE_DIM", 4096)
    max_new_tokens: int = _int("MAX_NEW_TOKENS", 4096)
    pdf_render_scale: float = float(os.environ.get("PDF_RENDER_SCALE", "2.0"))
    pdf_ocr_bands: int = _int("PDF_OCR_BANDS", 6)
    pdf_ocr_band_overlap: int = _int("PDF_OCR_BAND_OVERLAP", 40)

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024
