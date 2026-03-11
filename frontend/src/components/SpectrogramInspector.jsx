import { useCallback, useEffect, useRef, useState } from "react";
import { fetchSpectrogram } from "../api";

// ---------------------------------------------------------------------------
// Colour palette helpers
// ---------------------------------------------------------------------------

/** Viridis-style blue-yellow heat map for the mix layer (0=dark, 255=bright). */
function viridisRgb(t) {
  // Simplified 5-stop viridis approximation
  const stops = [
    [68, 1, 84],
    [59, 82, 139],
    [33, 145, 140],
    [94, 201, 98],
    [253, 231, 37],
  ];
  const scaled = t * (stops.length - 1);
  const lo = Math.floor(scaled);
  const hi = Math.min(lo + 1, stops.length - 1);
  const f = scaled - lo;
  return stops[lo].map((v, i) => Math.round(v + f * (stops[hi][i] - v)));
}

/** Warm red-orange palette for the vocal overlay (0=transparent, 255=bright). */
function warmRgb(t) {
  const stops = [
    [80, 0, 0],
    [180, 40, 0],
    [240, 100, 20],
    [255, 180, 60],
    [255, 240, 120],
  ];
  const scaled = t * (stops.length - 1);
  const lo = Math.floor(scaled);
  const hi = Math.min(lo + 1, stops.length - 1);
  const f = scaled - lo;
  return stops[lo].map((v, i) => Math.round(v + f * (stops[hi][i] - v)));
}

// Pre-build 256-entry LUT for performance
const VIRIDIS_LUT = new Uint8Array(256 * 3);
const WARM_LUT = new Uint8Array(256 * 3);
for (let i = 0; i < 256; i++) {
  const [r1, g1, b1] = viridisRgb(i / 255);
  VIRIDIS_LUT[i * 3] = r1;
  VIRIDIS_LUT[i * 3 + 1] = g1;
  VIRIDIS_LUT[i * 3 + 2] = b1;
  const [r2, g2, b2] = warmRgb(i / 255);
  WARM_LUT[i * 3] = r2;
  WARM_LUT[i * 3 + 1] = g2;
  WARM_LUT[i * 3 + 2] = b2;
}

// ---------------------------------------------------------------------------
// Drawing helpers
// ---------------------------------------------------------------------------

/**
 * Draw a spectrogram layer onto an ImageData buffer using the provided LUT.
 * The uint8 flat array is stored in (n_freq, n_time) row-major order.
 * Canvas y-axis is inverted: frequency[0] (low) => bottom, frequency[n_freq-1] (high) => top.
 */
function paintLayer(imgData, uint8Flat, nFreq, nTime, lut, alpha255) {
  const { width: cw, height: ch } = imgData;
  const data = imgData.data;
  const xScale = cw / nTime;
  const yScale = ch / nFreq;

  for (let fi = 0; fi < nFreq; fi++) {
    const row = uint8Flat.subarray(fi * nTime, (fi + 1) * nTime);
    // fi=0 is lowest frequency -> canvas bottom
    const yCanvas = ch - (fi + 1) * yScale;
    const y0 = Math.max(0, Math.floor(yCanvas));
    const y1 = Math.min(ch, Math.ceil(yCanvas + yScale));

    for (let ti = 0; ti < nTime; ti++) {
      const val = row[ti];
      const lutIdx = val * 3;
      const r = lut[lutIdx];
      const g = lut[lutIdx + 1];
      const b = lut[lutIdx + 2];
      const x0 = Math.max(0, Math.floor(ti * xScale));
      const x1 = Math.min(cw, Math.ceil((ti + 1) * xScale));

      for (let y = y0; y < y1; y++) {
        for (let x = x0; x < x1; x++) {
          const idx = (y * cw + x) * 4;
          if (alpha255 === 255) {
            data[idx] = r;
            data[idx + 1] = g;
            data[idx + 2] = b;
            data[idx + 3] = 255;
          } else {
            // Alpha-blend onto existing content
            const a = alpha255 / 255;
            data[idx] = Math.round(data[idx] * (1 - a) + r * a);
            data[idx + 1] = Math.round(data[idx + 1] * (1 - a) + g * a);
            data[idx + 2] = Math.round(data[idx + 2] * (1 - a) + b * a);
            data[idx + 3] = 255;
          }
        }
      }
    }
  }
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

/**
 * SpectrogramInspector â P2-B, P2-C, P2-D
 *
 * Props:
 *   jobId             â used to fetch /spectrogram/{jobId}
 *   audioRef          â shared React ref pointing to the <audio> element
 *   evidenceEvents    â evidence.events[] from Phase-1 (array of {id, label, timestamp_s})
 *   durationSeconds   â total audio duration for timeline mapping
 *   pitchFrames       â optional pitch_frames[] for P2-D pitch line overlay
 */
export default function SpectrogramInspector({
  jobId,
  audioRef,
  evidenceEvents = [],
  durationSeconds = 0,
  pitchFrames = [],
}) {
  const canvasRef = useRef(null);
  const staticCanvasRef = useRef(null); // off-screen buffer for static layers
  const rafRef = useRef(null);

  const [spectrogramData, setSpectrogramData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [tooltip, setTooltip] = useState(null); // { x, y, label }

  // Fetch on mount (inspector is only mounted when the <details> is opened)
  useEffect(() => {
    if (!jobId) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchSpectrogram(jobId)
      .then((data) => {
        if (!cancelled) {
          setSpectrogramData(data);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err.message || "Failed to load spectrogram.");
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [jobId]);

  // Decode base64 uint8 arrays lazily
  const decodeFrames = useCallback((b64) => {
    const bin = atob(b64);
    const arr = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
    return arr;
  }, []);

  // Draw static layers (mix + vocal + evidence markers + pitch line) to off-screen buffer
  const drawStatic = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas || !spectrogramData) return;

    const cw = canvas.width;
    const ch = canvas.height;

    // ImageData may not be available in JSDOM test environments Ã¢ skip canvas painting
    if (typeof ImageData === "undefined" || cw === 0 || ch === 0) return;

    // Paint into ImageData
    const imgData = new ImageData(cw, ch);

    const mix = spectrogramData.mix;
    if (mix && mix.frames_b64) {
      const mixBytes = decodeFrames(mix.frames_b64);
      paintLayer(imgData, mixBytes, mix.n_freq, mix.n_time, VIRIDIS_LUT, 255);
    }

    const voc = spectrogramData.vocals;
    if (voc && voc.available && voc.frames_b64) {
      const vocBytes = decodeFrames(voc.frames_b64);
      paintLayer(imgData, vocBytes, voc.n_freq, voc.n_time, WARM_LUT, Math.round(0.55 * 255));
    }

    // Store the static frame in an off-screen canvas for fast playhead redraws
    let offscreen = staticCanvasRef.current;
    if (!offscreen) {
      offscreen = document.createElement("canvas");
      staticCanvasRef.current = offscreen;
    }
    offscreen.width = cw;
    offscreen.height = ch;
    const offCtx = offscreen.getContext("2d");
    offCtx.putImageData(imgData, 0, 0);

    // Draw evidence event markers on the off-screen canvas (static)
    if (durationSeconds > 0) {
      evidenceEvents.forEach((ev) => {
        const t = ev.timestamp_s ?? ev.time;
        if (t == null || !Number.isFinite(t)) return;
        const x = Math.round((t / durationSeconds) * cw);
        offCtx.save();
        offCtx.strokeStyle = "rgba(255, 255, 80, 0.75)";
        offCtx.lineWidth = 2;
        offCtx.setLineDash([4, 3]);
        offCtx.beginPath();
        offCtx.moveTo(x, 0);
        offCtx.lineTo(x, ch);
        offCtx.stroke();
        offCtx.restore();
      });
    }

    // P2-D: pitch line overlay from pitch_frames
    if (Array.isArray(pitchFrames) && pitchFrames.length > 0 && mix && mix.frequencies_hz) {
      const freqs = mix.frequencies_hz;
      const fMin = freqs[0];
      const fMax = freqs[freqs.length - 1];
      const logFMin = Math.log(fMin);
      const logFMax = Math.log(fMax);
      offCtx.save();
      offCtx.strokeStyle = "rgba(255, 255, 255, 0.8)";
      offCtx.lineWidth = 1.5;
      offCtx.beginPath();
      let started = false;
      const dur = durationSeconds > 0 ? durationSeconds : (mix.times_s?.[mix.times_s.length - 1] ?? 1);
      pitchFrames.forEach((frame) => {
        const f0 = frame.f0_hz ?? frame.f0;
        const t = frame.time ?? frame.time_s;
        if (!f0 || f0 < fMin || f0 > fMax || t == null) {
          started = false;
          return;
        }
        const x = (t / dur) * cw;
        const logF = Math.log(f0);
        // y: 0 = top = fMax, ch = bottom = fMin
        const y = ch * (1 - (logF - logFMin) / (logFMax - logFMin));
        if (!started) {
          offCtx.moveTo(x, y);
          started = true;
        } else {
          offCtx.lineTo(x, y);
        }
      });
      offCtx.stroke();
      offCtx.restore();
    }
  }, [spectrogramData, evidenceEvents, durationSeconds, pitchFrames, decodeFrames]);

  // Composite static buffer + animated playhead onto the visible canvas
  const drawFrame = useCallback(() => {
    const canvas = canvasRef.current;
    const offscreen = staticCanvasRef.current;
    if (!canvas || !offscreen) return;
    const ctx = canvas.getContext("2d");
    const cw = canvas.width;
    const ch = canvas.height;

    ctx.clearRect(0, 0, cw, ch);
    ctx.drawImage(offscreen, 0, 0);

    // Animated playhead
    if (audioRef && audioRef.current && durationSeconds > 0) {
      const t = audioRef.current.currentTime ?? 0;
      const x = (t / durationSeconds) * cw;
      ctx.save();
      ctx.strokeStyle = "rgba(255, 255, 255, 0.95)";
      ctx.lineWidth = 2;
      ctx.shadowColor = "rgba(0,0,0,0.5)";
      ctx.shadowBlur = 3;
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, ch);
      ctx.stroke();
      ctx.restore();
    }

    rafRef.current = requestAnimationFrame(drawFrame);
  }, [audioRef, durationSeconds]);

  // React to canvas resize: re-compute static layer and canvas dimensions
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !spectrogramData) return;

    // ResizeObserver may not be available in test environments (JSDOM)
    if (typeof ResizeObserver === "undefined") {
      const rect = canvas.getBoundingClientRect();
      canvas.width = rect.width || 800;
      canvas.height = rect.height || 200;
      drawStatic();
      return () => {};
    }
    const ro = new ResizeObserver(() => {
      const rect = canvas.getBoundingClientRect();
      canvas.width = rect.width || 800;
      canvas.height = rect.height || 200;
      drawStatic();
    });
    ro.observe(canvas);

    // Initial draw
    const rect = canvas.getBoundingClientRect();
    canvas.width = rect.width || 800;
    canvas.height = rect.height || 200;
    drawStatic();

    return () => ro.disconnect();
  }, [spectrogramData, drawStatic]);

  // Start/stop RAF loop (requestAnimationFrame may be absent in JSDOM)
  useEffect(() => {
    if (!spectrogramData) return;
    if (typeof requestAnimationFrame === "undefined") return;
    rafRef.current = requestAnimationFrame(drawFrame);
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, [spectrogramData, drawFrame]);

  // Tooltip on mousemove â show nearest evidence event label
  const handleMouseMove = useCallback(
    (e) => {
      if (!spectrogramData || durationSeconds <= 0 || !evidenceEvents.length) return;
      const canvas = canvasRef.current;
      if (!canvas) return;
      const rect = canvas.getBoundingClientRect();
      const mouseX = e.clientX - rect.left;
      const tAtMouse = (mouseX / rect.width) * durationSeconds;

      let closest = null;
      let closestDist = Infinity;
      evidenceEvents.forEach((ev) => {
        const t = ev.timestamp_s ?? ev.time;
        if (t == null) return;
        const dist = Math.abs(t - tAtMouse);
        if (dist < closestDist && dist < durationSeconds * 0.015) {
          closestDist = dist;
          closest = ev;
        }
      });

      if (closest) {
        setTooltip({ x: mouseX, y: e.clientY - rect.top - 28, label: closest.label ?? "Event" });
      } else {
        setTooltip(null);
      }
    },
    [spectrogramData, durationSeconds, evidenceEvents],
  );

  const handleMouseLeave = useCallback(() => setTooltip(null), []);

  // Render
  if (loading) {
    return <div className="spectrogram-inspector__loading" aria-live="polite">Loading spectrogramâ¦</div>;
  }

  if (error) {
    return (
      <div className="spectrogram-inspector__error" role="alert">
        Spectrogram unavailable: {error}
      </div>
    );
  }

  if (!spectrogramData) {
    return null;
  }

  return (
    <div className="spectrogram-inspector">
      <div className="spectrogram-inspector__canvas-wrap">
        <canvas
          ref={canvasRef}
          className="spectrogram-inspector__canvas"
          aria-label="Audio spectrogram inspector"
          role="img"
          onMouseMove={handleMouseMove}
          onMouseLeave={handleMouseLeave}
        />
        {tooltip ? (
          <div
            className="spectrogram-inspector__tooltip"
            style={{ left: tooltip.x, top: tooltip.y }}
            aria-hidden="true"
          >
            {tooltip.label}
          </div>
        ) : null}
      </div>
      {!spectrogramData.vocals?.available ? (
        <p className="spectrogram-inspector__vocals-note">
          Vocal overlay unavailable (Demucs not installed or cache miss).
        </p>
      ) : null}
    </div>
  );
}
