from mcp.server.fastmcp import FastMCP
import json

from backend.rag.pipeline import (
    retrieve_evidence,
    web_search
)


mcp = FastMCP(
    "ResearchFlow"
)


@mcp.tool()
def document_search(question: str) -> list[dict]:
    """
    Search the user's uploaded documents
    for relevant research evidence.
    """

    return retrieve_evidence(
        question,
        k=3
    )


@mcp.tool()
def web_search_tool(question: str) -> list[dict]:
    """
    Search the web for external or current
    research information.
    """

    return web_search(
        question
    )


if __name__ == "__main__":
    mcp.run(
        transport="stdio"
    )