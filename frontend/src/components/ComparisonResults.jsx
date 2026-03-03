/**
 * Post-session comparison report display.
 *
 * @param {object}   props
 * @param {object}   props.sessionReport - Full session_report message from the WebSocket:
 *                     { session_id, reference_id, duration_s,
 *                       comparison: { pitch, rhythm, range, formants } }
 * @param {Function} props.onClose      - Called when the user clicks "Close"
 * @param {Function} props.onStartNew   - Called when the user clicks "Start New Session"
 */

const formatMmSs = (totalSeconds) => {
  const s = Math.max(0, Math.floor(totalSeconds ?? 0));
  const mm = String(Math.floor(s / 60)).padStart(2, "0");
  const ss = String(s % 60).padStart(2, "0");
  return `${mm}:${ss}`;
};

const fmt = (value, decimals = 1) => {
  if (value === null || value === undefined) return "—";
  const n = Number(value);
  if (!isFinite(n)) return "—";
  return n.toFixed(decimals);
};

const fmtPct = (ratio, decimals = 1) => {
  if (ratio === null || ratio === undefined) return "—";
  const n = Number(ratio);
  if (!isFinite(n)) return "—";
  return `${(n * 100).toFixed(decimals)}%`;
};

const fmtCents = (cents) => {
  if (cents === null || cents === undefined) return "—";
  const n = Number(cents);
  if (!isFinite(n)) return "—";
  const sign = n >= 0 ? "+" : "";
  return `${sign}${n.toFixed(1)}¢`;
};

/** A single metric card with label + value. */
const MetricCard = ({ label, value, highlight }) => (
  <div className={`metric-card${highlight ? " metric-card--highlight" : ""}`}>
    <dt className="metric-card__label">{label}</dt>
    <dd className="metric-card__value">{value}</dd>
  </div>
);

/** A titled section card wrapping metric cards + optional coaching text. */
const SectionCard = ({ title, children, coaching }) => (
  <section className="comparison-results__section">
    <h3 className="comparison-results__section-title">{title}</h3>
    {children}
    {coaching ? (
      <p className="comparison-results__coaching">{coaching}</p>
    ) : null}
  </section>
);

const ComparisonResults = ({ sessionReport, onClose, onStartNew }) => {
  const { session_id, reference_id, duration_s, comparison = {} } = sessionReport ?? {};
  const { pitch = {}, rhythm = {}, range = {}, formants = {} } = comparison;

  const durationLabel = duration_s != null ? formatMmSs(duration_s) : "—";

  // --- Pitch coaching ---
  const mape = pitch.mean_absolute_pitch_error_cents;
  let pitchCoaching = null;
  if (mape != null) {
    const v = Number(mape);
    if (v <= 25)
      pitchCoaching = `Mean pitch error of ${v.toFixed(1)} cents — within target of ±25 cents.`;
    else if (v <= 50)
      pitchCoaching = `Mean pitch error of ${v.toFixed(1)} cents — slightly above target of ±25 cents.`;
    else
      pitchCoaching = `Mean pitch error of ${v.toFixed(1)} cents — significantly above target of ±25 cents.`;
  }

  // --- Rhythm coaching ---
  const hitRate = rhythm.note_hit_rate;
  let rhythmCoaching = null;
  if (hitRate != null) {
    const refNotes = rhythm.reference_note_count ?? 0;
    const moeMs = rhythm.mean_onset_error_ms ?? 0;
    const within = moeMs <= 150 ? "within" : "outside";
    rhythmCoaching = `${fmtPct(hitRate)} of reference notes were matched. Mean onset error ${fmt(moeMs)} ms — ${within} the 150 ms onset tolerance.`;
  }

  // --- Range coaching ---
  const coverage = range.range_coverage_ratio;
  let rangeCoaching = null;
  if (coverage != null)
    rangeCoaching = `Your observed range covered ${fmtPct(coverage)} of the reference pitch range.`;

  return (
    <div className="comparison-view comparison-view--report comparison-results">
      {/* Header */}
      <header className="comparison-results__header">
        <h2 className="comparison-results__title">Session Complete</h2>
        <div className="comparison-results__meta">
          <span>Duration: <strong>{durationLabel}</strong></span>
          {reference_id ? (
            <span>Reference: <strong>{reference_id}</strong></span>
          ) : null}
        </div>
      </header>

      {/* Section 2: Pitch Accuracy */}
      <SectionCard title="Pitch Accuracy" coaching={pitchCoaching}>
        <dl className="metrics-panel__grid">
          <MetricCard
            label="Mean Abs. Error"
            value={`${fmt(pitch.mean_absolute_pitch_error_cents)} ¢`}
          />
          <MetricCard
            label="Accuracy (±50 ¢)"
            value={fmtPct(pitch.pitch_accuracy_ratio)}
          />
          <MetricCard
            label="Pitch Bias"
            value={fmtCents(pitch.pitch_bias_cents)}
          />
          <MetricCard
            label="Stability (std dev)"
            value={`${fmt(pitch.pitch_stability_cents)} ¢`}
          />
        </dl>
      </SectionCard>

      {/* Section 3: Rhythm Accuracy */}
      <SectionCard title="Rhythm Accuracy" coaching={rhythmCoaching}>
        <dl className="metrics-panel__grid">
          <MetricCard
            label="Note Hit Rate"
            value={fmtPct(rhythm.note_hit_rate)}
          />
          <MetricCard
            label="Mean Onset Error"
            value={`${fmt(rhythm.mean_onset_error_ms)} ms`}
          />
          <MetricCard
            label="Rhythmic Consistency"
            value={`${fmt(rhythm.rhythmic_consistency_ms)} ms`}
          />
          <MetricCard
            label="Notes Matched"
            value={
              rhythm.matched_note_count != null && rhythm.reference_note_count != null
                ? `${rhythm.matched_note_count} / ${rhythm.reference_note_count}`
                : "—"
            }
          />
        </dl>
      </SectionCard>

      {/* Section 4: Vocal Range */}
      <SectionCard title="Vocal Range" coaching={rangeCoaching}>
        <dl className="metrics-panel__grid">
          <MetricCard
            label="Range Overlap"
            value={`${fmt(range.range_overlap_semitones)} st`}
          />
          <MetricCard
            label="Range Coverage"
            value={fmtPct(range.range_coverage_ratio)}
          />
          <MetricCard
            label="Tessitura Offset"
            value={
              range.tessitura_center_offset_semitones != null
                ? `${fmtCents(range.tessitura_center_offset_semitones * 100)} (~${fmt(range.tessitura_center_offset_semitones)} st)`
                : "—"
            }
          />
          <MetricCard
            label="Out-of-Range Notes"
            value={fmtPct(range.out_of_range_note_fraction)}
          />
        </dl>
      </SectionCard>

      {/* Section 5: Formant/Timbre */}
      <SectionCard title="Formant / Timbre">
        {formants.formant_data_available ? (
          <dl className="metrics-panel__grid">
            <MetricCard label="Mean F1 Deviation" value={`${fmt(formants.mean_f1_deviation_hz)} Hz`} />
            <MetricCard label="Mean F2 Deviation" value={`${fmt(formants.mean_f2_deviation_hz)} Hz`} />
            <MetricCard
              label="Spectral Centroid Δ"
              value={`${fmt(formants.spectral_centroid_deviation_hz)} Hz`}
            />
          </dl>
        ) : (
          <p className="comparison-results__unavailable">
            Formant comparison is not available in live streaming mode. For timbre
            analysis, upload the recorded audio to the main analysis tab.
          </p>
        )}
      </SectionCard>

      {/* Actions row */}
      <div className="comparison-results__actions">
        <button
          type="button"
          className="button button--primary"
          onClick={onStartNew}
        >
          ↺ Start New Session
        </button>
        <button
          type="button"
          className="button"
          onClick={onClose}
        >
          ← Close
        </button>
      </div>
    </div>
  );
};

export default ComparisonResults;
