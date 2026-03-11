/**
 * EvidenceReferences - Displays evidence references with audio playback
 * Shows timestamped track moments for diagnostic purposes
 */

import { useRef, useEffect } from "react";
import { formatTimestampLabel } from "./AnalysisFormatters";

function EvidenceReferences({
  results,
  evidence,
  evidenceEventMap,
  lowestEvidenceEvent,
  highestEvidenceEvent,
  audioSourceUrl,
  audioSourceLabel,
}) {
  const audioRef = useRef(null);
  const snippetTimeoutRef = useRef(null);
  const hasAudioReference = typeof audioSourceUrl === "string" && audioSourceUrl.trim().length > 0;

  useEffect(() => {
    return () => {
      if (snippetTimeoutRef.current) {
        window.clearTimeout(snippetTimeoutRef.current);
        snippetTimeoutRef.current = null;
      }
    };
  }, []);

  const jumpToEvidence = (event) => {
    const audio = audioRef.current;
    if (!audio) {
      return;
    }
    const timestamp = Number(event?.timestamp_s ?? event?.start_s);
    if (!Number.isFinite(timestamp) || timestamp < 0) {
      return;
    }
    audio.currentTime = timestamp;
  };

  const playEvidenceSnippet = (event) => {
    if (!hasAudioReference) {
      return;
    }
    const audio = audioRef.current;
    if (!audio) {
      return;
    }
    const timestamp = Number(event?.timestamp_s ?? event?.start_s);
    if (!Number.isFinite(timestamp) || timestamp < 0) {
      return;
    }

    const snippetDurationSeconds = 3;
    const start = Math.max(0, timestamp - 1.5);
    audio.currentTime = start;

    const playPromise = audio.play?.();
    if (playPromise && typeof playPromise.catch === "function") {
      playPromise.catch(() => {});
    }

    if (snippetTimeoutRef.current) {
      window.clearTimeout(snippetTimeoutRef.current);
    }
    snippetTimeoutRef.current = window.setTimeout(() => {
      audio.pause?.();
      snippetTimeoutRef.current = null;
    }, snippetDurationSeconds * 1000);
  };

  return (
    <section className="results__section results__section--evidence" aria-label="Evidence references">
      <div className="results__section-header">
        <h3 className="results__section-title">Evidence references</h3>
        <p className="results__section-meta">
          Each diagnostic is linked to timestamped track moments so you can jump and listen without using charts.
        </p>
      </div>

      {hasAudioReference ? (
        <audio
          ref={audioRef}
          className="results__evidence-audio"
          controls
          preload="metadata"
          src={audioSourceUrl}
          aria-label={
            audioSourceLabel
              ? `Evidence playback source: ${audioSourceLabel}`
              : "Evidence playback source"
          }
        />
      ) : (
        <p className="evidence-actions__fallback">
          Audio playback is unavailable for this result. Use timestamp references to locate moments manually.
        </p>
      )}

      <ul className="results__evidence-list">
        {[
          { key: "lowest", title: "Lowest voiced note", event: lowestEvidenceEvent },
          { key: "highest", title: "Highest voiced note", event: highestEvidenceEvent },
        ].map((row) => {
          if (!row.event) {
            return null;
          }

          const timestampLabel =
            row.event.timestamp_label ?? formatTimestampLabel(row.event.timestamp_s ?? row.event.start_s);
          const noteLabel = row.event.note ?? "Unknown note";

          return (
            <li key={row.key} className="evidence-row">
              <div className="evidence-row__meta">
                <p className="guidance-card__question">{row.title}</p>
                <p className="guidance-card__detail">
                  {noteLabel} at {timestampLabel}
                </p>
              </div>
              <div className="evidence-actions" role="group" aria-label={`${row.title} actions`}>
                <button
                  type="button"
                  className="button button--secondary"
                  onClick={() => jumpToEvidence(row.event)}
                  disabled={!hasAudioReference}
                >
                  Jump to {timestampLabel}
                </button>
                {hasAudioReference ? (
                  <button
                    type="button"
                    className="button"
                    onClick={() => playEvidenceSnippet(row.event)}
                  >
                    Listen snippet
                  </button>
                ) : null}
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

export default EvidenceReferences;
