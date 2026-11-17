"""The MCP client must reuse ONE server process for all tool calls."""

import asyncio
import sys
import textwrap

from mcp import StdioServerParameters

from backend.mcp import client as mcp_module

FAKE_SERVER = textwrap.dedent(
    """
    import os
    from mcp.server.fastmcp import FastMCP

    mcp = FastMCP("fake")

    @mcp.tool()
    def whoami(question: str) -> dict:
        return {"pid": os.getpid(), "question": question}

    if __name__ == "__main__":
        mcp.run(transport="stdio")
    """
)


def test_tool_calls_share_one_server_process(tmp_path, monkeypatch):
    server_file = tmp_path / "fake_server.py"
    server_file.write_text(FAKE_SERVER)

    monkeypatch.setattr(
        mcp_module,
        "server_params",
        StdioServerParameters(command=sys.executable, args=[str(server_file)]),
    )

    async def scenario():
        client = mcp_module.MCPClient(call_timeout=30)
        try:
            results = await asyncio.gather(
                *[
                    client.call_tool("whoami", {"question": f"q{i}"})
                    for i in range(4)
                ]
            )
            later = await client.call_tool("whoami", {"question": "again"})
        finally:
            await client.close()
        return results, later

    results, later = asyncio.run(scenario())

    pids = {r["pid"] for r in results} | {later["pid"]}
    assert len(pids) == 1, f"expected one server process, got {pids}"
    assert sorted(r["question"] for r in results) == ["q0", "q1", "q2", "q3"]
