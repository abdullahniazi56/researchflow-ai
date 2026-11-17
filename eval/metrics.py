"""Pure metric functions (no models), so they can be unit-tested."""

import re
import statistics


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def is_relevant(item: dict, case: dict) -> bool:
    """A retrieved chunk is relevant if it comes from the expected file
    and one of the expected pages."""
    return (
        _norm(item.get("source")) == _norm(case["source"])
        and item.get("page") in case["pages"]
    )


def first_relevant_rank(retrieved: list[dict], case: dict) -> int | None:
    """1-based rank of the first relevant chunk, or None."""
    for rank, item in enumerate(retrieved, start=1):
        if is_relevant(item, case):
            return rank
    return None


def answer_is_correct(answer: str, keywords: list[str]) -> bool:
    """Every expected keyword must appear in the answer (case-insensitive)."""
    text = _norm(answer)
    return all(_norm(k) in text for k in keywords)


def summarize_retrieval(ranks: list[int | None]) -> dict:
    n = len(ranks) or 1
    return {
        "questions": len(ranks),
        "hit@1": sum(1 for r in ranks if r == 1) / n,
        "hit@3": sum(1 for r in ranks if r is not None and r <= 3) / n,
        "mrr": sum(1 / r for r in ranks if r) / n,
    }


def summarize_answers(rows: list[dict]) -> dict:
    n = len(rows) or 1
    cited = sum(r["cited_claims"] for r in rows)
    supported = sum(r["supported_claims"] for r in rows)
    latencies = [r["seconds"] for r in rows]
    return {
        "answer_accuracy": sum(1 for r in rows if r["correct"]) / n,
        "citation_support_rate": supported / cited if cited else 0.0,
        "invalid_citations": sum(r["invalid_citations"] for r in rows),
        "median_seconds": statistics.median(latencies) if latencies else 0.0,
    }
