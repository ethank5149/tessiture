import { useId, useMemo, useRef, useState } from "react";
import ReportExporter from "./ReportExporter";
import SpectrogramInspector from "./SpectrogramInspector";
import SummaryMetrics from "./SummaryMetrics";
import EvidenceReferences from "./EvidenceReferences";
import PracticeGuidance from "./PracticeGuidance";
import InferentialStatistics from "./InferentialStatistics";
import CalibrationSummary from "./CalibrationSummary";
import PitchTimeline from "./PitchTimeline";
import VocalProfileCard from "./VocalProfileCard";
import SongSuggestions from "./SongSuggestions";
import WarmUpRoutine from "./WarmUpRoutine";
import SessionHistory from "./SessionHistory";
import {
  normalizeQualityWarnings,
  normalizeEvidencePayload,
  isPlainObject,
} from "./AnalysisFormatters";

/**
 * AdvancedInspectorToggle — collapsible spectrogram section.
 */
function AdvancedInspectorToggle({ jobId, audioRef, results, duration }) {
  const [isOpen, setIsOpen] = useState(false);
  return (
    <details
      className="results__disclosure"
      open={isOpen}
      onToggle={(e) => setIsOpen(e.currentTarget.open)}
    >
      <summary>Audio spectrogram (advanced)</summary>
      {isOpen ? (
        <div className="results__disclosure__body">
          <p className="results__section-copy">
            This shows the frequency content of your recording over time. 
            The horizontal axis is time, the vertical axis is frequency (pitch), 
            and the white line is your detected pitch. Brighter colors mean louder frequencies.
          </p>
          <SpectrogramInspector
            jobId={jobId}
            audioRef={audioRef}
            evidenceEvents={results?.evidence?.events ?? []}
            durationSeconds={duration ?? 0}
            pitchFrames={results?.pitch?.frames ?? results?.pitch_frames ?? []}
          />
        </div>
      ) : null}
    </details>
  );
}

/**
 * ConfidenceBadge — one-glance analysis quality indicator derived from
 * calibration metrics.  Replaces the raw calibration table for most users.
 */
function ConfidenceBadge({ calibrationSummary }) {
  if (!calibrationSummary) return null;

  const bias = Math.abs(calibrationSummary.mean_pitch_bias_cents ?? 0);
  const std = calibrationSummary.pitch_error_std_cents ?? 0;
  const samples = calibrationSummary.voiced_frame_count ?? 0;

  let level = "high";
  let label = "High confidence";
  let description = "Stable, well-calibrated results across the detected frequency range.";

  if (samples < 5 || std > 15 || bias > 10) {
    level = "low";
    label = "Low confidence";
    description = "Limited data or high variance — treat these results as rough estimates.";
  } else if (std > 5 || bias > 3) {
    level = "medium";
    label = "Moderate confidence";
    description = "Reasonable results with some measurement uncertainty in extreme ranges.";
  }

  return (
    <div className={`confidence-badge confidence-badge--${level}`} role="status" aria-label={`Analysis confidence: ${label}`}>
      <span aria-hidden="true">{level === "high" ? "✓" : level === "medium" ? "~" : "!"}</span>
      <span>{label}</span>
      <span style={{ fontWeight: 400, fontSize: "0.8rem", opacity: 0.8, marginLeft: 4 }}>
        — {description}
      </span>
    </div>
  );
}

function AnalysisResults({
  results = null,
  status = null,
  error = null,
  isFetchingResults = false,
  onDownloadCsv,
  onDownloadJson,
  onDownloadPdf,
  audioSourceUrl = null,
  audioSourceLabel = null,
  jobId = null,
}) {
  const titleId = useId();
  const hasResults = Boolean(results && Object.keys(results).length > 0);
  const audioRef = useRef(null);

  // --- Extract data from results ------------------------------------------
  const pitchFrames =
    (Array.isArray(results?.pitch?.frames) && results.pitch.frames) ||
    (Array.isArray(results?.pitch_frames) && results.pitch_frames) ||
    [];
  const hasPitchFrames = pitchFrames.length > 0;
  const hasNoteEvents =
    (Array.isArray(results?.note_events) && results.note_events.length > 0) ||
    (Array.isArray(results?.notes?.events) && results.notes.events.length > 0);
  const hasTessituraHistogram =
    (Array.isArray(results?.tessitura?.histogram) && results.tessitura.histogram.length > 0) ||
    (Array.isArray(results?.tessitura?.pdf?.density) && results.tessitura.pdf.density.length > 0);

  const inferentialStatistics =
    results?.inferential_statistics && typeof results.inferential_statistics === "object"
      ? results.inferential_statistics
      : null;
  const inferentialMetrics =
    inferentialStatistics?.metrics && typeof inferentialStatistics.metrics === "object"
      ? Object.entries(inferentialStatistics.metrics)
      : [];
  const hasInferentialMetrics = inferentialMetrics.length > 0;

  const isSparseCompletedResults =
    status?.status === "completed" &&
    hasResults &&
    !hasPitchFrames &&
    !hasNoteEvents &&
    !hasTessituraHistogram &&
    !hasInferentialMetrics;

  const qualityWarnings = normalizeQualityWarnings(results?.warnings);
  const evidence = useMemo(() => normalizeEvidencePayload(results?.evidence), [results]);
  const evidenceEventMap = useMemo(() => {
    const map = new Map();
    evidence.events.forEach((event) => {
      if (typeof event.id === "string" && event.id.trim()) {
        map.set(event.id, event);
      }
    });
    return map;
  }, [evidence]);
  const lowestEvidenceEvent = evidence.lowest_voiced_note_ref
    ? evidenceEventMap.get(evidence.lowest_voiced_note_ref)
    : null;
  const highestEvidenceEvent = evidence.highest_voiced_note_ref
    ? evidenceEventMap.get(evidence.highest_voiced_note_ref)
    : null;

  const calibrationSummary = isPlainObject(results?.calibration?.summary)
    ? results.calibration.summary
    : null;

  const duration = results?.metadata?.duration_seconds ?? results?.duration_seconds ?? results?.summary?.duration_seconds;
  const readableStatus = (status?.status ?? "waiting").replace(/_/g, " ");

  // Tessitura bounds for pitch timeline
  const tessituraLow = results?.tessitura?.metrics?.tessitura_band?.[0]
    ?? results?.summary?.tessitura_range?.[0];
  const tessituraHigh = results?.tessitura?.metrics?.tessitura_band?.[1]
    ?? results?.summary?.tessitura_range?.[1];

  return (
    <section className="card results" aria-labelledby={titleId} aria-busy={isFetchingResults}>
      <header className="card__header results__header">
        <div className="results__header-row">
          <h2 id={titleId} className="card__title">Analysis results</h2>
          <p className={`results__status results__status--${status?.status ?? "idle"}`}>{readableStatus}</p>
        </div>
        <ConfidenceBadge calibrationSummary={calibrationSummary} />
      </header>

      {error ? <p className="results__error" role="alert">{error}</p> : null}

      {!hasResults ? (
        <p className="results__empty">Results will appear here after the job completes.</p>
      ) : (
        <>
          {isSparseCompletedResults ? (
            <p className="results__empty" role="status">
              Analysis completed, but the file did not contain enough detectable pitch activity for detailed personalized guidance.
            </p>
          ) : null}

          {qualityWarnings.length ? (
            <section className="results__section" aria-label="Analysis quality warnings">
              <h3 className="results__section-title">Analysis quality notes</h3>
              <ul>
                {qualityWarnings.map((warning, index) => (
                  <li key={`${warning}-${index}`}>{warning}</li>
                ))}
              </ul>
            </section>
          ) : null}

          {/* ── LAYER 1: Dashboard (always visible) ─────────────────── */}
          {/* Identity + key outcomes — what every user sees first.       */}

          <SessionHistory results={results} />

          <VocalProfileCard results={results} />

          <SummaryMetrics results={results} />

          {hasPitchFrames && (
            <PitchTimeline
              pitchFrames={pitchFrames}
              durationSeconds={duration ?? 0}
              tessituraLow={tessituraLow}
              tessituraHigh={tessituraHigh}
            />
          )}

          {/* ── LAYER 2: Coaching (expandable, open by default) ─────── */}
          {/* Actionable guidance — what to practice, sing, and warm up.  */}

          <details className="results__disclosure" open>
            <summary>What to do next</summary>
            <div className="results__disclosure__body">
              <SongSuggestions results={results} />

              <EvidenceReferences
                results={results}
                evidence={evidence}
                evidenceEventMap={evidenceEventMap}
                lowestEvidenceEvent={lowestEvidenceEvent}
                highestEvidenceEvent={highestEvidenceEvent}
                audioSourceUrl={audioSourceUrl}
                audioSourceLabel={audioSourceLabel}
              />
              <PracticeGuidance results={results} evidence={evidence} />

              <WarmUpRoutine results={results} />
            </div>
          </details>

          {/* ── LAYER 3: Technical details (opt-in, closed) ─────────── */}
          {/* Statistical inference and calibration — power users only.   */}

          {(hasInferentialMetrics || calibrationSummary) && (
            <details className="results__disclosure">
              <summary>Technical statistics & calibration</summary>
              <div className="results__disclosure__body">
                {hasInferentialMetrics && (
                  <InferentialStatistics
                    inferentialStatistics={inferentialStatistics}
                    inferentialMetrics={inferentialMetrics}
                  />
                )}
                {calibrationSummary && (
                  <CalibrationSummary
                    calibrationSummary={calibrationSummary}
                    calibrationTabId={`${titleId}-calib`}
                    titleId={`${titleId}-calib-title`}
                  />
                )}
              </div>
            </details>
          )}

          {/* ── Advanced: spectrogram inspector ─────────────────────── */}

          {jobId ? (
            <AdvancedInspectorToggle
              jobId={jobId}
              audioRef={audioRef}
              results={results}
              duration={duration}
            />
          ) : null}

          <ReportExporter
            disabled={isFetchingResults}
            onDownloadCsv={onDownloadCsv}
            onDownloadJson={onDownloadJson}
            onDownloadPdf={onDownloadPdf}
          />
        </>
      )}
    </section>
  );
}

export default AnalysisResults;
