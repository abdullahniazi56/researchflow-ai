
import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv

load_dotenv()

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"

def get_connection():
    return psycopg.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=os.getenv("POSTGRES_PORT", "5432"),
        dbname=os.getenv("POSTGRES_DB", "researchflow"),
        user=os.getenv("POSTGRES_USER", "postgres"),
        password=os.getenv("POSTGRES_PASSWORD"),
    )


def create_research_session(session_id: str, title: str):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO research_sessions (session_id, title)
                VALUES (%s, %s)
                ON CONFLICT (session_id) DO NOTHING;
                """,
                (session_id, title),
            )


def create_message(session_id: str, role: str, content: str):
    with get_connection() as conn:
         with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO research_messages
                        (session_id, role, content)
                    VALUES (%s, %s, %s)
                    RETURNING id;

                    """,
                    (session_id, role, content),
                ) 
                return cur.fetchone()[0]


def get_session_message(session_id: str):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT role, content, created_at
                FROM research_messages
                WHERE session_id = %s
                ORDER BY created_at ASC;
                """,
                (session_id,)
            )
            return cur.fetchall()


def create_research_source(
    message_id: int,
    source_type: str,
    source_name: str,
    source_url: str | None = None,
    page_number: int | None = None,
):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO research_sources
                    (message_id, source_type, source_name,
                     source_url, page_number)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id;
                """,
                (
                    message_id,
                    source_type,
                    source_name,
                    source_url,
                    page_number,
                ),
            )
            return cur.fetchone()[0]



def get_messages_with_sources(session_id: str):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    m.id,
                    m.role,
                    m.content,
                    m.created_at,
                    s.source_name,
                    s.source_type,
                    s.source_url,
                    s.page_number
                FROM research_messages AS m
                LEFT JOIN research_sources AS s
                    ON m.id = s.message_id
                WHERE m.session_id = %s
                ORDER BY m.created_at ASC, s.id ASC;
                """,
                (session_id,)
            )

            records = cur.fetchall()

    messages = {}

    for record in records:
        (
            message_id,
            role,
            content,
            created_at,
            source_name,
            source_type,
            source_url,
            page_number,
        ) = record

        if message_id not in messages:
            messages[message_id] = {
                "id": message_id,
                "role": role,
                "content": content,
                "created_at": created_at,
                "sources": [],
            }

        if source_name is not None:
            messages[message_id]["sources"].append({
                "name": source_name,
                "type": source_type,
                "url": source_url,
                "page": page_number,
            })

    return list(messages.values())



def get_research_session():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    session_id,
                    title,
                    created_at
                FROM research_sessions
                ORDER BY created_at DESC;
                """
            )

            records = cur.fetchall()

            return [
                {
                    "session_id": record[0],
                    "title": record[1],
                    "created_at": record[2],
                }
                for record in records
            ]


def get_research_session_by_id(session_id: str):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT session_id, title, created_at
                FROM research_sessions
                WHERE session_id = %s;
                """,
                (session_id,)
            )

            record = cur.fetchone()

            if record is None:
                return None

            return {
                "session_id": record[0],
                "title": record[1],
                "created_at": record[2],
            }


def delete_research_session(session_id: str):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM research_sessions
                WHERE session_id = %s
                RETURNING session_id;
                """,
                (session_id,)
            )

            deleted = cur.fetchone()
            return deleted is not None


def update_research_session_title(
    session_id: str,
    new_title: str
):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE research_sessions
                SET title = %s
                WHERE session_id = %s
                RETURNING session_id;
                """,
                (new_title, session_id)
            )

            updated = cur.fetchone()
            return updated is not None

def research_session_exists(session_id: str):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 1
                FROM research_sessions
                WHERE session_id = %s;
                """,
                (session_id,)
            )
            return cur.fetchone() is not None


# --------------------------------------------------
# SCHEMA
# --------------------------------------------------

def init_db():
    """Create any missing tables (existing tables are left untouched)."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(SCHEMA_PATH.read_text(encoding="utf-8"))


# --------------------------------------------------
# UPLOADED DOCUMENTS
# --------------------------------------------------

def document_exists(file_hash: str) -> bool:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM documents WHERE file_hash = %s;",
                (file_hash,),
            )
            return cur.fetchone() is not None


def create_document(
    document_id: str,
    filename: str,
    file_hash: str,
    pages: int,
    chunks: int,
):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO documents
                    (document_id, filename, file_hash, pages, chunks)
                VALUES (%s, %s, %s, %s, %s);
                """,
                (document_id, filename, file_hash, pages, chunks),
            )


def list_documents():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT document_id, filename, pages, chunks, uploaded_at
                FROM documents
                ORDER BY uploaded_at DESC;
                """
            )

            return [
                {
                    "document_id": record[0],
                    "filename": record[1],
                    "pages": record[2],
                    "chunks": record[3],
                    "uploaded_at": record[4],
                }
                for record in cur.fetchall()
            ]


if __name__ == "__main__":
    records = get_messages_with_sources("session-python-001")

    for record in records:
     print(record)