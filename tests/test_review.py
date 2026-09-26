from pathlib import Path

from rich.console import Console
from typer.testing import CliRunner

from foldwise.cli import app
from foldwise.config import Config, Node
from foldwise.plan import PlanItem
from foldwise.tui import review


def cfg_for(root) -> Config:
    return Config(inboxes=[], roots=[], sensitive_dest="~/S", review_dir="~/R", tree={
        str(root / "Docs/Areas"): Node("areas", {str(root / "Docs/Areas/Tax"): Node("tax"),
                                                 str(root / "Docs/Areas/Legal"): Node("legal")}),
        str(root / "Docs/Photos"): Node("photos")})


def scripted(*answers):
    it = iter(answers)
    return lambda prompt: next(it)


def test_rule_from_name_uses_the_longest_word():
    rule = review.rule_from_name("Majestic-Metals-cutlist-v2.xlsx", "~/Clients")
    assert rule.pattern == r"(?i)(?<![a-z])majestic(?![a-z])" and rule.dest == "~/Clients"
    assert review.rule_from_name("123.pdf", "~/x") is None


def test_pick_folder_filter_number_skip_quit(tmp_path):
    con = Console(file=open("/dev/null", "w"))
    leaves = ["~/Docs/Areas/Tax", "~/Docs/Areas/Legal", "~/Docs/Photos"]
    assert review.pick_folder(leaves, scripted("leg", "1"), con) == "~/Docs/Areas/Legal"
    assert review.pick_folder(leaves, scripted("s"), con) is None
    try:
        review.pick_folder(leaves, scripted("q"), con)
        raise AssertionError("expected Quit")
    except review.Quit:
        pass


def test_interactive_collects_moves_and_rules(tmp_path):
    cfg = cfg_for(tmp_path)
    held = [PlanItem(str(tmp_path / "in/acme-invoice.pdf"), "", "hold", "low confidence"),
            PlanItem(str(tmp_path / "in/skipme.txt"), "", "hold", "low confidence"),
            PlanItem(str(tmp_path / "in/never.txt"), "", "hold", "low confidence")]
    con = Console(file=open("/dev/null", "w"))
    moves, rules = review.interactive(held, cfg, scripted("1", "y", "s", "q"), con)
    assert [m.dest for m in moves] == [str(tmp_path / "Docs/Areas/Tax/acme-invoice.pdf")]
    assert rules[0].pattern == r"(?i)(?<![a-z])invoice(?![a-z])"


def test_cli_review_writes_a_plan_and_rules(home, make):
    root = make({"Documents/Tax/tax-2021.pdf": "1", "Documents/Tax/tax-2022.pdf": "2", "Documents/Photos/p.jpg": "p",
                 "Downloads/quarterly-numbers.xlsx": "q"}, root=Path(home))
    runner = CliRunner()
    env = {"COLUMNS": "200"}
    runner.invoke(app, ["init", "--root", str(root / "Documents"), "--inbox", str(root / "Downloads")], env=env)
    runner.invoke(app, ["sort"], env=env)
    result = runner.invoke(app, ["review"], input="tax\n1\ny\n", env=env)
    assert result.exit_code == 0, result.output
    assert "Added 1 rules" in result.output and "1 to move" in result.output
    runner.invoke(app, ["apply"], env=env)
    assert (root / "Documents/Tax/quarterly-numbers.xlsx").exists()
