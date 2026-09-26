from pathlib import Path

import pytest


@pytest.fixture
def home(tmp_path, monkeypatch):
    """Isolated FOLDWISE_HOME and HOME so nothing touches the real machine."""
    monkeypatch.setenv("FOLDWISE_HOME", str(tmp_path / "fw"))
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path


@pytest.fixture
def make(tmp_path):
    """make({"a/b.txt": "text", "c.bin": b"..."}) creates files under tmp_path and returns tmp_path."""

    def _make(spec: dict[str, str | bytes], root: Path | None = None) -> Path:
        base = root or tmp_path
        for rel, data in spec.items():
            p = base / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(data, bytes):
                p.write_bytes(data)
            else:
                p.write_text(data)
        return base

    return _make
