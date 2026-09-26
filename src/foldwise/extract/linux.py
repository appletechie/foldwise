"""Linux: tesseract OCR and exiftool metadata when installed; empty strings when not."""
import json
from pathlib import Path

from .base import run


def ocr(path: Path, timeout: float) -> str:
    return run(["tesseract", str(path), "-", "--psm", "3"], timeout).decode(errors="ignore")


def metadata(path: Path, timeout: float) -> str:
    out = run(["exiftool", "-j", "-ImageSize", "-Make", "-Model", "-Software", str(path)], timeout)
    try:
        data = (json.loads(out) or [{}])[0] if out else {}
    except (json.JSONDecodeError, IndexError):
        return ""
    parts = []
    if data.get("ImageSize"):
        parts.append(f"{str(data['ImageSize']).replace(' ', 'x')} px")
    if data.get("Model"):
        parts.append(f"camera {data.get('Make', '')} {data['Model']}".replace("  ", " "))
    if data.get("Software"):
        parts.append(f"made with {data['Software']}")
    return " | ".join(parts)
