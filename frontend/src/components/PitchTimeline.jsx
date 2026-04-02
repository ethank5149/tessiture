/**
 * PitchTimeline — Interactive pitch-over-time canvas visualization.
 *
 * Shows the detected f0 trajectory colored by confidence, with horizontal
 * guide lines at note boundaries and hover tooltips showing note name,
 * frequency, and confidence at the cursor position.
 *
 * This replaces the "text-only" analysis for the most important visual:
 * seeing your pitch over time.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

const NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];

function midiToNoteName(midi) {
  if (!Number.isFinite(midi)) return "—";
  const rounded = Math.round(midi);
  const pc = ((rounded % 12) + 12) % 12;
  const octave = Math.floor(rounded / 12) - 1;
  return `${NOTE_NAMES[pc]}${octave}`;
}

function midiToHz(midi) {
  return 440.0 * Math.pow(2, (midi - 69) / 12);
}

/** Map a confidence value [0, 1] to an RGBA color string.
 *  Low confidence → dim red, high confidence → bright cyan/green. */
function confidenceColor(confidence, alpha = 1.0) {
  const c = Math.max(0, Math.min(1, confidence));
  // Red → Yellow → Green → Cyan
  const r = Math.round(255 * Math.max(0, 1 - 2 * c));
  const g = Math.round(255 * Math.min(1, 2 * c));
  const b = Math.round(100 * c);
  return `rgba(${r},${g},${b},${alpha})`;
}

function PitchTimeline({ pitchFrames = [], durationSeconds = 0, tessituraLow, tessituraHigh }) {
  const canvasRef = useRef(null);
  const containerRef = useRef(null);
  const [tooltip, setTooltip] = useState(null);
  const [canvasSize, setCanvasSize] = useState({ width: 800, height: 280 });

  // Extract voiced frames with valid data
  const voicedFrames = useMemo(() => {
    return pitchFrames
      .filter((f) => {
        const midi = f?.midi;
        return Number.isFinite(midi) && midi > 0 && Number.isFinite(f?.time);
      })
      .map((f) => ({
        time: f.time,
        midi: f.midi,
        f0: f.f0_hz || f.f0 || midiToHz(f.midi),
        confidence: Number.isFinite(f.confidence) ? f.confidence : 0.5,
        note: f.note || midiToNoteName(f.midi),
      }));
  }, [pitchFrames]);

  // Compute MIDI range for Y axis
  const { midiMin, midiMax } = useMemo(() => {
    if (voicedFrames.length === 0) return { midiMin: 48, midiMax: 72 };
    const midis = voicedFrames.map((f) => f.midi);
    const lo = Math.floor(Math.min(...midis)) - 2;
    const hi = Math.ceil(Math.max(...midis)) + 2;
    return { midiMin: lo, midiMax: Math.max(hi, lo + 6) };
  }, [voicedFrames]);

  // Responsive resize
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const w = Math.round(entry.contentRect.width);
        if (w > 100) setCanvasSize({ width: w, height: 280 });
      }
    });
    observer.observe(container);
    return () => observer.disconnect();
  }, []);

  // Draw
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return; // jsdom or unsupported browser — skip drawing
    const { width, height } = canvasSize;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = width * dpr;
    canvas.height = height * dpr;
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    const pad = { top: 10, right: 16, bottom: 28, left: 48 };
    const plotW = width - pad.left - pad.right;
    const plotH = height - pad.top - pad.bottom;

    const maxTime = durationSeconds > 0 ? durationSeconds : Math.max(...voicedFrames.map((f) => f.time), 1);
    const timeToX = (t) => pad.left + (t / maxTime) * plotW;
    const midiToY = (m) => pad.top + plotH - ((m - midiMin) / (midiMax - midiMin)) * plotH;

    // Clear
    ctx.clearRect(0, 0, width, height);

    // Tessitura band background
    if (Number.isFinite(tessituraLow) && Number.isFinite(tessituraHigh)) {
      ctx.fillStyle = "rgba(96, 165, 250, 0.08)";
      const y1 = midiToY(tessituraHigh);
      const y2 = midiToY(tessituraLow);
      ctx.fillRect(pad.left, y1, plotW, y2 - y1);
    }

    // Note guide lines (one per semitone for natural notes, dashed for others)
    ctx.textAlign = "right";
    ctx.textBaseline = "middle";
    ctx.font = "10px system-ui, sans-serif";
    for (let midi = Math.ceil(midiMin); midi <= Math.floor(midiMax); midi++) {
      const pc = ((midi % 12) + 12) % 12;
      const isNatural = [0, 2, 4, 5, 7, 9, 11].includes(pc);
      if (!isNatural && (midiMax - midiMin) > 18) continue; // skip accidentals for wide ranges
      const y = midiToY(midi);
      ctx.strokeStyle = isNatural ? "rgba(167, 179, 209, 0.18)" : "rgba(167, 179, 209, 0.07)";
      ctx.lineWidth = isNatural ? 0.8 : 0.4;
      ctx.setLineDash(isNatural ? [] : [3, 4]);
      ctx.beginPath();
      ctx.moveTo(pad.left, y);
      ctx.lineTo(pad.left + plotW, y);
      ctx.stroke();
      ctx.setLineDash([]);
      // Label
      if (isNatural || (midiMax - midiMin) <= 12) {
        ctx.fillStyle = "rgba(167, 179, 209, 0.55)";
        ctx.fillText(midiToNoteName(midi), pad.left - 5, y);
      }
    }

    // Time axis labels
    ctx.textAlign = "center";
    ctx.textBaseline = "top";
    ctx.fillStyle = "rgba(167, 179, 209, 0.55)";
    const nTicks = Math.min(10, Math.ceil(maxTime));
    const tickStep = maxTime / nTicks;
    for (let i = 0; i <= nTicks; i++) {
      const t = i * tickStep;
      const x = timeToX(t);
      ctx.fillText(`${t.toFixed(1)}s`, x, pad.top + plotH + 6);
      ctx.strokeStyle = "rgba(167, 179, 209, 0.08)";
      ctx.lineWidth = 0.5;
      ctx.beginPath();
      ctx.moveTo(x, pad.top);
      ctx.lineTo(x, pad.top + plotH);
      ctx.stroke();
    }

    // Plot pitch points (draw as connected line segments colored by confidence)
    if (voicedFrames.length > 1) {
      const sorted = [...voicedFrames].sort((a, b) => a.time - b.time);
      for (let i = 1; i < sorted.length; i++) {
        const prev = sorted[i - 1];
        const curr = sorted[i];
        // Skip gaps > 0.3s (phrase breaks)
        if (curr.time - prev.time > 0.3) continue;
        const avgConf = (prev.confidence + curr.confidence) / 2;
        ctx.strokeStyle = confidenceColor(avgConf, 0.85);
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(timeToX(prev.time), midiToY(prev.midi));
        ctx.lineTo(timeToX(curr.time), midiToY(curr.midi));
        ctx.stroke();
      }
    }

    // Draw individual points for sparse data
    if (voicedFrames.length > 0 && voicedFrames.length < 200) {
      for (const f of voicedFrames) {
        ctx.fillStyle = confidenceColor(f.confidence, 0.9);
        ctx.beginPath();
        ctx.arc(timeToX(f.time), midiToY(f.midi), 2.5, 0, Math.PI * 2);
        ctx.fill();
      }
    }
  }, [voicedFrames, canvasSize, durationSeconds, midiMin, midiMax, tessituraLow, tessituraHigh]);

  // Shared tooltip hit-test logic for both mouse and touch
  const updateTooltipAtPosition = useCallback(
    (clientX, clientY) => {
      const canvas = canvasRef.current;
      if (!canvas || voicedFrames.length === 0) return;
      const rect = canvas.getBoundingClientRect();
      const mx = clientX - rect.left;
      const my = clientY - rect.top;
      const { width } = canvasSize;
      const pad = { top: 10, right: 16, bottom: 28, left: 48 };
      const plotW = width - pad.left - pad.right;
      const maxTime = durationSeconds > 0 ? durationSeconds : Math.max(...voicedFrames.map((f) => f.time), 1);
      const hoverTime = ((mx - pad.left) / plotW) * maxTime;

      let nearest = null;
      let nearestDist = Infinity;
      for (const f of voicedFrames) {
        const dist = Math.abs(f.time - hoverTime);
        if (dist < nearestDist && dist < 0.15) {
          nearest = f;
          nearestDist = dist;
        }
      }
      if (nearest) {
        setTooltip({
          x: mx,
          y: my,
          note: nearest.note,
          hz: nearest.f0.toFixed(1),
          confidence: (nearest.confidence * 100).toFixed(0),
          time: nearest.time.toFixed(2),
        });
      } else {
        setTooltip(null);
      }
    },
    [voicedFrames, canvasSize, durationSeconds]
  );

  const handleMouseMove = useCallback(
    (e) => updateTooltipAtPosition(e.clientX, e.clientY),
    [updateTooltipAtPosition]
  );

  const handleTouchMove = useCallback(
    (e) => {
      if (e.touches.length > 0) {
        e.preventDefault();
        updateTooltipAtPosition(e.touches[0].clientX, e.touches[0].clientY);
      }
    },
    [updateTooltipAtPosition]
  );

  const handleMouseLeave = useCallback(() => setTooltip(null), []);
  const handleTouchEnd = useCallback(() => setTooltip(null), []);

  if (voicedFrames.length === 0) {
    return null;
  }

  return (
    <section className="results__section results__section--pitch-timeline" aria-label="Pitch timeline">
      <h3 className="results__section-title">Pitch timeline</h3>
      <p className="results__section-copy">
        Your detected pitch over time. Brighter colors mean higher confidence.
        {Number.isFinite(tessituraLow) && " The shaded band shows your comfortable singing range (tessitura)."}
        {" "}Hover or tap for details.
      </p>
      <div ref={containerRef} style={{ position: "relative", width: "100%" }}>
        <canvas
          ref={canvasRef}
          style={{ display: "block", width: "100%", cursor: "crosshair", touchAction: "none" }}
          onMouseMove={handleMouseMove}
          onMouseLeave={handleMouseLeave}
          onTouchStart={handleTouchMove}
          onTouchMove={handleTouchMove}
          onTouchEnd={handleTouchEnd}
          role="img"
          aria-label="Pitch trajectory chart showing detected pitch over time"
        />
        {tooltip && (
          <div
            className="pitch-timeline__tooltip"
            style={{
              position: "absolute",
              left: Math.min(tooltip.x + 12, canvasSize.width - 160),
              top: Math.max(tooltip.y - 48, 4),
              pointerEvents: "none",
            }}
          >
            <strong>{tooltip.note}</strong> — {tooltip.hz} Hz
            <br />
            Confidence: {tooltip.confidence}% · {tooltip.time}s
          </div>
        )}
      </div>
    </section>
  );
}

export default PitchTimeline;
