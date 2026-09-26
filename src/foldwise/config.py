"""taxonomy.yaml: the user's folder tree, rules, and policy. Keys are paths as written (~/...) or grouping labels."""
from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import asdict, dataclass, field
from pathlib import Path

import yaml

MAX_CHILDREN = 8
MATCH_KINDS = ("name", "content", "ext")


def expand(p: str | Path) -> Path:
    return Path(p).expanduser()


def is_group(key: str) -> bool:
    """A grouping node (e.g. "Client work") is a choice level with no folder of its own."""
    return not key.startswith(("~", "/"))


@dataclass
class Node:
    desc: str
    children: dict[str, Node] = field(default_factory=dict)
    dest: str | None = None
    hold: bool = False


@dataclass
class Rule:
    match: str
    pattern: str
    dest: str


@dataclass
class Policy:
    min_confidence: float = 0.75
    min_confidence_single: float = 0.85
    hold_meaningless_names: bool = True


@dataclass
class Config:
    inboxes: list[str]
    roots: list[str]
    sensitive_dest: str
    review_dir: str
    exclude: list[str] = field(default_factory=list)
    protect: list[str] = field(default_factory=list)
    snapshots: list[str] = field(default_factory=list)
    repos: str = "hold"
    policy: Policy = field(default_factory=Policy)
    tree: dict[str, Node] = field(default_factory=dict)
    rules: list[Rule] = field(default_factory=list)
    models: list[str] = field(default_factory=list)
    llm: dict = field(default_factory=dict)
    version: int = 1

    def paths(self, name: str) -> list[Path]:
        return [expand(p) for p in getattr(self, name)]


def _node_from(d: dict) -> Node:
    return Node(
        desc=d.get("desc", ""),
        children={k: _node_from(v) for k, v in (d.get("children") or {}).items()},
        dest=d.get("dest"),
        hold=bool(d.get("hold", False)),
    )


def _node_to(n: Node) -> dict:
    out: dict = {"desc": n.desc}
    if n.children:
        out["children"] = {k: _node_to(v) for k, v in n.children.items()}
    if n.dest:
        out["dest"] = n.dest
    if n.hold:
        out["hold"] = True
    return out


def from_dict(d: dict) -> Config:
    return Config(
        inboxes=d.get("inboxes", []),
        roots=d.get("roots", []),
        sensitive_dest=d["sensitive_dest"],
        review_dir=d["review_dir"],
        exclude=d.get("exclude", []),
        protect=d.get("protect", []),
        snapshots=d.get("snapshots", []),
        repos=d.get("repos", "hold"),
        policy=Policy(**d.get("policy", {})),
        tree={k: _node_from(v) for k, v in (d.get("tree") or {}).items()},
        rules=[Rule(**r) for r in d.get("rules", [])],
        models=d.get("models", []),
        llm=d.get("llm", {}),
        version=d.get("version", 1),
    )


def to_dict(c: Config) -> dict:
    return {
        "version": c.version,
        "inboxes": c.inboxes,
        "roots": c.roots,
        "exclude": c.exclude,
        "protect": c.protect,
        "snapshots": c.snapshots,
        "sensitive_dest": c.sensitive_dest,
        "review_dir": c.review_dir,
        "repos": c.repos,
        "policy": asdict(c.policy),
        "models": c.models,
        "llm": c.llm,
        "tree": {k: _node_to(v) for k, v in c.tree.items()},
        "rules": [asdict(r) for r in c.rules],
    }


def load(path: Path) -> Config:
    return from_dict(yaml.safe_load(path.read_text()))


def save(c: Config, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(yaml.safe_dump(to_dict(c), sort_keys=False, allow_unicode=True))
    tmp.replace(path)


def iter_nodes(tree: dict[str, Node]) -> Iterator[tuple[str, Node]]:
    for key, node in tree.items():
        yield key, node
        yield from iter_nodes(node.children)


def validate(c: Config) -> list[str]:
    problems = []
    for key, node in iter_nodes(c.tree):
        if len(node.children) > MAX_CHILDREN:
            problems.append(f"{key}: {len(node.children)} children (max {MAX_CHILDREN}); "
                            f"group them so each choice has at most {MAX_CHILDREN} options")
        if is_group(key) and not node.children:
            problems.append(f"{key}: a grouping node needs at least one folder under it")
    for r in c.rules:
        if r.match not in MATCH_KINDS:
            problems.append(f"rule {r.pattern!r}: match must be one of {', '.join(MATCH_KINDS)}, not {r.match!r}")
        try:
            re.compile(r.pattern)
        except re.error as e:
            problems.append(f"rule {r.pattern!r}: {e}")
    return problems


def contains(key: str, node: Node, path: Path) -> bool:
    if not is_group(key):
        return path.is_relative_to(expand(key))
    return any(contains(k, n, path) for k, n in node.children.items())


def label_path(tree: dict[str, Node], path: Path) -> list[str]:
    """The chain of tree keys that leads to the folder holding `path` (empty when it is outside the tree)."""
    level, out = tree, []
    while level:
        k = next((k for k in level if contains(k, level[k], path)), None)
        if k is None:
            break
        out.append(k)
        level = level[k].children
    return out
