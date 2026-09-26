import os
import sys
import time
import zipfile
from pathlib import Path

import pytest

from foldwise import extract
from foldwise.extract import base, text


# Minimal one-page PDF with the text "Invoice 4411" (Helvetica), built with a real xref table so
# pypdf (the fallback when pdftotext is absent, as on CI runners) can parse it too.
def _pdf_with_xref(objects: list[bytes]) -> bytes:
    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for i, obj in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode() + b"0000000000 65535 f \n"
    for off in offsets[1:]:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


_CONTENT = b"BT /F1 18 Tf 20 60 Td (Invoice 4411) Tj ET\n"
PDF = _pdf_with_xref([
    b"<< /Type /Catalog /Pages 2 0 R >>",
    b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 144] /Contents 4 0 R"
    b" /Resources << /Font << /F1 5 0 R >> >> >>",
    b"<< /Length %d >>\nstream\n" % len(_CONTENT) + _CONTENT + b"endstream",
    b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
])


def docx(path: Path, body: str) -> Path:
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("word/document.xml", f"<w:document><w:body><w:t>{body}</w:t></w:body></w:document>")
    return path


def test_run_times_out_and_tolerates_missing_binaries():
    t0 = time.monotonic()
    assert base.run(["sleep", "5"], timeout=0.5) == b""
    assert time.monotonic() - t0 < 3
    assert base.run(["definitely-not-a-real-binary-xyz"]) == b""


def test_plain_text_with_awkward_name(make):
    root = make({"QR Code & Confirmation: Winter Las Vegas 2024 — ünï.txt": "badge pick-up Tuesday"})
    ex = extract.read(root / "QR Code & Confirmation: Winter Las Vegas 2024 — ünï.txt")
    assert ex.text == "badge pick-up Tuesday" and ex.source == "text"


def test_pdf_office_zip_and_folder(make, tmp_path):
    root = make({"inv.pdf": PDF, "dir/a.md": "x", "dir/b.md": "y"})
    assert "Invoice 4411" in extract.read(root / "inv.pdf").text
    assert "Quarterly plan" in extract.read(docx(tmp_path / "plan.docx", "Quarterly plan")).text
    with zipfile.ZipFile(tmp_path / "kit.zip", "w") as z:
        z.writestr("cut-list.md", "x")
    assert "cut-list.md" in extract.read(tmp_path / "kit.zip").text
    assert extract.read(root / "dir").text == "folder containing: a.md, b.md"


def test_odd_files_return_empty_without_raising(make, tmp_path):
    root = make({"empty.txt": b"", "fake.txt": b"\x00\x01\x02binary", "bad.zip": b"not a zip", "bad.docx": b"nope",
                 "bad.pdf": b"%PDF-garbage"})
    for name in ("empty.txt", "fake.txt", "bad.zip", "bad.docx", "bad.pdf"):
        ex = extract.read(root / name)
        assert ex.text == "" and ex.source == "none", name
    assert extract.read(tmp_path / "vanished.txt").source == "none"


def test_large_files_are_read_in_bounded_chunks(make):
    root = make({"huge.log": "line of log text\n" * 600_000})
    ex = extract.read(root / "huge.log")
    assert 0 < len(ex.text) <= extract.TEXT_LIMIT


@pytest.mark.skipif(os.geteuid() == 0, reason="root can read anything")
def test_permission_denied(make):
    root = make({"locked.txt": "secret plans"})
    (root / "locked.txt").chmod(0)
    try:
        assert extract.read(root / "locked.txt").source == "none"
    finally:
        (root / "locked.txt").chmod(0o644)


def test_secrets_are_flagged_and_masked(make):
    key = "sk-" + "Z9y8X7w6V5u4T3s2R1q0P9o8"
    root = make({"notes.md": f"deploy with {key} tomorrow"})
    ex = extract.read(root / "notes.md")
    assert ex.sensitive and key not in ex.text


def test_text_reader_limits(make):
    root = make({"a.txt": "abc"})
    assert text.read_text(root / "a.txt", 5) == ("abc", "text")
    assert text.MAX_BYTES == 200_000


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS only")
def test_macos_ocr_child_process_on_blank_png(tmp_path):
    pytest.importorskip("Vision")
    import struct
    import zlib

    def png(w, h):
        raw = b"".join(b"\x00" + b"\xff\xff\xff" * w for _ in range(h))
        chunk = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d))  # noqa: E731
        return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))

    (tmp_path / "blank.png").write_bytes(png(64, 64))
    ex = extract.read(tmp_path / "blank.png")
    assert ex.source in ("ocr", "none")
    assert "64x64 px" in ex.metadata or ex.metadata == ""
