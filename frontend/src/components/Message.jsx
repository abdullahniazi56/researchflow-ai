import Markdown from "../Markdown";
import SourceList from "../SourceList";

function VerificationBadge({ verification }) {
  if (!verification || !verification.cited_claims) return null;

  const { cited_claims: cited, supported_claims: supported } = verification;
  const allGood = supported === cited;

  return (
    <span
      className={`verify-badge ${allGood ? "verify-ok" : "verify-warn"}`}
      title={
        allGood
          ? "Every cited claim matches its source."
          : `Check these claims:\n${(verification.weak_claims || []).join("\n")}`
      }
    >
      {supported}/{cited} citations verified
    </span>
  );
}

export default function Message({ message }) {
  const isAssistant = message.role === "assistant";

  return (
    <article
      className={`chat-message ${isAssistant ? "assistant-message" : "user-message"}`}
    >
      <div className={`message-avatar ${isAssistant ? "assistant-avatar" : ""}`}>
        {isAssistant ? "✳" : "You"}
      </div>

      <div className="message-body">
        <div className="message-heading">
          <strong>{isAssistant ? "ResearchFlow AI" : "You"}</strong>
          {isAssistant && <VerificationBadge verification={message.verification} />}
          {isAssistant && message.seconds != null && (
            <span className="message-time">{message.seconds}s</span>
          )}
        </div>

        {isAssistant ? (
          <div
            className={`message-content answer-text ${
              message.failed ? "answer-failed" : ""
            }`}
          >
            <Markdown text={message.content} />
          </div>
        ) : (
          <div className="message-content user-question">{message.content}</div>
        )}

        {isAssistant && <SourceList items={message.sources} />}
      </div>
    </article>
  );
}
