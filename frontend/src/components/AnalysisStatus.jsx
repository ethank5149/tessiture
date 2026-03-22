const STATE_MESSAGES = {
  idle: "Ready to analyze",
  queued: "Waiting in queue…",
  processing: "Analyzing your recording…",
  completed: "Analysis complete!",
  failed: "Analysis failed",
  error: "Something went wrong",
};

const STAGE_MESSAGES = {
  queued: "Waiting for an available slot…",
  preprocessing: "Preparing your audio…",
  pitch_estimation: "Detecting pitch…",
  tessitura_analysis: "Mapping your vocal range…",
  advanced_analysis: "Running advanced analysis…",
  comparison: "Comparing to reference…",
  reporting: "Generating your report…",
  completed: "Done!",
};

const STATE_ICONS = {
  idle: "⏳",
  queued: "⏳",
  processing: "⏳",
  completed: "✅",
  failed: "❌",
  error: "❌",
};

function AnalysisStatus({
  jobId = null,
  status = null,
  error = null,
  isPolling = false,
  isFetchingResults = false,
}) {
  const hasActiveJob = Boolean(jobId);
  const state = status?.status ?? (hasActiveJob ? "queued" : "idle");
  const stage = status?.stage ?? state;
  const detail = status?.message ?? status?.detail;
  const numericProgress = Number(status?.progress);
  const progress = hasActiveJob
    ? Number.isFinite(numericProgress)
      ? Math.max(0, Math.min(100, Math.round(numericProgress)))
      : state === "completed" || state === "failed" || state === "error"
        ? 100
        : 0
    : null;
  const isBusy = Boolean(isPolling || isFetchingResults);

  const stateMessage = STATE_MESSAGES[state] || state;
  const stageMessage = STAGE_MESSAGES[stage] || stage.replace(/_/g, " ");
  const stateIcon = STATE_ICONS[state] || "•";

  return (
    <section className="card status" aria-labelledby="analysis-status-title">
      <header className="card__header">
        <h2 id="analysis-status-title" className="card__title">Analysis status</h2>
      </header>
      <div className="status__body">
        <div className="status__message">
          <span className="status__message-icon" aria-hidden="true">{stateIcon}</span>
          <p className={`status__message-text status__message-text--${state}`}>{stateMessage}</p>
        </div>

        {hasActiveJob && stageMessage && (
          <p className="status__stage">{stageMessage}</p>
        )}

        {hasActiveJob ? (
          <div className="status__progress-group">
            <label className="status__label" htmlFor="analysis-progress">Progress</label>
            <div className="status__progress-meta">
              <progress
                id="analysis-progress"
                className="status__progress"
                max={100}
                value={progress ?? 0}
              >
                {progress ?? 0}%
              </progress>
              <span className="status__progress-value">{progress ?? 0}%</span>
            </div>
          </div>
        ) : null}

        {hasActiveJob && detail && (
          <p className="status__detail">{detail}</p>
        )}

        {isBusy ? (
          <p className="status__activity" role="status" aria-live="polite" aria-atomic="true">
            {isFetchingResults ? "Fetching results…" : "Polling for updates…"}
          </p>
        ) : null}

        {error ? (
          <p className="status__error" role="alert">{error}</p>
        ) : null}

        {hasActiveJob && jobId && (
          <details className="status__technical">
            <summary className="status__technical-summary">Technical details (for support)</summary>
            <p className="status__technical-content">Job ID: <code>{jobId}</code></p>
          </details>
        )}
      </div>
    </section>
  );
}

export default AnalysisStatus;
