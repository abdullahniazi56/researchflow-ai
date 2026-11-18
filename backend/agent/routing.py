"""Cheap rules for when to call the planner and when to hit the web.

PDFs are always searched first; the web is only used when the best
reranker score is low or the question is about recent events.
"""

import os
import re

# ms-marco scores run roughly -11..11, above 0 is usually relevant
DOC_RELEVANCE_THRESHOLD = float(os.getenv("DOC_RELEVANCE_THRESHOLD", "0"))

# auto | always | never
PLANNER_MODE = os.getenv("PLANNER_MODE", "auto").strip().lower()

PLANNING_MIN_WORDS = int(os.getenv("PLANNING_MIN_WORDS", "14"))

MULTI_PART_PATTERN = re.compile(
    r"\b(compare|comparison|versus|vs\.?|difference|differences|"
    r"pros and cons|advantages and disadvantages|history and|"
    r"step by step)\b",
    re.IGNORECASE,
)

RECENCY_PATTERN = re.compile(
    r"\b(latest|newest|recent|recently|current|currently|today|"
    r"this year|this month|news|now|upcoming|20[2-9]\d)\b",
    re.IGNORECASE,
)


def needs_planning(question: str) -> bool:
    if PLANNER_MODE == "always":
        return True
    if PLANNER_MODE == "never":
        return False

    words = len(question.split())
    has_multiple_questions = question.count("?") > 1

    return (
        words >= PLANNING_MIN_WORDS
        or has_multiple_questions
        or bool(MULTI_PART_PATTERN.search(question))
    )


def best_document_score(evidence: list[dict]) -> float | None:
    scores = [
        item["rerank_score"]
        for item in evidence
        if isinstance(item.get("rerank_score"), (int, float))
    ]
    return max(scores) if scores else None


def needs_web_search(
    question: str,
    document_evidence: list[dict],
    research_round: int = 0,
) -> bool:
    if research_round > 0:
        return True

    if RECENCY_PATTERN.search(question):
        return True

    if not document_evidence:
        return True

    best = best_document_score(document_evidence)

    # no score to judge by
    if best is None:
        return False

    return best < DOC_RELEVANCE_THRESHOLD
