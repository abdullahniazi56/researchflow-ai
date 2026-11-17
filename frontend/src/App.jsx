
import { useEffect, useRef, useState } from "react";
import {
  startResearch,
  getSessions,
  getSessionMessages,
  deleteSession,
  renameSession,
  uploadDocument,
  getDocuments,
} from "./api";
import "./App.css";
import "./theme.css";
import EvidenceBackground from "./EvidenceBackground";
import Markdown from "./Markdown";
import SourceList from "./SourceList";

function App() {
  const [question, setQuestion] = useState("");
  const [research, setResearch] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [sessions, setSessions] = useState([]);
  const [selectedSession, setSelectedSession] = useState(null);
  const [sessionMessages, setSessionMessages] = useState([]);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [documents, setDocuments] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [uploadMessage, setUploadMessage] = useState("");
  const [uploadError, setUploadError] = useState("");
  const [serverOnline, setServerOnline] = useState(null);
  const [elapsed, setElapsed] = useState(0);
  const fileInputRef = useRef(null);

  useEffect(() => {
    loadSessions();
    loadDocuments();
  }, []);

  // Count seconds while a research request is running.
  useEffect(() => {
    if (!loading) return undefined;

    const startedAt = Date.now();
    const timer = setInterval(() => {
      setElapsed(Math.round((Date.now() - startedAt) / 1000));
    }, 1000);

    return () => {
      clearInterval(timer);
      setElapsed(0);
    };
  }, [loading]);

  async function loadDocuments() {
    try {
      const data = await getDocuments();
      setDocuments(Array.isArray(data) ? data : []);
    } catch (err) {
      console.error("Failed to load documents:", err);
    }
  }

  async function handleFileChange(event) {
    const file = event.target.files?.[0];
    // Reset the input so the same file can be chosen again later.
    event.target.value = "";

    if (!file) return;

    setUploadMessage("");
    setUploadError("");

    // Quick checks for a fast message; the backend checks again.
    if (file.type !== "application/pdf") {
      setUploadError("Please choose a PDF file.");
      return;
    }

    if (file.size > 20 * 1024 * 1024) {
      setUploadError("File is too large (max 20 MB).");
      return;
    }

    setUploading(true);

    try {
      const data = await uploadDocument(file);
      setUploadMessage(
        `${data.filename}: ${data.chunks} chunks added`
      );
      await loadDocuments();
    } catch (err) {
      setUploadError(getErrorMessage(err, "Upload failed."));
    } finally {
      setUploading(false);
    }
  }

  async function loadSessions() {
    try {
      const data = await getSessions();
      setSessions(Array.isArray(data) ? data : []);
      setServerOnline(true);
    } catch (err) {
      if (!err?.response) setServerOnline(false);
      console.error("Failed to load research history:", err);
    }
  }

  function getSessionId(session) {
    return session?.session_id ?? session?.id;
  }

  function getErrorMessage(err, fallback) {
    // No response at all means the backend could not be reached.
    if (err && !err.response && err.code === "ERR_NETWORK") {
      setServerOnline(false);
      return (
        "Can't reach the ResearchFlow server at 127.0.0.1:8000. " +
        "Start the backend (uvicorn backend.main:app --reload) and try again."
      );
    }

    return (
      err?.response?.data?.detail ||
      err?.message ||
      fallback
    );
  }

  async function handleSubmit(event) {
    event.preventDefault();

    const trimmedQuestion = question.trim();
    if (!trimmedQuestion || loading) return;

    setLoading(true);
    setError("");
    setResearch(null);
    setSelectedSession(null);
    setSessionMessages([]);
    setSidebarOpen(false);

    try {
      const data = await startResearch(trimmedQuestion);
      setResearch(data);
      await loadSessions();
    } catch (err) {
      setError(
        getErrorMessage(
          err,
          "Could not connect to ResearchFlow AI."
        )
      );
    } finally {
      setLoading(false);
    }
  }

  async function handleOpenSession(session) {
    const sessionId = getSessionId(session);
    if (!sessionId || loading) return;

    setLoading(true);
    setError("");
    setResearch(null);
    setQuestion("");
    setSelectedSession(session);
    setSessionMessages([]);
    setSidebarOpen(false);

    try {
      const data = await getSessionMessages(sessionId);
      const messages = Array.isArray(data)
        ? data
        : data?.messages;

      setSessionMessages(
        Array.isArray(messages) ? messages : []
      );
    } catch (err) {
      setError(
        getErrorMessage(
          err,
          "Could not load this research session."
        )
      );
    } finally {
      setLoading(false);
    }
  }

  function handleNewResearch() {
    setQuestion("");
    setResearch(null);
    setError("");
    setSelectedSession(null);
    setSessionMessages([]);
    setSidebarOpen(false);
  }

  async function handleRenameSession(session) {
    const sessionId = getSessionId(session);
    if (!sessionId || loading) return;

    const newTitle = window.prompt(
      "Enter new research title:",
      session.title || "Untitled Research"
    );

    if (newTitle === null || !newTitle.trim()) return;

    setError("");

    try {
      await renameSession(sessionId, newTitle.trim());

      setSelectedSession((current) =>
        getSessionId(current) === sessionId
          ? { ...current, title: newTitle.trim() }
          : current
      );

      await loadSessions();
    } catch (err) {
      setError(
        getErrorMessage(err, "Could not rename research.")
      );
    }
  }

  async function handleDeleteSession(session) {
    const sessionId = getSessionId(session);
    if (!sessionId || loading) return;

    if (!window.confirm("Delete this research session?")) {
      return;
    }

    setError("");

    try {
      await deleteSession(sessionId);

      if (getSessionId(selectedSession) === sessionId) {
        setSelectedSession(null);
        setSessionMessages([]);
        setResearch(null);
      }

      await loadSessions();
    } catch (err) {
      setError(
        getErrorMessage(err, "Could not delete research.")
      );
    }
  }

  function renderSources(sources) {
    return <SourceList items={sources} />;
  }

  function renderEvidence(evidence) {
    return <SourceList items={evidence} />;
  }

  function renderMessage(message, index) {
    const isAssistant = message.role === "assistant";
    const content = message.content || message.message || "";

    return (
      <article
        className={`chat-message ${
          isAssistant ? "assistant-message" : "user-message"
        }`}
        key={message.id ?? `${message.role}-${index}`}
      >
        <div
          className={`message-avatar ${
            isAssistant ? "assistant-avatar" : ""
          }`}
        >
          {isAssistant ? "✳" : "You"}
        </div>

        <div className="message-body">
          <div className="message-heading">
            <strong>
              {isAssistant
                ? "ResearchFlow AI"
                : message.role === "user"
                  ? "You"
                  : message.role || "Message"}
            </strong>
          </div>

          {isAssistant ? (
            <div className="message-content answer-text">
              <Markdown text={content} />
            </div>
          ) : (
            <div className="message-content user-question">
              {content}
            </div>
          )}

          {isAssistant && renderSources(message.sources)}
        </div>
      </article>
    );
  }

  return (
    <div className="app-shell">
      <EvidenceBackground />

      {sidebarOpen && (
        <button
          className="mobile-backdrop"
          aria-label="Close navigation"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      <aside
        className={`sidebar ${
          sidebarOpen ? "sidebar-open" : ""
        }`}
      >
        <div className="brand">
          <div className="brand-mark">✳</div>
          <span>
            ResearchFlow <b>AI</b>
          </span>
        </div>

        <button
          className="new-research"
          onClick={handleNewResearch}
          disabled={loading}
        >
          <span>＋</span> New research
        </button>

        <div className="sidebar-section">
          <p className="section-label">Workspace</p>

          <button
            className={`sidebar-link ${
              !selectedSession ? "active" : ""
            }`}
            onClick={handleNewResearch}
            disabled={loading}
          >
            <span>⌂</span> Research chat
          </button>

          <div className="history-heading">
            <p className="section-label">Recent research</p>
            <span>{sessions.length}</span>
          </div>

          <div className="history-list">
            {sessions.length === 0 ? (
              <p className="history-empty">
                Your research sessions will appear here.
              </p>
            ) : (
              sessions.map((session) => {
                const sessionId = getSessionId(session);

                const isActive =
                  getSessionId(selectedSession) === sessionId;

                return (
                  <div
                    className="history-row"
                    key={sessionId}
                  >
                    <button
                      className={`history-item ${
                        isActive ? "active" : ""
                      }`}
                      onClick={() => handleOpenSession(session)}
                      disabled={loading}
                      title={
                        session.title || "Untitled research"
                      }
                    >
                      <span className="history-title">
                        {session.title || "Untitled research"}
                      </span>
                    </button>

                    <div className="history-actions">
                      <button
                        className="history-action"
                        onClick={() =>
                          handleRenameSession(session)
                        }
                        disabled={loading}
                        title="Rename research"
                        aria-label="Rename research"
                      >
                        ✎
                      </button>

                      <button
                        className="history-action delete-action"
                        onClick={() =>
                          handleDeleteSession(session)
                        }
                        disabled={loading}
                        title="Delete research"
                        aria-label="Delete research"
                      >
                        ×
                      </button>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>

        <div className="sidebar-section">
          <div className="history-heading">
            <p className="section-label">Documents</p>
            <span>{documents.length}</span>
          </div>

          {documents.length === 0 ? (
            <p className="history-empty">
              Attach a PDF next to the question box. It will be
              searched with every question.
            </p>
          ) : (
            <ul className="document-list">
              {documents.map((doc) => (
                <li key={doc.document_id} title={doc.filename}>
                  <span className="document-name">
                    {doc.filename}
                  </span>
                  <small>{doc.pages} pages</small>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="sidebar-footer">
          Answers cite your PDFs and the web
        </div>
      </aside>

      <main className="main-panel">
        <header className="topbar">
          <button
            className="mobile-menu"
            onClick={() => setSidebarOpen(true)}
            aria-label="Open navigation"
          >
            ☰
          </button>

          <div className="topbar-title">
            Research workspace
          </div>

          <div
            className={`status ${
              serverOnline === false ? "status-offline" : ""
            }`}
          >
            <span className="status-dot" />
            {serverOnline === false
              ? "Server offline"
              : serverOnline
                ? "Server connected"
                : "Connecting…"}
          </div>
        </header>

        <section className="workspace">
          {selectedSession ? (
            <div className="conversation-view">
              <div className="conversation-header">
                <p className="eyebrow">RESEARCH HISTORY</p>

                <h1>
                  {selectedSession.title || "Research session"}
                </h1>

                <p className="description">
                  Your saved conversation and its available citations.
                </p>
              </div>

              {loading && (
                <div className="loading-indicator">
                  <span className="loading-spinner" />
                  Loading conversation…
                </div>
              )}

              {!loading && sessionMessages.length === 0 && (
                <div className="empty-state">
                  <span className="empty-state-icon">◷</span>
                  <h3>No messages found</h3>
                  <p>
                    This session does not contain any saved messages.
                  </p>
                </div>
              )}

              <div className="chat-thread">
                {sessionMessages.map(renderMessage)}
              </div>

              <button
                className="secondary-button"
                onClick={handleNewResearch}
                disabled={loading}
              >
                ＋ Start new research
              </button>
            </div>
          ) : (
            <div className="research-view">
              {!research && (
                <div className="welcome-content">
                  <h1>
                    Ask a question.
                    <br />
                    Get an answer you can check.
                  </h1>

                  <p className="description">
                    ResearchFlow searches your PDFs and the web, then
                    writes an answer where every claim links back to
                    its source.
                  </p>
                </div>
              )}

              <div className="active-chat">
                {research && (
                  <div className="chat-thread">
                    {question && (
                      <article className="chat-message user-message">
                        <div className="message-avatar">You</div>

                        <div className="message-body">
                          <div className="message-heading">
                            <strong>You</strong>
                          </div>

                          <div className="message-content user-question">
                            {question}
                          </div>
                        </div>
                      </article>
                    )}

                    <article className="chat-message assistant-message">
                      <div className="message-avatar assistant-avatar">
                        ✳
                      </div>

                      <div className="message-body">
                        <div className="message-heading">
                          <strong>ResearchFlow AI</strong>

                          <span className="result-status">
                            {(research.status || "processing").replace(
                              /_/g,
                              " "
                            )}
                          </span>
                        </div>

                        {research.answer ? (
                          <div className="message-content answer-text">
                            <Markdown text={research.answer} />
                          </div>
                        ) : (
                          <div className="message-content">
                            {research.message ||
                              "Research has not returned a final answer yet."}
                          </div>
                        )}

                        {renderEvidence(research.selected_evidence)}
                      </div>
                    </article>
                  </div>
                )}

                {loading && (
                  <div className="loading-indicator">
                    <span className="loading-spinner" />
                    {research
                      ? "Updating research…"
                      : "Planning, searching your PDFs and the web, then writing the answer…"}
                    {elapsed > 0 && (
                      <span className="elapsed">{elapsed}s</span>
                    )}
                  </div>
                )}

                {research?.session_id && (
                  <p className="session-id">
                    Session ID: {research.session_id}
                  </p>
                )}
              </div>

              <form
                className="question-form"
                onSubmit={handleSubmit}
              >
                <textarea
                  value={question}
                  onChange={(event) =>
                    setQuestion(event.target.value)
                  }
                  placeholder="Ask anything you want to research…"
                  rows={3}
                  disabled={loading}
                  aria-label="Research question"
                />

                <div className="form-bottom">
                  <div className="form-tools">
                    <input
                      ref={fileInputRef}
                      type="file"
                      accept="application/pdf"
                      onChange={handleFileChange}
                      hidden
                    />

                    <button
                      type="button"
                      className="attach-button"
                      onClick={() => fileInputRef.current?.click()}
                      disabled={uploading}
                      title="Attach a PDF (max 20 MB)"
                    >
                      {uploading ? (
                        <>
                          <span className="button-spinner" />
                          Uploading
                        </>
                      ) : (
                        <>
                          <svg
                            width="15"
                            height="15"
                            viewBox="0 0 24 24"
                            fill="none"
                            stroke="currentColor"
                            strokeWidth="2"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            aria-hidden="true"
                          >
                            <path d="M21.4 11.1 12.2 20.3a6 6 0 0 1-8.5-8.5l9.2-9.2a4 4 0 0 1 5.7 5.7l-9.2 9.2a2 2 0 0 1-2.8-2.8l8.5-8.5" />
                          </svg>
                          Attach PDF
                        </>
                      )}
                    </button>

                    {uploadError ? (
                      <span className="upload-error" role="alert">
                        {uploadError}
                      </span>
                    ) : uploadMessage ? (
                      <span className="upload-status">
                        {uploadMessage}
                      </span>
                    ) : (
                      <span className="form-hint">
                        {loading
                          ? "Researching… this can take a minute."
                          : "Searches your PDFs and the web."}
                      </span>
                    )}
                  </div>

                  <button
                    className="primary-button"
                    type="submit"
                    disabled={!question.trim() || loading}
                  >
                    {loading ? (
                      <>
                        <span className="button-spinner" />
                        Processing
                      </>
                    ) : (
                      "Start research"
                    )}
                  </button>
                </div>
              </form>
            </div>
          )}

          {error && (
            <div className="error-panel" role="alert">
              <strong>Something went wrong</strong>
              <p>{error}</p>

              <button
                className="secondary-button"
                onClick={() => setError("")}
              >
                Dismiss
              </button>
            </div>
          )}
        </section>
      </main>
    </div>
  );
}

export default App;
