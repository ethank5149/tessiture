const extractBins = (results) => {
  const bins =
    results?.tessitura?.histogram ??
    results?.tessitura?.heatmap ??
    results?.tessitura?.pdf?.density ??
    results?.tessitura_histogram ??
    results?.histogram ??
    [];

  const centers = Array.isArray(results?.tessitura?.pdf?.bin_centers)
    ? results.tessitura.pdf.bin_centers
    : [];

  if (!Array.isArray(bins)) {
    return [];
  }
  return bins
    .map((bin, index) => {
      if (typeof bin === "number") {
        return { value: bin, label: centers[index] ?? null };
      }
      if (bin && typeof bin === "object") {
        return {
          value: bin.value ?? bin.count ?? bin.intensity ?? null,
          label: bin.label ?? bin.pitch ?? bin.bin ?? centers[index] ?? null,
        };
      }
      return null;
    })
    .filter((bin) => bin && typeof bin.value === "number" && Number.isFinite(bin.value));
};

const computeQuantile = (values, percentile) => {
  if (!values.length) {
    return 0;
  }
  const sorted = [...values].sort((a, b) => a - b);
  const position = Math.max(0, Math.min(sorted.length - 1, (sorted.length - 1) * percentile));
  const lower = Math.floor(position);
  const upper = Math.ceil(position);
  if (lower === upper) {
    return sorted[lower];
  }
  const weight = position - lower;
  return sorted[lower] * (1 - weight) + sorted[upper] * weight;
};

function TessituraHeatmap({ results }) {
  const bins = extractBins(results);
  const hasBins = bins.length > 0;
  const values = bins.map((bin) => bin.value);
  const maxValue = Math.max(...values, 1);
  const minValue = Math.min(...values, 0);
  const spread = maxValue - minValue;
  const lowQuantile = computeQuantile(values, 0.1);
  const highQuantile = computeQuantile(values, 0.9);
  const robustSpread = highQuantile - lowQuantile;

  const width = 600;
  const height = 90;

  return (
    <section className="card chart">
      <header className="card__header">
        <h3 className="card__title">Session distribution summary (1D tessitura)</h3>
        <p className="card__meta">How your session was distributed across pitch bins, regardless of time order.</p>
      </header>
      <div className="chart__body" role="img" aria-label="Session tessitura distribution summary">
        {hasBins ? (
          <svg className="chart__svg" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none">
            {bins.map((bin, index) => {
              const x = (index / bins.length) * width;
              const barWidth = width / bins.length;
              const normalized =
                robustSpread > 1e-9
                  ? Math.min(Math.max((bin.value - lowQuantile) / robustSpread, 0), 1)
                  : spread > 1e-9
                    ? Math.min(Math.max((bin.value - minValue) / spread, 0), 1)
                    : 0.5;
              const boosted = Math.pow(normalized, 0.6);
              const opacity = 0.08 + boosted * 0.92;
              return (
                <rect
                  key={`${bin.label ?? index}`}
                  x={x}
                  y={0}
                  width={barWidth}
                  height={height}
                  fill="currentColor"
                  opacity={opacity}
                />
              );
            })}
          </svg>
        ) : (
          <p className="chart__placeholder">No tessitura histogram available in results.</p>
        )}
      </div>
      <footer className="chart__footer">
        <span>Bins: {bins.length || 0}</span>
        <span>Peak intensity: {maxValue.toFixed(2)}</span>
      </footer>
    </section>
  );
}

export default TessituraHeatmap;
