"""The whole flow through the CLI on a synthetic tree, asserting the tree after each step."""
from pathlib import Path

from typer.testing import CliRunner

from foldwise import config, paths
from foldwise.cli import app

KEY = "sk-" + "E2e0Test1Key2Value3Here4"
runner = CliRunner()
ENV = {"COLUMNS": "200"}


def run(*args):
    result = runner.invoke(app, list(args), env=ENV)
    assert result.exit_code == 0, result.output
    return result.output


def build(make, home):
    return make({
        "Documents/Areas/Finances/2021 Tax Return.pdf": "t21", "Documents/Areas/Finances/2022 Tax Return.pdf": "t22",
        "Documents/Areas/Finances/2023 Tax Return.pdf": "t23",
        "Documents/Areas/Clients/acme-brief-1.md": "a1", "Documents/Areas/Clients/acme-brief-2.md": "a2",
        "Documents/Areas/Clients/acme-brief-3.md": "a3",
        "Documents/Resources/Logos/logo-dark.png": b"dark", "Documents/Resources/Logos/logo-light.png": b"light",
        "Documents/Archives/Backups/old-copy-of-brief.md": "a1",
        "Documents/Evidence/case-photo.png": b"case",
        "Downloads/2024 Tax Return.pdf": "t24", "Downloads/acme-brief-4.md": "a4", "Downloads/brief copy.md": "a2",
        "Downloads/deploy-notes.md": f"deploy with {KEY}", "Downloads/3f9a2c1be7d84f02a1c9.png": b"hex",
        "Downloads/misc.txt": "misc", "Downloads/.DS_Store": b"x",
    }, root=Path(home))


def test_full_flow(home, make):
    root = build(make, home)
    docs, dl = root / "Documents", root / "Downloads"
    run("init", "--root", str(docs), "--inbox", str(dl))
    cfg = config.load(paths.config_file())
    cfg.protect, cfg.snapshots = ["~/Documents/Evidence"], ["~/Documents/Archives"]
    config.save(cfg, paths.config_file())

    run("sort")
    assert (dl / "2024 Tax Return.pdf").exists()  # preview moved nothing

    run("apply")
    assert (docs / "Areas/Finances/2024 Tax Return.pdf").exists()  # proposed rule "return"
    assert (docs / "Areas/Clients/acme-brief-4.md").exists()  # proposed rule "acme"
    assert (docs / "Duplicate-Review/brief copy.md").exists()  # byte-identical to acme-brief-2.md
    assert (docs / "Sensitive/deploy-notes.md").exists()  # contains a credential
    for held in ("3f9a2c1be7d84f02a1c9.png", "misc.txt", ".DS_Store"):
        assert (dl / held).exists(), held
    assert KEY not in (paths.sub("cache") / "extract.jsonl").read_text()

    run("undo")
    assert sorted(p.name for p in dl.iterdir()) == sorted([
        ".DS_Store", "2024 Tax Return.pdf", "3f9a2c1be7d84f02a1c9.png", "acme-brief-4.md", "brief copy.md",
        "deploy-notes.md", "misc.txt"])

    run("sort", "--apply")
    assert (docs / "Areas/Clients/acme-brief-4.md").exists()

    (docs / "Resources/Logos/logo-dark (1).png").write_bytes(b"dark")
    out = run("dedupe")
    assert "logo-dark (1).png" in out and "old-copy-of-brief.md" not in out and "case-photo" not in out
    run("apply")
    assert (docs / "Duplicate-Review/logo-dark (1).png").exists()
    out = run("dedupe", "--purge")
    assert "Deleted 2" in out
    assert (docs / "Resources/Logos/logo-dark.png").exists() and (docs / "Areas/Clients/acme-brief-2.md").exists()

    out = run("audit")
    assert "case-photo" not in out  # protected folders are never suggested

    out = run("status")
    assert "Move history" in out and "Waiting to sort: 2" in out
