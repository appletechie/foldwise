"""A plan is the reviewable list of what a command would do. Nothing moves until a plan is applied."""
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path


def _now() -> str:
    return datetime.now().isoformat(timespec="microseconds")


@dataclass
class PlanItem:
    src: str
    dest: str
    action: str  # "move" | "hold" | "suggest"
    reason: str
    confidence: float = 1.0


@dataclass
class Plan:
    command: str
    items: list[PlanItem]
    created: str = field(default_factory=_now)
    applied_at: str | None = None
    journal: str | None = None

    def moves(self) -> list[PlanItem]:
        return [i for i in self.items if i.action == "move"]


def _write(p: Plan, path: Path) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(asdict(p), indent=1, ensure_ascii=False))
    tmp.replace(path)


def save(p: Plan, directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    stamp = p.created.replace(":", "").replace("-", "").replace(".", "")
    path = directory / f"{stamp}-{p.command}.json"
    _write(p, path)
    return path


def load(path: Path) -> Plan:
    d = json.loads(path.read_text())
    d["items"] = [PlanItem(**i) for i in d["items"]]
    return Plan(**d)


def latest(directory: Path, command: str | None = None) -> Path | None:
    pattern = f"*-{command}.json" if command else "*.json"
    found = sorted(directory.glob(pattern)) if directory.is_dir() else []
    return found[-1] if found else None


def mark_applied(path: Path, journal: Path) -> None:
    p = load(path)
    p.applied_at, p.journal = _now(), str(journal)
    _write(p, path)
