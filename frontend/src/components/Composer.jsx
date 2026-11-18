import { useRef } from "react";
import { ArrowUpIcon, FileIcon, PaperclipIcon, StopIcon } from "./Icons";

/* The question box: glass panel with an animated edge while focused or busy. */

export default function Composer({
  value,
  onChange,
  onSubmit,
  onStop,
  loading,
  uploading,
  onAttach,
  status,
  scopeLabel,
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
      className={`composer ${loading ? "is-busy" : ""}`}
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
          isFollowUp ? "Ask a follow-up question…" : "Ask anything you want to research…"
        }
        rows={isFollowUp ? 1 : 2}
        disabled={loading}
        aria-label="Research question"
      />

      <div className="composer-bar">
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
          className="chip-button"
          onClick={() => fileInputRef.current?.click()}
          disabled={uploading}
          title="Attach a PDF (max 20 MB)"
        >
          {uploading ? <span className="button-spinner" /> : <PaperclipIcon size={15} />}
          {uploading ? "Indexing…" : "Attach PDF"}
        </button>

        <span className="scope-chip" title="Where the agent searches">
          <FileIcon size={13} />
          {scopeLabel}
        </span>

        <span
          className={`composer-status ${status.kind}`}
          role={status.kind === "error" ? "alert" : undefined}
        >
          {status.text}
        </span>

        {loading ? (
          <button type="button" className="send-button is-stop" onClick={onStop} aria-label="Stop research">
            <StopIcon size={16} />
          </button>
        ) : (
          <button
            className="send-button"
            type="submit"
            disabled={!value.trim()}
            aria-label={isFollowUp ? "Ask" : "Start research"}
          >
            <ArrowUpIcon size={18} />
          </button>
        )}
      </div>
    </form>
  );
}
