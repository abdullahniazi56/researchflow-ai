
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
  const fileInputRef = useRef(null);

  useEffect(() => {
    loadSessions();
    loadDocuments();
  }, []);

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
    } catch (err) {
      console.error("Failed to load research history:", err);
    }
  }

  function getSessionId(session) {
    return session?.session_id ?? session?.id;
  }

  function getErrorMessage(err, fallback) {
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
    if (!Array.isArray(sources) || sources.length === 0) {
      return null;
    }

    return (
      <section className="sources-section">
        <h3>Sources &amp; citations</h3>

        <div className="sources-grid">
          {sources.map((source, index) => {
            const url = source.source_url || source.url;

            const name =
              source.source_name ||
              source.name ||
              source.source ||
              source.title ||
              `Source ${index + 1}`;

            const page =
              source.page_number ?? source.page;

            return (
              <article
                className="source-card"
                key={`${url || name}-${index}`}
              >
                <span className="source-number">
                  SOURCE {index + 1}
                </span>

                <h4>{name}</h4>

                {page != null && (
                  <p className="source-meta">
                    Page: {page}
                  </p>
                )}

                {url ? (
                  <a
                    href={url}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    Open source ↗
                  </a>
                ) : (
                  <p className="source-meta">
                    No source URL available
                  </p>
                )}

                {source.snippet && (
                  <p className="source-snippet">
                    {source.snippet}
                  </p>
                )}
              </article>
            );
          })}
        </div>
      </section>
    );
  }

  function renderEvidence(evidence) {
    if (!Array.isArray(evidence) || evidence.length === 0) {
      return null;
    }

    return (
      <section className="sources-section">
        <h3>Research evidence</h3>

        <div className="sources-grid">
          {evidence.map((item, index) => {
            const url = item.url || item.source_url;

            const name =
              item.source ||
              item.source_name ||
              item.title ||
              `Evidence ${index + 1}`;

            const page = item.page ?? item.page_number;

            return (
              <article
                className="source-card"
                key={`${url || name}-${index}`}
              >
                <span className="source-number">
                  EVIDENCE {index + 1}
                </span>

                <h4>{name}</h4>

                {item.type && (
                  <p className="source-meta">
                    Type: {item.type}
                  </p>
                )}

                {page != null && (
                  <p className="source-meta">
                    Page: {page}
                  </p>
                )}

                {url && (
                  <a
                    href={url}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    Open source ↗
                  </a>
                )}

                {(item.content || item.snippet) && (
                  <p className="source-snippet">
                    {item.content || item.snippet}
                  </p>
                )}
              </article>
            );
          })}
        </div>
      </section>
    );
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

          <div className="message-content">
            {content}
          </div>

          {isAssistant && renderSources(message.sources)}
        </div>
      </article>
    );
  }

  return (
    <div className="app-shell">
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
          <p className="section-label">WORKSPACE</p>

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
            <p className="section-label">RECENT RESEARCH</p>
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
            <p className="section-label">DOCUMENTS</p>
            <span>{documents.length}</span>
          </div>

          <input
            ref={fileInputRef}
            type="file"
            accept="application/pdf"
            onChange={handleFileChange}
            hidden
          />

          <button
            type="button"
            className="secondary-button upload-button"
            onClick={() => fileInputRef.current?.click()}
            disabled={uploading}
          >
            {uploading ? "Uploading…" : "📎 Upload PDF"}
          </button>

          {uploadMessage && (
            <p className="upload-status">{uploadMessage}</p>
          )}

          {uploadError && (
            <p className="upload-error">{uploadError}</p>
          )}

          {documents.length === 0 ? (
            <p className="history-empty">
              Uploaded PDFs will appear here.
            </p>
          ) : (
            <ul className="document-list">
              {documents.map((doc) => (
                <li key={doc.document_id} title={doc.filename}>
                  <span className="document-name">
                    📄 {doc.filename}
                  </span>
                  <small>{doc.pages} pages</small>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="sidebar-footer">
          <span className="footer-status-dot" />
          AI-powered research workspace
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

          <div className="status">
            <span className="status-dot" />
            Research assistant
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
                  <div className="welcome-icon">✳</div>

                  <p className="eyebrow">
                    YOUR AI RESEARCH ASSISTANT
                  </p>

                  <h1>
                    Research smarter.
                    <br />
                    <span>Discover more.</span>
                  </h1>

                  <p className="description">
                    Ask a question and let ResearchFlow AI investigate,
                    gather evidence, and generate a source-backed answer.
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
                            {research.answer}
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
                      : "Researching your question…"}
                  </div>
                )}

                {research?.session_id && (
                  <p className="session-id">
                    Session ID: {research.session_id}
                  </p>
                )}
              </div>

              {!research && !loading && (
                <div className="suggestions">
                  <p className="section-label">NEED AN IDEA?</p>

                  <button
                    onClick={() =>
                      setQuestion(
                        "Explain the latest advances in RAG systems."
                      )
                    }
                  >
                    <span>✳</span>
                    Latest advances in RAG
                    <b>↗</b>
                  </button>

                  <button
                    onClick={() =>
                      setQuestion(
                        "Compare popular vector databases for AI applications."
                      )
                    }
                  >
                    <span>◈</span>
                    Compare vector databases
                    <b>↗</b>
                  </button>

                  <button
                    onClick={() =>
                      setQuestion(
                        "Research practical applications of AI agents."
                      )
                    }
                  >
                    <span>⌘</span>
                    Applications of AI agents
                    <b>↗</b>
                  </button>
                </div>
              )}

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
                  <span>
                    {loading
                      ? "Please wait…"
                      : "Clear questions lead to better research."}
                  </span>

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
                      <>
                        Start research <span>→</span>
                      </>
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
