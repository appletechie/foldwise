"""Score models on the frozen test set the way sort uses them: full descent, weakest confidence, agreement."""
from pathlib import Path

from ..config import Node, label_path
from ..model import question


def walk(models: list, state: dict, tree: dict[str, Node], depth: int) -> tuple[list, float]:
    if not models:
        raise ValueError("no models to evaluate: run `foldwise train` first, or pass models explicitly")
    level, path, conf = tree, [], 1.0
    while level and len(path) < depth:
        answers = [m.predict(state, question(level))["answers"]["c"] for m in models]
        if len({a["choice"] for a in answers}) > 1:
            return path + [None], 0.0  # disagreement never auto-moves
        conf = min([conf] + [a["answer_confidence"] for a in answers])
        path.append(answers[0]["choice"])
        level = level[answers[0]["choice"]].children
    return path, conf


def evaluate(models: list, files: list[Path], states: dict[Path, dict], tree: dict[str, Node],
             min_conf: float) -> dict:
    rows = []
    for f in files:
        labels = label_path(tree, f)
        path, conf = walk(models, states[f], tree, len(labels))
        rows.append((conf, path == labels))
    n = len(rows) or 1
    confident = [ok for c, ok in rows if c >= min_conf]
    best_k, best_threshold, hits = 0, None, 0
    for k, (c, ok) in enumerate(sorted(rows, key=lambda r: -r[0]), 1):
        hits += ok
        if hits / k >= 0.95:
            best_k, best_threshold = k, c
    return {"files": len(rows), "accuracy": sum(ok for _, ok in rows) / n, "auto_share": len(confident) / n,
            "auto_precision": sum(confident) / max(1, len(confident)), "coverage95": best_k / n,
            "threshold95": best_threshold}
