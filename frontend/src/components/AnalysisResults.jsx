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

const normalizeConfidence = (value) => {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return null;
  }
  if (value >= 0 && value <= 1) {
    return value;
  }
  if (value > 1 && value <= 100) {
    return value / 100;
  }
  return null;
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
  const confidence = summary?.confidence ?? summary?.overall_confidence;
  const normalizedConfidence = normalizeConfidence(confidence);
  const inferentialStatistics =
    results?.inferential_statistics && typeof results.inferential_statistics === "object"
      ? results.inferential_statistics
      : null;
  const inferentialMetrics =
    inferentialStatistics?.metrics && typeof inferentialStatistics.metrics === "object"
      ? Object.entries(inferentialStatistics.metrics)
      : [];

  useEffect(() => {
    if (!hasResults || !results) {
      return;
    }

    const pitchFrames = Array.isArray(results?.pitch?.frames) ? results.pitch.frames : [];
    const firstFrame = pitchFrames[0] ?? null;
    const notesNode = results?.notes;
    const noteEvents = Array.isArray(results?.note_events) ? results.note_events : [];
    const tessituraPdfDensity = Array.isArray(results?.tessitura?.pdf?.density)
      ? results.tessitura.pdf.density
      : [];

    console.info("[diagnostic] analysis payload shape", {
      jobStatus: status?.status ?? null,
      pitchFramesLength: pitchFrames.length,
      firstPitchFrameKeys: firstFrame ? Object.keys(firstFrame) : [],
      firstPitchFrameHasF0Hz: Boolean(firstFrame && Object.prototype.hasOwnProperty.call(firstFrame, "f0_hz")),
      firstPitchFrameHasF0: Boolean(firstFrame && Object.prototype.hasOwnProperty.call(firstFrame, "f0")),
      notesType: notesNode === null ? "null" : Array.isArray(notesNode) ? "array" : typeof notesNode,
      notesEventsLength: Array.isArray(results?.notes?.events) ? results.notes.events.length : 0,
      noteEventsLength: noteEvents.length,
      tessituraKeys: results?.tessitura && typeof results.tessitura === "object" ? Object.keys(results.tessitura) : [],
      tessituraPdfDensityLength: tessituraPdfDensity.length,
      tessituraHistogramLength: Array.isArray(results?.tessitura?.histogram) ? results.tessitura.histogram.length : 0,
      inferentialPreset: inferentialStatistics?.preset ?? null,
      inferentialMetricCount: inferentialMetrics.length,
    });
  }, [hasResults, results, status?.status, inferentialStatistics?.preset, inferentialMetrics.length]);

  return (
    <section className="card results" aria-labelledby={titleId} aria-busy={isFetchingResults}>
      <header className="card__header">
        <h2 id={titleId} className="card__title">Analysis results</h2>
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
            <p>
              This summary highlights how long the recording is, the lowest and highest detected pitches,
              your typical singing range (tessitura), and how confident the system is in these results.
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
                <dd>{formatValue(tessitura)}</dd>
              </div>
              <div className="summary-list__item">
                <dt>Overall confidence score</dt>
                <dd className="summary-list__confidence">
                  <span>{formatValue(confidence)}</span>
                  {normalizedConfidence !== null ? (
                    <meter
                      className="summary-list__meter"
                      min={0}
                      max={1}
                      low={0.5}
                      high={0.8}
                      optimum={1}
                      value={normalizedConfidence}
                    >
                      {(normalizedConfidence * 100).toFixed(0)}%
                    </meter>
                  ) : null}
                </dd>
              </div>
            </dl>
          </div>

          {inferentialMetrics.length ? (
            <section className="results__inferential" aria-label="Inferential statistics">
              <h3 className="results__inferential-title">How consistent each metric is (inferential statistics)</h3>
              <p className="results__inferential-meta">
                Analysis preset: {inferentialStatistics?.preset ?? "unknown"} · Confidence interval level: {formatValue(inferentialStatistics?.confidence_level)}
              </p>
              <p>
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
