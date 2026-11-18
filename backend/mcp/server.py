"""MCP server with the research tools (stdio, started by mcp/client.py)."""

from mcp.server.fastmcp import FastMCP

from backend.rag.pipeline import retrieve_evidence, web_search

mcp = FastMCP("ResearchFlow")


@mcp.tool()
def document_search(
    question: str,
    document_ids: list[str] | None = None,
) -> list[dict]:
    """Search the uploaded PDFs, optionally only the given document_ids."""
    return retrieve_evidence(question, k=3, document_ids=document_ids)


@mcp.tool()
def web_search_tool(question: str) -> list[dict]:
    """Search the web for external or current information."""
    return web_search(question)


if __name__ == "__main__":
    mcp.run(transport="stdio")
