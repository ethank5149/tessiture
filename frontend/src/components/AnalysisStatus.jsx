function AnalysisStatus({
  jobId = null,
  status = null,
  error = null,
  isPolling = false,
  isFetchingResults = false,
}) {
  const state = status?.status ?? (jobId ? "queued" : "idle");
  const detail = status?.detail ?? status?.message;
  const isBusy = Boolean(isPolling || isFetchingResults);

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
        {detail ? (
          <p className="status__detail">{detail}</p>
        ) : (
          <p className="status__detail">We will update this panel as the analysis runs.</p>
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
