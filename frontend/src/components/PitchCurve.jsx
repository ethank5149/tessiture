const toFiniteNumber = (value) => {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : null;
};

const normalizeFrames = (results) => {
  const candidates =
    results?.pitch?.frames ??
    results?.pitch?.f0_frames ??
    results?.pitch?.f0 ??
    results?.pitch_frames ??
    results?.frames ??
    [];

  if (Array.isArray(candidates)) {
    return candidates
      .map((entry) => {
        if (typeof entry === "number") {
          return { time: null, value: entry };
        }
        if (entry && typeof entry === "object") {
          return {
            time: entry.time ?? entry.t ?? entry.frame_time ?? null,
            value: entry.f0_hz ?? entry.f0 ?? entry.value ?? entry.pitch ?? null,
          };
        }
        return null;
      })
      .map((entry) => {
        if (!entry) {
          return null;
        }
        const value = toFiniteNumber(entry.value);
        if (value === null) {
          return null;
        }
        const time = toFiniteNumber(entry.time);
        return { time, value };
      })
      .filter(Boolean);
  }

  return [];
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

const formatHz = (value) => (Number.isFinite(value) ? `${value.toFixed(1)} Hz` : "—");

function PitchCurve({ results }) {
  const frames = normalizeFrames(results);
  const hasData = frames.length > 1;
  const values = frames.map((frame) => frame.value);
  const minValue = hasData ? Math.min(...values) : 0;
  const maxValue = hasData ? Math.max(...values) : 0;
  const range = Math.max(maxValue - minValue, 1e-6);

  const timedFrames = frames.filter((frame) => Number.isFinite(frame.time));
  const hasTimeAxis = timedFrames.length === frames.length && frames.length > 1;
  const minTime = hasTimeAxis ? Math.min(...timedFrames.map((frame) => frame.time)) : 0;
  const maxTime = hasTimeAxis ? Math.max(...timedFrames.map((frame) => frame.time)) : frames.length - 1;
  const timeSpan = Math.max(maxTime - minTime, 1e-6);

  const frameDiffs = values.slice(1).map((value, index) => Math.abs(value - values[index]));
  const medianStep = computeQuantile(frameDiffs, 0.5) ?? 0;
  const p10 = computeQuantile(values, 0.1);
  const p90 = computeQuantile(values, 0.9);
  const controlBand = Number.isFinite(p10) && Number.isFinite(p90) ? p90 - p10 : null;

  const segmentSize = Math.max(1, Math.floor(values.length / 4));
  const startSegment = values.slice(0, segmentSize);
  const endSegment = values.slice(values.length - segmentSize);
  const startMean = startSegment.length
    ? startSegment.reduce((sum, value) => sum + value, 0) / startSegment.length
    : null;
  const endMean = endSegment.length
    ? endSegment.reduce((sum, value) => sum + value, 0) / endSegment.length
    : null;
  const driftHz = Number.isFinite(startMean) && Number.isFinite(endMean) ? endMean - startMean : null;

  const stabilityLabel =
    medianStep <= 8
      ? "Steady"
      : medianStep <= 20
        ? "Moderately stable"
        : "Highly variable";
  const driftLabel =
    !Number.isFinite(driftHz) || Math.abs(driftHz) < 5
      ? "Little net drift"
      : driftHz > 0
        ? `Upward drift (${driftHz.toFixed(1)} Hz)`
        : `Downward drift (${Math.abs(driftHz).toFixed(1)} Hz)`;

  const width = 600;
  const height = 200;
  const points = hasData
    ? frames
        .map((frame, index) => {
          const xRaw = hasTimeAxis ? frame.time : index;
          const x = ((xRaw - (hasTimeAxis ? minTime : 0)) / (hasTimeAxis ? timeSpan : Math.max(frames.length - 1, 1))) * width;
          const y = height - ((frame.value - minValue) / range) * height;
          return `${x.toFixed(2)},${y.toFixed(2)}`;
        })
        .join(" ")
    : "";

  return (
    <section className="card chart chart--pitch-curve">
      <header className="card__header">
        <h3 className="card__title">Pitch control: stability and drift</h3>
        <p className="card__meta">
          This curve tracks your sung pitch contour so you can spot wobble, drift, and control improvements.
        </p>
      </header>

      <div className="chart__body" role="img" aria-label="Pitch stability and control curve">
        {hasData ? (
          <svg className="chart__svg" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none">
            <polyline fill="none" stroke="currentColor" strokeWidth="2" points={points} />
          </svg>
        ) : (
          <p className="chart__placeholder">Not enough pitch frames to evaluate pitch control yet.</p>
        )}
      </div>

      <div className="chart__axes" aria-hidden="true">
        <span>{hasTimeAxis ? "Start of phrase" : "First detected frame"}</span>
        <span>{hasTimeAxis ? "End of phrase" : "Last detected frame"}</span>
      </div>
      <p className="chart__axis-note">Vertical movement means lower pitch (down) or higher pitch (up).</p>

      {hasData ? (
        <div className="chart__callouts" aria-label="Pitch control callouts">
          <article className="chart__callout">
            <h4>Stability</h4>
            <p>
              {`${stabilityLabel} control. Typical frame-to-frame movement: ${medianStep.toFixed(1)} Hz.`}
            </p>
          </article>
          <article className="chart__callout">
            <h4>Drift</h4>
            <p>
              {`${driftLabel}. Practice slow sustained vowels to keep the center pitch consistent.`}
            </p>
          </article>
          <article className="chart__callout">
            <h4>Control band</h4>
            <p>
              {Number.isFinite(controlBand)
                ? `Most of your pitch lived inside a ${controlBand.toFixed(1)} Hz band (10th–90th percentile).`
                : "Control band is unavailable for sparse input."}
            </p>
          </article>
        </div>
      ) : null}

      {hasData ? (
        <details className="chart__advanced" aria-label="Advanced pitch metrics">
          <summary>Show advanced pitch metrics</summary>
          <dl className="chart__advanced-list">
            <div>
              <dt>Voiced frames</dt>
              <dd>{frames.length}</dd>
            </div>
            <div>
              <dt>Median step change</dt>
              <dd>{formatHz(medianStep)}</dd>
            </div>
            <div>
              <dt>10th–90th percentile band</dt>
              <dd>{Number.isFinite(controlBand) ? formatHz(controlBand) : "—"}</dd>
            </div>
            <div>
              <dt>Start-to-end drift</dt>
              <dd>{Number.isFinite(driftHz) ? formatHz(driftHz) : "—"}</dd>
            </div>
            <div>
              <dt>Time coverage</dt>
              <dd>{hasTimeAxis ? `${timeSpan.toFixed(2)}s` : "Frame-indexed"}</dd>
            </div>
          </dl>
        </details>
      ) : null}

      <footer className="chart__footer">
        <span>Lowest tracked: {formatHz(minValue)}</span>
        <span>Highest tracked: {formatHz(maxValue)}</span>
      </footer>
    </section>
  );
}

export default PitchCurve;
