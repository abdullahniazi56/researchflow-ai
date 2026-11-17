"""Research endpoints: new sessions, follow-ups, streaming, auth."""

import json

import pytest
from fastapi.testclient import TestClient

import backend.main as main


@pytest.fixture
def api(monkeypatch):
    state = {"sessions": {"research-existing"}, "messages": [], "calls": []}

    monkeypatch.setattr(main, "research_session_exists", lambda sid: sid in state["sessions"])
    monkeypatch.setattr(main, "create_research_session", lambda sid, title: state["sessions"].add(sid))
    monkeypatch.setattr(
        main, "create_message",
        lambda sid, role, content: state["messages"].append((sid, role, content)) or 1,
    )
    monkeypatch.setattr(
        main, "load_history",
        lambda sid: [{"role": "user", "content": "What is Nike?"},
                     {"role": "assistant", "content": "Nike is a sportswear company."}],
    )

    async def fake_run(question, session_id, history=None, document_ids=None):
        state["calls"].append({"question": question, "history": history, "document_ids": document_ids})
        return {
            "session_id": session_id, "status": "completed", "answer": "An answer",
            "selected_evidence": [], "verification": {"cited_claims": 1, "supported_claims": 1},
        }

    async def fake_stream(question, session_id, history=None, document_ids=None):
        yield {"type": "step", "step": "plan", "message": "Researching the question directly"}
        yield {"type": "result", **(await fake_run(question, session_id, history, document_ids))}

    monkeypatch.setattr(main, "run_research", fake_run)
    monkeypatch.setattr(main, "stream_research", fake_stream)
    monkeypatch.setattr(main, "save_research_answer", lambda sid, result: None)

    client = TestClient(main.app)
    client.state = state
    return client


def test_new_question_creates_session(api):
    response = api.post("/research", json={"question": "What is RAG?"})

    assert response.status_code == 200
    body = response.json()
    assert body["session_id"].startswith("research-")
    assert body["answer"] == "An answer"
    assert body["verification"]["supported_claims"] == 1
    assert api.state["calls"][0]["history"] == []


def test_follow_up_uses_session_history(api):
    response = api.post(
        "/research",
        json={"question": "When was it founded?", "session_id": "research-existing"},
    )

    assert response.status_code == 200
    assert response.json()["session_id"] == "research-existing"
    assert api.state["calls"][0]["history"][0]["content"] == "What is Nike?"


def test_follow_up_to_unknown_session_is_404(api):
    response = api.post("/research", json={"question": "Hi there", "session_id": "nope"})
    assert response.status_code == 404


def test_document_filter_is_passed_to_research(api):
    api.post("/research", json={"question": "Summarise", "document_ids": ["doc-1"]})
    assert api.state["calls"][0]["document_ids"] == ["doc-1"]


def test_stream_sends_steps_then_result(api):
    response = api.post("/research/stream", json={"question": "What is RAG?"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")

    events = [
        json.loads(line[len("data: "):])
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]
    assert [e["type"] for e in events] == ["session", "step", "result"]
    assert events[-1]["answer"] == "An answer"
    assert events[-1]["message"] == "Research completed."


def test_api_key_is_required_when_configured(api, monkeypatch):
    monkeypatch.setattr(main, "API_KEY", "secret")
    monkeypatch.setattr(main, "get_research_session", lambda: [])

    assert api.get("/sessions").status_code == 401
    assert api.get("/sessions", headers={"X-API-Key": "wrong"}).status_code == 401
    assert api.get("/sessions", headers={"X-API-Key": "secret"}).status_code == 200
    assert api.get("/health").status_code == 200


def test_delete_document(api, monkeypatch, tmp_path):
    removed = []
    monkeypatch.setattr(main, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(main, "delete_document", lambda doc_id: "nike.pdf" if doc_id == "d1" else None)
    monkeypatch.setattr(main, "delete_document_chunks", lambda doc_id: removed.append(doc_id))
    (tmp_path / "d1.pdf").write_bytes(b"%PDF-1.4")

    assert api.delete("/documents/d1").status_code == 200
    assert removed == ["d1"]
    assert not (tmp_path / "d1.pdf").exists()
    assert api.delete("/documents/missing").status_code == 404
