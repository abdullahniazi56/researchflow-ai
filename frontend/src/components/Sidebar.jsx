import { ClockIcon, FileIcon, PenIcon, PlusIcon, TrashIcon } from "./Icons";

export default function Sidebar({
  open,
  busy,
  serverOnline,
  sessions,
  activeSessionId,
  documents,
  selectedDocIds,
  onNew,
  onOpenSession,
  onRenameSession,
  onDeleteSession,
  onToggleDocument,
  onDeleteDocument,
}) {
  return (
    <aside className={`sidebar ${open ? "sidebar-open" : ""}`}>
      <div className="brand">
        <span className="brand-orb" aria-hidden="true" />
        <span className="brand-name">ResearchFlow</span>
        <span className="brand-tag">AI</span>
      </div>

      <button className="new-research" onClick={onNew} disabled={busy}>
        <PlusIcon size={16} />
        New research
      </button>

      <section className="nav-section">
        <header className="nav-heading">
          <ClockIcon size={14} />
          <span>Recent research</span>
          <span className="nav-count">{sessions.length}</span>
        </header>

        <div className="history-list">
          {sessions.length === 0 ? (
            <p className="nav-empty">Your research sessions will appear here.</p>
          ) : (
            sessions.map((session) => {
              const title = session.title || "Untitled research";
              const isActive = session.session_id === activeSessionId;

              return (
                <div
                  className={`history-row ${isActive ? "is-active" : ""}`}
                  key={session.session_id}
                >
                  <button
                    className="history-item"
                    onClick={() => onOpenSession(session)}
                    disabled={busy}
                    title={title}
                  >
                    <span className="history-title">{title}</span>
                  </button>

                  <div className="row-actions">
                    <button
                      className="icon-button"
                      onClick={() => onRenameSession(session)}
                      disabled={busy}
                      aria-label={`Rename ${title}`}
                      title="Rename"
                    >
                      <PenIcon size={13} />
                    </button>
                    <button
                      className="icon-button danger"
                      onClick={() => onDeleteSession(session)}
                      disabled={busy}
                      aria-label={`Delete ${title}`}
                      title="Delete"
                    >
                      <TrashIcon size={13} />
                    </button>
                  </div>
                </div>
              );
            })
          )}
        </div>
      </section>

      <section className="nav-section">
        <header className="nav-heading">
          <FileIcon size={14} />
          <span>Documents</span>
          <span className="nav-count">{documents.length}</span>
        </header>

        {documents.length === 0 ? (
          <p className="nav-empty">
            Attach a PDF from the question box. It is searched with every question.
          </p>
        ) : (
          <>
            <p className="doc-scope-hint">
              {selectedDocIds.length
                ? `Searching ${selectedDocIds.length} selected`
                : "Searching all. Tick to narrow."}
            </p>
            <ul className="document-list">
              {documents.map((doc) => {
                const checked = selectedDocIds.includes(doc.document_id);
                return (
                  <li key={doc.document_id} className={checked ? "is-selected" : ""}>
                    <label title={doc.filename}>
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() => onToggleDocument(doc.document_id)}
                        disabled={busy}
                      />
                      <span className="doc-check" aria-hidden="true" />
                      <span className="document-name">{doc.filename}</span>
                    </label>
                    <span className="doc-pages">{doc.pages}p</span>
                    <button
                      className="icon-button danger"
                      onClick={() => onDeleteDocument(doc)}
                      disabled={busy}
                      aria-label={`Delete ${doc.filename}`}
                      title="Delete PDF"
                    >
                      <TrashIcon size={13} />
                    </button>
                  </li>
                );
              })}
            </ul>
          </>
        )}
      </section>

      <footer className={`sidebar-footer ${serverOnline === false ? "is-offline" : ""}`}>
        <span className="live-dot" aria-hidden="true" />
        <span>
          {serverOnline === false
            ? "Agent offline"
            : serverOnline
              ? "Agent online"
              : "Connecting…"}
        </span>
        <span className="footer-meta">PDF · Web · MCP</span>
      </footer>
    </aside>
  );
}
