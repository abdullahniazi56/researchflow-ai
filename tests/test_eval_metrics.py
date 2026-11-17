from eval.metrics import (
    answer_is_correct,
    first_relevant_rank,
    summarize_answers,
    summarize_retrieval,
)

CASE = {"source": "nike.pdf", "pages": [2, 4]}


def test_first_relevant_rank():
    retrieved = [
        {"source": "puma.pdf", "page": 2},
        {"source": "Nike.pdf", "page": 4},
    ]
    assert first_relevant_rank(retrieved, CASE) == 2
    assert first_relevant_rank([{"source": "nike.pdf", "page": 9}], CASE) is None


def test_answer_keywords():
    assert answer_is_correct("Founded in 1964 by Bill Bowerman.", ["1964", "bowerman"])
    assert not answer_is_correct("Founded in 1964.", ["1964", "Bowerman"])


def test_retrieval_summary():
    summary = summarize_retrieval([1, 2, None, 1])
    assert summary["hit@1"] == 0.5
    assert summary["hit@3"] == 0.75
    assert round(summary["mrr"], 3) == round((1 + 0.5 + 0 + 1) / 4, 3)


def test_answer_summary():
    rows = [
        {"correct": True, "cited_claims": 2, "supported_claims": 2, "invalid_citations": 0, "seconds": 3},
        {"correct": False, "cited_claims": 2, "supported_claims": 1, "invalid_citations": 1, "seconds": 5},
    ]
    summary = summarize_answers(rows)
    assert summary["answer_accuracy"] == 0.5
    assert summary["citation_support_rate"] == 0.75
    assert summary["invalid_citations"] == 1
    assert summary["median_seconds"] == 4
