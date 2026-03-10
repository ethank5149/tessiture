import { useEffect, useId, useMemo, useState } from "react";
import PitchCurve from "./PitchCurve";
import PianoRoll from "./PianoRoll";
import TessituraHeatmap from "./TessituraHeatmap";
import ReportExporter from "./ReportExporter";

const RESULTS_VIEWS = {
  analysis: "analysis",
  calibration: "calibration",
};

const NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];

const isPlainObject = (value) =>
  Boolean(value) && typeof value === "object" && !Array.isArray(value);

const summarizeNumericSeries = (values) => {
  const numericValues = values.filter((value) => Number.isFinite(value));
  if (!numericValues.length) {
    return { count: 0, min: null, max: null, mean: null };
  }

  const total = numericValues.reduce((sum, value) => sum + value, 0);
  return {
    count: numericValues.length,
    min: Math.min(...numericValues),
    max: Math.max(...numericValues),
    mean: total / numericValues.length,
  };
};

const computeQuantile = (values, percentile) => {
  const numericValues = values.filter((value) => Number.isFinite(value));
  if (!numericValues.length) {
    return null;
  }
  const sorted = [...numericValues].sort((a, b) => a - b);
  const position = Math.max(0, Math.min(sorted.length - 1, (sorted.length - 1) * percentile));
  const lower = Math.floor(position);
  const upper = Math.ceil(position);
  if (lower === upper) {
    return sorted[lower];
  }
  const weight = position - lower;
  return sorted[lower] * (1 - weight) + sorted[upper] * weight;
};

const formatMidiNote = (midiValue) => {
  if (!Number.isFinite(midiValue)) {
    return "—";
  }
  const rounded = Math.round(midiValue);
  const pitchClass = ((rounded % 12) + 12) % 12;
  const octave = Math.floor(rounded / 12) - 1;
  return `${NOTE_NAMES[pitchClass]}${octave} (${midiValue.toFixed(1)} MIDI)`;
};

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

const normalizeQualityWarnings = (warnings) => {
  if (!Array.isArray(warnings)) {
    return [];
  }
  return warnings
    .filter((warning) => typeof warning === "string" && warning.trim())
    .map((warning) => warning.trim());
};

const hzToMidi = (hz) => {
  if (!Number.isFinite(hz) || hz <= 0) {
    return null;
  }
  return 69 + 12 * Math.log2(hz / 440);
};

function VocalSeparationStatus({ vocalSeparation }) {
  if (!vocalSeparation || typeof vocalSeparation !== "object") {
    return null;
  }

  const { applied, audio_type_requested, model } = vocalSeparation;

  if (applied === true) {
    return (
      <p className="vocal-separation-status vocal-separation-status--applied" role="status">
        <span className="vocal-separation-status__badge">AI vocal extraction applied</span>
        <span className="vocal-separation-status__detail">
          Vocals were separated from the mix using {model ?? "htdemucs"} before analysis
        </span>
      </p>
    );
  }

  if (applied === false && audio_type_requested === "mixed") {
    return (
      <p className="vocal-separation-status vocal-separation-status--warn" role="status">
        Vocal extraction unavailable — analyzed as uploaded
      </p>
    );
  }

  if (applied === false && (audio_type_requested === "isolated" || !audio_type_requested)) {
    return (
      <p className="vocal-separation-status vocal-separation-status--isolated" role="status">
        Analyzed as isolated vocals
      </p>
    );
  }

  return null;
}

const extractPitchFramesForHeatmap = (results) => {
  const frames = results?.pitch?.frames ?? results?.pitch_frames ?? [];
  if (!Array.isArray(frames)) {
    return [];
  }

  return frames
    .map((frame, index) => {
      if (!frame || typeof frame !== "object") {
        return null;
      }

      const rawTime = frame.time ?? frame.t ?? index;
      const rawMidi = frame.midi ?? frame.note_midi ?? frame.pitch_midi ?? null;
      const rawHz = frame.f0_hz ?? frame.f0 ?? frame.frequency_hz ?? null;

      const time = Number(rawTime);
      const midi = Number.isFinite(Number(rawMidi)) ? Number(rawMidi) : hzToMidi(Number(rawHz));
      if (!Number.isFinite(time) || !Number.isFinite(midi)) {
        return null;
      }

      const confidence = Number(frame.confidence ?? frame.weight ?? frame.probability);
      const weight = Number.isFinite(confidence) && confidence > 0 ? confidence : 1;

      return { time, midi, weight };
    })
    .filter(Boolean);
};

function TimePitchHeatmap({ results }) {
  const heatmapData = useMemo(() => {
    const frames = extractPitchFramesForHeatmap(results);
    if (!frames.length) {
      return null;
    }

    const minTime = Math.min(...frames.map((frame) => frame.time));
    const maxTime = Math.max(...frames.map((frame) => frame.time));
    const minMidi = Math.min(...frames.map((frame) => frame.midi));
    const maxMidi = Math.max(...frames.map((frame) => frame.midi));

    const timeSpan = Math.max(maxTime - minTime, 1e-6);
    const pitchSpan = Math.max(maxMidi - minMidi, 1e-6);

    const timeBins = Math.max(24, Math.min(120, Math.round(frames.length / 4)));
    const pitchBins = Math.max(18, Math.min(72, Math.round(pitchSpan) + 6));

    const matrix = Array.from({ length: pitchBins }, () => Array.from({ length: timeBins }, () => 0));

    frames.forEach((frame) => {
      const normalizedTime = Math.min(Math.max((frame.time - minTime) / timeSpan, 0), 1);
      const normalizedPitch = Math.min(Math.max((frame.midi - minMidi) / pitchSpan, 0), 1);
      const xBin = Math.min(timeBins - 1, Math.floor(normalizedTime * timeBins));
      const yBinFromBottom = Math.min(pitchBins - 1, Math.floor(normalizedPitch * pitchBins));
      const yBin = pitchBins - 1 - yBinFromBottom;
      matrix[yBin][xBin] += frame.weight;
    });

    const values = matrix.flat();
    const maxValue = Math.max(...values, 0);
    const totalWeight = values.reduce((sum, value) => sum + value, 0);

    const timeColumnTotals = Array.from({ length: timeBins }, (_, xIndex) =>
      matrix.reduce((sum, row) => sum + row[xIndex], 0)
    );
    const busiestTimeColumnValue = Math.max(...timeColumnTotals, 0);
    const busiestTimeColumnIndex = timeColumnTotals.indexOf(busiestTimeColumnValue);
    const busiestTimeStart = (busiestTimeColumnIndex / timeBins) * timeSpan;
    const busiestTimeEnd = ((busiestTimeColumnIndex + 1) / timeBins) * timeSpan;

    const highBandThreshold = minMidi + pitchSpan * 0.75;
    const highBandWeight = frames.reduce(
      (sum, frame) => sum + (frame.midi >= highBandThreshold ? frame.weight : 0),
      0
    );
    const highBandRatio = totalWeight > 0 ? highBandWeight / totalWeight : 0;

    const midiValues = frames.map((frame) => frame.midi);
    const midiQ25 = computeQuantile(midiValues, 0.25);
    const midiQ75 = computeQuantile(midiValues, 0.75);
    const focusedPitchBand =
      Number.isFinite(midiQ25) && Number.isFinite(midiQ75) ? Math.max(midiQ75 - midiQ25, 0) : null;

    const stepDiffs = frames.slice(1).map((frame, index) => Math.abs(frame.midi - frames[index].midi));
    const jumpRatio = stepDiffs.length
      ? stepDiffs.filter((difference) => Number.isFinite(difference) && difference >= 2).length /
        stepDiffs.length
      : 0;

    return {
      matrix,
      maxValue,
      minMidi,
      maxMidi,
      timeSpan,
      timeBins,
      pitchBins,
      insights: {
        busiestTimeStart,
        busiestTimeEnd,
        timeFocusRatio: totalWeight > 0 ? busiestTimeColumnValue / totalWeight : 0,
        highBandRatio,
        focusedPitchBand,
        jumpRatio,
      },
    };
  }, [results]);

  const width = 600;
  const height = 240;

  const insightChips = (() => {
    if (!heatmapData) {
      return [];
    }

    const busiestChip = `Busiest window: ${heatmapData.insights.busiestTimeStart.toFixed(1)}s–${heatmapData.insights.busiestTimeEnd.toFixed(1)}s. Repeat that phrase slowly to clean intonation.`;
    const highBandPercent = Math.round(heatmapData.insights.highBandRatio * 100);
    const highBandChip = `High-range load: ${highBandPercent}% of voiced frames in upper-range bins. ${
      highBandPercent >= 35
        ? "Alternate high drills with easy mid-range resets."
        : "High-range load looks manageable; keep endurance sets short and consistent."
    }`;

    const movementChip = heatmapData.insights.jumpRatio >= 0.25
      ? "Frequent large pitch jumps detected. Practice slow glides and interval accuracy before tempo runs."
      : "Pitch movement is relatively smooth. Keep reinforcing phrase connection and breath pacing.";

    return [busiestChip, highBandChip, movementChip];
  })();

  return (
    <section className="card chart chart--time-pitch">
      <header className="card__header">
        <h3 className="card__title">When and where your range work happened</h3>
        <p className="card__meta">
          Darker cells mean you spent more sung time there. Use this to spot repeated trouble moments and pacing issues.
        </p>
      </header>

      <div className="chart__body" role="img" aria-label="Time and pitch usage map across the session">
        {heatmapData ? (
          <svg className="chart__svg" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none">
            <rect width={width} height={height} fill="transparent" />
            {heatmapData.matrix.map((row, yIndex) =>
              row.map((cellValue, xIndex) => {
                if (cellValue <= 0 || heatmapData.maxValue <= 0) {
                  return null;
                }

                const normalized = Math.min(Math.max(cellValue / heatmapData.maxValue, 0), 1);
                const opacity = 0.1 + Math.pow(normalized, 0.65) * 0.9;
                const cellWidth = width / heatmapData.timeBins;
                const cellHeight = height / heatmapData.pitchBins;

                const timeStart = (xIndex / heatmapData.timeBins) * heatmapData.timeSpan;
                const timeEnd = ((xIndex + 1) / heatmapData.timeBins) * heatmapData.timeSpan;
                const pitchTop =
                  heatmapData.maxMidi -
                  (yIndex / heatmapData.pitchBins) * (heatmapData.maxMidi - heatmapData.minMidi);
                const pitchBottom =
                  heatmapData.maxMidi -
                  ((yIndex + 1) / heatmapData.pitchBins) * (heatmapData.maxMidi - heatmapData.minMidi);

                return (
                  <rect
                    key={`${xIndex}-${yIndex}`}
                    x={xIndex * cellWidth}
                    y={yIndex * cellHeight}
                    width={cellWidth}
                    height={cellHeight}
                    fill="currentColor"
                    opacity={opacity}
                  >
                    <title>{`Time ${timeStart.toFixed(1)}s–${timeEnd.toFixed(1)}s · ${formatMidiNote(pitchBottom)} to ${formatMidiNote(pitchTop)} · intensity ${cellValue.toFixed(2)}`}</title>
                  </rect>
                );
              })
            )}
          </svg>
        ) : (
          <p className="chart__placeholder">No time-aligned pitch frames are available for this practice map.</p>
        )}
      </div>

      <div className="chart__axes" aria-hidden="true">
        <span>Start of recording</span>
        <span>End of recording</span>
      </div>
      <p className="chart__axis-note">Vertical axis reads from lower pitch (bottom) to higher pitch (top).</p>

      <div className="chart__legend" aria-label="Time and pitch map legend">
        <span className="chart__legend-title">Cell intensity</span>
        <div className="chart__legend-scale">
          <span>Brief/rare</span>
          <span className="chart__legend-gradient" />
          <span>Frequent/sustained</span>
        </div>
      </div>

      {insightChips.length ? (
        <div className="insight-chips" aria-label="Time and pitch practice insights">
          {insightChips.map((chip) => (
            <p key={chip} className="insight-chip">
              {chip}
            </p>
          ))}
        </div>
      ) : null}

      <footer className="chart__footer">
        <span>Timeline: {heatmapData ? `0.0s–${heatmapData.timeSpan.toFixed(1)}s` : "—"}</span>
        <span>
          Observed pitch: {heatmapData ? `${formatMidiNote(heatmapData.minMidi)} to ${formatMidiNote(heatmapData.maxMidi)}` : "—"}
        </span>
      </footer>
    </section>
  );
}

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
  const hasPitchFrames =
    (Array.isArray(results?.pitch?.frames) && results.pitch.frames.length > 0) ||
    (Array.isArray(results?.pitch_frames) && results.pitch_frames.length > 0);
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
  const qualityWarnings = normalizeQualityWarnings(results?.warnings);

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

              <section className="results__section" aria-label="How to interpret analysis results">
                <h3 className="results__section-title">Interpretation help</h3>
                <p className="results__section-copy">
                  Use summary metrics as your quick snapshot, then confirm patterns in the visualizations before drawing conclusions about range or consistency.
                </p>
              </section>

              {qualityWarnings.length ? (
                <section className="results__section" aria-label="Analysis quality warnings">
                  <h3 className="results__section-title">Analysis quality notes</h3>
                  <ul>
                    {qualityWarnings.map((warning, index) => (
                      <li key={`${warning}-${index}`}>{warning}</li>
                    ))}
                  </ul>
                </section>
              ) : null}

              <section className="results__section results__section--summary" aria-label="Summary metrics">
                <h3 className="results__section-title">Summary</h3>
                <p className="results__summary-intro">
                  This overview highlights duration, pitch limits, and tessitura range.
                </p>
                <VocalSeparationStatus vocalSeparation={results?.metadata?.vocal_separation} />
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
                  <h3 className="results__section-title">What should I practice next?</h3>
                  <p className="results__section-meta">
                    Use these views as a quick practice plan: range balance, time hotspots, and pitch control.
                  </p>
                </div>
                <div className="results__visual-guide" aria-label="Visualization practice guide">
                  <article className="results__visual-guide-item">
                    <h4>Range usage map</h4>
                    <p>Question answered: Which parts of my usable range are undertrained right now?</p>
                  </article>
                  <article className="results__visual-guide-item">
                    <h4>Time × pitch map</h4>
                    <p>Question answered: Which moments and pitch bands should I isolate in the next repetition?</p>
                  </article>
                  <article className="results__visual-guide-item">
                    <h4>Pitch control curve</h4>
                    <p>Question answered: Is my pitch staying steady, drifting, or jumping between notes?</p>
                  </article>
                </div>
                <p className="results__section-copy">
                  Suggested flow: inspect note-level detail in the piano roll, then use the three coaching views below to pick your next drill.
                </p>
                <div className="results__visuals">
                  <PianoRoll results={results} />
                  <TessituraHeatmap results={results} />
                  <TimePitchHeatmap results={results} />
                  <PitchCurve results={results} />
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
