"""MCP server exposing ResearchFlow's research tools.

Runs as a separate process (stdio transport). The API starts it once
through backend/mcp/client.py and reuses it for every tool call.
"""

from mcp.server.fastmcp import FastMCP

from backend.rag.pipeline import retrieve_evidence, web_search

mcp = FastMCP("ResearchFlow")


@mcp.tool()
def document_search(
    question: str,
    document_ids: list[str] | None = None,
) -> list[dict]:
    """Search the user's uploaded PDFs for evidence.

    document_ids: optional list of uploaded document IDs; when given,
    only those PDFs are searched.
    """
    return retrieve_evidence(question, k=3, document_ids=document_ids)


@mcp.tool()
def web_search_tool(question: str) -> list[dict]:
    """Search the web for external or current information."""
    return web_search(question)


if __name__ == "__main__":
    mcp.run(transport="stdio")
