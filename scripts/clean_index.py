"""Remove legacy chunks from Qdrant.

Chunks without a document_id come from the old ingestion script. They
have no row in the documents table and duplicate re-uploaded PDFs.

Usage (from the project root, with Qdrant running):

    python -m scripts.clean_index          # show how many would be removed
    python -m scripts.clean_index --yes    # remove them
"""

import argparse

from qdrant_client import QdrantClient, models

from backend.rag.vectorstore import COLLECTION_NAME, QDRANT_URL

LEGACY_FILTER = models.Filter(
    must=[models.IsEmptyCondition(is_empty=models.PayloadField(key="metadata.document_id"))]
)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--yes", action="store_true", help="actually delete the legacy chunks")
    args = parser.parse_args()

    client = QdrantClient(url=QDRANT_URL)
    total = client.count(COLLECTION_NAME, exact=True).count
    legacy = client.count(COLLECTION_NAME, count_filter=LEGACY_FILTER, exact=True).count

    print(f"Collection '{COLLECTION_NAME}': {total} chunks, {legacy} legacy (no document_id).")

    if not legacy:
        print("Nothing to clean.")
        return

    if not args.yes:
        print("Run again with --yes to delete them.")
        return

    client.delete(COLLECTION_NAME, points_selector=models.FilterSelector(filter=LEGACY_FILTER))
    remaining = client.count(COLLECTION_NAME, exact=True).count
    print(f"Deleted {legacy} legacy chunks. {remaining} chunks remain.")


if __name__ == "__main__":
    main()
