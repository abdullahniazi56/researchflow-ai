
import asyncio
import json
import sys
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
    """One long-lived MCP session shared by all tool calls.

    The server loads the models on start, so it is started once and
    restarted only if it dies.
    """

    def __init__(self, call_timeout: float = 120):
        self.call_timeout = call_timeout
        self._session: ClientSession | None = None
        self._task: asyncio.Task | None = None
        self._ready: asyncio.Event | None = None
        self._stop: asyncio.Event | None = None
        self._lock: asyncio.Lock | None = None

    async def _run_session(self):
        # stdio_client has to be entered and exited in the same task
        try:
            async with stdio_client(server_params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    self._session = session
                    self._ready.set()
                    await self._stop.wait()
        finally:
            self._session = None

    async def start(self):
        if self._lock is None:
            self._lock = asyncio.Lock()

        async with self._lock:
            if (
                self._session is not None
                and self._task is not None
                and not self._task.done()
            ):
                return

            self._ready = asyncio.Event()
            self._stop = asyncio.Event()
            self._task = asyncio.create_task(self._run_session())

            ready_waiter = asyncio.create_task(self._ready.wait())
            done, _ = await asyncio.wait(
                {ready_waiter, self._task},
                return_when=asyncio.FIRST_COMPLETED,
            )

            if self._task in done:
                ready_waiter.cancel()
                self._task.result()
                raise RuntimeError("MCP server stopped during startup.")

    async def list_tools(self):
        await self.start()
        result = await self._session.list_tools()
        return result.tools

    async def call_tool(
        self,
        tool_name: str,
        arguments: dict,
    ):
        await self.start()

        result = await asyncio.wait_for(
            self._session.call_tool(tool_name, arguments),
            timeout=self.call_timeout,
        )
        return parse_mcp_result(result)

    async def close(self):
        if self._stop is not None:
            self._stop.set()

        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=10)
            except Exception:
                self._task.cancel()

        self._task = None
        self._session = None


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
