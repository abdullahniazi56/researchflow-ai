"""LangGraph research agent.

    START -> planner -> (fan-out) research_worker x N -> fan_in -> decision
          decision --(no evidence, retry once)--> planner
          decision --> selection -> answer -> verify -> END

* planner          rewrites follow-ups and splits complex questions (LLM, only when needed)
* research_worker  collects evidence for one sub-question, in parallel (MCP tools)
* decision         retries once with web search if nothing useful was found
* selection        merges and de-duplicates evidence, gives each piece an ID
* answer           writes the grounded answer with [E#] citations (LLM)
* verify           checks citations with the reranker and turns them into sources
"""

import logging
import operator
import os
from typing import Annotated, TypedDict

from langchain_core.messages import HumanMessage
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from backend.agent.routing import needs_planning, needs_web_search
from backend.mcp.client import get_mcp_tools, mcp_client
from backend.rag.pipeline import (
    create_research_plan,
    generate_answer,
    resolve_citations,
    select_evidence,
    verify_citations,
)

logger = logging.getLogger("researchflow.agent")

# "rules": cheap rule-based tool choice (default, saves LLM quota)
# "llm":   the LLM picks tools through tool calling
ROUTING_MODE = os.getenv("ROUTING_MODE", "rules").strip().lower()

MAX_RESEARCH_ROUNDS = 2


class ResearchState(TypedDict, total=False):
    question: str                      # the user's latest message
    history: list[dict]                # recent messages of this session
    document_ids: list[str] | None     # search only these PDFs (optional)
    standalone_question: str           # question rewritten without context
    research_questions: list[str]      # sub-questions for this round
    results: Annotated[list, operator.add]  # worker outputs (merged)
    selected_evidence: list[dict]
    raw_answer: str
    answer: str
    verification: dict
    research_round: int


def initial_state(
    question: str,
    history: list[dict] | None = None,
    document_ids: list[str] | None = None,
) -> ResearchState:
    return {
        "question": question,
        "history": history or [],
        "document_ids": document_ids or None,
        "standalone_question": question,
        "research_questions": [],
        "results": [],
        "selected_evidence": [],
        "raw_answer": "",
        "answer": "",
        "verification": {},
        "research_round": 0,
    }


# --------------------------------------------------
# EVIDENCE NORMALIZATION
# --------------------------------------------------

def normalize_evidence(result, tool_name: str) -> list[dict]:
    """Convert MCP tool output into a consistent evidence format."""
    is_web = tool_name == "web_search_tool"

    if result is None:
        return []

    if isinstance(result, list):
        evidence = []
        for item in result:
            evidence.extend(normalize_evidence(item, tool_name))
        return evidence

    if isinstance(result, dict):
        for key in ("evidence", "results"):
            if isinstance(result.get(key), (list, dict)):
                return normalize_evidence(result[key], tool_name)

        content = result.get("content") or result.get("snippet")
        if not isinstance(content, str) or not content.strip():
            return []

        item = result.copy()
        item["content"] = content
        item.setdefault("source", "Web Search" if is_web else "Document Search")
        item.setdefault("type", "web" if is_web else "document")
        item.setdefault("url", None)
        item.setdefault("page", None)
        item.setdefault("snippet", content[:300])
        return [item]

    if isinstance(result, str) and result.strip():
        return [{
            "content": result,
            "source": "Web Search" if is_web else "Document Search",
            "url": None,
            "page": None,
            "snippet": result[:300],
            "type": "web" if is_web else "document",
        }]

    return []


# --------------------------------------------------
# NODES
# --------------------------------------------------

def planner_node(state: ResearchState):
    question = state["question"]
    history = state.get("history") or []

    # Retry round: search the (already rewritten) question directly.
    if state["research_round"] > 0:
        return {"research_questions": [state.get("standalone_question") or question]}

    # A first, simple question needs no planner call at all.
    if not history and not needs_planning(question):
        logger.info("Planner skipped (no LLM call).")
        return {"standalone_question": question, "research_questions": [question]}

    try:
        plan = create_research_plan(question, history)
    except Exception as exc:
        logger.warning("Planner failed, using the original question: %s", exc)
        return {"standalone_question": question, "research_questions": [question]}

    return {
        "standalone_question": plan.standalone_question,
        "research_questions": plan.sub_questions,
    }


async def run_tool(tool_name: str, arguments: dict, errors: list) -> list:
    """Call one MCP tool and return its evidence in the standard format."""
    try:
        result = await mcp_client.call_tool(tool_name, arguments)
    except Exception as exc:
        errors.append(f"{tool_name} failed: {type(exc).__name__}: {exc}")
        return []

    if result is None:
        errors.append(f"{tool_name} returned no result.")
        return []

    return normalize_evidence(result, tool_name)


_tool_calling_llm = None


def tool_calling_llm():
    """LLM with the MCP tools bound (only built when ROUTING_MODE=llm)."""
    global _tool_calling_llm
    if _tool_calling_llm is None:
        from backend.llm import bind_tools_with_fallback
        _tool_calling_llm = bind_tools_with_fallback(get_mcp_tools())
    return _tool_calling_llm


async def choose_tools_with_llm(question: str) -> list[tuple[str, str]]:
    """Ask the LLM which tools to call. Returns (tool_name, query) pairs."""
    instruction = (
        f"Research the following question:\n\n{question}\n\n"
        "Choose the research tools needed to collect evidence. Use "
        "document_search for the user's uploaded PDFs. Use web_search_tool "
        "for external or current information. You may use one or both. "
        "Do not answer the question."
    )
    response = await tool_calling_llm().ainvoke([HumanMessage(content=instruction)])

    return [
        (call["name"], call.get("args", {}).get("question") or question)
        for call in (response.tool_calls or [])[:2]
        if call["name"] in ("document_search", "web_search_tool")
    ]


async def research_worker(state: dict):
    """Collect evidence for one sub-question."""
    question = state["question"]
    research_round = state["research_round"]
    document_ids = state.get("document_ids")
    errors: list[str] = []
    evidence: list[dict] = []

    def doc_args(query):
        args = {"question": query}
        if document_ids:
            args["document_ids"] = document_ids
        return args

    if ROUTING_MODE == "llm" and research_round == 0:
        try:
            choices = await choose_tools_with_llm(question)
        except Exception as exc:
            errors.append(f"Tool selection failed, using rules: {exc}")
            choices = []

        for tool_name, query in choices:
            args = doc_args(query) if tool_name == "document_search" else {"question": query}
            evidence.extend(await run_tool(tool_name, args, errors))

        if choices:
            return {"results": [{
                "question": question,
                "evidence": evidence,
                "errors": errors,
                "research_round": research_round,
            }]}

    # Rules: PDFs first (local, free), web only when needed.
    evidence = await run_tool("document_search", doc_args(question), errors)

    if needs_web_search(question, evidence, research_round):
        evidence.extend(await run_tool("web_search_tool", {"question": question}, errors))
    else:
        logger.info("Web search skipped: PDFs answered %r", question)

    return {"results": [{
        "question": question,
        "evidence": evidence,
        "errors": errors,
        "research_round": research_round,
    }]}


def fan_out_research(state: ResearchState):
    return [
        Send(
            "research_worker",
            {
                "question": question,
                "research_round": state["research_round"],
                "document_ids": state.get("document_ids"),
            },
        )
        for question in state["research_questions"]
    ]


def fan_in_node(state: ResearchState):
    return {"research_round": state["research_round"] + 1}


def agent_decision(state: ResearchState):
    current_round = state["research_round"] - 1
    current = [r for r in state["results"] if r.get("research_round") == current_round]

    if not current:
        return "selection"

    has_evidence = any(r.get("evidence") for r in current)

    # Nothing useful found: one more round (with web search).
    if not has_evidence and state["research_round"] < MAX_RESEARCH_ROUNDS:
        return "research"

    return "selection"


def selection_node(state: ResearchState):
    return {"selected_evidence": select_evidence(state["results"])}


def answer_node(state: ResearchState):
    raw = generate_answer(
        state.get("standalone_question") or state["question"],
        state["selected_evidence"],
        state.get("history"),
    )
    return {"raw_answer": raw}


def verify_node(state: ResearchState):
    evidence = state["selected_evidence"]
    cleaned, report = verify_citations(state["raw_answer"], evidence)
    return {
        "answer": resolve_citations(cleaned, evidence),
        "verification": report,
    }


# --------------------------------------------------
# GRAPH
# --------------------------------------------------

graph = StateGraph(ResearchState)

graph.add_node("planner", planner_node)
graph.add_node("research_worker", research_worker)
graph.add_node("fan_in", fan_in_node)
graph.add_node("decision", lambda state: {})
graph.add_node("selection", selection_node)
graph.add_node("answer", answer_node)
graph.add_node("verify", verify_node)

graph.add_edge(START, "planner")
graph.add_conditional_edges("planner", fan_out_research)
graph.add_edge("research_worker", "fan_in")
graph.add_edge("fan_in", "decision")
graph.add_conditional_edges(
    "decision",
    agent_decision,
    {"research": "planner", "selection": "selection"},
)
graph.add_edge("selection", "answer")
graph.add_edge("answer", "verify")
graph.add_edge("verify", END)

app = graph.compile()
