
import asyncio
import json
import sys
from contextlib import AsyncExitStack
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from langchain_core.tools import StructuredTool


PROJECT_ROOT = Path(__file__).resolve().parents[2]

server_params = StdioServerParameters(
    command=sys.executable,
    args=["-m", "backend.mcp.server"],
    cwd=str(PROJECT_ROOT),
)


def parse_mcp_result(result):
    if result.isError:
        raise RuntimeError(f"MCP tool failed: {result.content}")

    parsed = []

    for block in result.content:
        text = getattr(block, "text", None)

        if text is None:
            continue

        try:
            parsed.append(json.loads(text))
        except json.JSONDecodeError:
            parsed.append(text)

    if len(parsed) == 1:
        return parsed[0]

    return parsed



class MCPClient:
    async def _run_session(self, operation, *args):
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                return await operation(session, *args)

    async def _list_tools(self, session):
        result = await session.list_tools()
        return result.tools

    async def _call_tool(
        self,
        session,
        tool_name: str,
        arguments: dict,
    ):
        result = await session.call_tool(
            tool_name,
            arguments,
        )
        return parse_mcp_result(result)

    async def list_tools(self):
        return await self._run_session(self._list_tools)

    async def call_tool(
        self,
        tool_name: str,
        arguments: dict,
    ):
        return await self._run_session(
            self._call_tool,
            tool_name,
            arguments,
        )

    async def close(self):
        # Each operation owns and closes its own MCP session.
        # Nothing persistent remains to close here.
        return None



mcp_client = MCPClient()


def create_document_search_tool():
    async def execute(question: str):
        return await mcp_client.call_tool(
            "document_search",
            {"question": question}
        )

    return StructuredTool.from_function(
        coroutine=execute,
        name="document_search",
        description=(
            "Search uploaded documents for relevant research evidence."
        ),
    )


def create_web_search_tool():
    async def execute(question: str):
        return await mcp_client.call_tool(
            "web_search_tool",
            {"question": question}
        )

    return StructuredTool.from_function(
        coroutine=execute,
        name="web_search_tool",
        description=(
            "Search the web for external or current research "
            "evidence and source details."
        ),
    )


def get_mcp_tools():
    return [
        create_document_search_tool(),
        create_web_search_tool(),
    ]


async def close_mcp_client():
    await mcp_client.close()



async def test_mcp_tools():
    try:
        tools = await mcp_client.list_tools()

        for tool in tools:
            print(f"Tool: {tool.name}")

        result = await mcp_client.call_tool(
            "web_search_tool",
            {"question": "Nike company history and founding"}
            )

        print("\nWeb search result:")
        print(result)

    finally:
        await close_mcp_client()



if __name__ == "__main__":
    asyncio.run(test_mcp_tools())
