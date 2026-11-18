"""PDF -> chunks -> Qdrant."""

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

    loader = PyPDFLoader(str(file_path))
    pages = loader.load()

    for page in pages:
        page.metadata["filename"] = original_filename
        page.metadata["document_id"] = document_id

    chunks = splitter.split_documents(pages)

    chunks = [chunk for chunk in chunks if chunk.page_content.strip()]

    if chunks:
        ensure_collection()
        vector_store.add_documents(chunks)

    return {
        "pages": len(pages),
        "chunks": len(chunks),
    }


def delete_document_chunks(document_id: str) -> None:
    from qdrant_client import models

    from backend.rag.vectorstore import COLLECTION_NAME, client

    client.delete(
        collection_name=COLLECTION_NAME,
        points_selector=models.FilterSelector(
            filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="metadata.document_id",
                        match=models.MatchValue(value=document_id),
                    )
                ]
            )
        ),
    )
