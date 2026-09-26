"""Extraction cache keyed by path, size and mtime. Stores masked text only."""
import json
from dataclasses import asdict
from pathlib import Path

from . import extract
from .extract import Extracted


def _key(path: Path) -> str:
    st = path.stat()
    return f"{path}|{st.st_size}|{st.st_mtime_ns}"


class Cache:
    def __init__(self, path: Path):
        self.entries: dict[str, Extracted] = {}
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            for line in path.read_text().splitlines():
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:  # a line cut short by a crash
                    continue
                self.entries[d["k"]] = Extracted(**d["v"])
        self.fh = path.open("a")

    def read(self, path: Path, timeout: float = 30.0) -> Extracted:
        try:
            key = _key(path)
        except OSError:
            return Extracted()
        if key not in self.entries:
            self.entries[key] = extract.read(path, timeout)
            self.fh.write(json.dumps({"k": key, "v": asdict(self.entries[key])}) + "\n")
            self.fh.flush()
        return self.entries[key]

    def close(self) -> None:
        self.fh.close()
