import json
from pathlib import Path

from typer.testing import CliRunner

from foldwise import agent
from foldwise.cli import app
from foldwise.config import Config, Node
from foldwise.extract import Extracted
from foldwise.plan import PlanItem


def cfg_for(root) -> Config:
    return Config(inboxes=[], roots=[], sensitive_dest="~/S", review_dir="~/R",
                  tree={str(root / "Docs/Tax"): Node("taxes"), str(root / "Docs/Photos"): Node("photos")})


def test_payload_withholds_credentials_and_marks_images(tmp_path):
    held = [PlanItem(str(tmp_path / "a.pdf"), "", "hold", "low confidence"),
            PlanItem(str(tmp_path / "keys.txt"), "", "hold", "low confidence"),
            PlanItem(str(tmp_path / "shot.png"), "", "hold", "meaningless name")]
    read = {"a.pdf": Extracted("invoice"), "keys.txt": Extracted("x", sensitive=True), "shot.png": Extracted("")}
    payload = agent.held_payload(cfg_for(tmp_path), held, lambda p: read[p.name])
    assert [f["filename"] for f in payload["files"]] == ["a.pdf", "shot.png"]
    assert payload["withheld"] == [str(tmp_path / "keys.txt")]
    assert payload["files"][1]["is_image"] and payload["files"][1]["held_because"] == "meaningless name"
    assert set(payload["folders"]) == {str(tmp_path / "Docs/Tax"), str(tmp_path / "Docs/Photos")}
    assert "foldwise review --import" in payload["instructions"]
    assert payload["export_id"] and "export_id" in payload["instructions"]


def test_import_accepts_only_exported_ids_and_taxonomy_folders(tmp_path):
    cfg = cfg_for(tmp_path)
    (tmp_path / "a.pdf").write_text("a")
    (tmp_path / "gone.pdf").write_text("g")
    held = [PlanItem(str(tmp_path / "a.pdf"), "", "hold", "x"), PlanItem(str(tmp_path / "gone.pdf"), "", "hold", "x")]
    payload = agent.held_payload(cfg, held, lambda p: Extracted("t"))
    (tmp_path / "gone.pdf").unlink()
    answers = {"export_id": payload["export_id"], "suggestions": [
        {"id": 0, "dest": str(tmp_path / "Docs/Tax"), "reason": "invoice", "path": "/etc/passwd"},
        {"id": 1, "dest": str(tmp_path / "Docs/Tax"), "reason": "gone"},
        {"id": 7, "dest": str(tmp_path / "Docs/Tax"), "reason": "not exported"},
        {"id": 0, "dest": "/etc", "reason": "not a taxonomy folder"},
        {"id": 0, "dest": "none", "reason": "skip"},
    ]}
    moves, problems = agent.import_suggestions(cfg, payload, answers)
    assert [(m.src, m.dest) for m in moves] == [(str(tmp_path / "a.pdf"), str(tmp_path / "Docs/Tax/a.pdf"))]
    assert len(problems) == 3 and any("gone" in p for p in problems) and any("/etc" in p for p in problems)


def test_import_rejects_answers_from_a_different_export(tmp_path):
    cfg = cfg_for(tmp_path)
    (tmp_path / "a.pdf").write_text("a")
    held = [PlanItem(str(tmp_path / "a.pdf"), "", "hold", "x")]
    first = agent.held_payload(cfg, held, lambda p: Extracted("t"))
    second = agent.held_payload(cfg, held, lambda p: Extracted("t"))
    assert first["export_id"] != second["export_id"]
    stale = {"export_id": first["export_id"],
             "suggestions": [{"id": 0, "dest": str(tmp_path / "Docs/Tax"), "reason": "stale"}]}
    moves, problems = agent.import_suggestions(cfg, second, stale)
    assert moves == [] and any("export" in p for p in problems)
    missing = {"suggestions": [{"id": 0, "dest": str(tmp_path / "Docs/Tax"), "reason": "no id"}]}
    assert agent.import_suggestions(cfg, second, missing)[0] == []


def test_cli_export_then_import(home, make):
    root = make({"Documents/Tax/tax-2021.pdf": "1", "Documents/Photos/p.jpg": "p",
                 "Downloads/quarterly-numbers.xlsx": "q"}, root=Path(home))
    runner, env = CliRunner(), {"COLUMNS": "200"}
    runner.invoke(app, ["init", "--root", str(root / "Documents"), "--inbox", str(root / "Downloads")], env=env)
    runner.invoke(app, ["sort"], env=env)
    out = root / "held.json"
    result = runner.invoke(app, ["review", "--export", str(out)], env=env)
    assert result.exit_code == 0, result.output
    payload = json.loads(out.read_text())
    answer = root / "answers.json"
    answer.write_text(json.dumps({"export_id": payload["export_id"],
                                  "suggestions": [{"id": payload["files"][0]["id"], "dest": "~/Documents/Tax",
                                                   "reason": "quarterly numbers"}]}))
    result = runner.invoke(app, ["review", "--import", str(answer)], env=env)
    assert result.exit_code == 0, result.output
    assert "1 to move" in result.output
    runner.invoke(app, ["apply"], env=env)
    assert (root / "Documents/Tax/quarterly-numbers.xlsx").exists()

    stale = root / "stale.json"
    stale.write_text(json.dumps({"export_id": "deadbeef", "suggestions": []}))
    result = runner.invoke(app, ["review", "--import", str(stale)], env=env)
    assert result.exit_code == 1 and "no export" in result.output
    broken = root / "broken.json"
    broken.write_text("{not json")
    result = runner.invoke(app, ["review", "--import", str(broken)], env=env)
    assert result.exit_code == 1 and "not valid JSON" in result.output
