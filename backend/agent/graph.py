import asyncio
import logging
import operator
from typing import Annotated, TypedDict

from langgraph.types import Send
from langgraph.graph import StateGraph, START, END
from backend.agent.routing import needs_planning, needs_web_search
from backend.mcp.client import get_mcp_tools, close_mcp_client
import uuid

from backend.db import create_message, create_research_session , create_research_source

from backend.rag.pipeline import (
    create_research_plan,
    select_evidence,
    build_context,
    generate_answer,
)


class ResearchState(TypedDict):
    question: str
    research_questions: list
    results: Annotated[list, operator.add]
    selected_evidence: list
    context: str
    answer: str
    research_round: int


def normalize_evidence(result, tool_name: str) -> list[dict]:
    """Convert MCP tool output into a consistent evidence format."""

    if result is None:
        return []

    # Case 1: The MCP tool returns multiple results.
    if isinstance(result, list):
        evidence = []

        for item in result:
            evidence.extend(
                normalize_evidence(item, tool_name)
            )

        return evidence

    # Case 2: The MCP tool returns a dictionary.
    if isinstance(result, dict):

        # Handle wrappers containing nested evidence.
        for key in ("evidence", "results"):
            if key in result and isinstance(result[key], (list, dict)):
                return normalize_evidence(
                    result[key], tool_name
                )

        # Ignore dictionaries that contain no usable text.
        content = result.get("content") or result.get("snippet")

        if not isinstance(content, str) or not content.strip():
            return []

        item = result.copy()
        item["content"] = content

        item.setdefault(
            "source",
            "Web Search" if tool_name == "web_search_tool"
            else "Document Search"
        )

        item.setdefault(
            "type",
            "web" if tool_name == "web_search_tool"
            else "document"
        )

        item.setdefault("url", None)
        item.setdefault("page", None)
        item.setdefault("snippet", content[:300])

        return [item]

    # Case 3: The MCP tool returns plain text.
    if isinstance(result, str) and result.strip():
        return [{
            "content": result,
            "source": (
                "Web Search"
                if tool_name == "web_search_tool"
                else "Document Search"
            ),
            "url": None,
            "page": None,
            "snippet": result[:300],
            "type": (
                "web"
                if tool_name == "web_search_tool"
                else "document"
            )
        }]

    return []


logger = logging.getLogger("researchflow.agent")

mcp_tools = get_mcp_tools()

tool_map = {
    tool.name: tool
    for tool in mcp_tools
}


def planner_node(state: ResearchState):
    question = state["question"]

    # Retry rounds and simple questions don't need the planner LLM:
    # researching the question as it is works just as well.
    if state["research_round"] > 0 or not needs_planning(question):
        logger.info("Planner skipped (no LLM call).")
        return {"research_questions": [question]}

    try:
        questions = create_research_plan(question)
    except Exception as exc:
        # If the LLM is unavailable, still research the original question.
        logger.warning("Planner failed, using the original question: %s", exc)
        questions = []

    return {
        "research_questions": questions or [question]
    }


async def run_tool(tool_name: str, question: str, errors: list) -> list:
    """Call one MCP tool and return its evidence in the standard format."""
    try:
        result = await tool_map[tool_name].ainvoke({"question": question})
    except Exception as exc:
        errors.append(f"{tool_name} failed: {type(exc).__name__}: {exc}")
        return []

    if result is None:
        errors.append(f"{tool_name} returned no result.")
        return []

    return normalize_evidence(result, tool_name)


async def research_worker(state: dict):
    """Collect evidence for one sub-question, without any LLM call.

    1. Search the uploaded PDFs (local and free).
    2. Search the web only if the PDFs are not relevant enough,
       or the question is about recent events.
    """
    question = state["question"]
    research_round = state["research_round"]
    errors = []

    evidence = await run_tool("document_search", question, errors)

    if needs_web_search(question, evidence, research_round):
        evidence.extend(
            await run_tool("web_search_tool", question, errors)
        )
    else:
        logger.info("Web search skipped: PDFs answered %r", question)

    return {
        "results": [{
            "question": question,
            "evidence": evidence,
            "errors": errors,
            "research_round": research_round,
        }]
    }


def fan_out_research(state: ResearchState):
    return [
        Send(
            "research_worker",
            {
                "question": question,
                "research_round": state["research_round"]
            }
        )
        for question in state["research_questions"]
    ]


def fan_in_node(state: ResearchState):
    return {
        "research_round": state["research_round"] + 1
    }



def agent_decision(state: ResearchState):
    current_round = state["research_round"] - 1

    current_results = [
        result
        for result in state["results"]
        if result.get("research_round") == current_round
    ]

    # No worker results: don't enter an endless research loop.
    if not current_results:
        return "selection"

    # Check whether any worker returned usable evidence.
    has_evidence = any(
        result.get("evidence")
        for result in current_results
    )

    # Retry once if this round produced no usable evidence.
    if not has_evidence and state["research_round"] < 2:
        return "research"

    return "selection"







def selection_node(state: ResearchState):
    selected = select_evidence(
        state["results"]
    )

    return {
        "selected_evidence": selected
    }


def context_node(state: ResearchState):
    context = build_context(
        state["selected_evidence"]
    )

    return {
        "context": context
    }


def answer_node(state: ResearchState):
    answer = generate_answer(
        state["question"],
        state["selected_evidence"]
    )

    return {
        "answer": answer
    }


graph = StateGraph(ResearchState)

graph.add_node("planner", planner_node)
graph.add_node("research_worker", research_worker)
graph.add_node("fan_in", fan_in_node)
graph.add_node("decision", lambda state: {})
graph.add_node("selection", selection_node)
graph.add_node("context", context_node)
graph.add_node("answer", answer_node)

graph.add_edge(START, "planner")

graph.add_conditional_edges(
    "planner",
    fan_out_research
)

graph.add_edge("research_worker", "fan_in")
graph.add_edge("fan_in", "decision")

graph.add_conditional_edges(
    "decision",
    agent_decision,
    {
        "research": "planner",
        "selection": "selection"
    }
)



graph.add_edge("selection", "context")
graph.add_edge("context", "answer")
graph.add_edge("answer", END)



app = graph.compile()




async def main():
    try:
        initial_state = {
            "question": "What is the history and evolution of Nike?",
            "research_questions": [],
            "results": [],
            "selected_evidence": [],
            "context": "",
            "answer": "",
            "research_round": 0
        }

        session_id = f"research-{uuid.uuid4().hex[:12]}"

        create_research_session(
            session_id,
            "ResearchFlow Research"
        )

        create_message(
            session_id,
            "user",
            initial_state["question"]
        )

        result = await app.ainvoke(initial_state)

        

        print(
            result.get("answer")
            or "Research stopped before answer generation."
        )

        answer = result.get("answer")

        if answer:
            answer_message_id = create_message(
                session_id,
                "assistant",
                answer
            )

            saved_sources = set()

            for item in result.get("selected_evidence", []):
                source_key = (
                    item.get("type", "unknown"),
                    item.get("source", "Unknown source"),
                    item.get("url"),
                    item.get("page"),
                )

                if source_key in saved_sources:
                    continue

                saved_sources.add(source_key)

                create_research_source(
                    message_id=answer_message_id,
                    source_type=item.get("type", "unknown"),
                    source_name=item.get("source", "Unknown source"),
                    source_url=item.get("url"),
                    page_number=item.get("page"),
                )

    finally:
        await close_mcp_client()


if __name__ == "__main__":
    asyncio.run(main())

