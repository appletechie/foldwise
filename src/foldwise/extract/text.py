import re
import zipfile
from pathlib import Path

from .base import run

MAX_BYTES = 200_000
OFFICE_MEMBERS = {".docx": ("word/document.xml",), ".xlsx": ("xl/sharedStrings.xml",)}


def _office(path: Path) -> str:
    try:
        with zipfile.ZipFile(path) as z:
            wanted = OFFICE_MEMBERS.get(path.suffix.lower(), ())
            names = [n for n in z.namelist() if n in wanted or n.startswith("ppt/slides/slide")]
            xml = " ".join(z.read(n).decode(errors="ignore") for n in names)
    except (zipfile.BadZipFile, OSError, KeyError):
        return ""
    return re.sub(r"<[^>]+>", " ", xml)


def _pdf(path: Path, timeout: float) -> str:
    out = run(["pdftotext", "-l", "3", str(path), "-"], timeout)
    if out.strip():
        return out.decode(errors="ignore")
    from pypdf import PdfReader

    try:
        reader = PdfReader(str(path))
        return "\n".join((page.extract_text() or "") for page in reader.pages[:3])
    except Exception:  # pypdf raises many exception types on malformed files; any of them means "no text"
        return ""


def read_text(path: Path, timeout: float) -> tuple[str, str]:
    ext = path.suffix.lower()
    if path.is_dir():
        names = sorted(p.name for p in path.iterdir() if not p.name.startswith("."))[:100]
        return "folder containing: " + ", ".join(names), "listing"
    if ext == ".pdf":
        return _pdf(path, timeout), "text"
    if ext in (".docx", ".xlsx", ".pptx"):
        return _office(path), "text"
    if ext == ".zip":
        try:
            with zipfile.ZipFile(path) as z:
                return "zip archive containing: " + ", ".join(z.namelist()[:100]), "listing"
        except (zipfile.BadZipFile, OSError):
            return "", "none"
    with path.open("rb") as fh:
        raw = fh.read(MAX_BYTES)
    if b"\x00" in raw[:4096]:
        return "", "none"
    return raw.decode("utf-8", errors="ignore"), "text"
