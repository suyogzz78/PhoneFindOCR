"""The OCR engine. Everything model-specific lives in this one file."""
import sys
import tempfile
import threading
from pathlib import Path
from typing import Protocol

from PIL import Image

from .config import Settings
# from abc import ABC,abstractmethod


class OcrEngine(Protocol):
    """Protocol for an OCR engine. Implementations must be thread-safe."""
    
    # ellipsis literal (...) used to unset the method body, indicating that subclasses must implement this method.
    def read_text(self, img: Image.Image) -> str: ...

""" Usage of  yield helps to create a generator that can produce a sequence of values over time, rather than computing them all at once and returning them in a list. This is particularly useful for traversing nested data structures, as it allows you to yield values as they are found, without needing to store them all in memory at once. In this case, _all_strings is a recursive generator function that yields all string values found within a nested structure (which can be a string, dictionary, list, or tuple). This approach is memory-efficient and allows for lazy evaluation of the strings in the structure."""
def _all_strings(value: object):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from _all_strings(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            yield from _all_strings(child)


class IndicOcrEngine:
    """Wraps bodhan-ai/indic-ocr. Loaded once at startup (~3 GB RAM)."""

    def __init__(self, model_dir: str, max_new_tokens: int): 
        sys.path.insert(0, model_dir)
        from indic_ocr import IndicOCR  # type: ignore  (lives inside the model folder)

        self._model = IndicOCR.from_pretrained(model_dir, max_new_tokens=max_new_tokens)
        _ = self._model.recognizer  # force weights into RAM now, not on first request
        # The model is not thread-safe and the GPU is a single resource.
        self._lock = threading.Lock()

    """Reads text from an image.Uses the above protocol """
    def read_text(self, img: Image.Image) -> str:
        # model.parse() takes a file path, so write the image to a temp file
        with tempfile.TemporaryDirectory() as tmp, self._lock:
            path = Path(tmp) / "page.png"
            img.save(path)
            res = self._model.parse(str(path))
        return "\n".join(_all_strings(res))

class StubOcrEngine:
    """Fake engine for tests : always 'reads' the same two numbers,using this we can test the entire pipeline without loading the real model (~3 GB RAM)."""

    def read_text(self, img: Image.Image) -> str:
        return "Ram 98412 34567\nSita +977-9851234567"


def _find_model_dir(settings: Settings) -> str:
    if settings.model_path:
        if not Path(settings.model_path).is_dir():
            raise RuntimeError(f"MODEL_PATH does not exist: {settings.model_path}")
        return settings.model_path
    # Fallback: look in the local Hugging Face cache (no network).
    from huggingface_hub import snapshot_download

    return snapshot_download("bodhan-ai/indic-ocr", local_files_only=True)


def load_engine(settings: Settings) -> OcrEngine:
    
    #if the stub is enabled , then return the stub engine which is a fake engine
    if settings.use_stub:
        return StubOcrEngine()
    #else use a real engine which is the indiocr engine
    return IndicOcrEngine(_find_model_dir(settings), settings.max_new_tokens)
