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
  const readableStage = (hasActiveJob ? stage : "not_started").replace(/_/g, " ");

  return (
    <section className="card status" aria-labelledby="analysis-status-title">
      <header className="card__header">
        <h2 id="analysis-status-title" className="card__title">Analysis status</h2>
        <p className="card__meta">{jobId ? `Job ${jobId}` : "No active job"}</p>
      </header>
      <div className="status__body">
        <dl className="status__row">
          <dt className="status__label">State</dt>
          <dd className={`status__value status__value--${state}`}>{state}</dd>
        </dl>
        <dl className="status__row">
          <dt className="status__label">Stage</dt>
          <dd className="status__stage">{readableStage}</dd>
        </dl>
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
        {hasActiveJob ? (
          detail ? (
            <p className="status__detail">{detail}</p>
          ) : (
            <p className="status__detail">We will update this panel as the analysis runs.</p>
          )
        ) : (
          <p className="status__detail">Progress will appear after you submit a job.</p>
        )}
        {isBusy ? (
          <p className="status__activity" role="status" aria-live="polite" aria-atomic="true">
            {isFetchingResults ? "Fetching results…" : "Polling for updates…"}
          </p>
        ) : null}
        {error ? (
          <p className="status__error" role="alert">{error}</p>
        ) : null}
      </div>
    </section>
  );
}

export default AnalysisStatus;
