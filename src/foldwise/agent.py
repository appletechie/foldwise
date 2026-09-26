"""Hand held files to a coding agent (Claude Code, Codex, Cursor, ...) and take its answers back.

The saved export is the trust anchor: answers name files by export id, never by path, and may only
choose folders that exist in the taxonomy. Nothing here moves files; the result is a plan.
"""
import json
import uuid
from pathlib import Path

from . import paths
from . import plan as plans
from .config import Config, expand, is_group, iter_nodes
from .extract import IMAGE_EXT
from .llm.base import CONTENT_CHARS, schema
from .plan import PlanItem

AGENT_INSTRUCTIONS = (
    "Sort each file into one of the folders. You may open the file at `path` (images included) to decide. "
    'Answer with JSON {"export_id": "<the export_id from this file>", '
    '"suggestions": [{"id": <file id>, "dest": <folder key or "none">, "reason": <short reason>}]}, '
    "save it to a file, and run `foldwise review --import <that file>` (or call the propose_moves MCP tool). "
    "Do not move, rename or delete files yourself; the user applies the resulting plan with `foldwise apply`."
)


def leaves(cfg: Config) -> dict[str, str]:
    return {k: n.desc for k, n in iter_nodes(cfg.tree) if not n.children and not is_group(k)}


def held_items() -> list[PlanItem]:
    pp = plans.latest(paths.sub("plans"), "sort")
    if pp is None:
        return []
    return [i for i in plans.load(pp).items if i.action == "hold" and Path(i.src).exists()]


def held_payload(cfg: Config, held: list[PlanItem], read) -> dict:
    files, withheld = [], []
    for n, item in enumerate(held):
        p = Path(item.src)
        ex = read(p)
        if ex.sensitive:
            withheld.append(str(p))
            continue
        files.append({"id": n, "path": str(p), "filename": p.name, "metadata": ex.metadata,
                      "content": ex.text[:CONTENT_CHARS], "is_image": p.suffix.lower() in IMAGE_EXT,
                      "held_because": item.reason})
    folders = leaves(cfg)
    return {"version": 1, "export_id": uuid.uuid4().hex, "instructions": AGENT_INSTRUCTIONS, "folders": folders,
            "files": files, "withheld": withheld, "answer_schema": schema(list(folders))}


def _export_path(payload: dict | None = None) -> Path:
    # One file per export so two interleaved exports cannot cross; last-export.json stays as a pointer.
    if payload is not None:
        return paths.sub("agent") / f"export-{payload['export_id']}.json"
    return paths.sub("agent") / "last-export.json"


def save_export(payload: dict) -> Path:
    path = _export_path(payload)
    path.write_text(json.dumps(payload, indent=1, ensure_ascii=False))
    _export_path().write_text(json.dumps({"export_id": payload["export_id"], "file": path.name}))
    return path


def load_export(export_id: str | None = None) -> dict:
    if export_id is None:
        try:
            pointer = json.loads(_export_path().read_text())
        except (OSError, json.JSONDecodeError) as e:
            raise FileNotFoundError("no export yet: run `foldwise review --export FILE` (or the list_held tool) "
                                    "first") from e
        export_id = pointer.get("export_id")
    path = paths.sub("agent") / f"export-{export_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"no export {export_id!r}: re-run `foldwise review --export FILE` "
                                "(or the list_held tool) first")
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as e:
        raise ValueError(f"saved export {path.name} is corrupt (re-export): {e}") from e


def import_suggestions(cfg: Config, payload: dict, answers: dict) -> tuple[list[PlanItem], list[str]]:
    if answers.get("export_id") != payload.get("export_id"):
        return [], [f"answers are for export {answers.get('export_id')!r}, not {payload.get('export_id')!r}: "
                    "re-run `foldwise review --export` and answer the fresh file (it must echo the export_id)"]
    by_id = {f["id"]: f for f in payload.get("files", [])}
    folders = leaves(cfg)
    moves, problems, taken = [], [], set()
    for s in answers.get("suggestions", []):
        f, dest = by_id.get(s.get("id")), s.get("dest")
        if f is None:
            problems.append(f"unknown file id {s.get('id')!r}")
            continue
        if dest in (None, "none"):
            continue
        if dest not in folders:
            # reported even for an already-taken id: the agent must learn the folder was rejected
            problems.append(f"{f['filename']}: {dest!r} is not a folder in the taxonomy")
            continue
        if f["id"] in taken:
            continue
        src = Path(f["path"])
        if not src.exists():
            problems.append(f"{f['filename']}: gone since the export")
            continue
        taken.add(f["id"])
        moves.append(PlanItem(str(src), str(expand(dest) / src.name), "move",
                              f"review via agent: {str(s.get('reason', ''))[:120]}"))
    return moves, problems
