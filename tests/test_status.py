from pathlib import Path

from typer.testing import CliRunner

from foldwise.cli import app

runner = CliRunner()


def test_status_shows_tree_waiting_plan_history_and_untracked(home, make):
    root = make({
        "Documents/Areas/Tax/a.pdf": "a", "Documents/Areas/Legal/b.pdf": "b",
        "Documents/Clients/acme-brief-1.md": "1", "Documents/Clients/acme-brief-2.md": "2",
        "Documents/Clients/acme-brief-3.md": "3",
        "Downloads/acme-brief-new.md": "n", "Downloads/random.txt": "r",
    }, root=Path(home))
    env = {"COLUMNS": "200"}
    runner.invoke(app, ["init", "--root", str(root / "Documents"), "--inbox", str(root / "Downloads")], env=env)
    runner.invoke(app, ["sort", "--apply"], env=env)
    (root / "Documents/Areas/Untracked").mkdir()
    out = runner.invoke(app, ["status"], env=env)
    assert out.exit_code == 0, out.output
    text = out.output
    for expected in ("Folders", "Areas", "Tax", "Untracked 0 (not in taxonomy)", "Waiting to sort: 1",
                      "Last plan: sort", "Move history", "foldwise undo", "no fine-tuned model"):
        assert expected in text, expected
