"""Tests the real PDF loading and chunking, with a fake vector store."""

from pathlib import Path

import pytest

from backend.rag import ingestion
from backend.rag.vectorstore import vector_store

SAMPLE_PDF = Path(__file__).resolve().parents[1] / "data" / "sample.pdf"


@pytest.mark.skipif(not SAMPLE_PDF.exists(), reason="data/sample.pdf not found")
def test_ingest_pdf_creates_chunks_with_metadata():
    vector_store.added.clear()

    result = ingestion.ingest_pdf(SAMPLE_PDF, "my-report.pdf", "doc-123")

    assert result["pages"] > 0
    assert result["chunks"] > 0
    assert len(vector_store.added) == result["chunks"]

    for chunk in vector_store.added:
        assert chunk.page_content.strip()
        assert chunk.metadata["filename"] == "my-report.pdf"
        assert chunk.metadata["document_id"] == "doc-123"
        assert "page" in chunk.metadata
