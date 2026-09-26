"""laya ensemble: walk the tree level by level; every model must agree, and the weakest confidence decides."""
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .config import Node, Policy, is_group
from .extract import Extracted

QUESTION = "Which folder does this file belong in?"
NO_NAME = re.compile(r"(?i)^([0-9a-f]{8,}|[0-9a-f-]{32,}|image|unnamed|untitled|download|img_\d+|dsc_?\d+|pxl_\d+)"
                     r"( ?\(\d+\))?$")

_CACHE: dict = {}


class Predictor(Protocol):
    def predict(self, state: dict, questions: dict) -> dict: ...


def meaningless(stem: str) -> bool:
    return NO_NAME.match(stem) is not None


def state_for(name: str, ex: Extracted) -> dict:
    return {"filename": name, "metadata": ex.metadata, "content": ex.text}


def question(level: dict[str, Node]) -> dict:
    return {"c": {"type": "choice", "instructions": QUESTION, "criteria": {k: n.desc for k, n in level.items()}}}


def threshold(policy: Policy, n_models: int) -> float:
    return policy.min_confidence if n_models > 1 else policy.min_confidence_single


@dataclass
class Descent:
    path: list[str]
    confidence: float
    dest: str | None
    held: str | None


def descend(tree: dict[str, Node], state: dict, models: list[Predictor], min_conf: float) -> Descent:
    level, path, conf, dest = tree, [], 1.0, None
    while level:
        answers = [m.predict(state, question(level))["answers"]["c"] for m in models]
        conf = min([conf] + [a["answer_confidence"] for a in answers])
        choice = answers[0]["choice"]
        path.append(choice)
        if len({a["choice"] for a in answers}) > 1:
            return Descent(path, conf, None, "models disagree")
        if conf < min_conf:
            return Descent(path, conf, None, "low confidence")
        node = level[choice]
        if node.hold:
            return Descent(path, conf, None, "held folder")
        dest = node.dest or (None if is_group(choice) else choice)
        level = node.children
    return Descent(path, conf, dest, None if dest else "no folder chosen")


def load_models(names: list[str], models_dir: Path) -> list[Predictor]:
    found = [models_dir / n for n in names if (models_dir / n / "rl_agent_config.json").exists()]
    if not found:
        return []
    from laya import Agent  # imported here so commands that never classify with a model start fast

    # Cache per checkpoint mtime, so repeated preview_sort calls (notably over MCP) reuse
    # loaded models while a retrain (new mtime) is still picked up, even by long-lived servers.
    try:
        key = tuple((str(p), (p / "rl_agent_config.json").stat().st_mtime_ns) for p in found)
    except OSError:
        key = None
    if key is not None and key in _CACHE:
        return _CACHE[key]
    models = [Agent(str(p)) for p in found]
    if key is not None:
        _CACHE[key] = models
    return models
