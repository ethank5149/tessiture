# Integration Guide — Breathing Life Into Tessiture

This document tells you exactly how to wire the new components into the existing codebase.

---

## 1. PitchMonitor — Real-Time Pitch Tuner

### New files
- `frontend/src/components/PitchMonitor.jsx` ← the component
- `frontend/src/components/PitchMonitor.css` ← its styles

### Wire into App.jsx

**Step A:** Import at the top of `App.jsx`:
```jsx
import PitchMonitor from "./components/PitchMonitor";
import "./components/PitchMonitor.css";
```

**Step B:** Add a new source card. Find `SOURCE_CARDS` (~line 88) and add:
```jsx
const SOURCE_CARDS = [
  { id: "upload",   emoji: "📁", label: "Upload a File",    desc: "Analyze your own recording" },
  { id: "example",  emoji: "🎵", label: "Example Library",  desc: "Pick a demo track — no upload needed" },
  { id: "live",     emoji: "🎤", label: "Record Live",      desc: "Mic comparison session" },
  { id: "practice", emoji: "🎯", label: "Pitch Monitor",    desc: "See your pitch in real time — the daily practice tool" },
];
```

**Step C:** Handle the new source in `selectSource`. After the existing
`setAnalysisMode(src === "live" ? "compare" : null);` line, add:
```jsx
if (src === "practice") {
  // Practice mode has no analysis mode — it's standalone
  setAnalysisMode(null);
}
```

**Step D:** Render the PitchMonitor. Find the `{/* ── Step 2 */}` region
(around line 494) and add a new branch alongside the upload/example/live blocks:

```jsx
{/* Practice source: standalone pitch monitor, no analysis pipeline */}
{audioSource === "practice" ? (
  <section
    className="step-panel step-panel--visible"
    aria-label="Pitch monitor"
  >
    <PitchMonitor />
  </section>
) : null}
```

That's it — the pitch monitor is fully self-contained. No backend calls, no job polling.

---

## 2. Expanded Song Database

### New files
- `frontend/src/components/songDatabase.js` ← 150+ songs with genre + difficulty
- `frontend/src/components/SongSuggestions.new.jsx` ← replacement component

### Integration
Replace the existing `SongSuggestions.jsx` with `SongSuggestions.new.jsx`:

```bash
mv frontend/src/components/SongSuggestions.jsx frontend/src/components/SongSuggestions.old.jsx
mv frontend/src/components/SongSuggestions.new.jsx frontend/src/components/SongSuggestions.jsx
```

### Additional CSS for filters + difficulty badges

Add to `styles-additions.css`:

```css
/* Song suggestions filters */
.song-suggestions__filters {
  display: flex;
  gap: var(--space-md);
  margin-bottom: var(--space-md);
  flex-wrap: wrap;
}

.song-suggestions__filter {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.song-suggestions__filter-label {
  font-size: 0.75rem;
  color: var(--text-soft);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.song-suggestions__select {
  background: var(--surface-2);
  color: var(--text-primary);
  border: 1px solid var(--border-subtle);
  border-radius: 6px;
  padding: 0.4rem 0.75rem;
  font-size: 0.875rem;
  min-height: var(--touch-min);
  cursor: pointer;
}

.song-suggestions__difficulty {
  font-size: 0.7rem;
  padding: 2px 6px;
  border-radius: 4px;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.song-suggestions__difficulty[data-level="1"] {
  background: rgba(74, 222, 128, 0.15);
  color: #4ade80;
}

.song-suggestions__difficulty[data-level="2"] {
  background: rgba(251, 191, 36, 0.15);
  color: #fbbf24;
}

.song-suggestions__difficulty[data-level="3"] {
  background: rgba(251, 113, 133, 0.15);
  color: #fb7185;
}

.song-suggestions__show-more {
  margin-top: var(--space-sm);
  font-size: 0.875rem;
}

.song-suggestions__empty {
  color: var(--text-muted);
  font-style: italic;
  padding: var(--space-md) 0;
}
```

---

## 3. Audio-Synced PitchTimeline (Quick Enhancement)

This wires the existing `audioRef` so clicking the pitch timeline seeks the audio.

In `AnalysisResults.jsx`, the `audioRef` already exists and there's an audio element further down. The PitchTimeline just needs a small addition.

**In PitchTimeline.jsx**, add an `onSeek` prop and fire it on click:

```jsx
// Add to props:
function PitchTimeline({ pitchFrames = [], durationSeconds = 0, tessituraLow, tessituraHigh, onSeek }) {

// Add click handler (alongside handleMouseMove):
const handleClick = useCallback(
  (e) => {
    if (!onSeek || voicedFrames.length === 0) return;
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const pad = { top: 10, right: 16, bottom: 28, left: 48 };
    const plotW = canvasSize.width - pad.left - pad.right;
    const maxTime = durationSeconds > 0 ? durationSeconds : Math.max(...voicedFrames.map((f) => f.time), 1);
    const clickTime = ((mx - pad.left) / plotW) * maxTime;
    if (clickTime >= 0 && clickTime <= maxTime) {
      onSeek(clickTime);
    }
  },
  [onSeek, voicedFrames, canvasSize, durationSeconds]
);

// On the <canvas> element, add:
onClick={handleClick}
```

**In AnalysisResults.jsx**, when rendering PitchTimeline, add the audio element and handler:

```jsx
{/* Audio playback element — place before PitchTimeline */}
{audioSourceUrl && (
  <audio
    ref={audioRef}
    src={audioSourceUrl}
    preload="metadata"
    className="results__audio"
    controls
  />
)}

{hasPitchFrames && (
  <PitchTimeline
    pitchFrames={pitchFrames}
    durationSeconds={duration ?? 0}
    tessituraLow={tessituraLow}
    tessituraHigh={tessituraHigh}
    onSeek={(time) => {
      if (audioRef.current) {
        audioRef.current.currentTime = time;
        audioRef.current.play().catch(() => {});
      }
    }}
  />
)}
```

Add a bit of CSS for the audio element:
```css
.results__audio {
  width: 100%;
  margin-bottom: var(--space-sm);
  border-radius: 8px;
}
```

---

## Summary of changes

| Change | Files touched | Impact |
|--------|--------------|--------|
| Pitch Monitor | New: PitchMonitor.jsx, PitchMonitor.css. Modified: App.jsx | **Highest** — daily practice hook |
| Song Database | New: songDatabase.js, SongSuggestions.new.jsx | **High** — 6× more songs, filterable |
| Audio-synced timeline | Modified: PitchTimeline.jsx, AnalysisResults.jsx | **Medium** — makes results interactive |

None of these changes touch the backend or the analysis pipeline. They're all frontend-only.
