import { CheckIcon, PenIcon, SearchIcon, ShieldIcon, SparkIcon } from "./Icons";

const STEP_ICONS = {
  start: SparkIcon,
  plan: SparkIcon,
  search: SearchIcon,
  write: PenIcon,
  verify: ShieldIcon,
};

export default function ProgressSteps({ steps, elapsed }) {
  if (!steps.length) return null;

  return (
    <ol className="agent-timeline" aria-live="polite">
      {steps.map((step, index) => {
        const isActive = index === steps.length - 1;
        const Icon = isActive ? STEP_ICONS[step.step] || SparkIcon : CheckIcon;
        const detail = step.items?.length
          ? step.step === "search"
            ? step.items[0]
            : step.items.join(" · ")
          : "";

        return (
          <li key={`${step.step}-${index}`} className={isActive ? "is-active" : "is-done"}>
            <span className="timeline-node">
              <Icon size={13} />
            </span>
            <div className="timeline-body">
              <span className="timeline-title">{step.message}</span>
              {detail && <span className="timeline-detail">{detail}</span>}
            </div>
            {isActive && elapsed > 0 && <span className="timeline-time">{elapsed}s</span>}
          </li>
        );
      })}
    </ol>
  );
}
