"""One-off, not packaged: convert the private prototype into foldwise config and state.

    python scripts/import_prototype.py ~/Developer/1_Projects/file-organizer
"""
import json
import shutil
import sys
from pathlib import Path

from foldwise import config, paths
from foldwise.config import Config, Node, Policy, Rule


def node(d: dict) -> Node:
    return Node(d.get("desc", ""), {k: node(v) for k, v in d.get("children", {}).items()}, d.get("dest"),
                bool(d.get("hold")))


def main(src: Path) -> None:
    tax = json.loads((src / "taxonomy.json").read_text())
    cfg = Config(
        inboxes=["~/Downloads", "~/Desktop"],
        roots=["~/Documents/2_Areas", "~/Documents/3_Resources", "~/Documents/4_Archives", "~/Developer/1_Projects"],
        sensitive_dest="~/Documents/2_Areas/Finances-Legal/Sensitive",
        review_dir="~/Documents/4_Archives/09_Duplicate-Review",
        exclude=tax.get("exclude", []),
        protect=tax.get("dedupe_protect", []),
        snapshots=["~/Documents/4_Archives"],
        policy=Policy(min_confidence=tax.get("min_confidence", 0.75)),
        tree={k: node(v) for k, v in tax["tree"].items()},
        rules=[Rule(r["match"], r["pattern"], r["dest"]) for r in tax["rules"]],
    )
    models_dir = paths.sub("models")
    for name in tax.get("models", []):
        if (src / name / "rl_agent_config.json").exists():
            target = models_dir / f"prototype-{name}"
            if not target.exists():
                shutil.copytree(src / name, target)
            cfg.models.append(target.name)
    test_set = src / "cache" / "test_set.json"
    if test_set.exists():
        shutil.copy(test_set, paths.state_dir() / "test_set.json")
    config.save(cfg, paths.config_file())
    print(f"wrote {paths.config_file()}: {len(cfg.rules)} rules, models {cfg.models}")
    for problem in config.validate(cfg):
        print("check:", problem)


if __name__ == "__main__":
    main(Path(sys.argv[1]).expanduser())
