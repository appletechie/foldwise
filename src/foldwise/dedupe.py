"""Byte-identical duplicates. Extras go to the review folder; purge deletes only after re-verifying a twin."""
import hashlib
import re
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path

from .plan import PlanItem

COPY_NAME = re.compile(r"(?i)( \(\d+\)| copy( \d+)?|-\d+)$")
DUMP_DIR = re.compile(r"(?i)downloads?-(review-)?\d{4}|old-download-sorts")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def hash_index(paths: Iterable[Path], sizes: set[int]) -> dict[str, Path]:
    index: dict[str, Path] = {}
    for p in paths:
        if _size(p) in sizes:
            try:
                index.setdefault(sha256(p), p)
            except OSError:
                continue
    return index


def groups(files: Iterable[Path], protect: list[Path]) -> list[tuple[Path, list[Path]]]:
    by_size: dict[int, list[Path]] = defaultdict(list)
    for f in files:
        if (size := _size(f)) > 0:
            by_size[size].append(f)
    by_hash: dict[str, list[Path]] = defaultdict(list)
    for same_size in by_size.values():
        if len(same_size) > 1:
            for f in same_size:
                try:
                    by_hash[sha256(f)].append(f)
                except OSError:
                    continue

    def locked(f: Path) -> bool:
        return any(f.is_relative_to(p) for p in protect)

    out = []
    for same in by_hash.values():
        if len(same) < 2:
            continue
        # keep: a protected copy (it can't move), then a clean name, then not in a dump folder, then shallowest
        keep = min(same, key=lambda f: (not locked(f), bool(COPY_NAME.search(f.stem)),
                                        bool(DUMP_DIR.search(str(f.parent))), len(f.parts), str(f)))
        movable = sorted(f for f in same if f != keep and not locked(f))
        if movable:
            out.append((keep, movable))
    return sorted(out)


def plan_items(found: list[tuple[Path, list[Path]]], review_dir: Path) -> list[PlanItem]:
    return [PlanItem(str(f), str(review_dir / f.name), "move", f"duplicate of {keep}")
            for keep, copies in found for f in copies]


def purge(review_dir: Path, search: Iterable[Path]) -> tuple[list[Path], list[Path]]:
    waiting = sorted(f for f in review_dir.rglob("*") if f.is_file() and not f.name.startswith(".")) \
        if review_dir.is_dir() else []
    sizes = {_size(f) for f in waiting} - {0}
    index = hash_index((p for p in search if not p.is_relative_to(review_dir)), sizes)
    deleted, kept = [], []
    for f in waiting:
        if _size(f) == 0:
            kept.append(f)
            continue
        digest = sha256(f)
        twin = index.get(digest)
        if twin is not None and twin.exists() and sha256(twin) == digest:  # re-verify at delete time
            f.unlink()
            deleted.append(f)
        else:
            kept.append(f)
    return deleted, kept
