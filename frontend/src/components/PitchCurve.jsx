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
            value: entry.f0 ?? entry.value ?? entry.pitch ?? null,
          };
        }
        return null;
      })
      .filter((entry) => entry && typeof entry.value === "number" && Number.isFinite(entry.value));
  }

  return [];
};

function PitchCurve({ results }) {
  const frames = normalizeFrames(results);
  const hasData = frames.length > 1;
  const values = frames.map((frame) => frame.value);
  const minValue = Math.min(...values, 0);
  const maxValue = Math.max(...values, 1);
  const range = maxValue - minValue || 1;

  const width = 600;
  const height = 200;
  const points = hasData
    ? frames
        .map((frame, index) => {
          const x = (index / (frames.length - 1)) * width;
          const y = height - ((frame.value - minValue) / range) * height;
          return `${x.toFixed(2)},${y.toFixed(2)}`;
        })
        .join(" ")
    : "";

  return (
    <section className="card chart">
      <header className="card__header">
        <h3 className="card__title">Pitch curve</h3>
        <p className="card__meta">Fundamental frequency over time</p>
      </header>
      <div className="chart__body" role="img" aria-label="Pitch curve visualization">
        {hasData ? (
          <svg className="chart__svg" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none">
            <polyline
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              points={points}
            />
          </svg>
        ) : (
          <p className="chart__placeholder">No pitch frames available in results.</p>
        )}
      </div>
      <footer className="chart__footer">
        <span>Min: {minValue.toFixed(2)} Hz</span>
        <span>Max: {maxValue.toFixed(2)} Hz</span>
      </footer>
    </section>
  );
}

export default PitchCurve;
