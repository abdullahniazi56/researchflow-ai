"""Citation verification and evidence helpers (no models, no network)."""

import os
import sys
import types

os.environ["LLM_CACHE"] = "off"
os.environ.setdefault("GOOGLE_API_KEY", "test-key")
os.environ.setdefault("MISTRAL_API_KEY", "test-key")


class WordOverlapCrossEncoder:

    def __init__(self, *args, **kwargs):
        pass

    def predict(self, pairs):
        scores = []
        for claim, passage in pairs:
            claim_words = {w.strip(".,").lower() for w in claim.split() if len(w) > 3}
            passage_words = {w.strip(".,").lower() for w in passage.split()}
            scores.append(len(claim_words & passage_words) - 1.0)
        return scores


fake_st = types.ModuleType("sentence_transformers")
fake_st.CrossEncoder = WordOverlapCrossEncoder
sys.modules["sentence_transformers"] = fake_st

fake_tavily = types.ModuleType("tavily")
fake_tavily.TavilyClient = lambda **kwargs: None
sys.modules["tavily"] = fake_tavily

from backend.rag import pipeline  # noqa: E402

EVIDENCE = [
    {"evidence_id": "E1", "type": "document", "source": "nike.pdf", "page": 3,
     "content": "Nike was founded in 1964 by Bill Bowerman and Phil Knight."},
    {"evidence_id": "E2", "type": "web", "source": "Nike News",
     "url": "https://news.nike.com/x", "content": "Nike reported record revenue in 2025."},
]


def test_supported_claims_are_counted():
    answer = "Nike was founded in 1964 by Bowerman and Knight [E1]."
    cleaned, report = pipeline.verify_citations(answer, EVIDENCE)

    assert cleaned == answer
    assert report["cited_claims"] == 1
    assert report["supported_claims"] == 1
    assert report["weak_claims"] == []


def test_claim_that_does_not_match_its_evidence_is_flagged():
    answer = "The company makes electric cars on Mars [E1]."
    _, report = pipeline.verify_citations(answer, EVIDENCE)

    assert report["supported_claims"] == 0
    assert report["weak_claims"] == ["The company makes electric cars on Mars."]


def test_invented_evidence_ids_are_removed():
    answer = "Nike was founded in 1964 [E1][E7]."
    cleaned, report = pipeline.verify_citations(answer, EVIDENCE)

    assert "[E7]" not in cleaned
    assert "[E1]" in cleaned
    assert report["removed_invalid_citations"] == ["E7"]


def test_resolve_citations_formats_documents_and_links():
    text = pipeline.resolve_citations("Founded 1964 [E1]. Revenue grew [E2].", EVIDENCE)

    assert "[Source: nike.pdf, Page: 3]" in text
    assert "[Nike News](https://news.nike.com/x)" in text


def test_select_evidence_deduplicates_and_numbers():
    results = [
        {"question": "q1", "evidence": [EVIDENCE[0], EVIDENCE[0]]},
        {"question": "q2", "evidence": [EVIDENCE[1]]},
    ]
    selected = pipeline.select_evidence(results)

    assert [e["evidence_id"] for e in selected] == ["E1", "E2"]


def test_document_filter_targets_document_ids():
    assert pipeline.document_filter(None) is None
    condition = pipeline.document_filter(["a", "b"]).must[0]
    assert condition.key == "metadata.document_id"
    assert condition.match.any == ["a", "b"]


def test_history_is_formatted_for_prompts():
    text = pipeline.format_history([
        {"role": "user", "content": "What is Nike?"},
        {"role": "assistant", "content": "A sportswear company."},
    ])
    assert text == "User: What is Nike?\nAssistant: A sportswear company."


def test_no_evidence_gives_an_honest_answer_without_llm():
    assert "couldn't find any evidence" in pipeline.generate_answer("Q?", [])


def test_duplicate_chunks_are_returned_once(monkeypatch):
    from langchain_core.documents import Document

    def doc(text, page):
        return Document(page_content=text, metadata={"filename": "nike.pdf", "page": page})

    class FakeStore:
        def similarity_search_with_score(self, question, k, filter=None):
            return [
                (doc("Nike revenue grew in fiscal 2018.", 7), 0.9),
                (doc("Nike  revenue grew in fiscal 2018.", 7), 0.9),  # same text again
                (doc("Nike revenue was 46.3 billion in 2025.", 1), 0.8),
                (doc("Puma is a German company.", 0), 0.5),
            ]

    monkeypatch.setattr(pipeline, "vector_store", FakeStore())

    results = pipeline.retrieve_evidence("What was Nike revenue in 2025?", k=3)

    texts = [r["content"] for r in results]
    assert len(texts) == 3
    assert len({t.lower().replace("  ", " ") for t in texts}) == 3
    assert any("46.3" in t for t in texts)


def test_grouped_citations_are_split_and_reported():
    answer = "Nike was founded in 1964 by Bowerman and Knight [E1, E2]."
    cleaned, report = pipeline.verify_citations(answer, EVIDENCE)

    assert "[E1][E2]" in cleaned
    assert report["cited_ids"] == ["E1", "E2"]


def test_only_valid_ids_are_reported_as_cited():
    _, report = pipeline.verify_citations("Founded in 1964 by Knight [E2; E9].", EVIDENCE)
    assert report["cited_ids"] == ["E2"]
    assert report["removed_invalid_citations"] == ["E9"]
