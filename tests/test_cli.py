from pathlib import Path

from typer.testing import CliRunner

from foldwise.cli import app

runner = CliRunner()


def tree(make, home):
    return make({
        "Documents/Clients/acme-brief-1.md": "a1", "Documents/Clients/acme-brief-2.md": "a2",
        "Documents/Clients/acme-brief-3.md": "a3", "Documents/Other/misc.md": "m",
        "Downloads/acme-brief-new.md": "n", "Downloads/random.txt": "r",
    }, root=Path(home))


def run(*args):
    result = runner.invoke(app, list(args), env={"COLUMNS": "200"})
    assert result.exit_code == 0, result.output
    return result.output


def test_init_sort_apply_undo(home, make):
    root = tree(make, home)
    out = run("init", "--root", str(root / "Documents"), "--inbox", str(root / "Downloads"))
    assert "proposed rules" in out
    assert runner.invoke(app, ["init", "--root", str(root / "Documents")]).exit_code == 1  # refuses to overwrite
    out = run("sort")
    assert "Preview only" in out and (root / "Downloads/acme-brief-new.md").exists()
    out = run("apply")
    assert (root / "Documents/Clients/acme-brief-new.md").exists()
    assert (root / "Downloads/random.txt").exists()  # held: no model, no rule
    assert runner.invoke(app, ["apply"]).exit_code == 1  # already applied
    run("undo")
    assert (root / "Downloads/acme-brief-new.md").exists()
    assert not (root / "Documents/Clients/acme-brief-new.md").exists()


def test_sort_apply_flag_and_audit(home, make):
    root = tree(make, home)
    run("init", "--root", str(root / "Documents"), "--inbox", str(root / "Downloads"))
    run("sort", "--apply")
    assert (root / "Documents/Clients/acme-brief-new.md").exists()
    (root / "Documents/Other/acme-brief-lost.md").write_text("x")
    out = run("audit")
    assert "acme-brief-lost.md" in out and "suggest" in out
    run("apply", "--include-suggested")
    assert (root / "Documents/Clients/acme-brief-lost.md").exists()


def test_dedupe_then_purge(home, make):
    root = tree(make, home)
    (root / "Documents/Other/misc (1).md").write_text("m")
    run("init", "--root", str(root / "Documents"), "--inbox", str(root / "Downloads"))
    out = run("dedupe")
    assert "misc (1).md" in out
    run("apply")
    review = root / "Documents/Duplicate-Review"
    assert (review / "misc (1).md").exists() and (root / "Documents/Other/misc.md").exists()
    out = run("dedupe", "--purge")
    assert "Deleted 1" in out and not (review / "misc (1).md").exists()


def test_commands_need_a_config(home):
    result = runner.invoke(app, ["sort"])
    assert result.exit_code == 1 and "foldwise init" in result.output
