from foldwise import inventory
from foldwise.config import Config, Node


def cfg_for(root) -> Config:
    return Config(
        inboxes=[str(root / "Downloads")], roots=[str(root / "Docs"), str(root / "Code")],
        sensitive_dest=str(root / "Docs/Sensitive"), review_dir=str(root / "Docs/Review"),
        exclude=[str(root / "Docs/Private")], snapshots=[str(root / "Docs/Backups")],
        tree={str(root / "Docs/Areas"): Node("areas", {str(root / "Docs/Areas/Tax"): Node("tax")})},
    )


def test_inbox_items_skip_hidden_system_and_tree_folders(make):
    root = make({
        "Downloads/report.pdf": "x", "Downloads/.DS_Store": "x", "Downloads/.localized": "",
        "Downloads/Icon\r": "", "Downloads/kit/readme.md": "x",
        "Docs/Areas/loose.pdf": "x", "Docs/Areas/Tax/2024.pdf": "x",
    })
    items = inventory.inbox_items(cfg_for(root))
    names = sorted((i.path.name, i.kind) for i in items)
    assert names == [("kit", "inbox"), ("loose.pdf", "loose"), ("report.pdf", "inbox")]


def test_filed_files_prune_hidden_repo_excluded_review_and_snapshots(make):
    root = make({
        "Docs/Areas/Tax/2024.pdf": "x", "Docs/.hidden/a.txt": "x", "Docs/Private/p.txt": "x",
        "Docs/Review/dup.txt": "x", "Docs/Backups/old.txt": "x",
        "Code/app/.git/objects/ab": "x", "Code/app/node_modules/m/index.js": "x", "Code/app/README.md": "x",
    })
    (root / "Docs/link.pdf").symlink_to(root / "Docs/Areas/Tax/2024.pdf")
    cfg = cfg_for(root)
    got = sorted(str(p.relative_to(root)) for p in inventory.filed_files(cfg, skip_snapshots=True))
    assert got == ["Code/app/README.md", "Docs/Areas/Tax/2024.pdf"]
    with_snaps = {p.name for p in inventory.filed_files(cfg)}
    assert "old.txt" in with_snaps


def test_in_repo(make):
    root = make({"Code/app/.git/HEAD": "x", "Code/app/src/main.py": "x", "Docs/a.txt": "x"})
    assert inventory.in_repo(root / "Code/app/src")
    assert inventory.in_repo(root / "Code/app/_inbox/new.md")
    assert not inventory.in_repo(root / "Docs/a.txt")
