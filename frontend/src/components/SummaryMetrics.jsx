/**
 * SummaryMetrics - Displays summary metrics for analysis results
 * Shows recording length, pitch limits, and tessitura range
 */

import VocalSeparationStatus from "./VocalSeparationStatus";
import GlossaryTerm from "./GlossaryTerm";
import VocalRangeBar from "./VocalRangeBar";
import { classifyVoiceType } from "./VoiceTypeClassifier";
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

  // Classify voice type
  const voiceType = Number.isFinite(f0Min) && Number.isFinite(f0Max) 
    ? classifyVoiceType(f0Min, f0Max)
    : null;

  // Extract tessitura bounds for range bar
  const tessituraLow = tessitura?.[0];
  const tessituraHigh = tessitura?.[1];

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
          <dt>Lowest detected pitch (<GlossaryTerm term="f0">F0, Hz</GlossaryTerm>)</dt>
          <dd>{formatPitchWithNote(f0Min, f0MinNote)}</dd>
        </div>
        <div className="summary-list__item">
          <dt>Highest detected pitch (<GlossaryTerm term="f0">F0, Hz</GlossaryTerm>)</dt>
          <dd>{formatPitchWithNote(f0Max, f0MaxNote)}</dd>
        </div>
        <div className="summary-list__item">
          <dt>Comfortable singing range (<GlossaryTerm term="tessitura">tessitura</GlossaryTerm>)</dt>
          <dd>{formatRangeWithNotes(tessitura, tessituraNotes)}</dd>
        </div>
        {voiceType && (
          <div className="summary-list__item summary-list__item--voice-type">
            <dt>Voice type</dt>
            <dd>
              <strong>{voiceType.label}</strong> ({voiceType.confidence})
              <br />
              <span className="summary-list__item-detail">{voiceType.description}</span>
            </dd>
          </div>
        )}
      </dl>

      {Number.isFinite(f0Min) && Number.isFinite(f0Max) && (
        <VocalRangeBar
          f0MinHz={f0Min}
          f0MaxHz={f0Max}
          tessituraLow={tessituraLow}
          tessituraHigh={tessituraHigh}
          f0MinNote={f0MinNote}
          f0MaxNote={f0MaxNote}
        />
      )}
    </section>
  );
}

export default SummaryMetrics;
