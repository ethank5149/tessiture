const toFiniteNumber = (value) => {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : null;
};

const formatMidiLabel = (value) => {
  const numeric = toFiniteNumber(value);
  return numeric === null ? "—" : `MIDI ${numeric.toFixed(1)}`;
};

const formatRange = (range, notes = null) => {
  if (Array.isArray(notes) && notes.length >= 2 && notes[0] && notes[1]) {
    return `${notes[0]} to ${notes[1]}`;
  }
  if (Array.isArray(range) && range.length >= 2) {
    const low = toFiniteNumber(range[0]);
    const high = toFiniteNumber(range[1]);
    if (low !== null && high !== null) {
      return `${formatMidiLabel(low)} to ${formatMidiLabel(high)}`;
    }
  }
  return "—";
};

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

const describeBin = (bin, index, totalBins) => {
  if (typeof bin?.label === "string" && bin.label.trim()) {
    return bin.label.trim();
  }
  const labelNumber = toFiniteNumber(bin?.label);
  if (labelNumber !== null) {
    return formatMidiLabel(labelNumber);
  }
  if (index <= 0) {
    return "lowest area";
  }
  if (index >= totalBins - 1) {
    return "highest area";
  }
  return `zone ${index + 1}`;
};

const extractTessituraContext = (results) => {
  const metrics =
    results?.tessitura?.metrics && typeof results.tessitura.metrics === "object"
      ? results.tessitura.metrics
      : {};
  const summary = results?.summary && typeof results.summary === "object" ? results.summary : {};

  const tessituraBand = summary.tessitura_range ?? metrics.tessitura_band ?? null;
  const tessituraBandNotes = summary.tessitura_range_notes ?? metrics.tessitura_band_notes ?? null;
  const comfortBand = Array.isArray(metrics.comfort_band) ? metrics.comfort_band : null;
  const strainZones = Array.isArray(metrics.strain_zones) ? metrics.strain_zones : [];

  return {
    tessituraBand,
    tessituraBandNotes,
    comfortBand,
    strainZones,
  };
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

  const { tessituraBand, tessituraBandNotes, comfortBand, strainZones } = extractTessituraContext(results);

  const width = 600;
  const height = 90;

  const totalUsage = values.reduce((sum, value) => sum + value, 0);
  const mostUsedValue = hasBins ? Math.max(...values) : null;
  const leastUsedValue = hasBins ? Math.min(...values) : null;
  const mostUsedIndex = hasBins ? values.indexOf(mostUsedValue) : -1;
  const leastUsedIndex = hasBins ? values.indexOf(leastUsedValue) : -1;

  const upperStartIndex = Math.max(0, Math.floor(bins.length * 0.8));
  const upperUsage = bins.slice(upperStartIndex).reduce((sum, bin) => sum + bin.value, 0);
  const upperUsageRatio = totalUsage > 0 ? upperUsage / totalUsage : 0;

  const hasHighStrainZone = strainZones.some((zone) => {
    if (!zone || typeof zone !== "object") {
      return false;
    }
    const label = typeof zone.label === "string" ? zone.label.toLowerCase() : "";
    const reason = typeof zone.reason === "string" ? zone.reason.toLowerCase() : "";
    return label === "high" || reason.includes("above");
  });

  const overreachMessage = hasHighStrainZone || upperUsageRatio >= 0.35
    ? "You spent substantial time high in your range. Balance with gentle lower and mid-range resets between high drills."
    : "High-range usage looked manageable. Keep building with short high-note sets followed by easy recovery phrases.";

  const tessituraText = formatRange(tessituraBand, tessituraBandNotes);
  const comfortText = formatRange(comfortBand);
  const strainLabels = strainZones
    .map((zone) => (typeof zone?.label === "string" ? zone.label : null))
    .filter(Boolean)
    .join(", ");

  const zoneInterpretation =
    tessituraText !== "—" || comfortText !== "—" || strainZones.length
      ? `Session tessitura: ${tessituraText}. Comfort band: ${comfortText}.${strainLabels ? ` Strain flags: ${strainLabels}.` : ""}`
      : "Comfort-zone metrics were not included in this payload. Use the usage callouts below to choose your next range drill.";

  return (
    <section className="card chart chart--tessitura">
      <header className="card__header">
        <h3 className="card__title">Range usage: where your voice lived today</h3>
        <p className="card__meta">
          This view ignores timing and shows how often each part of your pitch range was used.
        </p>
        <p className="chart__prompt">Practice action: strengthen the underused zones, then re-check for a more balanced spread.</p>
      </header>

      <div className="chart__body" role="img" aria-label="Range-usage distribution across lower to higher pitch zones">
        {hasBins ? (
          <svg className="chart__svg" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none">
            {bins.map((bin, index) => {
              const barWidth = width / bins.length;
              const x = index * barWidth;
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
                  key={`${index}-${String(bin.label ?? "bin")}`}
                  x={x}
                  y={0}
                  width={barWidth}
                  height={height}
                  fill="currentColor"
                  opacity={opacity}
                >
                  <title>{`${describeBin(bin, index, bins.length)}: usage ${bin.value.toFixed(2)}`}</title>
                </rect>
              );
            })}
          </svg>
        ) : (
          <p className="chart__placeholder">No range-usage histogram is available for this session.</p>
        )}
      </div>

      <div className="chart__axes" aria-hidden="true">
        <span>Lower part of your current range</span>
        <span>Higher part of your current range</span>
      </div>

      <div className="chart__legend" aria-label="Range usage legend">
        <span className="chart__legend-title">Usage intensity</span>
        <div className="chart__legend-scale">
          <span>Less used</span>
          <span className="chart__legend-gradient" />
          <span>Most used</span>
        </div>
      </div>

      <p className="chart__zone-note">{zoneInterpretation}</p>

      {hasBins ? (
        <div className="chart__callouts" aria-label="Range-usage coaching callouts">
          <article className="chart__callout">
            <h4>Most-used zone</h4>
            <p>
              {`${describeBin(bins[mostUsedIndex], mostUsedIndex, bins.length)} carried the most singing time. Keep it as your warm-up anchor, then expand out from it.`}
            </p>
          </article>
          <article className="chart__callout">
            <h4>Least-used zone</h4>
            <p>
              {`${describeBin(bins[leastUsedIndex], leastUsedIndex, bins.length)} was used least. Add short scale fragments here to build confidence without strain.`}
            </p>
          </article>
          <article className="chart__callout">
            <h4>Potential overreach</h4>
            <p>{overreachMessage}</p>
          </article>
        </div>
      ) : null}

      <footer className="chart__footer">
        <span>Tracked zones: {bins.length || 0}</span>
        <span>Peak zone intensity: {maxValue.toFixed(2)}</span>
      </footer>
    </section>
  );
}

export default TessituraHeatmap;
