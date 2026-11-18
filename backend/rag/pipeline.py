"""Research building blocks: planning, retrieval, web search,
evidence selection, answer writing and citation checking."""

import logging
import os
import re

from dotenv import load_dotenv
from pydantic import BaseModel, Field
from qdrant_client import models
from sentence_transformers import CrossEncoder
from tavily import TavilyClient

from backend.llm import llm, structured_with_fallback
from backend.rag.vectorstore import vector_store
from prompts.research import answer_prompt, research_prompt

load_dotenv()

logger = logging.getLogger("researchflow.pipeline")


# --------------------------------------------------
# INITIALIZATION
# --------------------------------------------------

reranker = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")

tavily = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))

# How many candidates to fetch from Qdrant before reranking.
RETRIEVAL_CANDIDATES = int(os.getenv("RETRIEVAL_CANDIDATES", "20"))

# Cross-encoder score above which a cited claim counts as "supported".
CITATION_SUPPORT_THRESHOLD = float(
    os.getenv("CITATION_SUPPORT_THRESHOLD", "0")
)


def message_text(message) -> str:
    """Get plain text from a chat model reply (str or content blocks)."""
    content = getattr(message, "content", message)

    if isinstance(content, str):
        return content

    if isinstance(content, list):
        return "".join(
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        )

    return str(content)


def format_history(history: list[dict] | None, max_chars: int = 600) -> str:
    """Turn recent messages into a short text block for prompts."""
    if not history:
        return "(none)"

    lines = []
    for message in history:
        role = "User" if message.get("role") == "user" else "Assistant"
        text = re.sub(r"\s+", " ", message.get("content", "")).strip()
        lines.append(f"{role}: {text[:max_chars]}")

    return "\n".join(lines)


# --------------------------------------------------
# RESEARCH PLANNING (structured output)
# --------------------------------------------------

class ResearchPlan(BaseModel):
    standalone_question: str = Field(
        description="The user's latest message rewritten to be self-contained."
    )
    # Length limits are enforced in code: some providers reject
    # minItems/maxItems in tool schemas.
    sub_questions: list[str] = Field(
        description="One or two focused search questions."
    )


planner = structured_with_fallback(ResearchPlan)


def create_research_plan(
    question: str,
    history: list[dict] | None = None,
) -> ResearchPlan:
    prompt = research_prompt.invoke(
        {"question": question, "history": format_history(history)}
    )
    plan = planner.invoke(prompt)

    # Clean up and de-duplicate, keep at most two sub-questions.
    sub_questions = list(
        dict.fromkeys(q.strip() for q in plan.sub_questions if q.strip())
    )[:2]

    return ResearchPlan(
        standalone_question=plan.standalone_question.strip() or question,
        sub_questions=sub_questions or [question],
    )


# --------------------------------------------------
# DOCUMENT RETRIEVAL + RERANKING
# --------------------------------------------------

def document_filter(document_ids: list[str] | None):
    """Qdrant filter that keeps only chunks of the chosen PDFs."""
    if not document_ids:
        return None

    return models.Filter(
        must=[
            models.FieldCondition(
                key="metadata.document_id",
                match=models.MatchAny(any=list(document_ids)),
            )
        ]
    )


def page_number(raw_page):
    """PyPDF pages are zero-based; show one-based page numbers."""
    if raw_page is None:
        return None
    try:
        return int(raw_page) + 1
    except (TypeError, ValueError):
        return raw_page


def retrieve_evidence(
    question: str,
    k: int = 3,
    document_ids: list[str] | None = None,
) -> list[dict]:
    """Vector search in Qdrant, then rerank with a cross-encoder."""
    documents = vector_store.similarity_search_with_score(
        question,
        k=RETRIEVAL_CANDIDATES,
        filter=document_filter(document_ids),
    )

    if not documents:
        return []

    # The same text can be stored more than once (e.g. a PDF indexed
    # twice). Keep one copy, so the top-k results are all different.
    unique, seen_text = [], set()
    for doc, score in documents:
        text_key = re.sub(r"\s+", " ", doc.page_content).strip().lower()
        if text_key not in seen_text:
            seen_text.add(text_key)
            unique.append((doc, score))

    pairs = [[question, doc.page_content] for doc, _score in unique]
    rerank_scores = reranker.predict(pairs)

    ranked = sorted(
        zip(unique, rerank_scores),
        key=lambda item: item[1],
        reverse=True,
    )[:k]

    evidence = []

    for (doc, vector_score), rerank_score in ranked:
        source = (
            doc.metadata.get("filename")
            or doc.metadata.get("source")
            or "Unknown document"
        )

        evidence.append(
            {
                "content": doc.page_content,
                "source": source,
                "document_id": doc.metadata.get("document_id"),
                "url": None,
                "page": page_number(doc.metadata.get("page")),
                "snippet": doc.page_content[:200],
                "vector_score": float(vector_score),
                "rerank_score": float(rerank_score),
                "type": "document",
            }
        )

    return evidence


# --------------------------------------------------
# WEB SEARCH
# --------------------------------------------------

def web_search(question: str) -> list[dict]:
    response = tavily.search(query=question, max_results=5)

    evidence = []

    for result in response.get("results", []):
        content = result.get("content", "")

        if not isinstance(content, str) or not content.strip():
            continue

        evidence.append(
            {
                "content": content,
                "source": result.get("title") or "Web source",
                "url": result.get("url"),
                "page": None,
                "snippet": content[:200],
                "type": "web",
            }
        )

    return evidence


# --------------------------------------------------
# EVIDENCE SELECTION + CONTEXT
# --------------------------------------------------

def select_evidence(results: list) -> list[dict]:
    """Merge worker results, drop duplicates, give each item an ID."""
    selected = []
    seen = set()

    for result in results:
        if not isinstance(result, dict):
            continue

        question = result.get("question", "")

        for item in result.get("evidence", []):
            if not isinstance(item, dict):
                continue

            content = item.get("content", "")

            if not isinstance(content, str) or not content.strip():
                continue

            key = (item.get("source"), item.get("url"), content.strip())

            if key in seen:
                continue

            seen.add(key)

            evidence_item = item.copy()
            evidence_item["question"] = question
            evidence_item["evidence_id"] = f"E{len(selected) + 1}"

            selected.append(evidence_item)

    return selected


def build_context(selected_evidence: list) -> str:
    parts = []

    for item in selected_evidence:
        parts.append(
            f"Evidence ID: [{item['evidence_id']}]\n"
            f"Research question: {item.get('question', 'Not specified')}\n"
            f"Source: {item.get('source') or 'Unknown'}\n"
            f"Type: {item.get('type', 'unknown')}\n"
            f"Page: {item.get('page')}\n"
            f"URL: {item.get('url')}\n"
            f"Content: {item.get('content', '')}\n"
        )

    return "\n---\n".join(parts)


# --------------------------------------------------
# ANSWER GENERATION
# --------------------------------------------------

def generate_answer(
    question: str,
    selected_evidence: list,
    history: list[dict] | None = None,
) -> str:
    """Write the answer with [E#] citations (one LLM call)."""
    if not selected_evidence:
        return (
            "I couldn't find any evidence for this question in your "
            "documents or on the web, so I can't give a grounded answer."
        )

    prompt = answer_prompt.invoke(
        {
            "question": question,
            "context": build_context(selected_evidence),
            "history": format_history(history),
        }
    )

    # One call only. If the main model fails, llm.with_fallbacks()
    # in backend/llm.py retries once on the backup model.
    return message_text(llm.invoke(prompt))


# --------------------------------------------------
# CITATION VERIFICATION (no LLM: uses the reranker)
# --------------------------------------------------

CITATION_PATTERN = re.compile(r"\[(E\d+)\]")
SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")


def verify_citations(answer: str, selected_evidence: list) -> tuple[str, dict]:
    """Check every cited claim against the evidence it cites.

    * Citations to evidence IDs that don't exist are removed.
    * Each cited sentence is scored against its evidence with the
      cross-encoder. A low score means the evidence probably does not
      support the claim.

    Returns the cleaned answer and a small report for the UI.
    """
    evidence_map = {
        item["evidence_id"]: item
        for item in selected_evidence
        if isinstance(item, dict) and item.get("evidence_id")
    }

    invalid_ids = sorted(
        {eid for eid in CITATION_PATTERN.findall(answer) if eid not in evidence_map}
    )

    cleaned = CITATION_PATTERN.sub(
        lambda m: m.group(0) if m.group(1) in evidence_map else "",
        answer,
    )

    pairs = []
    claims = []

    for sentence in SENTENCE_SPLIT.split(cleaned):
        cited_ids = [
            eid for eid in CITATION_PATTERN.findall(sentence) if eid in evidence_map
        ]
        claim = CITATION_PATTERN.sub("", sentence)
        claim = re.sub(r"\s+([.,;:!?])", r"\1", claim).strip(" -*#\t")

        if not cited_ids or len(claim) < 15:
            continue

        claims.append(claim)
        for eid in cited_ids:
            pairs.append((len(claims) - 1, claim, evidence_map[eid]["content"]))

    supported = [False] * len(claims)

    if pairs:
        scores = reranker.predict([[claim, content] for _, claim, content in pairs])
        for (claim_index, _, _), score in zip(pairs, scores):
            if score >= CITATION_SUPPORT_THRESHOLD:
                supported[claim_index] = True

    report = {
        "cited_claims": len(claims),
        "supported_claims": sum(supported),
        "weak_claims": [c for c, ok in zip(claims, supported) if not ok][:5],
        "removed_invalid_citations": invalid_ids,
    }

    return cleaned, report


# --------------------------------------------------
# CITATION RESOLUTION ([E1] -> readable source)
# --------------------------------------------------

def resolve_citations(answer: str, selected_evidence: list) -> str:
    evidence_map = {
        item["evidence_id"]: item
        for item in selected_evidence
        if isinstance(item, dict) and item.get("evidence_id")
    }

    def replace_citation(match):
        item = evidence_map.get(match.group(1))

        if item is None:
            return match.group(0)

        source = str(item.get("source") or "Unknown source")
        # Escape square brackets so Markdown links don't break.
        source = source.replace("[", r"\[").replace("]", r"\]")
        url = item.get("url")
        page = item.get("page")

        if item.get("type") == "web" and url:
            return f"[{source}]({url})"

        if item.get("type") == "document":
            citation = f"[Source: {source}"
            if page is not None:
                citation += f", Page: {page}"
            return citation + "]"

        if url:
            return f"[{source}]({url})"

        return f"[Source: {source}]"

    return CITATION_PATTERN.sub(replace_citation, answer)
