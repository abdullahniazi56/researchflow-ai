import { useRef } from "react";

/* Question box with PDF attach, send and stop. */

export default function Composer({
  value,
  onChange,
  onSubmit,
  onStop,
  loading,
  uploading,
  onAttach,
  status,
  isFollowUp,
}) {
  const fileInputRef = useRef(null);

  function handleKeyDown(event) {
    // Enter sends, Shift+Enter adds a new line.
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      if (value.trim() && !loading) onSubmit();
    }
  }

  return (
    <form
      className="question-form"
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit();
      }}
    >
      <textarea
        value={value}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={
          isFollowUp
            ? "Ask a follow-up question…"
            : "Ask anything you want to research…"
        }
        rows={isFollowUp ? 2 : 3}
        disabled={loading}
        aria-label="Research question"
      />

      <div className="form-bottom">
        <div className="form-tools">
          <input
            ref={fileInputRef}
            type="file"
            accept="application/pdf"
            onChange={(event) => {
              const file = event.target.files?.[0];
              event.target.value = ""; // allow choosing the same file again
              if (file) onAttach(file);
            }}
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

          <span
            className={
              status.kind === "error"
                ? "upload-error"
                : status.kind === "ok"
                  ? "upload-status"
                  : "form-hint"
            }
            role={status.kind === "error" ? "alert" : undefined}
          >
            {status.text}
          </span>
        </div>

        {loading ? (
          <button type="button" className="secondary-button" onClick={onStop}>
            Stop
          </button>
        ) : (
          <button
            className="primary-button"
            type="submit"
            disabled={!value.trim()}
          >
            {isFollowUp ? "Ask" : "Start research"}
          </button>
        )}
      </div>
    </form>
  );
}
