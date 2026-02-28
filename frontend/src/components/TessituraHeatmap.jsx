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

function TessituraHeatmap({ results }) {
  const bins = extractBins(results);
  const hasBins = bins.length > 0;
  const maxValue = Math.max(...bins.map((bin) => bin.value), 1);

  const width = 600;
  const height = 90;

  return (
    <section className="card chart">
      <header className="card__header">
        <h3 className="card__title">Tessitura heatmap</h3>
        <p className="card__meta">Pitch density distribution</p>
      </header>
      <div className="chart__body" role="img" aria-label="Tessitura heatmap">
        {hasBins ? (
          <svg className="chart__svg" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none">
            {bins.map((bin, index) => {
              const x = (index / bins.length) * width;
              const barWidth = width / bins.length;
              const intensity = Math.min(bin.value / maxValue, 1);
              const opacity = 0.2 + intensity * 0.8;
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
