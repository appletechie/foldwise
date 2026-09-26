"""Apply plans with a write-ahead journal so every completed move can be undone, even after a crash."""
import json
import os
import shutil
from datetime import datetime
from pathlib import Path

from . import plan as plans


def free_name(dest: Path) -> Path:
    cand, n = dest, 1
    while cand.exists() or cand.is_symlink():
        cand = dest.with_name(f"{dest.stem} ({n}){dest.suffix}")
        n += 1
    return cand


def apply(plan_path: Path, journal_dir: Path, actions: tuple[str, ...] = ("move",)) -> tuple[Path, int, list[str]]:
    p = plans.load(plan_path)
    journal_dir.mkdir(parents=True, exist_ok=True)
    journal = journal_dir / f"{datetime.now():%Y%m%d-%H%M%S-%f}-{p.command}.jsonl"
    moved, skipped = 0, []
    with journal.open("a") as fh:
        for item in p.items:
            if item.action not in actions:
                continue
            src = Path(item.src)
            if not (src.exists() or src.is_symlink()):
                skipped.append(f"{item.src}: gone since the preview")
                continue
            dest = free_name(Path(item.dest))
            dest.parent.mkdir(parents=True, exist_ok=True)
            # Write-ahead: the entry is flushed and fsynced before the move, so a crash or
            # Ctrl-C between the two still leaves an entry undo can account for ("gone,
            # nothing to restore" when the move never ran).
            fh.write(json.dumps({"src": str(src), "dest": str(dest)}, ensure_ascii=False) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
            shutil.move(str(src), str(dest))
            moved += 1
    plans.mark_applied(plan_path, journal)
    return journal, moved, skipped


def undo(journal: Path) -> tuple[int, list[str]]:
    restored, problems = 0, []
    for line in reversed(journal.read_text().splitlines()):
        entry = json.loads(line)
        src, dest = Path(entry["src"]), Path(entry["dest"])
        if not dest.exists():
            problems.append(f"{dest}: gone, nothing to restore")
            continue
        if src.exists():
            problems.append(f"{src}: occupied, left {dest} in place")
            continue
        src.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(dest), str(src))
        restored += 1
    journal.rename(journal.with_name(journal.stem + ".undone.jsonl"))
    return restored, problems


def latest_journal(directory: Path) -> Path | None:
    found = sorted(j for j in directory.glob("*.jsonl") if not j.name.endswith(".undone.jsonl")) \
        if directory.is_dir() else []
    return found[-1] if found else None
