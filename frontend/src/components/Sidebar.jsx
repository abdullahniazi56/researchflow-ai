/* Navigation: new research, past sessions and uploaded PDFs. */

export default function Sidebar({
  open,
  busy,
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
        <div className="brand-mark">✳</div>
        <span>
          ResearchFlow <b>AI</b>
        </span>
      </div>

      <button className="new-research" onClick={onNew} disabled={busy}>
        <span>＋</span> New research
      </button>

      <div className="sidebar-section">
        <div className="history-heading">
          <p className="section-label">Recent research</p>
          <span>{sessions.length}</span>
        </div>

        <div className="history-list">
          {sessions.length === 0 ? (
            <p className="history-empty">Your research sessions will appear here.</p>
          ) : (
            sessions.map((session) => {
              const title = session.title || "Untitled research";
              const isActive = session.session_id === activeSessionId;

              return (
                <div className="history-row" key={session.session_id}>
                  <button
                    className={`history-item ${isActive ? "active" : ""}`}
                    onClick={() => onOpenSession(session)}
                    disabled={busy}
                    title={title}
                  >
                    <span className="history-title">{title}</span>
                  </button>

                  <div className="history-actions">
                    <button
                      className="history-action"
                      onClick={() => onRenameSession(session)}
                      disabled={busy}
                      title="Rename"
                      aria-label={`Rename ${title}`}
                    >
                      ✎
                    </button>
                    <button
                      className="history-action delete-action"
                      onClick={() => onDeleteSession(session)}
                      disabled={busy}
                      title="Delete"
                      aria-label={`Delete ${title}`}
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
            Attach a PDF from the question box. It is searched with every question.
          </p>
        ) : (
          <>
            <p className="doc-scope-hint">
              {selectedDocIds.length
                ? `Searching ${selectedDocIds.length} selected PDF${
                    selectedDocIds.length > 1 ? "s" : ""
                  }`
                : "Searching all PDFs. Tick some to narrow the search."}
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
                      <span className="document-name">{doc.filename}</span>
                    </label>
                    <small>{doc.pages} p.</small>
                    <button
                      className="history-action delete-action"
                      onClick={() => onDeleteDocument(doc)}
                      disabled={busy}
                      title="Delete PDF"
                      aria-label={`Delete ${doc.filename}`}
                    >
                      ×
                    </button>
                  </li>
                );
              })}
            </ul>
          </>
        )}
      </div>

      <div className="sidebar-footer">Answers cite your PDFs and the web</div>
    </aside>
  );
}
