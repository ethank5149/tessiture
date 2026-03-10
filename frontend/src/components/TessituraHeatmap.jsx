const toFiniteNumber = (value) => {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : null;
};

const formatRange = (range, notes = null) => {
  if (Array.isArray(notes) && notes.length >= 2 && notes[0] && notes[1]) {
    return `${notes[0]} to ${notes[1]}`;
  }

  if (Array.isArray(range) && range.length >= 2) {
    const low = toFiniteNumber(range[0]);
    const high = toFiniteNumber(range[1]);
    if (low !== null && high !== null) {
      return `${low.toFixed(1)} to ${high.toFixed(1)} Hz`;
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

  if (!Array.isArray(bins)) {
    return [];
  }

  return bins
    .map((bin) => {
      if (typeof bin === "number") {
        return bin;
      }
      if (bin && typeof bin === "object") {
        const numeric = toFiniteNumber(bin.value ?? bin.count ?? bin.intensity);
        return numeric ?? null;
      }
      return null;
    })
    .filter((value) => Number.isFinite(value) && value >= 0);
};

const extractTessituraContext = (results) => {
  const metrics =
    results?.tessitura?.metrics && typeof results.tessitura.metrics === "object"
      ? results.tessitura.metrics
      : {};
  const summary = results?.summary && typeof results.summary === "object" ? results.summary : {};

  return {
    tessituraBand: summary.tessitura_range ?? metrics.tessitura_band ?? null,
    tessituraBandNotes: summary.tessitura_range_notes ?? metrics.tessitura_band_notes ?? null,
  };
};

const BAND_LABELS = ["lower", "middle", "upper"];

const summarizeBandUsage = (values) => {
  if (!values.length) {
    return null;
  }

  const total = values.reduce((sum, value) => sum + value, 0);
  const bandSize = Math.ceil(values.length / BAND_LABELS.length);
  const bands = BAND_LABELS.map((label, bandIndex) => {
    const start = bandIndex * bandSize;
    const end = Math.min(values.length, start + bandSize);
    const usage = values.slice(start, end).reduce((sum, value) => sum + value, 0);

    return {
      label,
      usage,
      ratio: total > 0 ? usage / total : 0,
    };
  });

  return bands.reduce((best, band) => (band.usage > best.usage ? band : best), bands[0]);
};

function TessituraHeatmap({ results }) {
  const values = extractBins(results);
  const topBand = summarizeBandUsage(values);

  const { tessituraBand, tessituraBandNotes } = extractTessituraContext(results);
  const tessituraText = formatRange(tessituraBand, tessituraBandNotes);

  const summaryText = topBand
    ? `Most detected range effort was in the ${topBand.label} band (${Math.round(topBand.ratio * 100)}%).`
    : "No range-usage distribution is available in this payload.";

  return (
    <section className="results-helper" aria-label="Range effort helper">
      <h3 className="results-helper__title">Range effort helper</h3>
      <p className="results-helper__copy">{summaryText}</p>
      {tessituraText !== "—" ? (
        <p className="results-helper__copy">Reported tessitura: {tessituraText}.</p>
      ) : null}
    </section>
  );
}

export default TessituraHeatmap;
