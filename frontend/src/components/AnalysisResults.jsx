import { useEffect, useId } from "react";
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

const formatPValue = (value) => {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return "—";
  }
  if (value < 0.001) {
    return "<0.001";
  }
  return value.toFixed(3);
};

const prettifyMetricName = (name) =>
  String(name || "")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());

const formatRangeValue = (value) => {
  if (Array.isArray(value) && value.length >= 2) {
    const [low, high] = value;
    return `${formatValue(low)} to ${formatValue(high)}`;
  }
  return formatValue(value);
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
  const titleId = useId();
  const hasResults = Boolean(results && Object.keys(results).length > 0);

  const summary = results?.summary ?? results?.stats ?? results?.tessitura ?? null;
  const duration = results?.metadata?.duration_seconds ?? results?.duration_seconds ?? summary?.duration_seconds;
  const f0Min = results?.pitch?.f0_min ?? summary?.f0_min ?? summary?.min_f0;
  const f0Max = results?.pitch?.f0_max ?? summary?.f0_max ?? summary?.max_f0;
  const tessitura = summary?.tessitura_range ?? summary?.range;
  const inferentialStatistics =
    results?.inferential_statistics && typeof results.inferential_statistics === "object"
      ? results.inferential_statistics
      : null;
  const inferentialMetrics =
    inferentialStatistics?.metrics && typeof inferentialStatistics.metrics === "object"
      ? Object.entries(inferentialStatistics.metrics)
      : [];
  const hasPitchFrames = Array.isArray(results?.pitch?.frames) && results.pitch.frames.length > 0;
  const hasNoteEvents =
    (Array.isArray(results?.note_events) && results.note_events.length > 0) ||
    (Array.isArray(results?.notes?.events) && results.notes.events.length > 0);
  const hasTessituraHistogram =
    (Array.isArray(results?.tessitura?.histogram) && results.tessitura.histogram.length > 0) ||
    (Array.isArray(results?.tessitura?.pdf?.density) && results.tessitura.pdf.density.length > 0);
  const hasInferentialMetrics = inferentialMetrics.length > 0;
  const isSparseCompletedResults =
    status?.status === "completed" &&
    hasResults &&
    !hasPitchFrames &&
    !hasNoteEvents &&
    !hasTessituraHistogram &&
    !hasInferentialMetrics;
  const readableStatus = (status?.status ?? "waiting").replace(/_/g, " ");

  return (
    <section className="card results" aria-labelledby={titleId} aria-busy={isFetchingResults}>
      <header className="card__header results__header">
        <div className="results__header-row">
          <h2 id={titleId} className="card__title">Analysis results</h2>
          <p className={`results__status results__status--${status?.status ?? "idle"}`}>{readableStatus}</p>
        </div>
        <p className="card__meta">Key outcomes are shown first, with detailed plots and statistics below.</p>
      </header>

      {error ? <p className="results__error" role="alert">{error}</p> : null}

      {!hasResults ? (
        <p className="results__empty">Results will appear here after the job completes.</p>
      ) : (
        <>
          {isSparseCompletedResults ? (
            <p className="results__empty" role="status">
              Analysis completed, but the file did not contain enough detectable pitch activity to populate detailed charts.
            </p>
          ) : null}

          <section className="results__section results__section--summary" aria-label="Summary metrics">
            <h3 className="results__section-title">Summary</h3>
            <p className="results__summary-intro">
              This overview highlights duration, pitch limits, and tessitura range.
            </p>
            <dl className="summary-list">
              <div className="summary-list__item">
                <dt>Recording length (seconds)</dt>
                <dd>{formatValue(duration)}</dd>
              </div>
              <div className="summary-list__item">
                <dt>Lowest detected pitch (F0, Hz)</dt>
                <dd>{formatValue(f0Min)}</dd>
              </div>
              <div className="summary-list__item">
                <dt>Highest detected pitch (F0, Hz)</dt>
                <dd>{formatValue(f0Max)}</dd>
              </div>
              <div className="summary-list__item">
                <dt>Comfortable singing range (tessitura)</dt>
                <dd>{formatRangeValue(tessitura)}</dd>
              </div>
            </dl>
          </section>

          <section className="results__section results__section--visuals" aria-label="Analysis visualizations">
            <div className="results__section-header">
              <h3 className="results__section-title">Visualizations</h3>
              <p className="results__section-meta">
                Inspect pitch contour, note activity, and tessitura density in dedicated charts.
              </p>
            </div>
            <div className="results__visuals">
              <PitchCurve results={results} />
              <PianoRoll results={results} />
              <TessituraHeatmap results={results} />
            </div>
          </section>

          {inferentialMetrics.length ? (
            <section className="results__section results__inferential" aria-label="Inferential statistics">
              <div className="results__section-header">
                <h3 className="results__section-title">How consistent each metric is (inferential statistics)</h3>
                <p className="results__inferential-meta">
                  Analysis preset: {inferentialStatistics?.preset ?? "unknown"} · Confidence interval level: {formatValue(inferentialStatistics?.confidence_level)}
                </p>
              </div>
              <p className="results__section-copy">
                In the table below, “Estimate” is the best single value, “Confidence interval” is a likely range,
                “p-value” helps indicate whether a difference is meaningful, and “Samples (N)” is how many data points were used.
              </p>
              <div className="results__inferential-table-wrap">
                <table className="results__inferential-table">
                  <thead>
                    <tr>
                      <th scope="col">Metric</th>
                      <th scope="col">Estimate</th>
                      <th scope="col">Confidence interval (95%)</th>
                      <th scope="col">p-value (significance)</th>
                      <th scope="col">Samples (N)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {inferentialMetrics.map(([metricName, metricPayload]) => {
                      const ci = metricPayload?.confidence_interval ?? null;
                      return (
                        <tr key={metricName}>
                          <th scope="row">{prettifyMetricName(metricName)}</th>
                          <td>{formatValue(metricPayload?.estimate)}</td>
                          <td>{`[${formatValue(ci?.low)}, ${formatValue(ci?.high)}]`}</td>
                          <td>{formatPValue(metricPayload?.p_value)}</td>
                          <td>{formatValue(metricPayload?.n_samples)}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </section>
          ) : null}

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
