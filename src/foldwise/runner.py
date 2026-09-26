"""Build a plan: extract (cached), decide, collect. Shared by sort, audit and review."""
from pathlib import Path

from . import model, paths
from .cache import Cache
from .classify import Context, decide, filed_index
from .config import Config
from .plan import Plan, PlanItem


def build_plan(cfg: Config, files: list[Path], command: str, audit: bool = False, models: list | None = None) -> Plan:
    if models is None:
        models = model.load_models(cfg.models, paths.sub("models"))
    ctx = Context(cfg, models, {} if audit else filed_index(cfg, files))
    cache = Cache(paths.sub("cache") / "extract.jsonl")
    items = []
    try:
        for f in files:
            d = decide(f, cache.read(f), ctx)
            if d.action == "skip":
                continue
            if audit:
                if d.action != "move" or f.parent.is_relative_to(d.dest):
                    continue  # audit reports only confident disagreements with where the file already is
                action = "suggest"
            else:
                action = d.action
            items.append(PlanItem(str(f), str(d.dest / f.name) if d.dest else "", action, d.reason,
                                  round(d.confidence, 2)))
    finally:
        cache.close()
    if audit:
        items.sort(key=lambda i: "credential" not in i.reason)
    return Plan(command, items)
