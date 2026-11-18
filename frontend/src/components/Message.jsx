import Markdown from "./Markdown";
import SourceList from "./SourceList";
import { ShieldIcon } from "./Icons";

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
      <ShieldIcon size={12} />
      {supported}/{cited} citations verified
    </span>
  );
}

export default function Message({ message }) {
  if (message.role !== "assistant") {
    return (
      <article className="msg msg-user">
        <div className="msg-bubble">{message.content}</div>
      </article>
    );
  }

  return (
    <article className={`msg msg-assistant ${message.failed ? "is-failed" : ""}`}>
      <header className="msg-header">
        <span className="msg-orb" aria-hidden="true" />
        <strong>ResearchFlow</strong>
        <VerificationBadge verification={message.verification} />
        {message.seconds != null && <span className="msg-time">{message.seconds}s</span>}
      </header>

      <div className="msg-answer">
        <Markdown text={message.content} />
      </div>

      <SourceList items={message.sources} />
    </article>
  );
}
