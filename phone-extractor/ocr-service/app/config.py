import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

def _int(name: str, default: int) -> int:
    value = os.environ.get(name)
    try:
        return int(value) if value is not None else default
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc


def _float(name: str, default: float) -> float:
    value = os.environ.get(name)
    try:
        return float(value) if value is not None else default
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a number") from exc


@dataclass(frozen=True)
class Settings:
    # Path to the model snapshot folder (the one that contains indic_ocr.py).
    # If empty we try the local Hugging Face cache instead.
    model_path: str = os.environ.get("MODEL_PATH", "")
    # OCR_STUB=1 swaps the real model for a fake one for testing purposes.
    use_stub: bool = os.environ.get("OCR_STUB", "") == "1"
    # Set this when the service is reachable over a network. Express sends it
    # as X-OCR-Token. Leaving it empty preserves local development behavior.
    internal_token: str = os.environ.get("OCR_INTERNAL_TOKEN", "")
    redis_url: str = os.environ.get("REDIS_URL", "")

    max_upload_mb: int = _int("MAX_UPLOAD_MB", 50)
    max_pages: int = _int("MAX_PAGES", 50)
    max_queued_jobs: int = _int("MAX_QUEUED_JOBS", 20)
    job_ttl_seconds: int = _int("JOB_TTL_SECONDS", 3600)

    # OCR tuning (same values the original project used)
    # Match the settings that recovered the full text in debug_page.py. Keep these
    # configurable because larger pages and token limits use more memory/time.
    max_image_dim: int = _int("MAX_IMAGE_DIM", 4096)
    max_new_tokens: int = _int("MAX_NEW_TOKENS", 4096)
    pdf_render_scale: float = _float("PDF_RENDER_SCALE", 2.0)
    pdf_ocr_bands: int = _int("PDF_OCR_BANDS", 6)
    pdf_ocr_band_overlap: int = _int("PDF_OCR_BAND_OVERLAP", 40)

    def __post_init__(self) -> None:
        positive = {
            "max_upload_mb": self.max_upload_mb,
            "max_pages": self.max_pages,
            "job_ttl_seconds": self.job_ttl_seconds,
            "max_image_dim": self.max_image_dim,
            "max_new_tokens": self.max_new_tokens,
            "pdf_render_scale": self.pdf_render_scale,
            "pdf_ocr_bands": self.pdf_ocr_bands,
        }
        invalid = [name for name, value in positive.items() if value <= 0]
        if self.max_queued_jobs < 0:
            invalid.append("max_queued_jobs")
        if invalid:
            raise RuntimeError(f"{', '.join(invalid)} must be greater than zero")
        if self.pdf_ocr_band_overlap < 0:
            raise RuntimeError("pdf_ocr_band_overlap must not be negative")

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024
