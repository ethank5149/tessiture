/**
 * StepIndicator - Visible step progress indicator
 * Shows current step in the workflow (1, 2, or 3)
 */

function StepIndicator({ currentStep = 1, steps = [] }) {
  const defaultSteps = [
    { label: "Choose source", description: "Select audio source" },
    { label: "Set up", description: "Configure analysis" },
    { label: "Results", description: "View results" },
  ];

  const stepsToShow = steps.length > 0 ? steps : defaultSteps;

  return (
    <div className="step-indicator" role="progressbar" aria-valuenow={currentStep} aria-valuemin={1} aria-valuemax={3}>
      {stepsToShow.map((step, index) => {
        const stepNum = index + 1;
        const isActive = stepNum === currentStep;
        const isCompleted = stepNum < currentStep;

        return (
          <div key={stepNum} className="step-indicator__step-group">
            <div
              className={`step-indicator__step ${isActive ? "step-indicator__step--active" : ""} ${
                isCompleted ? "step-indicator__step--completed" : ""
              }`}
            >
              <span className="step-indicator__step-number">
                {isCompleted ? "✓" : stepNum}
              </span>
              <span className="step-indicator__step-label">{step.label}</span>
            </div>

            {stepNum < stepsToShow.length && (
              <div className="step-indicator__connector" aria-hidden="true" />
            )}
          </div>
        );
      })}
    </div>
  );
}

export default StepIndicator;
