"""Training data from the user's own tree: a filed file's folder is its label."""
import json
import random
from collections import Counter, defaultdict
from pathlib import Path

from ..config import Config, Node, expand, is_group, label_path
from ..inventory import filed_files, in_repo
from ..model import question

REPO_EXT = {".md", ".txt", ".pdf", ".docx", ".xlsx", ".csv", ".png", ".jpg", ".jpeg", ".webp", ".pptx", ".html"}


def _levels(tree: dict[str, Node], labels: list[str]) -> list[dict[str, Node]]:
    level, out = tree, []
    for key in labels:
        out.append(level)
        level = level[key].children
    return out


def gather(cfg: Config, rng: random.Random, per_leaf: int = 60, per_repo: int = 8) -> list[Path]:
    repo_cache: dict[str, bool] = {}
    groups: dict[tuple, list[Path]] = defaultdict(list)
    for f in filed_files(cfg):
        labels = label_path(cfg.tree, f)
        if not labels:
            continue
        last = labels[-1]
        if last not in repo_cache:
            repo_cache[last] = not is_group(last) and in_repo(expand(last))
        if repo_cache[last] and f.suffix.lower() not in REPO_EXT:
            continue
        groups[(repo_cache[last], tuple(labels))].append(f)
    files: list[Path] = []
    for (repo, _), group in sorted(groups.items()):
        if repo:
            files += sorted(group, key=lambda f: (len(f.parts), f.name))[:per_repo]
        else:
            group = sorted(group)
            rng.shuffle(group)
            files += group[:per_leaf]
    return files


def frozen_split(files: list[Path], tree: dict[str, Node], test_file: Path,
                 rng: random.Random) -> tuple[list[Path], list[Path]]:
    """One fifth of each folder with 3+ files, chosen once and reused so every run is scored on the same files."""
    if test_file.exists():
        try:
            saved = json.loads(test_file.read_text())
        except json.JSONDecodeError:
            saved = []
        test = [p for p in map(Path, saved) if p.exists() and label_path(tree, p)]
        if len(test) < len(saved):
            print(f"frozen test set shrank {len(saved)} -> {len(test)}: files were deleted or moved out of the "
                  "tree; cross-run scores are less comparable than before")
    else:
        by_label: dict[tuple, list[Path]] = defaultdict(list)
        for f in files:
            by_label[tuple(label_path(tree, f))].append(f)
        test = []
        for _, group in sorted(by_label.items()):
            if len(group) >= 3:
                group = sorted(group)
                rng.shuffle(group)
                test += group[:max(1, len(group) // 5)]
        test.sort()
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text(json.dumps(sorted(map(str, test))))
    held = set(test)
    return [f for f in files if f not in held], test


def variant(state: dict, rng: random.Random) -> dict:
    """A harder copy, like real incoming files: a meaningless filename, or no text at all."""
    if state["content"] and rng.random() < 0.5:
        return {**state, "content": ""}
    return {**state, "filename": f"{rng.getrandbits(128):032x}{Path(state['filename']).suffix}"}


def training_states(files: list[Path], states: dict[Path, dict], tree: dict[str, Node], rng: random.Random,
                    min_per_leaf: int = 8, share: float = 0.5) -> list[tuple[Path, dict]]:
    by_leaf: dict[tuple, list[Path]] = defaultdict(list)
    for f in files:
        by_leaf[tuple(label_path(tree, f))].append(f)
    out: list[tuple[Path, dict]] = []
    for group in by_leaf.values():
        out += [(f, states[f]) for f in group]
        out += [(f, variant(states[f], rng)) for f in group if rng.random() < share]
        for i in range(max(0, min_per_leaf - len(group))):
            f = group[i % len(group)]
            out.append((f, variant(states[f], rng)))
    return out


def items_for(pairs: list[tuple[Path, dict]], tree: dict[str, Node], tok, max_len: int,
              head_max_len: int) -> list[dict]:
    from laya.common import QTYPES, build_sequence

    items = []
    for f, state in pairs:
        labels = label_path(tree, f)
        for level, gold in zip(_levels(tree, labels), labels, strict=True):
            q = question(level)["c"]
            keys = list(q["criteria"])
            if len(keys) < 2:
                continue  # a single-option level teaches nothing
            seq, markers = build_sequence(tok, state, {"t": "choice", "ins": q["instructions"],
                                                       "crit": q["criteria"]}, max_len, head_max_len)
            if len(markers) != len(keys):
                continue
            k = len(keys)
            items.append({"ids": seq, "markers": markers, "qtype": QTYPES["choice"],
                          "target": [0.95 if key == gold else 0.05 / (k - 1) for key in keys],
                          "label": keys.index(gold)})
    return items


def balance(files: list[Path], tree: dict[str, Node]) -> Counter:
    counts: Counter = Counter()
    for f in files:
        labels = label_path(tree, f)
        if labels:
            counts[expand(labels[-1]).name if not is_group(labels[-1]) else labels[-1]] += 1
    return counts
