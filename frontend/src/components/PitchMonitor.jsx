/**
 * PitchMonitor — Real-time pitch tuner using the microphone.
 *
 * This is the "hook" feature that transforms Tessiture from a one-shot
 * report generator into a daily practice companion. Sing into your mic
 * and see your pitch in real time — note name, cents offset, and a
 * scrolling history trail.
 *
 * Pitch detection: simplified YIN autocorrelation (same family as the
 * backend's PYIN estimator, keeping consistency). Runs entirely
 * client-side via Web Audio API — no backend calls needed.
 *
 * Architecture:
 *   getUserMedia → AudioContext → AnalyserNode → YIN → Canvas render
 *   All in a requestAnimationFrame loop; drops to idle when paused.
 */

import { useCallback, useEffect, useRef, useState } from "react";

// ── Constants ──────────────────────────────────────────────────────────────

const NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];
const MIN_F0 = 65;   // C2 — lowest reasonable singing pitch
const MAX_F0 = 1400; // ~F6 — highest reasonable singing pitch
const YIN_THRESHOLD = 0.15;
const HISTORY_SECONDS = 8;
const HISTORY_FPS = 30;
const HISTORY_LENGTH = HISTORY_SECONDS * HISTORY_FPS;

// ── Pitch detection (YIN autocorrelation) ──────────────────────────────────

function yin(buffer, sampleRate) {
  const halfLen = Math.floor(buffer.length / 2);
  const minPeriod = Math.floor(sampleRate / MAX_F0);
  const maxPeriod = Math.min(halfLen, Math.floor(sampleRate / MIN_F0));

  if (maxPeriod <= minPeriod) return null;

  // Step 1-2: Difference function
  const diff = new Float32Array(maxPeriod + 1);
  for (let tau = 1; tau <= maxPeriod; tau++) {
    let sum = 0;
    for (let i = 0; i < halfLen; i++) {
      const d = buffer[i] - buffer[i + tau];
      sum += d * d;
    }
    diff[tau] = sum;
  }

  // Step 3: Cumulative mean normalized difference
  const cmndf = new Float32Array(maxPeriod + 1);
  cmndf[0] = 1;
  let runningSum = 0;
  for (let tau = 1; tau <= maxPeriod; tau++) {
    runningSum += diff[tau];
    cmndf[tau] = runningSum > 0 ? (diff[tau] * tau) / runningSum : 1;
  }

  // Step 4: Absolute threshold — find first dip below threshold
  let bestTau = -1;
  for (let tau = minPeriod; tau <= maxPeriod; tau++) {
    if (cmndf[tau] < YIN_THRESHOLD) {
      // Walk to the local minimum
      while (tau + 1 <= maxPeriod && cmndf[tau + 1] < cmndf[tau]) {
        tau++;
      }
      bestTau = tau;
      break;
    }
  }

  if (bestTau < 0) return null;

  // Step 5: Parabolic interpolation for sub-sample accuracy
  const s0 = bestTau > 0 ? cmndf[bestTau - 1] : cmndf[bestTau];
  const s1 = cmndf[bestTau];
  const s2 = bestTau < maxPeriod ? cmndf[bestTau + 1] : cmndf[bestTau];
  const shift = (s0 - s2) / (2 * (s0 - 2 * s1 + s2) || 1);
  const refinedTau = bestTau + (Number.isFinite(shift) ? shift : 0);

  const frequency = sampleRate / refinedTau;
  if (frequency < MIN_F0 || frequency > MAX_F0) return null;

  // Confidence: 1 - cmndf value (lower cmndf = more periodic = higher confidence)
  const confidence = Math.max(0, Math.min(1, 1 - s1));

  return { frequency, confidence };
}

function hzToMidi(hz) {
  if (!hz || hz <= 0) return null;
  return 69 + 12 * Math.log2(hz / 440);
}

function midiToNoteName(midi) {
  if (!Number.isFinite(midi)) return "—";
  const rounded = Math.round(midi);
  const pc = ((rounded % 12) + 12) % 12;
  const octave = Math.floor(rounded / 12) - 1;
  return `${NOTE_NAMES[pc]}${octave}`;
}

function midiToCents(midi) {
  if (!Number.isFinite(midi)) return 0;
  return Math.round((midi - Math.round(midi)) * 100);
}

// ── Canvas rendering ───────────────────────────────────────────────────────

function drawMonitor(ctx, width, height, current, history, dpr) {
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, width, height);

  const pad = { top: 80, right: 20, bottom: 40, left: 20 };
  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;

  // Background gradient
  const bg = ctx.createLinearGradient(0, 0, 0, height);
  bg.addColorStop(0, "rgba(15, 23, 40, 0.6)");
  bg.addColorStop(1, "rgba(7, 11, 20, 0.8)");
  ctx.fillStyle = bg;
  ctx.fillRect(0, 0, width, height);

  // ── Current note display (top area) ──────────────────────────────────

  if (current) {
    const noteName = midiToNoteName(current.midi);
    const cents = midiToCents(current.midi);
    const centsAbs = Math.abs(cents);

    // Note name — large
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.font = "bold 42px system-ui, -apple-system, sans-serif";
    ctx.fillStyle = centsAbs < 10 ? "#4ade80" : centsAbs < 25 ? "#fbbf24" : "#fb7185";
    ctx.fillText(noteName, width / 2, 38);

    // Cents offset
    ctx.font = "16px system-ui, sans-serif";
    ctx.fillStyle = "rgba(167, 179, 209, 0.8)";
    const centsLabel = cents >= 0 ? `+${cents}¢` : `${cents}¢`;
    ctx.fillText(`${centsLabel}  ·  ${current.frequency.toFixed(1)} Hz`, width / 2, 65);

    // Cents meter bar
    const meterW = Math.min(300, plotW * 0.7);
    const meterH = 6;
    const meterX = (width - meterW) / 2;
    const meterY = pad.top - 8;

    // Background track
    ctx.fillStyle = "rgba(39, 53, 87, 0.5)";
    ctx.beginPath();
    ctx.roundRect(meterX, meterY, meterW, meterH, 3);
    ctx.fill();

    // Center tick
    ctx.fillStyle = "rgba(167, 179, 209, 0.3)";
    ctx.fillRect(meterX + meterW / 2 - 0.5, meterY - 2, 1, meterH + 4);

    // Indicator dot
    const indicatorX = meterX + meterW / 2 + (cents / 50) * (meterW / 2);
    const clampedX = Math.max(meterX + 4, Math.min(meterX + meterW - 4, indicatorX));
    ctx.fillStyle = centsAbs < 10 ? "#4ade80" : centsAbs < 25 ? "#fbbf24" : "#fb7185";
    ctx.beginPath();
    ctx.arc(clampedX, meterY + meterH / 2, 5, 0, Math.PI * 2);
    ctx.fill();

    // Glow
    ctx.shadowColor = ctx.fillStyle;
    ctx.shadowBlur = 10;
    ctx.beginPath();
    ctx.arc(clampedX, meterY + meterH / 2, 3, 0, Math.PI * 2);
    ctx.fill();
    ctx.shadowBlur = 0;
  } else {
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.font = "24px system-ui, -apple-system, sans-serif";
    ctx.fillStyle = "rgba(167, 179, 209, 0.4)";
    ctx.fillText("Sing something…", width / 2, 44);
  }

  // ── Pitch history trail ──────────────────────────────────────────────

  // Compute MIDI range from history
  const voicedHistory = history.filter((h) => h !== null);
  let midiMin = 55;
  let midiMax = 67;
  if (voicedHistory.length > 0) {
    const midis = voicedHistory.map((h) => h.midi);
    midiMin = Math.floor(Math.min(...midis)) - 2;
    midiMax = Math.ceil(Math.max(...midis)) + 2;
    if (midiMax - midiMin < 8) {
      const center = (midiMin + midiMax) / 2;
      midiMin = center - 4;
      midiMax = center + 4;
    }
  }

  const midiToY = (m) => pad.top + plotH - ((m - midiMin) / (midiMax - midiMin)) * plotH;
  const idxToX = (i) => pad.left + (i / (HISTORY_LENGTH - 1)) * plotW;

  // Note guide lines
  ctx.textAlign = "right";
  ctx.textBaseline = "middle";
  ctx.font = "10px system-ui, sans-serif";
  for (let midi = Math.ceil(midiMin); midi <= Math.floor(midiMax); midi++) {
    const pc = ((midi % 12) + 12) % 12;
    const isNatural = [0, 2, 4, 5, 7, 9, 11].includes(pc);
    if (!isNatural && (midiMax - midiMin) > 14) continue;
    const y = midiToY(midi);
    if (y < pad.top || y > pad.top + plotH) continue;

    ctx.strokeStyle = isNatural ? "rgba(167, 179, 209, 0.15)" : "rgba(167, 179, 209, 0.05)";
    ctx.lineWidth = isNatural ? 0.8 : 0.4;
    ctx.setLineDash(isNatural ? [] : [3, 5]);
    ctx.beginPath();
    ctx.moveTo(pad.left, y);
    ctx.lineTo(pad.left + plotW, y);
    ctx.stroke();
    ctx.setLineDash([]);

    if (isNatural || (midiMax - midiMin) <= 10) {
      ctx.fillStyle = "rgba(167, 179, 209, 0.35)";
      ctx.fillText(midiToNoteName(midi), pad.left - 4, y);
    }
  }

  // Draw trail
  if (voicedHistory.length > 1) {
    let prevIdx = -1;
    for (let i = 0; i < history.length; i++) {
      const h = history[i];
      if (!h) {
        prevIdx = -1;
        continue;
      }
      if (prevIdx >= 0 && history[prevIdx]) {
        const age = 1 - i / history.length; // 0 = newest, 1 = oldest
        const alpha = 0.15 + 0.7 * (1 - age);
        const conf = h.confidence;
        const r = Math.round(255 * Math.max(0, 1 - 2 * conf));
        const g = Math.round(255 * Math.min(1, 2 * conf));
        const b = Math.round(100 * conf);
        ctx.strokeStyle = `rgba(${r},${g},${b},${alpha})`;
        ctx.lineWidth = 1.5 + 1.5 * (1 - age);
        ctx.beginPath();
        ctx.moveTo(idxToX(prevIdx), midiToY(history[prevIdx].midi));
        ctx.lineTo(idxToX(i), midiToY(h.midi));
        ctx.stroke();
      }
      prevIdx = i;
    }

    // Current position dot (glow)
    if (current) {
      const x = idxToX(history.length - 1);
      const y = midiToY(current.midi);
      const centsAbs = Math.abs(midiToCents(current.midi));
      const color = centsAbs < 10 ? "#4ade80" : centsAbs < 25 ? "#fbbf24" : "#fb7185";

      ctx.shadowColor = color;
      ctx.shadowBlur = 12;
      ctx.fillStyle = color;
      ctx.beginPath();
      ctx.arc(x, y, 5, 0, Math.PI * 2);
      ctx.fill();
      ctx.shadowBlur = 0;
    }
  }

  // Time label
  ctx.textAlign = "center";
  ctx.textBaseline = "top";
  ctx.font = "10px system-ui, sans-serif";
  ctx.fillStyle = "rgba(167, 179, 209, 0.3)";
  ctx.fillText(`← ${HISTORY_SECONDS}s`, pad.left + 20, pad.top + plotH + 8);
  ctx.fillText("now →", pad.left + plotW - 20, pad.top + plotH + 8);
}

// ── Component ──────────────────────────────────────────────────────────────

function PitchMonitor() {
  const [isListening, setIsListening] = useState(false);
  const [micError, setMicError] = useState(null);
  const [sessionStats, setSessionStats] = useState(null);

  const canvasRef = useRef(null);
  const containerRef = useRef(null);
  const canvasSizeRef = useRef({ width: 600, height: 340 });

  // Audio refs — persisted across renders
  const audioCtxRef = useRef(null);
  const analyserRef = useRef(null);
  const streamRef = useRef(null);
  const rafRef = useRef(null);
  const historyRef = useRef(new Array(HISTORY_LENGTH).fill(null));
  const frameCountRef = useRef(0);
  const currentRef = useRef(null);

  // Session tracking
  const sessionStartRef = useRef(null);
  const sessionNotesRef = useRef([]);

  // Responsive canvas sizing
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const w = Math.round(entry.contentRect.width);
        if (w > 200) {
          canvasSizeRef.current = { width: w, height: 340 };
          const canvas = canvasRef.current;
          if (canvas) {
            const dpr = window.devicePixelRatio || 1;
            canvas.width = w * dpr;
            canvas.height = 340 * dpr;
            canvas.style.width = `${w}px`;
            canvas.style.height = "340px";
          }
        }
      }
    });
    observer.observe(container);
    return () => observer.disconnect();
  }, []);

  // Render loop (runs when listening)
  const renderFrame = useCallback(() => {
    const analyser = analyserRef.current;
    const canvas = canvasRef.current;
    if (!analyser || !canvas) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const bufferLength = analyser.fftSize;
    const buffer = new Float32Array(bufferLength);
    analyser.getFloatTimeDomainData(buffer);

    // Check for signal (avoid detecting silence)
    let rms = 0;
    for (let i = 0; i < bufferLength; i++) rms += buffer[i] * buffer[i];
    rms = Math.sqrt(rms / bufferLength);

    let detected = null;
    if (rms > 0.01) {
      const result = yin(buffer, audioCtxRef.current.sampleRate);
      if (result && result.confidence > 0.5) {
        const midi = hzToMidi(result.frequency);
        detected = {
          frequency: result.frequency,
          confidence: result.confidence,
          midi,
          note: midiToNoteName(midi),
          cents: midiToCents(midi),
        };
      }
    }

    // Update history at fixed FPS
    frameCountRef.current++;
    const framesPerSample = Math.max(1, Math.round(60 / HISTORY_FPS));
    if (frameCountRef.current % framesPerSample === 0) {
      historyRef.current.push(detected);
      if (historyRef.current.length > HISTORY_LENGTH) {
        historyRef.current.shift();
      }
    }

    // Track session notes
    if (detected) {
      sessionNotesRef.current.push(detected.midi);
    }

    currentRef.current = detected;

    const { width, height } = canvasSizeRef.current;
    const dpr = window.devicePixelRatio || 1;
    drawMonitor(ctx, width, height, detected, historyRef.current, dpr);

    rafRef.current = requestAnimationFrame(renderFrame);
  }, []);

  const startListening = useCallback(async () => {
    setMicError(null);
    setSessionStats(null);

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: false,
          noiseSuppression: false,
          autoGainControl: false,
        },
      });

      const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
      const source = audioCtx.createMediaStreamSource(stream);
      const analyser = audioCtx.createAnalyser();
      analyser.fftSize = 4096; // Good resolution for vocal range
      analyser.smoothingTimeConstant = 0;
      source.connect(analyser);

      audioCtxRef.current = audioCtx;
      analyserRef.current = analyser;
      streamRef.current = stream;
      historyRef.current = new Array(HISTORY_LENGTH).fill(null);
      frameCountRef.current = 0;
      sessionStartRef.current = Date.now();
      sessionNotesRef.current = [];

      setIsListening(true);
      rafRef.current = requestAnimationFrame(renderFrame);
    } catch (err) {
      if (err.name === "NotAllowedError") {
        setMicError("Microphone access denied. Check your browser permissions.");
      } else if (err.name === "NotFoundError") {
        setMicError("No microphone found. Connect one and try again.");
      } else {
        setMicError(`Microphone error: ${err.message}`);
      }
    }
  }, [renderFrame]);

  const stopListening = useCallback(() => {
    if (rafRef.current) cancelAnimationFrame(rafRef.current);
    rafRef.current = null;

    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
    if (audioCtxRef.current) {
      audioCtxRef.current.close().catch(() => {});
      audioCtxRef.current = null;
    }
    analyserRef.current = null;

    // Compute session stats
    const notes = sessionNotesRef.current;
    if (notes.length > 10 && sessionStartRef.current) {
      const midiMin = Math.min(...notes);
      const midiMax = Math.max(...notes);
      const durationSec = Math.round((Date.now() - sessionStartRef.current) / 1000);
      setSessionStats({
        low: midiToNoteName(midiMin),
        high: midiToNoteName(midiMax),
        span: Math.round(midiMax - midiMin),
        duration: durationSec,
        samples: notes.length,
      });
    }

    setIsListening(false);
    currentRef.current = null;
  }, []);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      if (streamRef.current) streamRef.current.getTracks().forEach((t) => t.stop());
      if (audioCtxRef.current) audioCtxRef.current.close().catch(() => {});
    };
  }, []);

  // Draw idle state when not listening
  useEffect(() => {
    if (isListening) return;
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const { width, height } = canvasSizeRef.current;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = width * dpr;
    canvas.height = height * dpr;
    drawMonitor(ctx, width, height, null, new Array(HISTORY_LENGTH).fill(null), dpr);
  }, [isListening]);

  return (
    <section className="pitch-monitor" aria-label="Real-time pitch monitor">
      <div className="pitch-monitor__header">
        <h3 className="pitch-monitor__title">Pitch Monitor</h3>
        <p className="pitch-monitor__subtitle">
          Sing into your microphone and see your pitch in real time.
          Green means you're on-pitch, yellow is slightly off, red means adjust.
        </p>
      </div>

      <div ref={containerRef} className="pitch-monitor__canvas-wrap">
        <canvas
          ref={canvasRef}
          className="pitch-monitor__canvas"
          role="img"
          aria-label={
            isListening
              ? `Real-time pitch display. ${currentRef.current ? `Current note: ${currentRef.current.note}` : "Waiting for voice…"}`
              : "Pitch monitor — press Start to begin"
          }
        />
      </div>

      <div className="pitch-monitor__controls">
        {!isListening ? (
          <button
            type="button"
            className="button button--primary pitch-monitor__start"
            onClick={startListening}
          >
            🎤 Start listening
          </button>
        ) : (
          <button
            type="button"
            className="button pitch-monitor__stop"
            onClick={stopListening}
          >
            ⏹ Stop
          </button>
        )}
        {micError && (
          <p className="pitch-monitor__error" role="alert">{micError}</p>
        )}
      </div>

      {sessionStats && !isListening && (
        <div className="pitch-monitor__session-summary">
          <h4>Session summary</h4>
          <div className="pitch-monitor__session-stats">
            <div className="pitch-monitor__stat">
              <span className="pitch-monitor__stat-value">{sessionStats.low} – {sessionStats.high}</span>
              <span className="pitch-monitor__stat-label">Range used</span>
            </div>
            <div className="pitch-monitor__stat">
              <span className="pitch-monitor__stat-value">{sessionStats.span} semitones</span>
              <span className="pitch-monitor__stat-label">Span</span>
            </div>
            <div className="pitch-monitor__stat">
              <span className="pitch-monitor__stat-value">{sessionStats.duration}s</span>
              <span className="pitch-monitor__stat-label">Duration</span>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}

export default PitchMonitor;
