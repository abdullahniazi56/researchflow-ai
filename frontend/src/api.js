import axios from "axios";

// Configure in frontend/.env (see .env.example):
//   VITE_API_URL=http://127.0.0.1:8000
//   VITE_API_KEY=...   (only if the backend has API_KEY set)
export const API_URL = (
  import.meta.env.VITE_API_URL || "http://127.0.0.1:8000"
).replace(/\/$/, "");

const API_KEY = import.meta.env.VITE_API_KEY || "";

const authHeaders = API_KEY ? { "X-API-Key": API_KEY } : {};

const api = axios.create({
  baseURL: API_URL,
  headers: { "Content-Type": "application/json", ...authHeaders },
});

export class ApiError extends Error {
  constructor(message, { status = null, offline = false } = {}) {
    super(message);
    this.status = status;
    this.offline = offline;
  }
}

/** Turn any axios/fetch error into a short, useful message. */
export function toApiError(err, fallback = "Something went wrong.") {
  if (err instanceof ApiError) return err;

  const noResponse =
    (err?.isAxiosError && !err.response) ||
    (err instanceof TypeError && /fetch/i.test(err.message));

  if (noResponse) {
    return new ApiError(
      `Can't reach the ResearchFlow server at ${API_URL}. ` +
        "Start the backend (uvicorn backend.main:app --reload) and try again.",
      { offline: true }
    );
  }

  return new ApiError(
    err?.response?.data?.detail || err?.message || fallback,
    { status: err?.response?.status ?? null }
  );
}

// ---------- Research ----------

/**
 * Run research and receive live progress (Server-Sent Events).
 * onEvent is called for every event: session, step, result.
 */
export async function streamResearch(
  { question, sessionId, documentIds },
  onEvent,
  signal
) {
  let response;

  try {
    response = await fetch(`${API_URL}/research/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders },
      body: JSON.stringify({
        question,
        session_id: sessionId || null,
        document_ids: documentIds?.length ? documentIds : null,
      }),
      signal,
    });
  } catch (err) {
    if (err.name === "AbortError") throw err;
    throw toApiError(err);
  }

  if (!response.ok) {
    let detail = `Request failed (${response.status})`;
    try {
      detail = (await response.json()).detail || detail;
    } catch {
      // keep the generic message
    }
    throw new ApiError(detail, { status: response.status });
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });

    let boundary;
    while ((boundary = buffer.indexOf("\n\n")) >= 0) {
      const block = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);

      const line = block
        .split("\n")
        .find((l) => l.startsWith("data: "));

      if (line) onEvent(JSON.parse(line.slice(6)));
    }
  }
}

// ---------- Sessions ----------

export async function getSessions() {
  const response = await api.get("/sessions");
  return response.data.sessions;
}

export async function getSessionMessages(sessionId) {
  const response = await api.get(`/sessions/${sessionId}/messages`);
  return response.data.messages;
}

export async function deleteSession(sessionId) {
  const response = await api.delete(`/sessions/${sessionId}`);
  return response.data;
}

export async function renameSession(sessionId, title) {
  const response = await api.patch(`/sessions/${sessionId}`, { title });
  return response.data;
}

// ---------- Documents ----------

export async function uploadDocument(file) {
  const formData = new FormData();
  // "file" must match the FastAPI parameter name in upload_document()
  formData.append("file", file);

  // Override the default JSON header, otherwise axios would
  // convert the FormData into JSON and the file would not be sent.
  const response = await api.post("/documents/upload", formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });

  return response.data;
}

export async function getDocuments() {
  const response = await api.get("/documents");
  return response.data.documents;
}

export async function deleteDocument(documentId) {
  const response = await api.delete(`/documents/${documentId}`);
  return response.data;
}

export default api;
