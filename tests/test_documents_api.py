"""Tests for the PDF upload endpoints (database and ingestion are mocked)."""

import pytest
from fastapi.testclient import TestClient

import backend.main as main

VALID_PDF = b"%PDF-1.4\n fake pdf body"


@pytest.fixture
def client(tmp_path, monkeypatch):
    saved_documents = []
    known_hashes = set()

    monkeypatch.setattr(main, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(
        main, "document_exists", lambda file_hash: file_hash in known_hashes
    )

    def fake_create_document(document_id, filename, file_hash, pages, chunks):
        known_hashes.add(file_hash)
        saved_documents.append(
            {
                "document_id": document_id,
                "filename": filename,
                "pages": pages,
                "chunks": chunks,
            }
        )

    monkeypatch.setattr(main, "create_document", fake_create_document)
    monkeypatch.setattr(main, "list_documents", lambda: saved_documents)
    monkeypatch.setattr(
        main,
        "ingest_pdf",
        lambda path, filename, document_id: {"pages": 2, "chunks": 5},
    )

    # no context manager -> lifespan (init_db) doesn't run
    test_client = TestClient(main.app)
    test_client.saved_documents = saved_documents
    test_client.upload_dir = tmp_path
    return test_client


def upload(client, content=VALID_PDF, name="report.pdf"):
    return client.post(
        "/documents/upload",
        files={"file": (name, content, "application/pdf")},
    )


def test_upload_valid_pdf(client):
    response = upload(client)

    assert response.status_code == 200
    body = response.json()
    assert body["filename"] == "report.pdf"
    assert body["pages"] == 2
    assert body["chunks"] == 5

    saved = list(client.upload_dir.iterdir())
    assert len(saved) == 1
    assert saved[0].name == f"{body['document_id']}.pdf"


def test_same_pdf_twice_is_rejected(client):
    assert upload(client).status_code == 200

    response = upload(client, name="renamed-copy.pdf")

    assert response.status_code == 409
    assert "already been uploaded" in response.json()["detail"]


def test_non_pdf_extension_is_rejected(client):
    response = upload(client, content=b"hello", name="notes.txt")
    assert response.status_code == 400


def test_fake_pdf_content_is_rejected(client):
    response = upload(client, content=b"MZ not really a pdf", name="virus.pdf")

    assert response.status_code == 400
    assert "not a valid PDF" in response.json()["detail"]


def test_too_large_file_is_rejected(client, monkeypatch):
    monkeypatch.setattr(main, "MAX_UPLOAD_BYTES", 10)

    response = upload(client)

    assert response.status_code == 413
    assert list(client.upload_dir.iterdir()) == []


def test_pdf_without_text_is_rejected_and_file_removed(client, monkeypatch):
    monkeypatch.setattr(
        main,
        "ingest_pdf",
        lambda path, filename, document_id: {"pages": 3, "chunks": 0},
    )

    response = upload(client)

    assert response.status_code == 422
    assert list(client.upload_dir.iterdir()) == []
    assert client.saved_documents == []


def test_ingestion_error_returns_500_and_file_removed(client, monkeypatch):
    def broken_ingest(path, filename, document_id):
        raise ValueError("broken pdf")

    monkeypatch.setattr(main, "ingest_pdf", broken_ingest)

    response = upload(client)

    assert response.status_code == 500
    assert list(client.upload_dir.iterdir()) == []


def test_list_documents(client):
    upload(client)

    response = client.get("/documents")

    assert response.status_code == 200
    documents = response.json()["documents"]
    assert len(documents) == 1
    assert documents[0]["filename"] == "report.pdf"


def test_unknown_session_returns_404(client, monkeypatch):
    monkeypatch.setattr(main, "get_research_session_by_id", lambda session_id: None)

    response = client.get("/sessions/does-not-exist")

    assert response.status_code == 404
