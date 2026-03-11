/**
 * SummaryMetrics - Displays summary metrics for analysis results
 * Shows recording length, pitch limits, and tessitura range
 */

import VocalSeparationStatus from "./VocalSeparationStatus";
import { formatValue, formatPitchWithNote, formatRangeWithNotes } from "./AnalysisFormatters";

function SummaryMetrics({ results }) {
  const summary = results?.summary ?? results?.stats ?? results?.tessitura ?? null;
  const duration = results?.metadata?.duration_seconds ?? results?.duration_seconds ?? summary?.duration_seconds;
  const f0Min = results?.pitch?.f0_min ?? summary?.f0_min ?? summary?.min_f0;
  const f0Max = results?.pitch?.f0_max ?? summary?.f0_max ?? summary?.max_f0;
  const tessitura = summary?.tessitura_range ?? summary?.range;
  const f0MinNote = summary?.f0_min_note ?? results?.pitch?.f0_min_note ?? null;
  const f0MaxNote = summary?.f0_max_note ?? results?.pitch?.f0_max_note ?? null;
  const tessituraNotes =
    summary?.tessitura_range_notes ?? results?.tessitura?.metrics?.tessitura_band_notes ?? null;

  return (
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
  );
}

export default SummaryMetrics;
