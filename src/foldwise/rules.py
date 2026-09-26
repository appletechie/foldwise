"""Deterministic rules: checked before any model. propose() finds filename words unique to one folder."""
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

from .config import Config, Rule, expand, is_group, iter_nodes
from .inventory import filed_files

TOKEN = re.compile(r"[a-z]{4,}")
STOPWORDS = {"copy", "final", "draft", "image", "file", "document", "untitled", "screenshot", "scan", "edited",
             "version", "report", "notes", "export", "download", "page"}


def matches(rule: Rule, name: str, text: str) -> bool:
    if rule.match == "name":
        return re.search(rule.pattern, name) is not None
    if rule.match == "content":
        return re.search(rule.pattern, text) is not None
    return re.fullmatch(rule.pattern, Path(name).suffix.lower().lstrip(".")) is not None


def first_match(rules: list[Rule], name: str, text: str) -> Rule | None:
    return next((r for r in rules if matches(r, name, text)), None)


def render_dest(rule: Rule, path: Path) -> Path:
    year = datetime.fromtimestamp(path.lstat().st_mtime).year
    try:
        return expand(rule.dest.format(year=year))
    except (KeyError, ValueError, IndexError):
        return expand(rule.dest)  # a literal {...} in a real folder name is not a placeholder


def _tokens(name: str) -> set[str]:
    return set(TOKEN.findall(Path(name).stem.lower())) - STOPWORDS


def propose(cfg: Config, per_leaf: int = 3, min_files: int = 3) -> list[Rule]:
    leaves = [k for k, n in iter_nodes(cfg.tree) if not n.children and not is_group(k)]
    counts = {leaf: Counter(t for f in filed_files(cfg, [expand(leaf)]) for t in _tokens(f.name)) for leaf in leaves}
    out = []
    for leaf in leaves:
        picked = 0
        for token, n in counts[leaf].most_common():
            if n < min_files or picked == per_leaf:
                break
            if all(token not in counts[other] for other in leaves if other != leaf):
                out.append(Rule("name", rf"(?i)(?<![a-z]){token}(?![a-z])", leaf))
                picked += 1
    return out
