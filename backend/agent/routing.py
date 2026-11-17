"""Rule-based decisions that used to cost an LLM call.

Before, the agent asked the LLM "which tool should I use?" for every
sub-question and always ran the planner. Both decisions can be made
with cheap rules, which saves most of the LLM quota:

* needs_planning: only split long or multi-part questions.
* needs_web_search: always search the uploaded PDFs first (free and
  local); go to the web only when the PDFs don't answer the question
  well enough, or the question is clearly about recent events.

All thresholds can be changed in .env without touching code.
"""

import os
import re

# Cross-encoder (ms-marco) scores are roughly -11..+11; above 0 means
# "probably relevant". Raise it to use the web more often.
DOC_RELEVANCE_THRESHOLD = float(os.getenv("DOC_RELEVANCE_THRESHOLD", "0"))

# "auto" (default), "always" or "never"
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
    """Should the planner LLM split this question into sub-questions?"""
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
    """Decide whether to also search the web for this sub-question."""
    # Second round means the first round found nothing useful.
    if research_round > 0:
        return True

    # Questions about recent events need fresh information.
    if RECENCY_PATTERN.search(question):
        return True

    if not document_evidence:
        return True

    best = best_document_score(document_evidence)

    # No score available: trust the documents we found.
    if best is None:
        return False

    return best < DOC_RELEVANCE_THRESHOLD
