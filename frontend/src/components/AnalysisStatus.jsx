function AnalysisStatus({
  jobId = null,
  status = null,
  error = null,
  isPolling = false,
  isFetchingResults = false,
}) {
  const state = status?.status ?? (jobId ? "queued" : "idle");
  const detail = status?.detail ?? status?.message;

  return (
    <section className="card status" aria-live="polite">
      <header className="card__header">
        <h2 className="card__title">Analysis status</h2>
        <p className="card__meta">{jobId ? `Job ${jobId}` : "No active job"}</p>
      </header>
      <div className="status__body">
        <div className="status__row">
          <span className="status__label">State</span>
          <span className={`status__value status__value--${state}`}>{state}</span>
        </div>
        {detail ? (
          <p className="status__detail">{detail}</p>
        ) : (
          <p className="status__detail">We will update this panel as the analysis runs.</p>
        )}
        {(isPolling || isFetchingResults) ? (
          <p className="status__activity" aria-busy="true">
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
