
import os
import re

from dotenv import load_dotenv
from tavily import TavilyClient
from sentence_transformers import CrossEncoder

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import tool

from backend.llm import llm
from backend.rag.vectorstore import vector_store
from prompts.research import research_prompt

load_dotenv()


# --------------------------------------------------
# INITIALIZATION
# --------------------------------------------------

reranker = CrossEncoder(
    "cross-encoder/ms-marco-MiniLM-L-6-v2"
)

tavily = TavilyClient(
    api_key=os.getenv("TAVILY_API_KEY")
)


# --------------------------------------------------
# RESEARCH PLANNING
# --------------------------------------------------

def create_research_plan(question: str) -> list[str]:
    prompt = research_prompt.invoke(
        {"question": question}
    )

    response = llm.invoke(prompt)
    raw = response.content

    if isinstance(raw, str):
        content = raw

    elif isinstance(raw, list):
        content = "".join(
            block.get("text", "")
            for block in raw
            if isinstance(block, dict)
            and block.get("type") == "text"
        )

    else:
        content = str(raw)

    questions = []

    for line in content.splitlines():
        q = line.strip()

        if not q:
            continue

        # Remove common numbered-list prefixes:
        # 1. Question
        # 1) Question
        # **1.** Question
        q = re.sub(
            r"^\s*(?:\*\*)?\d+[.)]\s*(?:\*\*)?\s*",
            "",
            q,
        ).strip()

        if q:
            questions.append(q)

    # Remove duplicate questions while preserving order.
    questions = list(dict.fromkeys(questions))

    return questions[:2]


# --------------------------------------------------
# DOCUMENT RETRIEVAL + RERANKING
# --------------------------------------------------

def retrieve_evidence(
    question: str,
    k: int = 3,
) -> list[dict]:

    documents = vector_store.similarity_search_with_score(
        question,
        k=10,
    )

    if not documents:
        return []

    pairs = [
        [question, doc.page_content]
        for doc, _score in documents
    ]

    rerank_scores = reranker.predict(pairs)

    ranked_documents = list(
        zip(documents, rerank_scores)
    )

    ranked_documents.sort(
        key=lambda item: item[1],
        reverse=True,
    )

    ranked_documents = ranked_documents[:k]

    evidence = []

    for (doc, vector_score), rerank_score in ranked_documents:
        # Support common metadata keys for the source filename.
        source = (
            doc.metadata.get("filename")
            or doc.metadata.get("source")
            or "Unknown document"
        )

        # Page metadata is commonly zero-based, but some ingestion
        # pipelines store a one-based page number.
        raw_page = doc.metadata.get("page")

        if raw_page is not None:
            try:
                page = int(raw_page)

                # Assumes the ingestion pipeline stores zero-based pages.
                page += 1
            except (TypeError, ValueError):
                page = raw_page
        else:
            page = None

        evidence.append(
            {
                "content": doc.page_content,
                "source": source,
                "url": None,
                "page": page,
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
    response = tavily.search(
        query=question,
        max_results=5,
    )

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
# LANGCHAIN TOOLS
# --------------------------------------------------

@tool
def document_search(question: str) -> list[dict]:
    """Search uploaded research documents for relevant evidence."""
    return retrieve_evidence(question, k=3)


@tool
def web_search_tool(question: str) -> list[dict]:
    """Search the web for external or current research evidence."""
    return web_search(question)


research_tools = [
    document_search,
    web_search_tool,
]


# --------------------------------------------------
# EVIDENCE SELECTION
# --------------------------------------------------

def select_evidence(results: list) -> list[dict]:
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

            key = (
                item.get("source"),
                item.get("url"),
                content.strip(),
            )

            if key in seen:
                continue

            seen.add(key)

            evidence_item = item.copy()
            evidence_item["question"] = question
            evidence_item["evidence_id"] = (
                f"E{len(selected) + 1}"
            )

            selected.append(evidence_item)

    return selected


# --------------------------------------------------
# CONTEXT BUILDING
# --------------------------------------------------

def build_context(selected_evidence: list) -> str:
    context_parts = []

    for item in selected_evidence:
        evidence_id = item["evidence_id"]

        context_parts.append(
            f"Evidence ID: [{evidence_id}]\n"
            f"Research question: "
            f"{item.get('question', 'Not specified')}\n"
            f"Source: {item.get('source') or 'Unknown'}\n"
            f"Type: {item.get('type', 'unknown')}\n"
            f"Page: {item.get('page')}\n"
            f"URL: {item.get('url')}\n"
            f"Content: {item.get('content', '')}\n"
        )

    return "\n---\n".join(context_parts)


# --------------------------------------------------
# ANSWER GENERATION PROMPT
# --------------------------------------------------

answer_prompt = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """
You are a research assistant.

Answer the user's question using the supplied research evidence.

Rules:
- Ground factual claims in the supplied evidence.
- Cite supporting claims using exact evidence IDs, such as [E1] or [E2].
- Use only evidence IDs that appear in the supplied context.
- Place citations immediately after the claims they support.
- Do not invent facts, sources, URLs, or page numbers.
- If evidence is insufficient, clearly state the limitation.
- Distinguish supported facts from uncertainty.
- Write a clear, well-structured answer.
- Do not create your own source labels or citation formats.
""",
        ),
        (
            "human",
            """
Research question:
{question}

Research context:
{context}

Answer the question using the evidence and include citations.
""",
        ),
    ]
)


# --------------------------------------------------
# CITATION RESOLUTION
# --------------------------------------------------

def resolve_citations(
    answer: str,
    selected_evidence: list,
) -> str:

    evidence_map = {
        item["evidence_id"]: item
        for item in selected_evidence
        if isinstance(item, dict) and item.get("evidence_id")
    }

    def replace_citation(match):
        evidence_id = match.group(1)
        item = evidence_map.get(evidence_id)

        # Preserve unknown IDs instead of inventing a source.
        if item is None:
            return match.group(0)

        source = item.get("source") or "Unknown source"
        url = item.get("url")
        page = item.get("page")
        evidence_type = item.get("type")

        # Escape square brackets in source titles to avoid
        # breaking Markdown link syntax.
        source = str(source).replace("[", r"\[").replace("]", r"\]")
        
        if evidence_type == "web" and url:
            return f"[{source}]({url})"

        if evidence_type == "document":
            citation = f"[Source: {source}"

            if page is not None:
                citation += f", Page: {page}"

            return citation + "]"

        if url:
            return f"[{source}]({url})"

        return f"[Source: {source}]"

    return re.sub(
        r"\[(E\d+)\]",
        replace_citation,
        answer,
    )


# --------------------------------------------------
# FINAL ANSWER
# --------------------------------------------------

def generate_answer(
    question: str,
    selected_evidence: list,
) -> str:

    context = build_context(selected_evidence)

    prompt = answer_prompt.invoke(
        {
            "question": question,
            "context": context,
        }
    )

    # One call only. If the main model fails (e.g. Gemini quota used up),
    # llm.with_fallbacks() in backend/llm.py retries once on the backup
    # model. Retrying Gemini here again would only waste more quota.
    response = llm.invoke(prompt)

    answer = response.content

    if isinstance(answer, list):
        answer = "".join(
            block.get("text", "")
            for block in answer
            if isinstance(block, dict)
            and block.get("type") == "text"
        )
    elif not isinstance(answer, str):
        answer = str(answer)

    return resolve_citations(
        answer,
        selected_evidence,
    )
