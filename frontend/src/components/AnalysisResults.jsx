import { useEffect, useId, useState } from "react";
import PitchCurve from "./PitchCurve";
import PianoRoll from "./PianoRoll";
import TessituraHeatmap from "./TessituraHeatmap";
import ReportExporter from "./ReportExporter";

const RESULTS_VIEWS = {
  analysis: "analysis",
  calibration: "calibration",
};

const isPlainObject = (value) =>
  Boolean(value) && typeof value === "object" && !Array.isArray(value);

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

const formatCountValue = (value) => {
  if (value === null || value === undefined || value === "") {
    return "—";
  }
  if (typeof value === "number") {
    return Number.isFinite(value) ? String(Math.round(value)) : "—";
  }
  const numeric = Number(value);
  if (Number.isFinite(numeric)) {
    return String(Math.round(numeric));
  }
  return String(value);
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

const formatMinMaxRange = (minValue, maxValue) => {
  if (
    (minValue === null || minValue === undefined || minValue === "") &&
    (maxValue === null || maxValue === undefined || maxValue === "")
  ) {
    return "—";
  }
  return `${formatValue(minValue)} to ${formatValue(maxValue)}`;
};

const formatPitchWithNote = (value, note) => {
  const renderedValue = formatValue(value);
  if (typeof note === "string" && note.trim()) {
    return renderedValue === "—" ? note : `${renderedValue} (${note})`;
  }
  return renderedValue;
};

const formatRangeWithNotes = (range, notes) => {
  const renderedRange = formatRangeValue(range);
  if (Array.isArray(notes) && notes.length >= 2 && notes[0] && notes[1]) {
    return `${renderedRange} (${notes[0]} to ${notes[1]})`;
  }
  return renderedRange;
};

const formatConfidenceIntervalWithNotes = (ci) => {
  const rendered = `[${formatValue(ci?.low)}, ${formatValue(ci?.high)}]`;
  if (
    typeof ci?.low_note === "string" &&
    ci.low_note.trim() &&
    typeof ci?.high_note === "string" &&
    ci.high_note.trim()
  ) {
    return `${rendered} (${ci.low_note} to ${ci.high_note})`;
  }
  return rendered;
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
  const [activeResultsView, setActiveResultsView] = useState(RESULTS_VIEWS.analysis);
  const hasResults = Boolean(results && Object.keys(results).length > 0);

  const summary = results?.summary ?? results?.stats ?? results?.tessitura ?? null;
  const duration = results?.metadata?.duration_seconds ?? results?.duration_seconds ?? summary?.duration_seconds;
  const f0Min = results?.pitch?.f0_min ?? summary?.f0_min ?? summary?.min_f0;
  const f0Max = results?.pitch?.f0_max ?? summary?.f0_max ?? summary?.max_f0;
  const tessitura = summary?.tessitura_range ?? summary?.range;
  const f0MinNote = summary?.f0_min_note ?? results?.pitch?.f0_min_note ?? null;
  const f0MaxNote = summary?.f0_max_note ?? results?.pitch?.f0_max_note ?? null;
  const tessituraNotes =
    summary?.tessitura_range_notes ?? results?.tessitura?.metrics?.tessitura_band_notes ?? null;
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

  const calibrationSummary = isPlainObject(results?.calibration?.summary)
    ? results.calibration.summary
    : null;
  const hasCalibrationSummary = Boolean(
    calibrationSummary && Object.keys(calibrationSummary).length > 0
  );
  const showResultsViewTabs = hasCalibrationSummary;

  useEffect(() => {
    if (!hasCalibrationSummary && activeResultsView === RESULTS_VIEWS.calibration) {
      setActiveResultsView(RESULTS_VIEWS.analysis);
    }
  }, [activeResultsView, hasCalibrationSummary]);

  const readableStatus = (status?.status ?? "waiting").replace(/_/g, " ");
  const analysisTabId = `${titleId}-tab-analysis`;
  const analysisPanelId = `${titleId}-panel-analysis`;
  const calibrationTabId = `${titleId}-tab-calibration`;
  const calibrationPanelId = `${titleId}-panel-calibration`;

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
          {hasCalibrationSummary ? (
            <div className="results__view-tabs" role="tablist" aria-label="Analysis result views">
              <button
                id={analysisTabId}
                className="button results__view-tab"
                type="button"
                role="tab"
                aria-selected={activeResultsView === RESULTS_VIEWS.analysis}
                aria-controls={analysisPanelId}
                onClick={() => setActiveResultsView(RESULTS_VIEWS.analysis)}
              >
                General analysis
              </button>
              <button
                id={calibrationTabId}
                className="button results__view-tab"
                type="button"
                role="tab"
                aria-selected={activeResultsView === RESULTS_VIEWS.calibration}
                aria-controls={calibrationPanelId}
                onClick={() => setActiveResultsView(RESULTS_VIEWS.calibration)}
              >
                Reference calibration
              </button>
            </div>
          ) : null}

          {activeResultsView === RESULTS_VIEWS.analysis ? (
            <div
              id={showResultsViewTabs ? analysisPanelId : undefined}
              role={showResultsViewTabs ? "tabpanel" : undefined}
              aria-labelledby={showResultsViewTabs ? analysisTabId : undefined}
            >
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
                    <dd>{formatPitchWithNote(f0Min, f0MinNote)}</dd>
                  </div>
                  <div className="summary-list__item">
                    <dt>Highest detected pitch (F0, Hz)</dt>
                    <dd>{formatPitchWithNote(f0Max, f0MaxNote)}</dd>
                  </div>
                  <div className="summary-list__item">
                    <dt>Comfortable singing range (tessitura)</dt>
                    <dd>{formatRangeWithNotes(tessitura, tessituraNotes)}</dd>
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
                              <td>{formatPitchWithNote(metricPayload?.estimate, metricPayload?.estimate_note)}</td>
                              <td>{formatConfidenceIntervalWithNotes(ci)}</td>
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
            </div>
          ) : null}

          {hasCalibrationSummary && activeResultsView === RESULTS_VIEWS.calibration ? (
            <section
              id={calibrationPanelId}
              className="results__section results__section--calibration"
              role="tabpanel"
              aria-labelledby={calibrationTabId}
              aria-label="Reference calibration summary"
            >
              <div className="results__section-header">
                <h3 className="results__section-title">Reference calibration summary</h3>
                <p className="results__section-meta">
                  These metrics come from reference dataset calibration (ground-truth generated data) and are not derived from uploaded or example track runtime behavior.
                </p>
              </div>
              <dl className="summary-list">
                <div className="summary-list__item">
                  <dt>Reference samples (N)</dt>
                  <dd>{formatCountValue(calibrationSummary?.reference_sample_count)}</dd>
                </div>
                <div className="summary-list__item">
                  <dt>Reference frequency range (Hz)</dt>
                  <dd>
                    {formatMinMaxRange(
                      calibrationSummary?.reference_frequency_min_hz,
                      calibrationSummary?.reference_frequency_max_hz
                    )}
                  </dd>
                </div>
                <div className="summary-list__item">
                  <dt>Frequency bins (total)</dt>
                  <dd>{formatCountValue(calibrationSummary?.frequency_bin_count)}</dd>
                </div>
                <div className="summary-list__item">
                  <dt>Frequency bins (populated)</dt>
                  <dd>{formatCountValue(calibrationSummary?.populated_frequency_bin_count)}</dd>
                </div>
                <div className="summary-list__item">
                  <dt>Mean pitch bias (cents)</dt>
                  <dd>{formatValue(calibrationSummary?.mean_pitch_bias_cents)}</dd>
                </div>
                <div className="summary-list__item">
                  <dt>Max absolute pitch bias (cents)</dt>
                  <dd>{formatValue(calibrationSummary?.max_abs_pitch_bias_cents)}</dd>
                </div>
                <div className="summary-list__item">
                  <dt>Mean pitch variance (cents²)</dt>
                  <dd>{formatValue(calibrationSummary?.mean_pitch_variance_cents2)}</dd>
                </div>
                <div className="summary-list__item">
                  <dt>Pitch error mean (cents)</dt>
                  <dd>{formatValue(calibrationSummary?.pitch_error_mean_cents)}</dd>
                </div>
                <div className="summary-list__item">
                  <dt>Pitch error standard deviation (cents)</dt>
                  <dd>{formatValue(calibrationSummary?.pitch_error_std_cents)}</dd>
                </div>
                <div className="summary-list__item">
                  <dt>Mean frame uncertainty (MIDI)</dt>
                  <dd>{formatValue(calibrationSummary?.mean_frame_uncertainty_midi)}</dd>
                </div>
                <div className="summary-list__item">
                  <dt>Voiced frame count</dt>
                  <dd>{formatCountValue(calibrationSummary?.voiced_frame_count)}</dd>
                </div>
              </dl>
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
