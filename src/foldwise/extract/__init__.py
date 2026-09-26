import sys
from pathlib import Path

from .. import sensitive
from .base import Extracted, run
from .text import read_text

__all__ = ["Extracted", "run", "read", "IMAGE_EXT", "TEXT_LIMIT"]

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".heic", ".tiff", ".bmp"}
TEXT_LIMIT = 6000


def _platform():
    if sys.platform == "darwin":
        from . import macos as plat
    else:
        from . import linux as plat
    return plat


def read(path: Path, timeout: float = 30.0) -> Extracted:
    """Text and metadata for one file or folder. Never raises: unreadable means empty."""
    plat = _platform()
    try:
        if path.is_file() and path.suffix.lower() in IMAGE_EXT:
            raw, source = plat.ocr(path, timeout), "ocr"
        else:
            raw, source = read_text(path, timeout)
        meta = plat.metadata(path, timeout) if path.is_file() else ""
    except OSError:  # vanished, permission denied, unreadable volume
        return Extracted()
    flat = " ".join(raw.split())
    return Extracted(
        text=sensitive.mask(flat)[:TEXT_LIMIT],
        metadata=meta,
        source=source if flat else "none",
        sensitive=sensitive.is_sensitive(flat),
    )
