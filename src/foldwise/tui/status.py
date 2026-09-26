"""foldwise status: the tree with file counts, what is waiting, the last plan, move history, models."""
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree

from .. import inventory, paths
from .. import plan as plans
from ..bootstrap import tilde
from ..config import Config, Node, expand, is_group, label_path


def _counts(cfg: Config) -> Counter:
    """One filed_files walk over all roots, bucketed by every ancestor folder on the label path.

    Keeps `status` O(tree) instead of one walk per taxonomy node (too slow on 90k-file trees)."""
    counts: Counter = Counter()
    for f in inventory.filed_files(cfg):
        for key in label_path(cfg.tree, f):
            if not is_group(key):
                counts[expand(key)] += 1
    return counts


def _count(path: Path, counts: Counter) -> int:
    return sum(n for p, n in counts.items() if p == path or p.is_relative_to(path))


def _folders(children: dict[str, Node]) -> set[Path]:
    out: set[Path] = set()
    for key, node in children.items():
        out |= _folders(node.children) if is_group(key) else {expand(key)}
    return out


def _add(parent: Tree, key: str, node: Node, cfg: Config, counts: Counter) -> None:
    if is_group(key):
        branch = parent.add(f"[bold]{escape(key)}[/]")
    else:
        p = expand(key)
        name = escape(p.name)
        if inventory.in_repo(p):
            branch = parent.add(f"{name} [dim]repo[/]")
        else:
            label = f"[bold]{name}[/]" if node.children else name
            branch = parent.add(f"{label} [cyan]{_count(p, counts)}[/]")
    for k, child in node.children.items():
        _add(branch, k, child, cfg, counts)
    if node.children and not is_group(key) and expand(key).is_dir():
        known = _folders(node.children)
        for d in sorted(x for x in expand(key).iterdir()
                        if x.is_dir() and not x.name.startswith(".") and x not in known):
            branch.add(f"[dim]{escape(d.name)} {_count(d, counts)} (not in taxonomy)[/]")


def _tree(cfg: Config, counts: Counter) -> Tree:
    t = Tree("[bold]Folders[/]  [dim]files per folder, including subfolders[/]")
    for key, node in cfg.tree.items():
        _add(t, key, node, cfg, counts)
    return t


def _waiting(cfg: Config) -> Panel:
    items = inventory.inbox_items(cfg)
    review = expand(cfg.review_dir)
    in_review = sum(1 for f in review.rglob("*") if f.is_file() and not f.name.startswith(".")) \
        if review.is_dir() else 0
    table = Table(show_header=False, box=None)
    for folder, n in Counter(tilde(i.path.parent) for i in items).most_common():
        table.add_row(f"[yellow]{n}[/]", escape(folder))
    if in_review:
        table.add_row(f"[magenta]{in_review}[/]", "in the duplicate review folder (foldwise dedupe --purge)")
    body = table if table.row_count else "[green]All inboxes clear[/]"
    return Panel(body, title=f"Waiting to sort: {len(items)}", border_style="yellow" if items else "green")


def _last_plan() -> Panel:
    pp = plans.latest(paths.sub("plans"))
    if pp is None:
        return Panel("[dim]no plan yet: run foldwise sort[/]", title="Last plan")
    p = plans.load(pp)
    pending = [i for i in p.items if i.action in ("move", "suggest") and Path(i.src).exists()]
    held = [i for i in p.items if i.action == "hold" and Path(i.src).exists()]
    title = f"Last plan: {p.command}, {p.created[:16].replace('T', ' ')}"
    if p.applied_at:
        body = f"[green]applied {p.applied_at[:16].replace('T', ' ')}[/]" + (f", {len(held)} held" if held else "")
        return Panel(body, title=title)
    table = Table(box=None)
    for col in ("", "file", "why"):
        table.add_column(col)
    for i in (pending + held)[:15]:
        table.add_row(i.action, escape(Path(i.src).name), escape(i.reason))
    table.caption = f"{len(pending)} to move, {len(held)} held: run foldwise apply"
    return Panel(table, title=title)


def _history() -> Panel:
    table = Table(box=None)
    for col in ("run", "moved", "mostly to", "undo"):
        table.add_column(col)
    for j in sorted(paths.sub("journal").glob("*.jsonl")):
        moves = [json.loads(line) for line in j.read_text().splitlines()]
        when = datetime.strptime(j.name[:15], "%Y%m%d-%H%M%S").strftime("%Y-%m-%d %H:%M")
        top = Counter(tilde(Path(m["dest"]).parent) for m in moves).most_common(2)
        undo = "[dim]undone[/]" if j.name.endswith(".undone.jsonl") else f"foldwise undo {j.name}"
        table.add_row(when, str(len(moves)), escape(", ".join(f"{d} ({n})" for d, n in top)), undo)
    return Panel(table if table.row_count else "[dim]no moves yet[/]", title="Move history")


def _models(cfg: Config) -> Panel:
    models_dir = paths.sub("models")
    found = [m for m in cfg.models if (models_dir / m / "rl_agent_config.json").exists()]
    lines = [f"[green]{escape(m)}[/]" for m in found] or ["[yellow]no fine-tuned model[/]: rules only "
                                                          "(run foldwise train)"]
    agree = "all models must agree, " if len(found) > 1 else ""
    threshold = cfg.policy.min_confidence if len(found) > 1 else cfg.policy.min_confidence_single
    lines.append(f"{len(cfg.rules)} rules; auto-move when {agree}confidence >= {threshold}")
    return Panel("\n".join(lines), title="Models")


def render(cfg: Config, console: Console) -> None:
    console.print(_tree(cfg, _counts(cfg)))
    for panel in (_waiting(cfg), _last_plan(), _history(), _models(cfg)):
        console.print(panel)
