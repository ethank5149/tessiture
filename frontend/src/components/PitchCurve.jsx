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

  if (!Array.isArray(candidates)) {
    return [];
  }

  return candidates
    .map((entry) => {
      if (typeof entry === "number") {
        return { value: entry };
      }
      if (entry && typeof entry === "object") {
        return {
          value: entry.f0_hz ?? entry.f0 ?? entry.value ?? entry.pitch ?? entry.midi ?? null,
        };
      }
      return null;
    })
    .map((entry) => {
      if (!entry) {
        return null;
      }
      const value = toFiniteNumber(entry.value);
      return value === null ? null : { value };
    })
    .filter(Boolean);
};

const summarizeTrendLabel = (values) => {
  if (values.length < 2) {
    return null;
  }

  const start = values[0];
  const end = values[values.length - 1];
  const drift = end - start;

  if (!Number.isFinite(drift) || Math.abs(drift) < 0.5) {
    return "mostly steady";
  }
  return drift > 0 ? "rising" : "falling";
};

function PitchCurve({ results }) {
  const values = normalizeFrames(results).map((frame) => frame.value);
  const trendLabel = summarizeTrendLabel(values);

  return (
    <section className="results-helper" aria-label="Pitch trend helper">
      <h3 className="results-helper__title">Pitch trend helper</h3>
      <p className="results-helper__copy">
        {trendLabel
          ? `Detected trend: ${trendLabel}. Use this as supporting context in PDF reports.`
          : "Not enough pitch data is available to summarize a trend."}
      </p>
    </section>
  );
}

export default PitchCurve;
