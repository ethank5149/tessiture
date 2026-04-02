/**
 * PitchMeter — Real-time pitch deviation display for live comparison.
 *
 * Shows:
 * - A horizontal deviation bar centered on "in tune" (0 cents)
 * - Current note name and reference note name side by side
 * - Running accuracy percentage
 * - Color-coded feedback: green (in tune), yellow (slightly off), red (way off)
 *
 * Receives chunk feedback from the WebSocket via props.
 */

import { useEffect, useRef, useMemo } from "react";

const CENTS_RANGE = 100; // ±100 cents displayed

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function centsToColor(absCents) {
  if (absCents < 15) return "var(--success, #4ade80)";
  if (absCents < 50) return "#fbbf24";
  return "var(--danger, #fb7185)";
}

function centsToLabel(cents) {
  if (Math.abs(cents) < 5) return "In tune";
  if (cents > 0) return `${Math.round(cents)}¢ sharp`;
  return `${Math.round(Math.abs(cents))}¢ flat`;
}

function PitchMeter({
  currentDeviation = null,    // cents deviation from reference (signed)
  userNote = null,            // current user note name string
  referenceNote = null,       // current reference note name string
  accuracyRatio = null,       // running accuracy ratio 0–1
  isVoiced = false,           // whether current frame is voiced
}) {
  const barRef = useRef(null);

  // Animate the bar smoothly
  useEffect(() => {
    const bar = barRef.current;
    if (!bar) return;

    if (!isVoiced || currentDeviation === null || !Number.isFinite(currentDeviation)) {
      bar.style.opacity = "0.2";
      bar.style.left = "50%";
      bar.style.backgroundColor = "var(--text-soft, #8d9ab8)";
      return;
    }

    const clamped = clamp(currentDeviation, -CENTS_RANGE, CENTS_RANGE);
    const pct = 50 + (clamped / CENTS_RANGE) * 50;
    bar.style.opacity = "1";
    bar.style.left = `${pct}%`;
    bar.style.backgroundColor = centsToColor(Math.abs(currentDeviation));
  }, [currentDeviation, isVoiced]);

  const accuracyPct = useMemo(() => {
    if (accuracyRatio === null || !Number.isFinite(accuracyRatio)) return null;
    return Math.round(accuracyRatio * 100);
  }, [accuracyRatio]);

  const deviationLabel = useMemo(() => {
    if (!isVoiced || currentDeviation === null || !Number.isFinite(currentDeviation)) {
      return "—";
    }
    return centsToLabel(currentDeviation);
  }, [currentDeviation, isVoiced]);

  return (
    <div className="pitch-meter" role="status" aria-live="polite" aria-label="Real-time pitch feedback">
      {/* Note names side by side */}
      <div className="pitch-meter__notes">
        <div className="pitch-meter__note-col">
          <span className="pitch-meter__note-label">You</span>
          <span className="pitch-meter__note-value" style={{ fontSize: "1.8rem", fontWeight: 700 }}>
            {isVoiced && userNote ? userNote : "—"}
          </span>
        </div>
        <div className="pitch-meter__note-col" style={{ opacity: 0.6 }}>
          <span className="pitch-meter__note-label">Reference</span>
          <span className="pitch-meter__note-value" style={{ fontSize: "1.8rem", fontWeight: 700 }}>
            {referenceNote || "—"}
          </span>
        </div>
      </div>

      {/* Deviation bar */}
      <div className="pitch-meter__bar-container">
        <div className="pitch-meter__bar-track">
          {/* Center line */}
          <div className="pitch-meter__bar-center" />
          {/* Indicator */}
          <div
            ref={barRef}
            className="pitch-meter__bar-indicator"
            style={{
              transition: "left 80ms ease-out, background-color 120ms ease",
            }}
          />
        </div>
        <div className="pitch-meter__bar-labels">
          <span>Flat</span>
          <span style={{ fontWeight: 600 }}>{deviationLabel}</span>
          <span>Sharp</span>
        </div>
      </div>

      {/* Running accuracy */}
      {accuracyPct !== null && (
        <div className="pitch-meter__accuracy">
          <span className="pitch-meter__accuracy-label">Pitch accuracy</span>
          <span
            className="pitch-meter__accuracy-value"
            style={{
              color: accuracyPct >= 70 ? "var(--success)" : accuracyPct >= 40 ? "#fbbf24" : "var(--danger)",
              fontSize: "1.4rem",
              fontWeight: 700,
            }}
          >
            {accuracyPct}%
          </span>
        </div>
      )}
    </div>
  );
}

export default PitchMeter;
