# Tessiture — Comprehensive Project Review

**Reviewed:** April 2026  
**Scope:** Full stack — backend DSP, API, frontend, UX, architecture, deployment

---

## Executive Summary

Tessiture has a **strong analytical engine and a weak delivery layer**. The backend is genuinely impressive — PYIN pitch estimation, Viterbi-smoothed key detection, LPC formants, Monte Carlo calibration, BCa bootstrap CIs, Demucs vocal separation. This is graduate-level DSP work. The problem is that none of this reaches the user in a way that feels alive or useful. The frontend is a functional but lifeless wizard that dumps analysis results into collapsible `<details>` sections. A vocal hobbyist uploads a recording, waits, gets a wall of data, and has no reason to come back.

The gap between what the backend *can do* and what the user *experiences* is the core issue. Fixing it doesn't require rewriting the analysis pipeline — it requires rethinking how the results are presented, making the app feel interactive rather than report-like, and giving users a reason to return.

---

## What's Working Well

### Backend / DSP (★★★★☆)
- **Analysis pipeline is comprehensive.** 5,400+ lines across pitch, chords, tessitura, vibrato, formants, phrase segmentation, comparison, and calibration. This is the project's real asset.
- **Statistical rigor is unusual for a hobbyist tool.** BCa bootstrap confidence intervals, Monte Carlo uncertainty quantification, inferential statistics with null hypothesis presets — this is publishable-quality methodology.
- **Vocal separation via Demucs** is a killer feature. Most hobbyist tools require isolated vocals; Tessiture can extract them.
- **Code quality is solid.** Clean module boundaries, type hints, docstrings, testable pure functions. The refactor into `api/analysis_core.py`, `api/stats.py`, `api/pitch_utils.py`, etc. was well executed.

### Deployment / CI (★★★★☆)
- The Makefile + semver + Forgejo Actions pipeline is mature. Auto-bumping from conventional commits, `.release-version` as single source of truth, health check verification — this is production-grade.
- Documentation is thorough (DEPLOYMENT.md, ARCHITECTURE.md, MATHEMATICAL_FOUNDATIONS.md).

### Frontend Components (★★★☆☆)
- **VocalProfileCard** is the best component in the app. It translates raw analysis into identity ("You're a Tenor — same voice type as Freddie Mercury"). This is exactly what a beginner wants.
- **SongSuggestions** is the right idea — making range data actionable.
- **WarmUpRoutine** is genuinely useful and well-designed pedagogically.
- Accessibility fundamentals are present: skip links, ARIA labels, `role="status"`, live regions.

---

## What Needs Work

### 1. The App Feels Like a Report Generator, Not a Practice Tool (Critical)

The core UX loop is: upload → wait → read results → leave. There's no reason to come back. A vocal hobbyist app needs a **practice loop**: sing → get feedback → see progress → try again.

**What's missing:**
- **No real-time pitch monitor.** The single most requested feature in vocal apps. "Sing into your mic and see your pitch on screen." The WebSocket infrastructure exists for live comparison, but there's no simple "pitch tuner" mode.
- **No session-over-session progress tracking.** SessionHistory uses localStorage but there's no "your range expanded by 3 semitones over the last month" view.
- **No guided practice mode.** WarmUpRoutine tells you *what* to do but doesn't listen to you *doing it*. Imagine: "Sing this note → [mic listens] → 'Great, you hit it within 8 cents!'"
- **No audio playback synced to analysis.** The pitch timeline shows data but you can't click a point and hear what was happening at that moment. The `audioRef` exists but isn't wired up.

### 2. Frontend Architecture Is a Monolith (High)

`App.jsx` is 708 lines with ~20 `useState` hooks managing a state machine manually. This makes iteration painful:

- **No routing.** Can't bookmark results, can't share a link, back button doesn't work. This is table stakes for a web app.
- **No state management.** The two-axis state machine (`audioSource` × `analysisMode`) is clever but fragile. Adding a new mode (e.g., "practice") means threading more state through the top level.
- **700-line render function** with deeply nested ternaries. Hard to reason about what renders when.

**Recommendation:** Introduce React Router (even just hash routing for the single-container deploy). Extract the state machine into a reducer or Zustand store. Break App.jsx into route-level page components.

### 3. Visual Design Is Functional but Forgettable (High)

The dark theme with `--brand: #60a5fa` (blue) on `--bg-canvas: #070b14` (near-black) is clean but generic. 2,500+ lines of hand-rolled CSS with no design system.

**Specific issues:**
- **No visual hierarchy in results.** VocalProfileCard, SummaryMetrics, PitchTimeline, and coaching sections all have the same visual weight. The most important insight (your voice type + range) should dominate the viewport.
- **The "step wizard" pattern doesn't spark joy.** Three emoji cards ("📁 Upload a File", "🎵 Example Library", "🎤 Record Live") feel utilitarian. The first impression should make someone want to try it.
- **No micro-interactions or transitions.** Results appear instantly. Panels toggle instantly. There's no sense of the app *working* or *responding* to you.
- **Mobile experience is an afterthought.** Safe-area-inset CSS exists but the component density and touch targets aren't mobile-first.

### 4. Bundle Size Is Bloated (Medium)

- `plotly.js-dist-min` is ~3.5MB minified. It's used for the spectrogram inspector and a few charts. For what Tessiture needs, Recharts (~400KB) or even raw Canvas/SVG would be 10× lighter.
- `axios` is unnecessary — `fetch` is sufficient and already used in some places.
- `jsmediatags` is pulled in for example track metadata but could be extracted server-side.

### 5. The Song Database Is Too Small (Medium)

25 hardcoded songs in `SongSuggestions.jsx`. This is the feature that makes range data *meaningful* to a beginner, but with only 25 entries, many users will get 2-3 suggestions max. This needs to be 200+ songs across genres, decades, and difficulty levels — and ideally filterable.

### 6. The Example Gallery Has No Examples (Medium)

`ExampleGallery` fetches from `/api/examples` but there's no `examples/` directory with actual audio files in the repo. A first-time user clicking "Example Library" will see an empty gallery or an error. The "no upload needed" promise is broken unless the deployer manually provisions example tracks.

### 7. Live Comparison Is Comparison-Only (Medium)

The "Record Live" source forces `analysisMode = "compare"`. But most people who want to use their mic don't want to compare against a reference — they want to see their pitch in real time, or do a full analysis of a live recording. The current flow forces them through reference track selection, which is a dead end if they just want to sing and see what happens.

---

## Prioritized Action Plan

### Phase 1: Make It Feel Alive (2-3 weeks)

1. **Add a real-time pitch monitor.** Simple canvas component: mic input → Web Audio API → autocorrelation or `AnalyserNode` → render pitch on a staff or piano roll. No backend needed. This becomes the "hook" that makes people open the app.

2. **Wire up audio playback to pitch timeline.** Click/scrub the PitchTimeline and hear the corresponding audio. Use the existing `audioRef` and `audioSourceUrl`.

3. **Add page transitions and micro-interactions.** Fade-in for results sections. Animated confidence badge. Smooth expand/collapse for `<details>`. The VocalProfileCard should animate in like it matters.

4. **Bundle a few example tracks.** Even 3-4 Creative Commons vocal recordings (e.g., from Musopen or Free Music Archive) would make the Example Library functional out of the box.

### Phase 2: Make It a Practice Tool (3-4 weeks)

5. **Guided warm-up mode.** WarmUpRoutine + mic input. The app plays a target note, listens to the user, and gives feedback ("You're 15 cents flat — try again"). Uses the same pitch estimation the backend uses, but running client-side via Web Audio.

6. **Progress dashboard.** Store analysis summaries (range, stability score, voice type) in localStorage or IndexedDB. Show a timeline chart: "March: D3–G4, April: C#3–A4 — your range grew!"

7. **Expand song database to 150+ entries.** Add difficulty rating, genre tags, and a search/filter UI.

8. **Add a "just sing" mic mode.** Record from mic → run full analysis (same as upload path, but skip the file picker). The current live mode should be renamed "Sing Along" and the new mode should be "Quick Record."

### Phase 3: Architecture Cleanup (2 weeks, parallelizable)

9. **Introduce React Router.** `/` (landing), `/analyze/:jobId` (results), `/practice` (pitch monitor + warm-up), `/progress` (dashboard). Results become shareable URLs.

10. **Extract state into Zustand or useReducer.** Kill the 20-hook state machine in App.jsx.

11. **Replace Plotly with Recharts or raw Canvas.** Save ~3MB in bundle size.

12. **Drop axios for fetch.** Minor but removes a dependency.

---

## Closing Thought

The analytical engine behind Tessiture is genuinely excellent — better than most commercial vocal analysis tools. The bottleneck isn't capability, it's delivery. A vocal hobbyist doesn't care about BCa bootstrap intervals; they care about "am I getting better?" and "what should I sing?" The components that bridge this gap (VocalProfileCard, SongSuggestions, WarmUpRoutine) are the right instincts — they just need to be the *entire* experience, not buried under technical layers.

The single highest-impact change is the real-time pitch monitor. It transforms Tessiture from "a tool you use once" into "a tool you open every time you practice." Everything else builds on that foundation.
