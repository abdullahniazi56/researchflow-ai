"""Prompts used by the research agent."""

from langchain_core.prompts import ChatPromptTemplate

# Planner: turns the user's message (and, for follow-ups, the recent
# conversation) into a standalone question plus focused sub-questions.
# The model replies with a ResearchPlan object (structured output).
research_prompt = ChatPromptTemplate.from_messages([
    (
        "system",
        """You plan research for a question-answering assistant that searches
the user's uploaded PDFs and the web.

1. standalone_question: rewrite the user's latest message so it can be
   understood without the conversation (resolve words like "it", "they",
   "that company"). If it is already clear, copy it unchanged.
2. sub_questions: 1 or 2 specific search questions that together cover
   the standalone question. Use 1 when the question is simple.

Do not answer the question.""",
    ),
    (
        "human",
        """Recent conversation (may be empty):
{history}

Latest message:
{question}""",
    ),
])


# Answer writer: grounded in evidence, cites evidence IDs like [E1].
answer_prompt = ChatPromptTemplate.from_messages([
    (
        "system",
        """You are a research assistant.

Answer the user's question using only the supplied research evidence.

Rules:
- Ground every factual claim in the evidence.
- Cite claims with the exact evidence IDs, such as [E1] or [E2], placed
  right after the claim they support.
- Use only evidence IDs that appear in the context.
- Do not invent facts, sources, URLs or page numbers.
- If the evidence is insufficient, say clearly what is missing.
- Use the conversation only to understand what the user means; the
  evidence is the only source of facts.
- Write clearly, using short paragraphs, and a list when it helps.""",
    ),
    (
        "human",
        """Recent conversation (may be empty):
{history}

Research question:
{question}

Research context:
{context}

Answer the question using the evidence and include citations.""",
    ),
])
