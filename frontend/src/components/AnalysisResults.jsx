import PitchCurve from "./PitchCurve";
import PianoRoll from "./PianoRoll";
import TessituraHeatmap from "./TessituraHeatmap";
import ReportExporter from "./ReportExporter";

const formatValue = (value) => {
  if (typeof value === "number") {
    return Number.isFinite(value) ? value.toFixed(2) : "—";
  }
  if (value === null || value === undefined || value === "") {
    return "—";
  }
  return String(value);
};

function AnalysisResults({
  results = null,
  status = null,
  error = null,
  isFetchingResults = false,
  onDownloadCsv,
  onDownloadJson,
  onDownloadPdf,
}) {
  const hasResults = Boolean(results && Object.keys(results).length > 0);

  const summary = results?.summary ?? results?.stats ?? results?.tessitura ?? null;
  const duration = results?.metadata?.duration_seconds ?? results?.duration_seconds ?? summary?.duration_seconds;
  const f0Min = results?.pitch?.f0_min ?? summary?.f0_min ?? summary?.min_f0;
  const f0Max = results?.pitch?.f0_max ?? summary?.f0_max ?? summary?.max_f0;
  const tessitura = summary?.tessitura_range ?? summary?.range;
  const confidence = summary?.confidence ?? summary?.overall_confidence;

  return (
    <section className="card results" aria-live="polite">
      <header className="card__header">
        <h2 className="card__title">Analysis results</h2>
        <p className="card__meta">
          {status?.status ? `Status: ${status.status}` : "Waiting for completed analysis."}
        </p>
      </header>

      {error ? <p className="results__error" role="alert">{error}</p> : null}

      {!hasResults ? (
        <p className="results__empty">Results will appear here after the job completes.</p>
      ) : (
        <>
          <div className="results__summary" aria-label="Summary metrics">
            <dl className="summary-list">
              <div className="summary-list__item">
                <dt>Duration (s)</dt>
                <dd>{formatValue(duration)}</dd>
              </div>
              <div className="summary-list__item">
                <dt>F0 min (Hz)</dt>
                <dd>{formatValue(f0Min)}</dd>
              </div>
              <div className="summary-list__item">
                <dt>F0 max (Hz)</dt>
                <dd>{formatValue(f0Max)}</dd>
              </div>
              <div className="summary-list__item">
                <dt>Tessitura range</dt>
                <dd>{formatValue(tessitura)}</dd>
              </div>
              <div className="summary-list__item">
                <dt>Confidence</dt>
                <dd>{formatValue(confidence)}</dd>
              </div>
            </dl>
          </div>

          <div className="results__visuals">
            <PitchCurve results={results} />
            <PianoRoll results={results} />
            <TessituraHeatmap results={results} />
          </div>

          <ReportExporter
            disabled={isFetchingResults}
            onDownloadCsv={onDownloadCsv}
            onDownloadJson={onDownloadJson}
            onDownloadPdf={onDownloadPdf}
          />
        </>
      )}
    </section>
  );
}

export default AnalysisResults;
