"""foldwise command line. Commands build plans; only `apply`, `sort --apply` and `dedupe --purge` change files."""
from pathlib import Path

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from . import config, dedupe, inventory, mover, paths
from . import plan as plans
from .bootstrap import init_config, tilde
from .config import Config, expand

app = typer.Typer(no_args_is_help=True, help="Learn your folder tree and keep it organized.")
console = Console()
ACTION = {"move": "[green]move[/]", "hold": "[yellow]hold[/]", "suggest": "[cyan]suggest[/]"}


def load_cfg() -> Config:
    f = paths.config_file()
    if not f.exists():
        console.print("No config yet. Run [bold]foldwise init[/] first.")
        raise typer.Exit(1)
    return config.load(f)


def show(p: plans.Plan, limit: int = 200) -> None:
    table = Table(box=None)
    for col in ("", "file", "to", "why"):
        table.add_column(col)
    for i in p.items[:limit]:
        dest = tilde(Path(i.dest).parent) if i.dest else ""
        table.add_row(ACTION[i.action], escape(Path(i.src).name), escape(dest), escape(i.reason))
    console.print(table)
    counts = {a: sum(i.action == a for i in p.items) for a in ACTION}
    more = f" ({len(p.items) - limit} more not shown)" if len(p.items) > limit else ""
    console.print(f"{counts['move']} to move, {counts['hold']} held, {counts['suggest']} suggested{more}")


def resolve(arg: Path | None, directory: Path, latest) -> Path | None:
    if arg is None:
        return latest(directory)
    return arg if arg.exists() else directory / arg.name


def build(cfg: Config, files: list[Path], command: str, audit: bool = False) -> plans.Plan:
    from .runner import build_plan

    return build_plan(cfg, files, command, audit=audit)


def apply_path(pp: Path, actions: tuple[str, ...] = ("move",)) -> None:
    journal, moved, skipped = mover.apply(pp, paths.sub("journal"), actions)
    for s in skipped:
        console.print(f"[yellow]skipped[/] {escape(s)}")
    console.print(f"Moved {moved}. Undo with: foldwise undo {journal.name}")


@app.command()
def init(
    root: list[Path] = typer.Option(None, help="Organized folder to learn from (repeatable)"),
    inbox: list[Path] = typer.Option(None, help="Folder to sort (repeatable; default Downloads and Desktop)"),
    force: bool = typer.Option(False, help="Overwrite an existing config"),
):
    """Build taxonomy.yaml from the folders you already have."""
    f = paths.config_file()
    if f.exists() and not force:
        console.print(f"{f} already exists; pass --force to rebuild it.")
        raise typer.Exit(1)
    home = Path.home()
    roots = [p.expanduser() for p in root] if root else [p for p in [home / "Documents"] if p.is_dir()]
    inboxes = [p.expanduser() for p in inbox] if inbox else [p for p in (home / "Downloads", home / "Desktop")
                                                              if p.is_dir()]
    if not roots:
        console.print("No organized folder found; pass --root.")
        raise typer.Exit(1)
    cfg = init_config(roots, inboxes)
    config.save(cfg, f)
    folders = sum(1 for _ in config.iter_nodes(cfg.tree))
    console.print(f"Wrote {f}: {folders} folders, {len(cfg.rules)} proposed rules.")
    for problem in config.validate(cfg):
        console.print(f"[yellow]check:[/] {escape(problem)}")
    console.print("Review that file, then run [bold]foldwise train[/] to fine-tune the model on your folders, "
                  "and [bold]foldwise sort[/] to preview.")


@app.command()
def sort(
    apply_now: bool = typer.Option(False, "--apply", help="Move confident items right away"),
    path: list[Path] = typer.Option(None, help="Sort these files instead of the inboxes"),
):
    """Preview where inbox files would go (add --apply to move them)."""
    cfg = load_cfg()
    files = [p.expanduser() for p in path] if path else [i.path for i in inventory.inbox_items(cfg)]
    p = build(cfg, files, "sort")
    pp = plans.save(p, paths.sub("plans"))
    show(p)
    if apply_now:
        apply_path(pp)
    else:
        console.print("Preview only. Run [bold]foldwise apply[/] to move.")


@app.command()
def apply(
    plan_file: Path = typer.Argument(None, help="Plan to apply (default: the latest)"),
    include_suggested: bool = typer.Option(False, help="Also apply audit suggestions"),
):
    """Apply a plan exactly as written."""
    pp = resolve(plan_file, paths.sub("plans"), plans.latest)
    if pp is None or not pp.exists():
        console.print("No plan to apply.")
        raise typer.Exit(1)
    if plans.load(pp).applied_at:
        console.print(f"{pp.name} was already applied.")
        raise typer.Exit(1)
    apply_path(pp, ("move", "suggest") if include_suggested else ("move",))


@app.command()
def undo(journal: Path = typer.Argument(None, help="Journal to reverse (default: the latest)")):
    """Reverse an applied run."""
    j = resolve(journal, paths.sub("journal"), mover.latest_journal)
    if j is None or not j.exists():
        console.print("Nothing to undo.")
        raise typer.Exit(1)
    restored, problems = mover.undo(j)
    for problem in problems:
        console.print(f"[yellow]skipped[/] {escape(problem)}")
    console.print(f"Restored {restored}.")


@app.command()
def audit(path: list[Path] = typer.Argument(None, help="Folders to audit (default: all roots)")):
    """Suggest moves for already-filed files that look misfiled. Never applied without --include-suggested."""
    cfg = load_cfg()
    roots = [p.expanduser() for p in path] if path else None
    files = list(inventory.filed_files(cfg, roots, skip_snapshots=True))
    p = build(cfg, files, "audit", audit=True)
    plans.save(p, paths.sub("plans"))
    show(p)
    console.print("Suggestions only. Review them, then: foldwise apply --include-suggested")


@app.command("dedupe")
def dedupe_command(
    path: list[Path] = typer.Argument(None, help="Folders to scan (default: roots and inboxes)"),
    purge: bool = typer.Option(False, help="Delete review-folder files that still have a verified twin"),
):
    """Find byte-identical copies and plan moving extras to the review folder."""
    cfg = load_cfg()
    review = expand(cfg.review_dir)
    roots = [p.expanduser() for p in path] if path else cfg.paths("roots") + cfg.paths("inboxes")
    if purge:
        search = (f for r in cfg.paths("roots") + cfg.paths("inboxes") for f in inventory.filed_files(cfg, [r]))
        deleted, kept = dedupe.purge(review, search)
        console.print(f"Deleted {len(deleted)} verified duplicates; kept {len(kept)} with no twin found.")
        return
    files = [f for r in roots for f in inventory.filed_files(cfg, [r], skip_snapshots=True)]
    p = plans.Plan("dedupe", dedupe.plan_items(dedupe.groups(files, cfg.paths("protect")), review))
    plans.save(p, paths.sub("plans"))
    show(p)
    console.print("Preview only. Run [bold]foldwise apply[/], check the review folder, then "
                  "[bold]foldwise dedupe --purge[/].")
