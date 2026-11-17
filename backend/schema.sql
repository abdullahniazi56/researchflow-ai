-- ResearchFlow AI database schema.
-- Safe to run many times: every table uses IF NOT EXISTS,
-- so existing tables and data are never changed.

CREATE TABLE IF NOT EXISTS research_sessions (
    session_id  TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS research_messages (
    id          SERIAL PRIMARY KEY,
    session_id  TEXT NOT NULL
                REFERENCES research_sessions (session_id) ON DELETE CASCADE,
    role        TEXT NOT NULL,
    content     TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS research_sources (
    id           SERIAL PRIMARY KEY,
    message_id   INTEGER NOT NULL
                 REFERENCES research_messages (id) ON DELETE CASCADE,
    source_type  TEXT NOT NULL,
    source_name  TEXT NOT NULL,
    source_url   TEXT,
    page_number  INTEGER
);

-- One row per uploaded PDF. file_hash stops the same file
-- from being ingested twice (which would duplicate chunks in Qdrant).
CREATE TABLE IF NOT EXISTS documents (
    document_id  TEXT PRIMARY KEY,
    filename     TEXT NOT NULL,
    file_hash    TEXT NOT NULL UNIQUE,
    pages        INTEGER NOT NULL,
    chunks       INTEGER NOT NULL,
    uploaded_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Indexes for the queries the API runs most often.
CREATE INDEX IF NOT EXISTS idx_sessions_created_at
    ON research_sessions (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_messages_session_created
    ON research_messages (session_id, created_at);

CREATE INDEX IF NOT EXISTS idx_sources_message
    ON research_sources (message_id);

CREATE INDEX IF NOT EXISTS idx_documents_uploaded_at
    ON documents (uploaded_at DESC);
