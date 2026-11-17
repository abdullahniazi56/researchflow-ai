"""Shared embedding model and Qdrant vector store.

Every module that needs the vector store (retrieval, ingestion)
imports it from here, so the model is configured in one place.
"""

import os

from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_qdrant import QdrantVectorStore

load_dotenv()

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
COLLECTION_NAME = os.getenv("QDRANT_COLLECTION", "researchflow_documents")

EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
# all-MiniLM-L6-v2 turns every text into a vector of 384 numbers.
EMBEDDING_SIZE = 384

embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)
client = QdrantClient(url=QDRANT_URL)


def ensure_collection() -> None:
    """Create the collection on first run if it does not exist yet."""
    if not client.collection_exists(COLLECTION_NAME):
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(
                size=EMBEDDING_SIZE,
                distance=Distance.COSINE,
            ),
        )


ensure_collection()

vector_store = QdrantVectorStore(
    client=client,
    collection_name=COLLECTION_NAME,
    embedding=embeddings,
)
