"""The decision pipeline, first match wins: protected, duplicate, credential, rule, meaningless name, model."""
from dataclasses import dataclass, field
from pathlib import Path

from .config import Config, expand
from .dedupe import hash_index, sha256
from .extract import Extracted
from .inventory import filed_files, in_repo
from .model import descend, meaningless, state_for, threshold
from .rules import first_match, render_dest


@dataclass
class Decision:
    action: str  # "move" | "hold" | "skip"
    dest: Path | None
    reason: str
    confidence: float = 1.0


@dataclass
class Context:
    cfg: Config
    models: list
    filed: dict[str, Path]
    seen: dict[str, Path] = field(default_factory=dict)


def filed_index(cfg: Config, incoming: list[Path]) -> dict[str, Path]:
    """Hashes of filed files whose size matches an incoming file (only those are worth hashing)."""
    sizes = set()
    for p in incoming:
        try:
            if p.is_file():
                sizes.add(p.stat().st_size)
        except OSError:
            continue
    sizes.discard(0)
    skip = set(incoming)
    return hash_index((f for f in filed_files(cfg, skip_snapshots=True) if f not in skip), sizes)


def _digest(path: Path) -> str | None:
    try:
        return sha256(path) if path.is_file() and path.stat().st_size > 0 else None
    except OSError:
        return None


def decide(path: Path, ex: Extracted, ctx: Context) -> Decision:
    cfg = ctx.cfg
    if any(path.is_relative_to(p) for p in cfg.paths("protect")):
        return Decision("skip", None, "protected")
    digest = _digest(path)
    if digest:
        twin = ctx.filed.get(digest) or ctx.seen.get(digest)
        if twin is not None and twin != path:
            return Decision("move", expand(cfg.review_dir), f"duplicate of {twin}")
        ctx.seen[digest] = path
    if ex.sensitive:
        return Decision("move", expand(cfg.sensitive_dest), "contains a credential")
    rule = first_match(cfg.rules, path.name, ex.text)
    if rule:
        return Decision("move", render_dest(rule, path), f"rule {rule.pattern}")
    if cfg.policy.hold_meaningless_names and meaningless(path.stem):
        return Decision("hold", None, "meaningless name", 0.0)
    if not ctx.models:
        return Decision("hold", None, "no fine-tuned model yet (run `foldwise train`)", 0.0)
    d = descend(cfg.tree, state_for(path.name, ex), ctx.models, threshold(cfg.policy, len(ctx.models)))
    if d.held:
        return Decision("hold", None, d.held, d.confidence)
    dest = expand(d.dest)
    if cfg.repos == "hold" and in_repo(dest):
        return Decision("hold", dest, "destination is inside a git repo", d.confidence)
    return Decision("move", dest, "model", d.confidence)
