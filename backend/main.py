"""ResearchFlow AI — FastAPI backend."""

import asyncio
import hashlib
import json
import logging
import os
import secrets
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.agent.service import (
    load_history,
    run_research,
    save_research_answer,
    stream_research,
)
from backend.db import (
    create_document,
    create_message,
    create_research_session,
    delete_document,
    delete_research_session,
    document_exists,
    get_messages_with_sources,
    get_research_session,
    get_research_session_by_id,
    init_db,
    list_documents,
    research_session_exists,
    update_research_session_title,
)
from backend.mcp.client import mcp_client
from backend.rag.ingestion import delete_document_chunks, ingest_pdf

load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("researchflow")


# --------------------------------------------------
# SETTINGS
# --------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[1]
UPLOAD_DIR = PROJECT_ROOT / "data" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20 MB

CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    ).split(",")
    if origin.strip()
]

# Optional: when API_KEY is set, every request (except health and docs)
# must send the header  X-API-Key: <API_KEY>
API_KEY = os.getenv("API_KEY") or None
PUBLIC_PATHS = {"/", "/health", "/docs", "/redoc", "/openapi.json"}


async def require_api_key(
    request: Request,
    x_api_key: str | None = Header(default=None),
):
    if not API_KEY or request.url.path in PUBLIC_PATHS:
        return
    if not secrets.compare_digest(x_api_key or "", API_KEY):
        raise HTTPException(status_code=401, detail="Invalid or missing API key.")


# --------------------------------------------------
# APP
# --------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create any missing database tables.
    try:
        init_db()
    except Exception as exc:
        logger.error("Database is not available: %s", exc)

    # Warm up the MCP tool server in the background, so the API is
    # usable right away and the models load before the first question.
    async def warm_up_tools():
        try:
            await mcp_client.start()
            logger.info("MCP tool server is ready.")
        except Exception as exc:
            logger.warning("MCP tool server could not start yet: %s", exc)

    warm_up = asyncio.create_task(warm_up_tools())

    yield

    warm_up.cancel()
    await mcp_client.close()


app = FastAPI(
    title="ResearchFlow AI API",
    description=(
        "Research agent that answers questions from your PDFs and the web, "
        "with verified citations."
    ),
    version="2.0.0",
    lifespan=lifespan,
    dependencies=[Depends(require_api_key)],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------
# SCHEMAS
# --------------------------------------------------

class UpdateSessionTitle(BaseModel):
    title: str = Field(min_length=1, max_length=100)


class ResearchRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    session_id: str | None = Field(
        default=None,
        description="Continue this session (follow-up question).",
    )
    document_ids: list[str] | None = Field(
        default=None,
        max_length=50,
        description="Search only these uploaded PDFs.",
    )


class ResearchResponse(BaseModel):
    message: str
    session_id: str
    question: str
    status: Literal["completed", "stopped", "failed"]
    answer: str | None = None
    selected_evidence: list[dict] = []
    verification: dict | None = None
    seconds: float | None = None


# --------------------------------------------------
# HEALTH + SESSIONS
# --------------------------------------------------

@app.get("/")
def home():
    return {"message": "ResearchFlow AI API is running"}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/sessions")
def list_sessions():
    return {"sessions": get_research_session()}


@app.get("/sessions/{session_id}")
def get_session_details(session_id: str):
    session = get_research_session_by_id(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Research session not found")
    return session


@app.get("/sessions/{session_id}/messages")
def get_session_messages(session_id: str):
    if not research_session_exists(session_id):
        raise HTTPException(status_code=404, detail="Research session not found")
    return {"session_id": session_id, "messages": get_messages_with_sources(session_id)}


@app.delete("/sessions/{session_id}")
def delete_session(session_id: str):
    if not delete_research_session(session_id):
        raise HTTPException(status_code=404, detail="Research session not found")
    return {"message": "Research session deleted successfully", "session_id": session_id}


@app.patch("/sessions/{session_id}")
def rename_session(session_id: str, body: UpdateSessionTitle):
    new_title = body.title.strip()
    if not new_title:
        raise HTTPException(status_code=422, detail="Title cannot be empty")
    if not update_research_session_title(session_id, new_title):
        raise HTTPException(status_code=404, detail="Research session not found")
    return {"message": "Research session title updated", "session_id": session_id, "title": new_title}


# --------------------------------------------------
# RESEARCH
# --------------------------------------------------

def open_session(body: ResearchRequest) -> tuple[str, str, list[dict]]:
    """Create a new session or continue an existing one.

    Returns (session_id, question, history). The history is loaded
    before the new question is saved, so it holds earlier turns only.
    """
    question = body.question.strip()
    if not question:
        raise HTTPException(status_code=422, detail="Research question cannot be empty")

    try:
        if body.session_id:
            if not research_session_exists(body.session_id):
                raise HTTPException(status_code=404, detail="Research session not found")
            session_id = body.session_id
            history = load_history(session_id)
        else:
            session_id = f"research-{uuid.uuid4().hex[:12]}"
            create_research_session(session_id, question[:100])
            history = []

        create_message(session_id, "user", question)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Database is not available: {exc}")

    return session_id, question, history


def result_message(result: dict) -> str:
    if result["status"] == "completed":
        return "Research completed."
    if result["status"] == "failed":
        return result.get("message", "Research failed.")
    return "Research stopped before an answer was generated."


@app.post("/research", response_model=ResearchResponse)
async def create_research_request(body: ResearchRequest):
    """Run the whole research and return the result in one response."""
    session_id, question, history = open_session(body)

    result = await run_research(question, session_id, history, body.document_ids)

    if result["status"] == "completed":
        save_research_answer(session_id, result)

    return {**result, "message": result_message(result), "question": question}


@app.post("/research/stream")
async def stream_research_request(body: ResearchRequest):
    """Run research and stream progress as Server-Sent Events.

    Each event is a line "data: {json}". Step events look like
    {"type": "step", "step": "search", "message": "..."}; the last event
    is {"type": "result", ...} with the same fields as POST /research.
    """
    session_id, question, history = open_session(body)

    async def events():
        yield sse({"type": "session", "session_id": session_id, "question": question})

        async for event in stream_research(question, session_id, history, body.document_ids):
            if event["type"] == "result":
                if event["status"] == "completed":
                    try:
                        save_research_answer(session_id, event)
                    except Exception as exc:
                        logger.error("Could not save the answer: %s", exc)
                event = {**event, "message": result_message(event), "question": question}
            yield sse(event)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def sse(data: dict) -> str:
    return f"data: {json.dumps(data, default=str)}\n\n"


# --------------------------------------------------
# DOCUMENTS
# --------------------------------------------------

# A plain "def" (not "async def"): PDF parsing and embedding are
# CPU-heavy, and FastAPI runs sync endpoints in a worker thread,
# so the server stays responsive while a file is processed.
@app.post("/documents/upload")
def upload_document(file: UploadFile = File(...)):
    filename = file.filename or "document.pdf"

    # 1. Extension check
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed.")

    # 2. Size check (read one byte past the limit to detect big files)
    contents = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(contents) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File is too large (max 20 MB).")

    # 3. Real PDF? Every PDF file starts with "%PDF-"
    if not contents.startswith(b"%PDF-"):
        raise HTTPException(status_code=400, detail="This file is not a valid PDF.")

    # 4. Duplicate check (same content = same hash, whatever the name)
    file_hash = hashlib.sha256(contents).hexdigest()
    try:
        already_uploaded = document_exists(file_hash)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Database is not available: {exc}")

    if already_uploaded:
        raise HTTPException(status_code=409, detail="This document has already been uploaded.")

    # 5. Save with our own name. Never use the user's filename in a
    #    path: a name like "../../backend/main.py" could overwrite files.
    document_id = uuid.uuid4().hex
    save_path = UPLOAD_DIR / f"{document_id}.pdf"
    save_path.write_bytes(contents)

    # 6. Ingest into Qdrant
    try:
        result = ingest_pdf(save_path, filename, document_id)
    except Exception as exc:
        save_path.unlink(missing_ok=True)
        if "refused" in str(exc).lower() or "connect" in str(exc).lower():
            raise HTTPException(
                status_code=503,
                detail=(
                    "The vector database (Qdrant) is not running on port 6333. "
                    "Start Qdrant and upload again."
                ),
            )
        raise HTTPException(status_code=500, detail=f"Could not process this PDF: {exc}")

    if result["chunks"] == 0:
        save_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=422,
            detail="No readable text found. The PDF may be a scanned image.",
        )

    # 7. Remember the document
    try:
        create_document(document_id, filename, file_hash, result["pages"], result["chunks"])
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"PDF was indexed but could not be saved to the database: {exc}",
        )

    return {
        "document_id": document_id,
        "filename": filename,
        "pages": result["pages"],
        "chunks": result["chunks"],
    }


@app.get("/documents")
def get_documents():
    return {"documents": list_documents()}


@app.delete("/documents/{document_id}")
def remove_document(document_id: str):
    """Delete a PDF: its chunks in Qdrant, its DB row and the file."""
    filename = delete_document(document_id)
    if filename is None:
        raise HTTPException(status_code=404, detail="Document not found")

    try:
        delete_document_chunks(document_id)
    except Exception as exc:
        logger.error("Could not delete chunks of %s: %s", document_id, exc)

    (UPLOAD_DIR / f"{document_id}.pdf").unlink(missing_ok=True)

    return {"message": "Document deleted", "document_id": document_id, "filename": filename}
