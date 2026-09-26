import json
import shutil

import pytest

from foldwise import mover, plan
from foldwise.plan import Plan, PlanItem

ODD = "QR Code & Confirmation: Winter Las Vegas 2024 — ünï.pdf"


def setup(make, tmp_path, names):
    root = make({f"inbox/{n}": n for n in names})
    items = [PlanItem(str(root / "inbox" / n), str(root / "dest" / n), "move", "test") for n in names]
    return root, plan.save(Plan("sort", items), tmp_path / "plans")


def test_apply_and_undo_round_trip_with_odd_names(make, tmp_path):
    root, pp = setup(make, tmp_path, [ODD, "a.txt"])
    journal, moved, skipped = mover.apply(pp, tmp_path / "journal")
    assert moved == 2 and skipped == []
    assert (root / "dest" / ODD).read_text() == ODD
    assert plan.load(pp).applied_at is not None
    restored, problems = mover.undo(journal)
    assert restored == 2 and problems == []
    assert (root / "inbox" / ODD).exists() and not (root / "dest" / ODD).exists()
    assert not journal.exists() and journal.with_name(journal.stem + ".undone.jsonl").exists()


def test_never_overwrites_and_counts_from_original_name(make, tmp_path):
    root = make({"dest/logo.png": "old", "dest/logo (1).png": "older", "inbox/logo.png": "new"})
    assert mover.free_name(root / "dest/logo.png") == root / "dest/logo (2).png"
    pp = plan.save(Plan("sort", [PlanItem(str(root / "inbox/logo.png"), str(root / "dest/logo.png"), "move", "t")]),
                   tmp_path / "plans")
    mover.apply(pp, tmp_path / "journal")
    assert (root / "dest/logo.png").read_text() == "old"
    assert (root / "dest/logo (2).png").read_text() == "new"


def test_source_gone_between_preview_and_apply(make, tmp_path):
    root, pp = setup(make, tmp_path, ["a.txt", "b.txt"])
    (root / "inbox/a.txt").unlink()
    _, moved, skipped = mover.apply(pp, tmp_path / "journal")
    assert moved == 1 and len(skipped) == 1 and "a.txt" in skipped[0]


def test_holds_and_suggestions_are_not_applied_by_default(make, tmp_path):
    root = make({"inbox/h.txt": "x", "inbox/s.txt": "x"})
    items = [PlanItem(str(root / "inbox/h.txt"), "", "hold", "low confidence"),
             PlanItem(str(root / "inbox/s.txt"), str(root / "d/s.txt"), "suggest", "audit")]
    pp = plan.save(Plan("audit", items), tmp_path / "plans")
    _, moved, _ = mover.apply(pp, tmp_path / "journal")
    assert moved == 0
    _, moved, _ = mover.apply(plan.save(Plan("audit", items), tmp_path / "plans"), tmp_path / "journal",
                              actions=("move", "suggest"))
    assert moved == 1 and (root / "d/s.txt").exists()


def test_interrupted_apply_can_be_undone(make, tmp_path, monkeypatch):
    root, pp = setup(make, tmp_path, ["1.txt", "2.txt", "3.txt"])
    real, calls = shutil.move, []

    def flaky(src, dst):
        calls.append(src)
        if len(calls) == 3:
            raise KeyboardInterrupt
        return real(src, dst)

    monkeypatch.setattr(mover.shutil, "move", flaky)
    with pytest.raises(KeyboardInterrupt):
        mover.apply(pp, tmp_path / "journal")
    monkeypatch.setattr(mover.shutil, "move", real)
    journal = mover.latest_journal(tmp_path / "journal")
    assert len(journal.read_text().splitlines()) == 3  # the interrupted move was journaled before it ran
    assert plan.load(pp).applied_at is None
    restored, problems = mover.undo(journal)
    assert restored == 2 and len(problems) == 1  # the never-moved entry reports "gone, nothing to restore"
    assert sorted(p.name for p in (root / "inbox").iterdir()) == ["1.txt", "2.txt", "3.txt"]


def test_undo_skips_occupied_sources(make, tmp_path):
    root, pp = setup(make, tmp_path, ["a.txt"])
    journal, _, _ = mover.apply(pp, tmp_path / "journal")
    (root / "inbox/a.txt").write_text("someone put a new file here")
    restored, problems = mover.undo(journal)
    assert restored == 0 and "occupied" in problems[0]
    assert (root / "dest/a.txt").exists()


def test_plan_latest_and_json_shape(tmp_path):
    first = plan.save(Plan("sort", []), tmp_path)
    second = plan.save(Plan("dedupe", []), tmp_path)
    assert plan.latest(tmp_path) == second != first
    assert plan.latest(tmp_path, "sort") == first
    assert plan.latest(tmp_path / "missing") is None
    assert json.loads(second.read_text())["command"] == "dedupe"
