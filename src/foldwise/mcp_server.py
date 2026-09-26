"""foldwise as an MCP server for coding agents. Tools read state and write plans; moving files stays a human step.

Register it in a harness as a stdio server whose command is `foldwise mcp`,
for example: claude mcp add foldwise -- foldwise mcp
"""
from pathlib import Path

from mcp.server import MCPServer

from . import agent, config, inventory, paths
from . import plan as plans
from .cache import Cache

server = MCPServer("foldwise")
NEXT = "ask the user to review the plan and run `foldwise apply` (and `foldwise undo` to reverse it)"


def _cfg() -> config.Config:
    f = paths.config_file()
    if not f.exists():
        raise RuntimeError("foldwise is not set up yet: ask the user to run `foldwise init`")
    return config.load(f)


@server.tool()
def status() -> dict:
    """Counts of files waiting in the inboxes and held for review, plus the rules and models in use."""
    cfg = _cfg()
    return {"waiting": len(inventory.inbox_items(cfg)), "held": len(agent.held_items()),
            "rules": len(cfg.rules), "models": cfg.models}


@server.tool()
def list_folders() -> dict:
    """Folder keys (use them as `dest`) and what each folder holds."""
    return {"folders": agent.leaves(_cfg())}


@server.tool()
def list_held() -> dict:
    """Files held for review: id, path, masked text, metadata and why each was held. Open image paths yourself
    to look at them. Files that contain credentials are withheld. Call this before propose_moves."""
    cfg = _cfg()
    cache = Cache(paths.sub("cache") / "extract.jsonl")
    try:
        payload = agent.held_payload(cfg, agent.held_items(), cache.read)
    finally:
        cache.close()
    agent.save_export(payload)
    return payload


@server.tool()
def preview_sort() -> dict:
    """Plan where inbox files would go and refresh the held list. Moves nothing."""
    from .runner import build_plan

    cfg = _cfg()
    p = build_plan(cfg, [i.path for i in inventory.inbox_items(cfg)], "sort")
    pp = plans.save(p, paths.sub("plans"))
    return {"plan": pp.name, "move": len(p.moves()), "hold": sum(i.action == "hold" for i in p.items),
            "items": [{"file": Path(i.src).name, "action": i.action, "to": i.dest, "why": i.reason}
                      for i in p.items[:200]],
            "next": NEXT}


@server.tool()
def propose_moves(suggestions: list[dict], export_id: str | None = None) -> dict:
    """Record folder choices for held files as a plan. Each suggestion is {"id": <id from list_held>,
    "dest": <folder key from list_folders, or "none">, "reason": <short reason>}; pass back the
    `export_id` from list_held so interleaved exports cannot cross. Nothing moves until the
    user runs `foldwise apply`."""
    cfg = _cfg()
    try:
        payload = agent.load_export(export_id)
    except (FileNotFoundError, ValueError) as e:
        return {"planned": 0, "problems": [str(e)], "next": NEXT}
    moves, problems = agent.import_suggestions(cfg, payload, {"export_id": payload["export_id"],
                                                              "suggestions": suggestions})
    result: dict = {"planned": len(moves), "problems": problems, "next": NEXT}
    if moves:
        result["plan"] = plans.save(plans.Plan("review", moves), paths.sub("plans")).name
    return result
