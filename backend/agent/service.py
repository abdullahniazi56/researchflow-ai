"""Runs the agent for the API and saves answers."""

import logging
import time

from backend.agent.graph import app, initial_state
from backend.db import (
    create_message,
    create_research_source,
    get_session_message,
)

logger = logging.getLogger("researchflow.service")

HISTORY_MESSAGES = 6


def load_history(session_id: str) -> list[dict]:
    rows = get_session_message(session_id)
    return [
        {"role": role, "content": content}
        for role, content, _created_at in rows[-HISTORY_MESSAGES:]
    ]


def failure_message(exc: Exception) -> str:
    text = str(exc)
    if any(m in text for m in ("429", "RESOURCE_EXHAUSTED", "quota", "rate limit", "Rate limit")):
        return (
            "The AI model's usage limit is reached for now. "
            "Try again later, or set LLM_PROVIDER=mistral in .env."
        )
    if any(m in text for m in ("503", "UNAVAILABLE", "overloaded", "high demand")):
        return (
            "The AI model is busy right now (the provider is overloaded). "
            "Please try again in a minute."
        )
    if "timed out" in text.lower() or "timeout" in text.lower():
        return "The AI model took too long to respond. Please try again."
    logger.error("Unexpected research error: %s", text)
    return "Research failed because of an unexpected error. Check the server log for details."


def build_result(session_id: str, state: dict, seconds: float) -> dict:
    answer = state.get("answer")
    return {
        "session_id": session_id,
        "status": "completed" if answer else "stopped",
        "answer": answer,
        "selected_evidence": state.get("selected_evidence", []),
        "verification": state.get("verification") or None,
        "standalone_question": state.get("standalone_question"),
        "seconds": round(seconds, 1),
    }


async def run_research(
    question: str,
    session_id: str,
    history: list[dict] | None = None,
    document_ids: list[str] | None = None,
) -> dict:
    started = time.perf_counter()

    try:
        state = await app.ainvoke(initial_state(question, history, document_ids))
    except Exception as exc:
        logger.exception("Research failed")
        return {
            "session_id": session_id,
            "status": "failed",
            "message": failure_message(exc),
            "answer": None,
            "selected_evidence": [],
            "verification": None,
        }

    result = build_result(session_id, state, time.perf_counter() - started)
    logger.warning(
        "Research %s finished in %.1fs (%d sources)",
        session_id, result["seconds"], len(result["selected_evidence"]),
    )
    return result


def describe_update(node: str, update: dict) -> dict | None:
    """Map a node update to a progress event for the UI."""
    if not isinstance(update, dict):
        return None

    if node == "planner":
        questions = update.get("research_questions") or []
        if len(questions) > 1:
            return {"step": "plan", "message": f"Planned {len(questions)} searches", "items": questions}
        return {"step": "plan", "message": "Researching the question directly", "items": questions}

    if node == "research_worker":
        for result in update.get("results", []):
            evidence = result.get("evidence", [])
            docs = sum(1 for e in evidence if e.get("type") == "document")
            web = sum(1 for e in evidence if e.get("type") == "web")
            return {
                "step": "search",
                "message": f"Found {docs} PDF and {web} web results",
                "items": [result.get("question", "")],
            }

    if node == "selection":
        count = len(update.get("selected_evidence", []))
        return {"step": "write", "message": f"Writing the answer from {count} sources"}

    if node == "verify":
        report = update.get("verification") or {}
        return {
            "step": "verify",
            "message": (
                f"Checked citations: {report.get('supported_claims', 0)} of "
                f"{report.get('cited_claims', 0)} claims supported"
            ),
        }

    return None


async def stream_research(
    question: str,
    session_id: str,
    history: list[dict] | None = None,
    document_ids: list[str] | None = None,
):
    started = time.perf_counter()
    final_state: dict = {}

    yield {"type": "step", "step": "start", "message": "Starting research"}

    try:
        async for mode, chunk in app.astream(
            initial_state(question, history, document_ids),
            stream_mode=["updates", "values"],
        ):
            if mode == "values":
                final_state = chunk
                continue

            for node, update in chunk.items():
                event = describe_update(node, update)
                if event:
                    at = round(time.perf_counter() - started, 1)
                    logger.info("[%s] %5.1fs %s: %s", session_id, at, node, event["message"])
                    yield {"type": "step", "at": at, **event}

    except Exception as exc:
        logger.exception("Research failed")
        yield {
            "type": "result",
            "session_id": session_id,
            "status": "failed",
            "message": failure_message(exc),
            "answer": None,
            "selected_evidence": [],
            "verification": None,
        }
        return

    yield {"type": "result", **build_result(session_id, final_state, time.perf_counter() - started)}


def save_research_answer(session_id: str, result: dict) -> None:
    answer = result.get("answer")
    if not answer:
        return

    message_id = create_message(session_id, "assistant", answer)
    saved = set()

    evidence = result.get("selected_evidence", [])
    cited = [item for item in evidence if item.get("cited")]

    for item in cited or evidence:
        key = (
            item.get("type", "unknown"),
            item.get("source", "Unknown source"),
            item.get("url"),
            item.get("page"),
        )
        if key in saved:
            continue
        saved.add(key)

        create_research_source(
            message_id=message_id,
            source_type=item.get("type", "unknown"),
            source_name=item.get("source", "Unknown source"),
            source_url=item.get("url"),
            page_number=item.get("page"),
        )
