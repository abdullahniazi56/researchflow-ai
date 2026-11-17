
import asyncio
import hashlib
import logging
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from backend.agent.service import (
    run_research,
    save_research_answer,
)
from backend.rag.ingestion import ingest_pdf
from backend.mcp.client import mcp_client

from backend.db import (
    get_research_session,
    get_messages_with_sources,
    delete_research_session,
    update_research_session_title,
    create_research_session,
    create_message,
    research_session_exists,
    get_research_session_by_id,
    init_db,
    document_exists,
    create_document,
    list_documents,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
UPLOAD_DIR = PROJECT_ROOT / "data" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20 MB


logger = logging.getLogger("researchflow")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create any missing database tables when the server starts.
    init_db()

    # Warm up the MCP tool server in the background: the API is usable
    # right away, and the models are usually loaded before the first
    # question arrives.
    async def warm_up_tools():
        try:
            await mcp_client.start()
            logger.warning("MCP tool server is ready.")
        except Exception as exc:
            logger.warning("MCP tool server could not start yet: %s", exc)

    warm_up = asyncio.create_task(warm_up_tools())

    yield

    warm_up.cancel()
    await mcp_client.close()


app = FastAPI(
    title="ResearchFlow AI API",
    description="API for managing research sessions",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class UpdateSessionTitle(BaseModel):
    title: str = Field(min_length=1, max_length=100)





class ResearchRequest(BaseModel):
    question: str = Field(
        min_length=1,
        max_length=2000,
        description="The research question to investigate",
    )


class ResearchResponse(BaseModel):
    message: str
    session_id: str
    question: str
    status: Literal["completed", "stopped", "failed"]
    answer: str | None = None
    selected_evidence: list[dict] = []


@app.get("/")
def home():
    return {"message": "ResearchFlow AI API is running"}


@app.get("/sessions")
def list_sessions():
    return {"sessions": get_research_session()}


@app.get("/sessions/{session_id}")
def get_session_details(session_id: str):
    session = get_research_session_by_id(session_id)

    if session is None:
        raise HTTPException(
            status_code=404,
            detail="Research session not found",
        )

    return session


@app.get("/sessions/{session_id}/messages")
def get_session_messages(session_id: str):
    if not research_session_exists(session_id):
        raise HTTPException(
            status_code=404,
            detail="Research session not found",
        )

    return {
        "session_id": session_id,
        "messages": get_messages_with_sources(session_id),
    }


@app.delete("/sessions/{session_id}")
def delete_session(session_id: str):
    if not delete_research_session(session_id):
        raise HTTPException(
            status_code=404,
            detail="Research session not found",
        )

    return {
        "message": "Research session deleted successfully",
        "session_id": session_id,
    }


@app.patch("/sessions/{session_id}")
def rename_session(
    session_id: str,
    body: UpdateSessionTitle,
):
    new_title = body.title.strip()

    if not new_title:
        raise HTTPException(
            status_code=422,
            detail="Title cannot be empty",
        )

    if not update_research_session_title(session_id, new_title):
        raise HTTPException(
            status_code=404,
            detail="Research session not found",
        )

    return {
        "message": "Research session title updated",
        "session_id": session_id,
        "title": new_title,
    }


@app.post("/research", response_model=ResearchResponse)
async def create_research_request(body: ResearchRequest):
    question = body.question.strip()

    if not question:
        raise HTTPException(
            status_code=422,
            detail="Research question cannot be empty",
        )

    session_id = f"research-{uuid.uuid4().hex[:12]}"

    create_research_session(session_id, question[:100])
    create_message(session_id, "user", question)

    result = await run_research(
        question=question,
        session_id=session_id,
    )

    if result["status"] == "completed":
        save_research_answer(session_id, result)

    if result["status"] == "completed":
        message = "Research completed."
    elif result["status"] == "failed":
        message = result["message"]
    else:
        message = "Research stopped before an answer was generated."

    return {
        "message": message,
        "session_id": session_id,
        "question": question,
        "status": result["status"],
        "answer": result.get("answer"),
        "selected_evidence": result.get("selected_evidence", []),
    }


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
        raise HTTPException(
            status_code=400,
            detail="Only PDF files are allowed.",
        )

    # 2. Size check (read one byte past the limit to detect big files)
    contents = file.file.read(MAX_UPLOAD_BYTES + 1)

    if len(contents) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail="File is too large (max 20 MB).",
        )

    # 3. Real PDF? Every PDF file starts with "%PDF-"
    if not contents.startswith(b"%PDF-"):
        raise HTTPException(
            status_code=400,
            detail="This file is not a valid PDF.",
        )

    # 4. Duplicate check (same content = same hash, whatever the name)
    file_hash = hashlib.sha256(contents).hexdigest()

    try:
        already_uploaded = document_exists(file_hash)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Database is not available: {exc}",
        )

    if already_uploaded:
        raise HTTPException(
            status_code=409,
            detail="This document has already been uploaded.",
        )

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

        raise HTTPException(
            status_code=500,
            detail=f"Could not process this PDF: {exc}",
        )

    if result["chunks"] == 0:
        save_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=422,
            detail=(
                "No readable text found. "
                "The PDF may be a scanned image."
            ),
        )

    # 7. Remember the document
    try:
        create_document(
            document_id,
            filename,
            file_hash,
            result["pages"],
            result["chunks"],
        )
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
