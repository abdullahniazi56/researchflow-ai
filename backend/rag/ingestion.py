"""Turn an uploaded PDF into chunks and store them in Qdrant."""

from pathlib import Path

from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

from backend.rag.vectorstore import ensure_collection, vector_store

splitter = RecursiveCharacterTextSplitter(
    chunk_size=1000,
    chunk_overlap=200,
)


def ingest_pdf(
    file_path: Path,
    original_filename: str,
    document_id: str,
) -> dict:
    """Load one PDF, split it into chunks and add them to Qdrant."""

    loader = PyPDFLoader(str(file_path))
    pages = loader.load()

    for page in pages:
        # The original name is shown in citations, e.g. [Source: nike.pdf, Page: 3]
        page.metadata["filename"] = original_filename
        page.metadata["document_id"] = document_id

    chunks = splitter.split_documents(pages)

    # Chunks that are only whitespace are useless for search.
    chunks = [chunk for chunk in chunks if chunk.page_content.strip()]

    if chunks:
        ensure_collection()
        vector_store.add_documents(chunks)

    return {
        "pages": len(pages),
        "chunks": len(chunks),
    }
