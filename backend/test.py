
import asyncio
from backend.mcp.client import get_mcp_tools

async def main():
    tools = get_mcp_tools()
    tool = next(t for t in tools if t.name == "document_search")

    print("Testing document search...", flush=True)

    result = await tool.ainvoke({
        "question": "What is the history and evolution of Nike?"
    })

    print(result)

if __name__ == "__main__":
    asyncio.run(main())
