/* Live research progress, fed by the streaming endpoint. */

export default function ProgressSteps({ steps, elapsed }) {
  if (!steps.length) return null;

  return (
    <ol className="progress-steps" aria-live="polite">
      {steps.map((step, index) => {
        const isLast = index === steps.length - 1;

        return (
          <li
            key={`${step.step}-${index}`}
            className={isLast ? "is-active" : "is-done"}
          >
            <span className="progress-marker" aria-hidden="true" />
            <span className="progress-text">
              {step.message}
              {step.items?.length > 0 && step.step !== "search" && (
                <span className="progress-items">
                  {step.items.join(" · ")}
                </span>
              )}
              {step.step === "search" && step.items?.[0] && (
                <span className="progress-items">{step.items[0]}</span>
              )}
            </span>
            {isLast && elapsed > 0 && (
              <span className="elapsed">{elapsed}s</span>
            )}
          </li>
        );
      })}
    </ol>
  );
}
