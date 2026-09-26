from foldwise.config import Config, Node, Rule
from foldwise.runner import build_plan


def cfg_for(root) -> Config:
    return Config(inboxes=[str(root / "Downloads")], roots=[str(root / "Docs")],
                  sensitive_dest=str(root / "Docs/Sensitive"), review_dir=str(root / "Docs/Review"),
                  tree={str(root / "Docs/Tax"): Node("tax"), str(root / "Docs/Notes"): Node("notes")},
                  rules=[Rule("name", r"(?i)tax return", str(root / "Docs/Tax"))])


def test_sort_plan_moves_and_holds(home, make):
    key = "sk-" + "Q1w2E3r4T5y6U7i8O9p0A1s2"
    root = make({"Downloads/2024 Tax Return.pdf": "t", "Downloads/creds.md": f"use {key}", "Downloads/misc.txt": "m"})
    plan = build_plan(cfg_for(root), sorted((root / "Downloads").iterdir()), "sort", models=[])
    by_name = {i.src.rsplit("/", 1)[1]: i for i in plan.items}
    assert by_name["2024 Tax Return.pdf"].action == "move"
    assert by_name["2024 Tax Return.pdf"].dest == str(root / "Docs/Tax/2024 Tax Return.pdf")
    assert by_name["creds.md"].dest == str(root / "Docs/Sensitive/creds.md")
    assert by_name["misc.txt"].action == "hold" and by_name["misc.txt"].dest == ""


def test_audit_keeps_only_disagreements_credentials_first(home, make):
    key = "sk-" + "Z1x2C3v4B5n6M7q8W9e0R1t2"
    root = make({"Docs/Notes/2023 Tax Return.pdf": "t23", "Docs/Notes/plan.md": f"key {key}",
                 "Docs/Tax/2022 Tax Return.pdf": "t22", "Docs/Notes/ideas.md": "i"})
    files = sorted(p for p in (root / "Docs").rglob("*") if p.is_file())
    plan = build_plan(cfg_for(root), files, "audit", audit=True, models=[])
    assert [(i.src.rsplit("/", 1)[1], i.action) for i in plan.items] == [("plan.md", "suggest"),
                                                                         ("2023 Tax Return.pdf", "suggest")]
