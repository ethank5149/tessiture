/**
 * Displays live running comparison metrics from a WebSocket comparison session.
 *
 * @param {object} props
 * @param {object|null} props.runningSummary - Latest running_summary message from WebSocket
 * @param {object|null} props.latestFeedback - Latest chunk_feedback message from WebSocket
 * @param {number} props.sessionElapsedS - Session elapsed time in seconds
 */

const formatMmSs = (totalSeconds) => {
  const s = Math.max(0, Math.floor(totalSeconds));
  const mm = String(Math.floor(s / 60)).padStart(2, "0");
  const ss = String(s % 60).padStart(2, "0");
  return `${mm}:${ss}`;
};

const deviationColorClass = (cents) => {
  if (cents === null || cents === undefined) return "";
  const abs = Math.abs(cents);
  if (abs <= 25) return "note-in-tune";
  if (abs <= 50) return "note-warning";
  return "note-off-pitch";
};

const formatCents = (cents) => {
  if (cents === null || cents === undefined) return "—";
  const sign = cents >= 0 ? "+" : "";
  return `${sign}${Math.round(cents)}¢`;
};

const ComparisonMetricsPanel = ({ runningSummary = null, latestFeedback = null, sessionElapsedS = 0 }) => {
  const userNote = latestFeedback?.user_note_name ?? null;
  const refNote = latestFeedback?.reference_note_name ?? null;
  const deviation = latestFeedback?.pitch_deviation_cents ?? null;
  const inTune = latestFeedback?.in_tune ?? null;

  const pitchAccuracy =
    runningSummary?.pitch_accuracy_ratio != null
      ? `${Math.round(runningSummary.pitch_accuracy_ratio * 100)}%`
      : "—";

  const meanDeviation =
    runningSummary?.mean_pitch_deviation_cents != null
      ? formatCents(runningSummary.mean_pitch_deviation_cents)
      : "—";

  const voicedCount = runningSummary?.voiced_chunk_count ?? 0;
  const totalCount = runningSummary?.total_chunk_count ?? 0;
  const framesDisplay = totalCount > 0 ? `${voicedCount} / ${totalCount}` : "—";

  const elapsed = runningSummary?.session_elapsed_s ?? sessionElapsedS;

  return (
    <section className="metrics-panel" aria-label="Live comparison metrics">
      {/* Current note display */}
      <div className="note-display" aria-live="polite" aria-atomic="true">
        {userNote ? (
          <>
            <span
              className={`note-display__note ${deviationColorClass(deviation)}`}
              aria-label={`Your note: ${userNote}`}
            >
              {userNote}
            </span>
            {deviation !== null ? (
              <span
                className={`note-display__deviation ${deviationColorClass(deviation)}`}
                aria-label={`Pitch deviation: ${formatCents(deviation)}`}
              >
                {formatCents(deviation)}
              </span>
            ) : null}
            {refNote ? (
              <span className="note-display__ref-note" aria-label={`Reference note: ${refNote}`}>
                vs <strong>{refNote}</strong>
              </span>
            ) : null}
            {inTune !== null ? (
              <span
                className={`note-display__status ${inTune ? "note-in-tune" : "note-off-pitch"}`}
                aria-label={inTune ? "In tune" : "Off pitch"}
              >
                {inTune ? "✓ In tune" : "✗ Off pitch"}
              </span>
            ) : null}
          </>
        ) : (
          <span className="note-display__silent" aria-label="No pitch detected">
            —
          </span>
        )}
      </div>

      {/* Running metric cards */}
      <dl className="metrics-panel__grid">
        <div className="metric-card">
          <dt className="metric-card__label">Pitch Accuracy</dt>
          <dd className="metric-card__value">{pitchAccuracy}</dd>
        </div>
        <div className="metric-card">
          <dt className="metric-card__label">Mean Deviation</dt>
          <dd className="metric-card__value">{meanDeviation}</dd>
        </div>
        <div className="metric-card">
          <dt className="metric-card__label">Voiced / Total</dt>
          <dd className="metric-card__value">{framesDisplay}</dd>
        </div>
        <div className="metric-card">
          <dt className="metric-card__label">Elapsed</dt>
          <dd className="metric-card__value" aria-label={`Session elapsed: ${formatMmSs(elapsed)}`}>
            {formatMmSs(elapsed)}
          </dd>
        </div>
      </dl>
    </section>
  );
};

export default ComparisonMetricsPanel;
