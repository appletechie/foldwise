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
