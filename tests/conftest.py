"""Shared test setup.

The real app loads an LLM, MCP tools, embedding models and connects
to Qdrant at import time. Unit tests should not need any of that,
so we register lightweight fake modules *before* the app is imported.
"""

import sys
import types
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


# Fake research agent (no LLM / MCP calls)
fake_service = types.ModuleType("backend.agent.service")


async def _fake_run_research(question: str, session_id: str) -> dict:
    return {
        "session_id": session_id,
        "status": "completed",
        "answer": "stub answer",
        "selected_evidence": [],
    }


fake_service.run_research = _fake_run_research
fake_service.save_research_answer = lambda *args, **kwargs: None
sys.modules["backend.agent.service"] = fake_service


# Fake vector store (no Qdrant, no embedding model)
class FakeVectorStore:
    def __init__(self):
        self.added = []

    def add_documents(self, documents):
        self.added.extend(documents)


fake_vectorstore = types.ModuleType("backend.rag.vectorstore")
fake_vectorstore.vector_store = FakeVectorStore()
fake_vectorstore.ensure_collection = lambda: None
sys.modules["backend.rag.vectorstore"] = fake_vectorstore
