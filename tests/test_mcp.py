import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from foldwise.cli import app


@pytest.fixture
def anyio_backend():
    return "asyncio"


def data(result):
    if result.structured_content is not None:
        return result.structured_content
    return json.loads(result.content[0].text)


@pytest.mark.anyio
async def test_agent_flow_over_mcp(home, make):
    from mcp import Client

    from foldwise.mcp_server import server

    root = make({"Documents/Tax/tax-2021.pdf": "1", "Documents/Photos/p.jpg": "p",
                 "Downloads/quarterly-numbers.xlsx": "q"}, root=Path(home))
    runner, env = CliRunner(), {"COLUMNS": "200"}
    runner.invoke(app, ["init", "--root", str(root / "Documents"), "--inbox", str(root / "Downloads")], env=env)

    async with Client(server, raise_exceptions=True) as client:
        tools = {t.name for t in (await client.list_tools()).tools}
        assert tools == {"status", "list_folders", "list_held", "preview_sort", "propose_moves"}
        preview = data(await client.call_tool("preview_sort", {}))
        assert preview["hold"] == 1 and preview["move"] == 0
        assert (root / "Downloads/quarterly-numbers.xlsx").exists()
        held = data(await client.call_tool("list_held", {}))
        file_id = held["files"][0]["id"]
        result = data(await client.call_tool("propose_moves", {"suggestions": [
            {"id": file_id, "dest": "~/Documents/Tax", "reason": "numbers"},
            {"id": 99, "dest": "~/Documents/Tax", "reason": "not exported"},
            {"id": file_id, "dest": "/etc", "reason": "not a folder"},
        ], "export_id": held["export_id"]}))
        assert result["planned"] == 1 and len(result["problems"]) == 2 and "foldwise apply" in result["next"]
        stale = data(await client.call_tool("propose_moves", {"suggestions": [
            {"id": file_id, "dest": "~/Documents/Tax", "reason": "stale"},
        ], "export_id": "deadbeef"}))
        assert stale["planned"] == 0 and any("export" in p for p in stale["problems"])
        status = data(await client.call_tool("status", {}))
        assert status["held"] == 1

    assert (root / "Downloads/quarterly-numbers.xlsx").exists()  # MCP never moves files
    runner.invoke(app, ["apply"], env=env)
    assert (root / "Documents/Tax/quarterly-numbers.xlsx").exists()
