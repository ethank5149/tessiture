/**
 * RealtimePitchTuner — Mic-in, pitch-on-screen. No backend call required.
 *
 * Uses Web Audio API: getUserMedia → AnalyserNode → autocorrelation pitch
 * detection → Canvas display.  Designed to be the "open every practice
 * session" hook.
 *
 * Algorithm: Chris Wilson's autocorrelation (ACf) — battle-tested for
 * monophonic vocal input, no dependencies.
 */

import { useCallback, useEffect, useRef, useState } from "react";

// ── Constants ──────────────────────────────────────────────────────────────

const NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];
const A4_MIDI = 69;
const A4_HZ = 440;
const BUFFER_SIZE = 2048;

// ── Pitch math ─────────────────────────────────────────────────────────────

function hzToMidi(hz) {
  if (!hz || hz <= 0) return null;
  return 12 * Math.log2(hz / A4_HZ) + A4_MIDI;
}

function noteInfoFromHz(hz) {
  const midi = hzToMidi(hz);
  if (midi === null) return null;
  const rounded = Math.round(midi);
  const pc = ((rounded % 12) + 12) % 12;
  const octave = Math.floor(rounded / 12) - 1;
  const cents = Math.round((midi - rounded) * 100);
  return {
    name: NOTE_NAMES[pc],
    octave,
    full: `${NOTE_NAMES[pc]}${octave}`,
    midi: rounded,
    cents,
    hz,
  };
}

/**
 * Autocorrelation-based pitch detector (adapted from Chris Wilson's PitchDetect).
 * Returns frequency in Hz, or null if no clear pitch is found.
 */
function autoCorrelate(buf, sampleRate) {
  const SIZE = buf.length;
  const MAX_SAMPLES = Math.floor(SIZE / 2);

  // RMS check — skip silence
  let rms = 0;
  for (let i = 0; i < SIZE; i++) rms += buf[i] * buf[i];
  rms = Math.sqrt(rms / SIZE);
  if (rms < 0.008) return null;

  let best_offset = -1;
  let best_correlation = 0;
  let foundGoodCorrelation = false;
  let lastCorrelation = 1;
  const correlations = new Float32Array(MAX_SAMPLES);

  for (let offset = 2; offset < MAX_SAMPLES; offset++) {
    let correlation = 0;
    for (let i = 0; i < MAX_SAMPLES; i++) {
      correlation += Math.abs(buf[i] - buf[i + offset]);
    }
    correlation = 1 - correlation / MAX_SAMPLES;
    correlations[offset] = correlation;

    if (correlation > 0.9 && correlation > lastCorrelation) {
      foundGoodCorrelation = true;
      if (correlation > best_correlation) {
        best_correlation = correlation;
        best_offset = offset;
      }
    } else if (foundGoodCorrelation) {
      // Parabolic interpolation for sub-sample accuracy
      const shift =
        (correlations[best_offset + 1] - correlations[best_offset - 1]) /
        correlations[best_offset];
      return sampleRate / (best_offset + 8 * shift);
    }
    lastCorrelation = correlation;
  }

  if (best_correlation > 0.01) return sampleRate / best_offset;
  return null;
}

// ── Canvas drawing ─────────────────────────────────────────────────────────

/**
 * Draw the tuner display onto a canvas context.
 * noteInfo: { name, octave, cents, hz } | null
 * smoothedHz: exponentially-smoothed frequency (for a stable needle)
 */
function drawTuner(ctx, width, height, noteInfo) {
  ctx.clearRect(0, 0, width, height);

  if (!noteInfo) {
    // Listening state
    ctx.fillStyle = "rgba(167, 179, 209, 0.3)";
    ctx.font = "bold 3rem system-ui, sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText("─ ─ ─", width / 2, height / 2 - 10);
    ctx.font = "0.9rem system-ui, sans-serif";
    ctx.fillStyle = "rgba(167, 179, 209, 0.45)";
    ctx.fillText("sing or play a note", width / 2, height / 2 + 40);
    return;
  }

  const { name, octave, cents, hz } = noteInfo;
  const inTune = Math.abs(cents) <= 8;
  const close = Math.abs(cents) <= 22;
  const noteColor = inTune ? "#4ade80" : close ? "#fbbf24" : "#fb7185";

  // ── Note name (large) ────────────────────────────────────────────────────
  const noteFontSize = Math.min(height * 0.38, 96);
  ctx.font = `bold ${noteFontSize}px system-ui, sans-serif`;
  ctx.textAlign = "center";
  ctx.textBaseline = "alphabetic";
  ctx.fillStyle = noteColor;
  // Slight glow for in-tune feedback
  if (inTune) {
    ctx.shadowColor = noteColor;
    ctx.shadowBlur = 24;
  }
  ctx.fillText(name, width / 2 - 12, height * 0.52);
  ctx.shadowBlur = 0;

  // Octave number (subscript style)
  ctx.font = `bold ${noteFontSize * 0.45}px system-ui, sans-serif`;
  ctx.textBaseline = "alphabetic";
  ctx.fillStyle = noteColor;
  ctx.fillText(String(octave), width / 2 + noteFontSize * 0.38, height * 0.52);

  // ── Hz label ─────────────────────────────────────────────────────────────
  ctx.font = "0.8rem system-ui, sans-serif";
  ctx.textAlign = "center";
  ctx.textBaseline = "top";
  ctx.fillStyle = "rgba(167, 179, 209, 0.6)";
  ctx.fillText(`${hz.toFixed(1)} Hz`, width / 2, height * 0.55);

  // ── Cents meter ───────────────────────────────────────────────────────────
  const meterW = Math.min(width - 96, 380);
  const meterX = (width - meterW) / 2;
  const meterY = height * 0.72;
  const meterH = 10;
  const meterR = meterH / 2;

  // Track background
  ctx.fillStyle = "rgba(39, 53, 87, 0.9)";
  ctx.beginPath();
  ctx.roundRect(meterX, meterY, meterW, meterH, meterR);
  ctx.fill();

  // Center reference mark
  ctx.fillStyle = "rgba(167, 179, 209, 0.5)";
  ctx.fillRect(meterX + meterW / 2 - 1, meterY - 5, 2, meterH + 10);

  // Needle dot
  const clampedCents = Math.max(-50, Math.min(50, cents));
  const needleX = meterX + meterW / 2 + (clampedCents / 50) * (meterW / 2);
  ctx.fillStyle = noteColor;
  ctx.shadowColor = noteColor;
  ctx.shadowBlur = inTune ? 12 : 0;
  ctx.beginPath();
  ctx.arc(
    Math.max(meterX + meterR + 2, Math.min(meterX + meterW - meterR - 2, needleX)),
    meterY + meterH / 2,
    8,
    0,
    Math.PI * 2
  );
  ctx.fill();
  ctx.shadowBlur = 0;

  // Scale labels
  ctx.fillStyle = "rgba(167, 179, 209, 0.45)";
  ctx.font = "0.7rem system-ui, sans-serif";
  ctx.textBaseline = "top";
  ctx.textAlign = "left";
  ctx.fillText("−50¢", meterX, meterY + meterH + 10);
  ctx.textAlign = "center";
  ctx.fillText("0¢", meterX + meterW / 2, meterY + meterH + 10);
  ctx.textAlign = "right";
  ctx.fillText("+50¢", meterX + meterW, meterY + meterH + 10);

  // Cents readout
  ctx.fillStyle = noteColor;
  ctx.font = `bold 0.78rem system-ui, sans-serif`;
  ctx.textAlign = "center";
  ctx.textBaseline = "top";
  ctx.fillText(
    `${cents >= 0 ? "+" : ""}${cents}¢  ${inTune ? "✓ in tune" : close ? "close" : "adjust"}`,
    width / 2,
    meterY + meterH + 28
  );
}

// ── Component ──────────────────────────────────────────────────────────────

function RealtimePitchTuner() {
  const [isActive, setIsActive] = useState(false);
  const [permission, setPermission] = useState("idle"); // 'idle' | 'granted' | 'denied' | 'requesting'
  const [noteInfo, setNoteInfo] = useState(null);
  const [canvasSize, setCanvasSize] = useState({ width: 600, height: 200 });

  const canvasRef = useRef(null);
  const containerRef = useRef(null);
  const audioCtxRef = useRef(null);
  const analyserRef = useRef(null);
  const sourceRef = useRef(null);
  const streamRef = useRef(null);
  const rafRef = useRef(null);
  const bufRef = useRef(null);
  // Exponential smoothing for stable note display
  const smoothHzRef = useRef(null);

  // Responsive canvas
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const w = Math.round(entry.contentRect.width);
        if (w > 80) setCanvasSize({ width: w, height: Math.min(220, Math.max(160, w * 0.32)) });
      }
    });
    observer.observe(container);
    return () => observer.disconnect();
  }, []);

  // Draw loop
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const { width, height } = canvasSize;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = width * dpr;
    canvas.height = height * dpr;
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    drawTuner(ctx, width, height, noteInfo);
  }, [noteInfo, canvasSize]);

  // Audio processing loop
  const startLoop = useCallback(() => {
    const analyser = analyserRef.current;
    if (!analyser) return;

    const buf = bufRef.current;

    const tick = () => {
      analyser.getFloatTimeDomainData(buf);
      const hz = autoCorrelate(buf, analyser.context.sampleRate);

      if (hz !== null && hz > 40 && hz < 2000) {
        // Exponential smoothing (α=0.25 for stability, snappy enough for practice)
        smoothHzRef.current =
          smoothHzRef.current === null
            ? hz
            : smoothHzRef.current * 0.75 + hz * 0.25;
        setNoteInfo(noteInfoFromHz(smoothHzRef.current));
      } else {
        // Decay: keep note visible briefly, then clear
        setNoteInfo((prev) => {
          if (!prev) return null;
          return null;
        });
        smoothHzRef.current = null;
      }

      rafRef.current = requestAnimationFrame(tick);
    };

    rafRef.current = requestAnimationFrame(tick);
  }, []);

  const stopLoop = useCallback(() => {
    if (rafRef.current) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
  }, []);

  const startTuner = useCallback(async () => {
    setPermission("requesting");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false },
      });
      streamRef.current = stream;

      const AudioContext = window.AudioContext || window.webkitAudioContext;
      const ctx = new AudioContext({ sampleRate: 44100 });
      audioCtxRef.current = ctx;

      const analyser = ctx.createAnalyser();
      analyser.fftSize = BUFFER_SIZE;
      analyserRef.current = analyser;
      bufRef.current = new Float32Array(BUFFER_SIZE);

      const source = ctx.createMediaStreamSource(stream);
      source.connect(analyser);
      sourceRef.current = source;

      setPermission("granted");
      setIsActive(true);
      smoothHzRef.current = null;
      startLoop();
    } catch (err) {
      setPermission(err.name === "NotAllowedError" ? "denied" : "error");
    }
  }, [startLoop]);

  const stopTuner = useCallback(() => {
    stopLoop();
    setIsActive(false);
    setNoteInfo(null);
    smoothHzRef.current = null;

    if (sourceRef.current) {
      sourceRef.current.disconnect();
      sourceRef.current = null;
    }
    if (audioCtxRef.current) {
      audioCtxRef.current.close();
      audioCtxRef.current = null;
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
    analyserRef.current = null;
    bufRef.current = null;
  }, [stopLoop]);

  // Clean up on unmount
  useEffect(() => {
    return () => {
      stopTuner();
    };
  }, [stopTuner]);

  return (
    <section className="pitch-tuner" aria-label="Real-time pitch tuner">
      <div className="pitch-tuner__header">
        <div>
          <h2 className="pitch-tuner__title">Pitch Tuner</h2>
          <p className="pitch-tuner__subtitle">
            Sing into your mic and see your note in real time — no analysis needed.
          </p>
        </div>
        <button
          type="button"
          className={`pitch-tuner__toggle button${isActive ? " pitch-tuner__toggle--stop" : ""}`}
          onClick={isActive ? stopTuner : startTuner}
          disabled={permission === "requesting"}
          aria-pressed={isActive}
        >
          {permission === "requesting"
            ? "Requesting mic…"
            : isActive
            ? "Stop"
            : "Start Tuner"}
        </button>
      </div>

      {permission === "denied" && (
        <p className="pitch-tuner__error" role="alert">
          Microphone access was denied. Enable it in your browser settings and try again.
        </p>
      )}

      {permission === "error" && (
        <p className="pitch-tuner__error" role="alert">
          Could not access your microphone. Make sure no other app is using it.
        </p>
      )}

      <div ref={containerRef} className="pitch-tuner__canvas-wrap">
        <canvas
          ref={canvasRef}
          className="pitch-tuner__canvas"
          role="img"
          aria-label={
            noteInfo
              ? `Detected note: ${noteInfo.full}, ${noteInfo.hz.toFixed(1)} Hz, ${noteInfo.cents >= 0 ? "+" : ""}${noteInfo.cents} cents`
              : "Listening for a note"
          }
          aria-live="polite"
          aria-atomic="true"
        />
        {!isActive && permission !== "requesting" && (
          <div className="pitch-tuner__overlay" aria-hidden="true">
            {permission === "idle" ? (
              <p className="pitch-tuner__hint">Press <strong>Start Tuner</strong> to begin</p>
            ) : null}
          </div>
        )}
      </div>

      {isActive && (
        <p className="pitch-tuner__status" role="status" aria-live="polite">
          {noteInfo
            ? `${noteInfo.full} · ${noteInfo.hz.toFixed(1)} Hz · ${noteInfo.cents >= 0 ? "+" : ""}${noteInfo.cents}¢`
            : "Listening…"}
        </p>
      )}
    </section>
  );
}

export default RealtimePitchTuner;
