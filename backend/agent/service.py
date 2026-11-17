
from backend.agent.graph import app


from backend.db import (
    create_message,
    create_research_source,
    get_session_message,
    research_session_exists,
)


async def run_research(question: str, session_id: str) -> dict:
    """Run the research workflow and return the final answer."""

    initial_state = {
        "question": question,
        "research_questions": [],
        "results": [],
        "selected_evidence": [],
        "context": "",
        "answer": "",
        "research_round": 0,
    }

    result = await app.ainvoke(initial_state)

    return {
        "session_id": session_id,
        "status": (
            "completed" if result.get("answer") else "stopped"
        ),
        "answer": result.get("answer"),
        "selected_evidence": result.get(
            "selected_evidence",
            [],
        ),
    }





def save_research_answer(
    session_id: str,
    result: dict,
) -> None:
    """Save the generated answer and its selected sources."""

    answer = result.get("answer")

    if not answer:
        return

    # Avoid saving the same answer text twice in one session.
    existing_messages = get_session_message(session_id)

    if any(
        role == "assistant" and content == answer
        for role, content, _ in existing_messages
    ):
        return

    answer_message_id = create_message(
        session_id,
        "assistant",
        answer,
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
