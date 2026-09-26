import os
import time

from foldwise import rules
from foldwise.config import Config, Node, Rule


def test_match_kinds():
    assert rules.matches(Rule("name", r"(?i)tax return", "~/x"), "2023 Tax Return.pdf", "")
    assert rules.matches(Rule("content", r"(?i)statement period", "~/x"), "a.pdf", "Statement Period: Aug")
    assert rules.matches(Rule("ext", r"ttf|otf", "~/x"), "Font.TTF", "")
    assert not rules.matches(Rule("ext", r"ttf", "~/x"), "notes.ttf.txt", "")


def test_first_match_order():
    rs = [Rule("name", "resume", "~/Hiring"), Rule("name", "(?i)peltekci.*resume", "~/Mine")]
    assert rules.first_match(rs, "peltekci resume.pdf", "").dest == "~/Hiring"
    assert rules.first_match(rs, "photo.png", "") is None


def test_render_dest_year(make):
    root = make({"Screenshot.png": b"x"})
    old = time.mktime((2025, 6, 1, 12, 0, 0, 0, 0, -1))
    os.utime(root / "Screenshot.png", (old, old))
    dest = rules.render_dest(Rule("name", "Screenshot", str(root / "Shots/{year}")), root / "Screenshot.png")
    assert dest == root / "Shots/2025"


def test_render_dest_literal_braces_are_not_placeholders(make):
    root = make({"a.txt": "x"})
    dest = rules.render_dest(Rule("name", "a", str(root / "Notes {drafts}")), root / "a.txt")
    assert dest == root / "Notes {drafts}"


def test_propose_finds_tokens_unique_to_one_leaf(make):
    root = make({
        "Docs/Tax/glossgenius-sales-jan.csv": "x", "Docs/Tax/glossgenius-sales-feb.csv": "x",
        "Docs/Tax/glossgenius-expenses.pdf": "x", "Docs/Tax/report-final.pdf": "x",
        "Docs/Logos/brand-logo.png": "x", "Docs/Logos/report-cover.png": "x",
    })
    cfg = Config(inboxes=[], roots=[str(root / "Docs")], sensitive_dest=str(root / "S"), review_dir=str(root / "R"),
                 tree={str(root / "Docs/Tax"): Node("tax"), str(root / "Docs/Logos"): Node("logos")})
    proposed = rules.propose(cfg)
    assert [(r.pattern, r.dest) for r in proposed] == [(r"(?i)(?<![a-z])glossgenius(?![a-z])", str(root / "Docs/Tax"))]
