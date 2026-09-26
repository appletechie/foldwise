"""Review held files: pick a folder for each; optionally turn the answer into a rule."""
import re
from collections.abc import Callable
from pathlib import Path

from rich.console import Console
from rich.markup import escape

from ..config import Config, Rule, expand, is_group, iter_nodes
from ..plan import PlanItem

TOKEN = re.compile(r"[A-Za-z]{4,}")
Ask = Callable[[str], str]


class Quit(Exception):
    pass


def leaf_keys(cfg: Config) -> list[str]:
    return [k for k, n in iter_nodes(cfg.tree) if not n.children and not is_group(k)]


def rule_from_name(name: str, dest: str) -> Rule | None:
    tokens = sorted(TOKEN.findall(Path(name).stem), key=len, reverse=True)
    if not tokens:
        return None
    return Rule("name", rf"(?i)(?<![a-z]){re.escape(tokens[0].lower())}(?![a-z])", dest)


def pick_folder(leaves: list[str], ask: Ask, console: Console) -> str | None:
    shown = leaves
    while True:
        for n, key in enumerate(shown[:30], 1):
            console.print(f"  {n:2}. {escape(key)}")
        answer = ask("number, text to filter, s to skip, q to quit").strip()
        if answer in ("", "s"):
            return None
        if answer == "q":
            raise Quit
        if answer.isdigit() and 1 <= int(answer) <= min(30, len(shown)):
            return shown[int(answer) - 1]
        shown = [k for k in leaves if answer.lower() in k.lower()] or leaves


def interactive(held: list[PlanItem], cfg: Config, ask: Ask, console: Console) -> tuple[list[PlanItem], list[Rule]]:
    moves, rules = [], []
    leaves = leaf_keys(cfg)
    try:
        for item in held:
            src = Path(item.src)
            console.print(f"\n[bold]{escape(src.name)}[/]  [dim]{escape(item.reason)}[/]")
            dest = pick_folder(leaves, ask, console)
            if dest is None:
                continue
            moves.append(PlanItem(item.src, str(expand(dest) / src.name), "move", "review"))
            if ask("make a rule from this filename? (y/n)").strip().lower() == "y":
                rule = rule_from_name(src.name, dest)
                if rule:
                    rules.append(rule)
    except Quit:
        pass
    return moves, rules


def llm_review(held: list[PlanItem], cfg: Config, provider, read, images: bool, confirm, ask: Ask,
               console: Console) -> tuple[list[PlanItem], list[Rule]]:
    from ..llm.base import review_items

    items, withheld = review_items([(Path(i.src), read(Path(i.src))) for i in held], images)
    for p in withheld:
        console.print(f"[yellow]not sent[/] {escape(p.name)}: contains a credential")
    if not items:
        return [], []
    leaves = {k: n.desc for k, n in iter_nodes(cfg.tree) if not n.children and not is_group(k)}
    with_images = sum(i.image is not None for i in items)
    console.print(f"Will send {len(items)} files ({with_images} with images) to {provider.name}: "
                  f"{provider.estimate(items, leaves)}")
    if not confirm("Send them?"):
        return [], []
    by_id = {i.id: i for i in items}
    moves, accepted, accept_all = [], [], False
    try:
        for s in provider.suggest(items, leaves):
            it = by_id[s.id]
            if s.dest is None:
                console.print(f"{escape(it.filename)}: no suggestion ({escape(s.reason)})")
                continue
            console.print(f"{escape(it.filename)} -> {escape(s.dest)}  [dim]{escape(s.reason)}[/]")
            answer = "a" if accept_all else ask("a accept, A accept all, e edit, r reject").strip()
            if answer == "A":
                accept_all, answer = True, "a"
            dest = s.dest if answer == "a" else pick_folder(list(leaves), ask, console) if answer == "e" else None
            if dest:
                moves.append(PlanItem(str(it.path), str(expand(dest) / it.filename), "move",
                                      f"review via {provider.name}"))
                accepted.append((it.filename, dest))
    except Quit:
        pass
    rules: list[Rule] = []
    if accepted and ask("make rules from the accepted filenames? (y/n)").strip().lower() == "y":
        rules = [r for name, dest in accepted if (r := rule_from_name(name, dest))]
    return moves, rules
