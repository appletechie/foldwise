"""What to look at: inbox items to sort, and filed files (for audit, dedupe and training)."""
import os
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from .config import Config, expand, is_group, iter_nodes

SYSTEM_FILES = {"Icon\r", "desktop.ini", "Thumbs.db"}
PRUNE = {".git", "node_modules", "__pycache__", ".venv", "venv"}


@dataclass(frozen=True)
class Item:
    path: Path
    kind: str  # "inbox" | "loose"


def skipped(path: Path, cfg: Config) -> bool:
    if path.name.startswith(".") or path.name in SYSTEM_FILES:
        return True
    blocked = cfg.paths("exclude") + [expand(cfg.review_dir)]
    return any(path.is_relative_to(b) for b in blocked)


def inbox_items(cfg: Config) -> list[Item]:
    folders = {expand(k) for k, _ in iter_nodes(cfg.tree) if not is_group(k)}
    items = []
    for inbox in cfg.paths("inboxes"):
        if inbox.is_dir():
            items += [Item(p, "inbox") for p in sorted(inbox.iterdir()) if not skipped(p, cfg) and p not in folders]
    for key, node in iter_nodes(cfg.tree):
        if node.children and not is_group(key) and expand(key).is_dir():  # loose files in a folder that has subfolders
            items += [Item(p, "loose") for p in sorted(expand(key).iterdir()) if p.is_file() and not skipped(p, cfg)]
    return items


def filed_files(cfg: Config, roots: list[Path] | None = None, skip_snapshots: bool = False) -> Iterator[Path]:
    blocked = cfg.paths("exclude") + [expand(cfg.review_dir)] + (cfg.paths("snapshots") if skip_snapshots else [])
    for root in roots or cfg.paths("roots"):
        if not root.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            here = Path(dirpath)
            dirnames[:] = [d for d in dirnames
                           if not d.startswith(".") and d not in PRUNE and not any((here / d) == b for b in blocked)]
            if any(here.is_relative_to(b) for b in blocked):
                dirnames[:] = []
                continue
            for name in filenames:
                p = here / name
                if not name.startswith(".") and name not in SYSTEM_FILES and not p.is_symlink():
                    yield p


def in_repo(path: Path) -> bool:
    return any((parent / ".git").exists() for parent in [path, *path.parents])
