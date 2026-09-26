"""foldwise init: turn the folders a person already has into a taxonomy plus starter rules."""
import os
from pathlib import Path

from .config import Config, Node
from .inventory import PRUNE, in_repo
from .rules import propose

PARA = {
    "Projects": "active projects with a goal and a deadline",
    "Areas": "ongoing responsibilities: work, business, finances, health, home",
    "Resources": "reference material: notes, research, manuals, design assets",
    "Archives": "finished or inactive material, old exports, backups",
}


def tilde(p: Path) -> str:
    home = Path.home()
    return "~/" + str(p.relative_to(home)) if p.is_relative_to(home) else str(p)


def _subdirs(d: Path) -> list[Path]:
    try:
        return sorted(c for c in d.iterdir() if c.is_dir() and not c.name.startswith(".") and c.name not in PRUNE)
    except OSError:
        return []


def describe(d: Path, sample: int = 8) -> str:
    names: list[str] = []
    for dirpath, dirnames, filenames in os.walk(d):
        dirnames[:] = sorted(x for x in dirnames if not x.startswith(".") and x not in PRUNE)
        names += [Path(n).stem for n in sorted(filenames) if not n.startswith(".")]
        if len(names) >= sample:
            break
    label = d.name.replace("-", " ").replace("_", " ")
    return f"{label}: {', '.join(names[:sample])}"[:240] if names else label


def _node(d: Path, depth: int) -> Node:
    kids = {} if depth <= 1 or in_repo(d) else {tilde(c): _node(c, depth - 1) for c in _subdirs(d)}
    return Node(describe(d), kids)


def build_tree(roots: list[Path], depth: int = 3) -> dict[str, Node]:
    return {tilde(child): _node(child, depth) for root in roots for child in _subdirs(root)}


def para_tree(root: Path) -> dict[str, Node]:
    return {tilde(root / name): Node(desc) for name, desc in PARA.items()}


def init_config(roots: list[Path], inboxes: list[Path]) -> Config:
    first = roots[0]
    cfg = Config(
        inboxes=[tilde(p) for p in inboxes],
        roots=[tilde(p) for p in roots],
        sensitive_dest=tilde(first / "Sensitive"),
        review_dir=tilde(first / "Duplicate-Review"),
        tree=build_tree(roots) or para_tree(first),
    )
    cfg.rules = propose(cfg)
    return cfg
