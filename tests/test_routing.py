"""Rules that replaced LLM calls for planning and tool selection."""

from backend.agent.routing import needs_planning, needs_web_search


def doc(score):
    return {"content": "text", "rerank_score": score, "type": "document"}


# ---------- planner ----------

def test_short_question_skips_planner():
    assert needs_planning("What is RAG?") is False


def test_comparison_uses_planner():
    assert needs_planning("Compare Nike and Puma") is True


def test_long_question_uses_planner():
    question = (
        "How did Nike grow from a small running shoe distributor into a "
        "global sports brand over the decades?"
    )
    assert needs_planning(question) is True


def test_multiple_questions_use_planner():
    assert needs_planning("What is Nike? Who founded it?") is True


# ---------- web search ----------

def test_relevant_pdf_evidence_skips_web():
    assert needs_web_search("What is Nike's mission?", [doc(4.2)]) is False


def test_weak_pdf_evidence_uses_web():
    assert needs_web_search("What is Nike's mission?", [doc(-3.0)]) is True


def test_no_pdf_evidence_uses_web():
    assert needs_web_search("What is Nike's mission?", []) is True


def test_recent_question_always_uses_web():
    assert needs_web_search("What is Nike's latest product?", [doc(8.0)]) is True


def test_retry_round_always_uses_web():
    assert needs_web_search("What is Nike's mission?", [doc(8.0)], 1) is True
