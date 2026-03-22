import { useEffect, useId, useMemo, useRef, useState } from "react";
import ReportExporter from "./ReportExporter";
import SpectrogramInspector from "./SpectrogramInspector";
import SummaryMetrics from "./SummaryMetrics";
import EvidenceReferences from "./EvidenceReferences";
import PracticeGuidance from "./PracticeGuidance";
import InferentialStatistics from "./InferentialStatistics";
import CalibrationSummary from "./CalibrationSummary";
import {
  normalizeQualityWarnings,
  normalizeEvidencePayload,
  isPlainObject,
} from "./AnalysisFormatters";

const RESULTS_VIEWS = {
  analysis: "analysis",
  calibration: "calibration",
};

/**
 * AdvancedInspectorToggle
 * Renders the SpectrogramInspector as a collapsible section.
 * The user can expand to view the spectrogram visualization.
 */
function AdvancedInspectorToggle({ jobId, audioRef, results, duration }) {
  const [isOpen, setIsOpen] = useState(false);
  return (
    <details
      className="spectrogram-inspector-toggle"
      open={isOpen}
      onToggle={(e) => setIsOpen(e.currentTarget.open)}
    >
      <summary className="spectrogram-inspector-toggle__summary">
        🔍 Audio spectrogram (advanced)
      </summary>
      {isOpen ? (
        <>
          <p className="spectrogram-inspector-toggle__description">
            This shows the frequency content of your recording over time. 
            The horizontal axis is time, the vertical axis is frequency (pitch), 
            and the white line is your detected pitch. Colored markers show key moments.
            Brighter colors mean louder frequencies.
          </p>
          <SpectrogramInspector
            jobId={jobId}
            audioRef={audioRef}
            evidenceEvents={results?.evidence?.events ?? []}
            durationSeconds={duration ?? 0}
            pitchFrames={results?.pitch?.frames ?? results?.pitch_frames ?? []}
          />
        </>
      ) : null}
    </details>
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
  const [activeResultsView, setActiveResultsView] = useState(RESULTS_VIEWS.analysis);
  const hasResults = Boolean(results && Object.keys(results).length > 0);
  const audioRef = useRef(null);

  // Extract data from results
  const hasPitchFrames =
    (Array.isArray(results?.pitch?.frames) && results.pitch.frames.length > 0) ||
    (Array.isArray(results?.pitch_frames) && results.pitch_frames.length > 0);
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
  const hasCalibrationSummary = Boolean(
    calibrationSummary && Object.keys(calibrationSummary).length > 0
  );
  const showResultsViewTabs = hasCalibrationSummary;

  useEffect(() => {
    if (!hasCalibrationSummary && activeResultsView === RESULTS_VIEWS.calibration) {
      setActiveResultsView(RESULTS_VIEWS.analysis);
    }
  }, [activeResultsView, hasCalibrationSummary]);

  const readableStatus = (status?.status ?? "waiting").replace(/_/g, " ");
  const analysisTabId = `${titleId}-tab-analysis`;
  const analysisPanelId = `${titleId}-panel-analysis`;
  const calibrationTabId = `${titleId}-tab-calibration`;
  const calibrationPanelId = `${titleId}-panel-calibration`;

  const duration = results?.metadata?.duration_seconds ?? results?.duration_seconds ?? results?.summary?.duration_seconds;

  return (
    <section className="card results" aria-labelledby={titleId} aria-busy={isFetchingResults}>
      <header className="card__header results__header">
        <div className="results__header-row">
          <h2 id={titleId} className="card__title">Analysis results</h2>
          <p className={`results__status results__status--${status?.status ?? "idle"}`}>{readableStatus}</p>
        </div>
        <p className="card__meta">Key outcomes are shown first, followed by plain-language practice guidance and supporting statistics.</p>
      </header>

      {error ? <p className="results__error" role="alert">{error}</p> : null}

      {!hasResults ? (
        <p className="results__empty">Results will appear here after the job completes.</p>
      ) : (
        <>
          {hasCalibrationSummary ? (
            <div className="results__view-tabs" role="tablist" aria-label="Analysis result views">
              <button
                id={analysisTabId}
                className="button results__view-tab"
                type="button"
                role="tab"
                aria-selected={activeResultsView === RESULTS_VIEWS.analysis}
                aria-controls={analysisPanelId}
                onClick={() => setActiveResultsView(RESULTS_VIEWS.analysis)}
              >
                General analysis
              </button>
              <button
                id={calibrationTabId}
                className="button results__view-tab"
                type="button"
                role="tab"
                aria-selected={activeResultsView === RESULTS_VIEWS.calibration}
                aria-controls={calibrationPanelId}
                onClick={() => setActiveResultsView(RESULTS_VIEWS.calibration)}
              >
                Reference calibration
              </button>
            </div>
          ) : null}

          {activeResultsView === RESULTS_VIEWS.analysis ? (
            <div
              id={showResultsViewTabs ? analysisPanelId : undefined}
              role={showResultsViewTabs ? "tabpanel" : undefined}
              aria-labelledby={showResultsViewTabs ? analysisTabId : undefined}
            >
              {isSparseCompletedResults ? (
                <p className="results__empty" role="status">
                  Analysis completed, but the file did not contain enough detectable pitch activity for detailed personalized guidance.
                </p>
              ) : null}

              <section className="results__section" aria-label="How to interpret analysis results">
                <h3 className="results__section-title">Interpretation help</h3>
                <p className="results__section-copy">
                  Use summary metrics as your quick snapshot, then follow the guidance cards below to pick one clear practice action.
                </p>
              </section>

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

              <SummaryMetrics results={results} />

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

              <InferentialStatistics
                inferentialStatistics={inferentialStatistics}
                inferentialMetrics={inferentialMetrics}
              />
            </div>
          ) : null}

          {hasCalibrationSummary && activeResultsView === RESULTS_VIEWS.calibration ? (
            <CalibrationSummary
              calibrationSummary={calibrationSummary}
              calibrationTabId={calibrationPanelId}
              titleId={calibrationTabId}
            />
          ) : null}

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
