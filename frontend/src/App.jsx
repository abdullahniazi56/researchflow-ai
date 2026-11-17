import { useCallback, useEffect, useRef, useState } from "react";
import {
  deleteDocument,
  deleteSession,
  getDocuments,
  getSessionMessages,
  getSessions,
  renameSession,
  streamResearch,
  toApiError,
  uploadDocument,
} from "./api";
import Composer from "./components/Composer";
import Message from "./components/Message";
import ProgressSteps from "./components/ProgressSteps";
import Sidebar from "./components/Sidebar";
import EvidenceBackground from "./EvidenceBackground";
import "./App.css";
import "./theme.css";

const DEFAULT_HINT = { kind: "hint", text: "Searches your PDFs and the web." };

function App() {
  // Sidebar data
  const [sessions, setSessions] = useState([]);
  const [documents, setDocuments] = useState([]);
  const [selectedDocIds, setSelectedDocIds] = useState([]);
  const [sidebarOpen, setSidebarOpen] = useState(false);

  // Current conversation
  const [activeSessionId, setActiveSessionId] = useState(null);
  const [activeTitle, setActiveTitle] = useState("");
  const [messages, setMessages] = useState([]);
  const [question, setQuestion] = useState("");

  // Request state
  const [loading, setLoading] = useState(false);
  const [steps, setSteps] = useState([]);
  const [elapsed, setElapsed] = useState(0);
  const [uploading, setUploading] = useState(false);
  const [composerStatus, setComposerStatus] = useState(DEFAULT_HINT);
  const [error, setError] = useState("");
  const [serverOnline, setServerOnline] = useState(null);

  const abortRef = useRef(null);
  const threadEndRef = useRef(null);

  const handleError = useCallback((err, fallback) => {
    const apiError = toApiError(err, fallback);
    if (apiError.offline) setServerOnline(false);
    setError(apiError.message);
    return apiError;
  }, []);

  const loadSessions = useCallback(async () => {
    try {
      const data = await getSessions();
      setSessions(Array.isArray(data) ? data : []);
      setServerOnline(true);
    } catch (err) {
      if (toApiError(err).offline) setServerOnline(false);
    }
  }, []);

  const loadDocuments = useCallback(async () => {
    try {
      const data = await getDocuments();
      const docs = Array.isArray(data) ? data : [];
      setDocuments(docs);
      // Forget selections of documents that no longer exist.
      setSelectedDocIds((ids) =>
        ids.filter((id) => docs.some((d) => d.document_id === id))
      );
    } catch {
      // the sessions call already reports offline
    }
  }, []);

  // First load: state is only set in promise callbacks, after the data arrives.
  useEffect(() => {
    let active = true;

    getSessions()
      .then((data) => {
        if (!active) return;
        setSessions(Array.isArray(data) ? data : []);
        setServerOnline(true);
      })
      .catch((err) => {
        if (active && toApiError(err).offline) setServerOnline(false);
      });

    getDocuments()
      .then((data) => {
        if (active) setDocuments(Array.isArray(data) ? data : []);
      })
      .catch(() => {});

    return () => {
      active = false;
    };
  }, []);

  // Seconds counter while research runs.
  useEffect(() => {
    if (!loading) return undefined;
    const startedAt = Date.now();
    const timer = setInterval(
      () => setElapsed(Math.round((Date.now() - startedAt) / 1000)),
      1000
    );
    return () => {
      clearInterval(timer);
      setElapsed(0);
    };
  }, [loading]);

  // Keep the newest message in view.
  useEffect(() => {
    threadEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, steps]);

  // ---------- Research ----------

  async function handleSubmit() {
    const text = question.trim();
    if (!text || loading) return;

    setError("");
    setQuestion("");
    setSteps([]);
    setLoading(true);
    setSidebarOpen(false);
    setMessages((current) => [
      ...current,
      { id: `local-${Date.now()}`, role: "user", content: text },
    ]);

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      await streamResearch(
        {
          question: text,
          sessionId: activeSessionId,
          documentIds: selectedDocIds,
        },
        (event) => {
          if (event.type === "session") {
            setActiveSessionId(event.session_id);
            setActiveTitle((title) => title || event.question.slice(0, 100));
          } else if (event.type === "step") {
            setSteps((current) => [...current, event]);
          } else if (event.type === "result") {
            const failed = event.status !== "completed";
            setMessages((current) => [
              ...current,
              {
                id: `local-${Date.now()}-a`,
                role: "assistant",
                content: failed ? event.message : event.answer,
                sources: failed ? [] : event.selected_evidence,
                verification: event.verification,
                seconds: event.seconds,
                failed,
              },
            ]);
          }
        },
        controller.signal
      );
      setServerOnline(true);
    } catch (err) {
      if (err.name === "AbortError") {
        setMessages((current) => [
          ...current,
          {
            id: `local-${Date.now()}-stop`,
            role: "assistant",
            content: "Research stopped.",
            failed: true,
          },
        ]);
      } else {
        handleError(err, "Research failed.");
      }
    } finally {
      abortRef.current = null;
      setLoading(false);
      setSteps([]);
      loadSessions();
    }
  }

  function handleStop() {
    abortRef.current?.abort();
  }

  // ---------- Sessions ----------

  function handleNewResearch() {
    if (loading) return;
    setActiveSessionId(null);
    setActiveTitle("");
    setMessages([]);
    setQuestion("");
    setError("");
    setSidebarOpen(false);
  }

  async function handleOpenSession(session) {
    if (loading) return;

    setError("");
    setSidebarOpen(false);
    setActiveSessionId(session.session_id);
    setActiveTitle(session.title || "Research session");
    setMessages([]);

    try {
      const data = await getSessionMessages(session.session_id);
      setMessages(Array.isArray(data) ? data : []);
    } catch (err) {
      handleError(err, "Could not load this research session.");
    }
  }

  async function handleRenameSession(session) {
    const title = window.prompt("New title:", session.title || "Untitled research");
    if (title === null || !title.trim()) return;

    try {
      await renameSession(session.session_id, title.trim());
      if (session.session_id === activeSessionId) setActiveTitle(title.trim());
      await loadSessions();
    } catch (err) {
      handleError(err, "Could not rename research.");
    }
  }

  async function handleDeleteSession(session) {
    if (!window.confirm(`Delete "${session.title || "this research"}"?`)) return;

    try {
      await deleteSession(session.session_id);
      if (session.session_id === activeSessionId) handleNewResearch();
      await loadSessions();
    } catch (err) {
      handleError(err, "Could not delete research.");
    }
  }

  // ---------- Documents ----------

  async function handleAttach(file) {
    if (file.type !== "application/pdf") {
      setComposerStatus({ kind: "error", text: "Please choose a PDF file." });
      return;
    }
    if (file.size > 20 * 1024 * 1024) {
      setComposerStatus({ kind: "error", text: "File is too large (max 20 MB)." });
      return;
    }

    setUploading(true);
    setComposerStatus({ kind: "hint", text: `Reading ${file.name}…` });

    try {
      const data = await uploadDocument(file);
      setComposerStatus({
        kind: "ok",
        text: `${data.filename}: ${data.chunks} chunks indexed`,
      });
      await loadDocuments();
    } catch (err) {
      const apiError = toApiError(err, "Upload failed.");
      if (apiError.offline) setServerOnline(false);
      setComposerStatus({ kind: "error", text: apiError.message });
    } finally {
      setUploading(false);
    }
  }

  function handleToggleDocument(documentId) {
    setSelectedDocIds((ids) =>
      ids.includes(documentId)
        ? ids.filter((id) => id !== documentId)
        : [...ids, documentId]
    );
  }

  async function handleDeleteDocument(doc) {
    if (!window.confirm(`Delete ${doc.filename}? It will no longer be searched.`)) {
      return;
    }
    try {
      await deleteDocument(doc.document_id);
      await loadDocuments();
    } catch (err) {
      handleError(err, "Could not delete the document.");
    }
  }

  // ---------- Render ----------

  const hasConversation = messages.length > 0 || loading;

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

      <Sidebar
        open={sidebarOpen}
        busy={loading}
        sessions={sessions}
        activeSessionId={activeSessionId}
        documents={documents}
        selectedDocIds={selectedDocIds}
        onNew={handleNewResearch}
        onOpenSession={handleOpenSession}
        onRenameSession={handleRenameSession}
        onDeleteSession={handleDeleteSession}
        onToggleDocument={handleToggleDocument}
        onDeleteDocument={handleDeleteDocument}
      />

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
            {activeTitle || "Research workspace"}
          </div>

          <div className={`status ${serverOnline === false ? "status-offline" : ""}`}>
            <span className="status-dot" />
            {serverOnline === false
              ? "Server offline"
              : serverOnline
                ? "Server connected"
                : "Connecting…"}
          </div>
        </header>

        <section className="workspace">
          {!hasConversation && (
            <div className="welcome-content">
              <h1>
                Ask a question.
                <br />
                Get an answer you can check.
              </h1>
              <p className="description">
                ResearchFlow searches your PDFs and the web, then writes an
                answer where every claim links back to its source.
              </p>
            </div>
          )}

          {hasConversation && (
            <div className="chat-thread">
              {messages.map((message, index) => (
                <Message key={message.id ?? index} message={message} />
              ))}

              {loading && (
                <div className="progress-panel">
                  <ProgressSteps
                    steps={steps.length ? steps : [{ step: "start", message: "Connecting" }]}
                    elapsed={elapsed}
                  />
                </div>
              )}
              <div ref={threadEndRef} />
            </div>
          )}

          {error && (
            <div className="error-panel" role="alert">
              <strong>Something went wrong</strong>
              <p>{error}</p>
              <button className="secondary-button" onClick={() => setError("")}>
                Dismiss
              </button>
            </div>
          )}

          <div className={hasConversation ? "composer-dock" : ""}>
            <Composer
              value={question}
              onChange={setQuestion}
              onSubmit={handleSubmit}
              onStop={handleStop}
              loading={loading}
              uploading={uploading}
              onAttach={handleAttach}
              status={
                selectedDocIds.length && composerStatus === DEFAULT_HINT
                  ? {
                      kind: "hint",
                      text: `Searching ${selectedDocIds.length} selected PDF${
                        selectedDocIds.length > 1 ? "s" : ""
                      } and the web.`,
                    }
                  : composerStatus
              }
              isFollowUp={Boolean(activeSessionId)}
            />
          </div>
        </section>
      </main>
    </div>
  );
}

export default App;
