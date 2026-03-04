# Tessiture — Architecture & Technical Reference

**Last updated:** 2026-03-04

This document is the authoritative technical reference for the Tessiture vocal analysis toolkit. It describes every component of the system as implemented, including the analysis pipeline, calibration system, comparison pipeline, frontend, and deployment architecture.

For mathematical proofs and derivations, see [MATHEMATICAL_FOUNDATIONS.md](MATHEMATICAL_FOUNDATIONS.md).
For API endpoints and configuration, see [API_REFERENCE.md](API_REFERENCE.md).
For deployment instructions, see [DEPLOYMENT.md](DEPLOYMENT.md).

---

## Table of Contents

1. [What Tessiture Is](#1-what-tessiture-is)
2. [Use Cases](#2-use-cases)
3. [System Architecture](#3-system-architecture)
4. [Analysis Pipeline](#4-analysis-pipeline)
5. [Calibration System](#5-calibration-system)
6. [Reference Track Comparison](#6-reference-track-comparison)
7. [Reporting & Export](#7-reporting--export)
8. [API Layer](#8-api-layer)
9. [Frontend](#9-frontend)
10. [Technology Stack](#10-technology-stack)
11. [Design Decisions & Constraints](#11-design-decisions--constraints)

---

## 1. What Tessiture Is

Tessiture is a browser-based vocal and acoustic analysis toolkit that extracts musical and voice features from audio recordings with statistically quantified uncertainty. It is a self-hosted web application comprising a Python/FastAPI backend, a React/Vite frontend, and a Docker-based deployment pipeline targeting Unraid NAS servers.

The name derives from "tessitura" — the vocal range in which a singer is most comfortable — which reflects the application's core mission: understanding and measuring the human voice.

**Production URL:** `https://tess.indecisivephysicist.space`

---

## 2. Use Cases

### Use Case 1: Upload & Analyze

A user uploads an audio file (WAV, MP3, FLAC, M4A, Opus). The backend processes it through a multi-stage DSP pipeline and returns a comprehensive analysis report including pitch trajectories, chord/key detection, tessitura metrics, vibrato characteristics, formant estimates, and uncertainty quantification. Results are available as interactive JSON, downloadable CSV, or formatted PDF.

### Use Case 2: Live Reference Comparison

A singer compares their live voice to a reference track in real time. The browser captures microphone audio via WebAudio API and streams raw PCM Float32 chunks over a WebSocket to the backend. The server returns per-chunk pitch deviation feedback and running session metrics. When the session ends, a full post-session comparison report is generated covering pitch accuracy, rhythm alignment, range coverage, and tessitura offset.

**Target users:** Vocalists practicing intonation, voice teachers assessing students, music producers evaluating takes, and anyone curious about the acoustic properties of a recording.

---

## 3. System Architecture

### High-Level Data Flow

```
Audio Upload / Mic Stream
  → Preprocessing (resample, mono, normalize)
  → [Optional] Vocal Separation (Demucs htdemucs)
  → STFT + Frequency Uncertainty
  → Harmonic Peak Detection
  → Pitch Estimation (HPS + Autocorrelation + Salience)
  → Viterbi Path Optimization
  → MIDI Conversion + Uncertainty Propagation
  → Chord Detection (template matching + softmax)
  → Key Detection (Krumhansl-Schmuckler correlation)
  → Tessitura Analysis (weighted PDF, comfort band, strain zones)
  → Advanced Features (vibrato, formants, phrase segmentation)
  → Bootstrap Inferential Statistics
  → Report Generation (JSON / CSV / PDF)
```

### Runtime Components

| Component | Technology | Location |
|-----------|-----------|----------|
| API server | FastAPI + Uvicorn | `api/` |
| Job execution | In-memory async job manager | `api/job_manager.py` |
| Analysis modules | NumPy, SciPy, librosa | `analysis/`, `calibration/` |
| Reporting | ReportLab, Matplotlib, Plotly | `reporting/` |
| Frontend | React + Vite | `frontend/` |
| Deployment | Docker, docker-compose | `deploy/unraid/` |

---

## 4. Analysis Pipeline

### 4.1 Audio Preprocessing

**Module:** `analysis/dsp/preprocessing.py`

1. **Float conversion** — Integer PCM samples are normalized to float32 [-1, 1].
2. **Mono downmix** — Multi-channel audio is averaged to mono with a channel-count heuristic (channels-first only when dim0 < dim1 and dim0 ≤ 8).
3. **Optional pre-emphasis** — First-order high-pass filter `y[n] = x[n] - α·x[n-1]` to compensate for the ~12 dB/octave glottal spectral roll-off. Disabled by default (α=0); 0.97 is the standard speech processing value.
4. **Resampling** — Polyphase resampling via `scipy.signal.resample_poly()` to 44,100 Hz target. Fallback: Hamming-windowed sinc lowpass + linear interpolation.
5. **Peak normalization** — Scale to 0.99 peak amplitude.

### 4.2 STFT

**Module:** `analysis/dsp/stft.py`

- **Window:** Hann (periodic), 4096 samples (~93 ms at 44.1 kHz).
- **Hop:** 512 samples (~11.6 ms).
- **Frequency resolution:** ~10.8 Hz per bin.
- **Frequency uncertainty:** `σ_f = Δf/√12` (uniform bin quantization model) — a conservative upper bound since parabolic interpolation in peak detection reduces this by 10–20×.
- **Window energy normalization** coefficient is computed and carried forward for proper magnitude scaling.

### 4.3 Harmonic Peak Detection

**Module:** `analysis/dsp/peak_detection.py`

For each STFT frame:

1. Find spectral peaks above –40 dB relative threshold using **parabolic (quadratic) interpolation** for sub-bin frequency accuracy (Smith, "Spectral Audio Signal Processing", 2011).
2. For each candidate fundamental, match detected peaks to harmonic targets (h=1..4) within a configurable tolerance (default 50 cents).
3. Score each candidate using a **glottal source model** weighting: `score = Σ(w_h · A_h) / Σ(w_h)` where `w_h = 1/h²`, reflecting that vocal harmonic energy naturally falls as 1/h².
4. Return top 6 candidates per frame, ranked by score.

### 4.4 Pitch Estimation

**Module:** `analysis/pitch/estimator.py`

Multi-method pitch estimation combining three complementary approaches:

1. **Harmonic Product Spectrum (HPS)** — Multiplies the spectrum at integer decimation rates (h=2..4) to reinforce harmonically related peaks (Schroeder, 1968).
2. **Autocorrelation** — Time-domain fundamental frequency estimation in the 80–1200 Hz range.
3. **Spectral prominence** — Ratio of energy around the candidate f0 to the mean spectral energy.

A **composite salience score** is computed per candidate:

```
S(f₀, t) = w_H · H_score + w_C · C_score + w_S · S_score
```

Default weights: H=0.474, C=0.263, S=0.263 (normalized to sum to 1).

**Voicing detection** thresholds: salience ≥ 0.15, f0 between 60–1600 Hz.

### 4.5 Viterbi Path Optimization

**Module:** `analysis/pitch/path_optimizer.py`

A **dynamic programming (Viterbi-like) algorithm** selects the optimal pitch trajectory across all frames, balancing local salience against temporal continuity:

```
E_path = Σ_t S(f_t, t) - λ · Σ_t |log₂(f_t / f_{t-1})|
```

- **Jump penalty** λ = 0.4 (log-frequency space ensures octave jumps are penalized proportionally).
- **Onset/offset penalties** (0.1) model voiced/unvoiced transitions.
- Backtracing recovers the globally optimal path.

**Scientific basis:** Viterbi (1967), adapted for pitch tracking as in pYIN (Mauch & Dixon, 2014).

### 4.6 MIDI Conversion + Uncertainty Propagation

**Module:** `analysis/pitch/midi_converter.py`

- **Frequency → MIDI:** `m = 69 + 12 · log₂(f / 440)` (standard equal temperament).
- **Uncertainty propagation** via first-order Taylor expansion: `σ_m = (12/ln 2) · (σ_f / f₀) = 17.312 · (σ_f / f₀)`.
- **Calibration integration:** Optional calibration hook provides frequency-dependent `(bias_hz, sigma_cal_hz)`. Analytic and calibration uncertainties are combined in **quadrature**: `σ_total = √(σ_analytic² + σ_cal²)`.
- **Cents deviation:** Computed relative to nearest MIDI integer using floor-based rounding (avoids Python banker's rounding at ±50-cent boundaries).

### 4.7 Chord Detection

**Module:** `analysis/chords/detector.py`

1. Build a 12-bin pitch-class probability distribution from active notes.
2. Match against chord templates (major, minor, diminished, augmented, dominant 7th, etc.).
3. Convert match scores to probabilities via **softmax**: `P(C_i) = exp(β · score_i) / Σ_j exp(β · score_j)` (β = inverse temperature).
4. Temporal smoothing via Viterbi with configurable self-transition bias.

### 4.8 Key Detection

**Module:** `analysis/chords/key_detector.py`

- **Algorithm:** Krumhansl-Schmuckler key-finding method.
- Build a pitch-class histogram from detected notes/chords.
- Correlate with **Krumhansl-Kessler tonal profiles** (1982): 24 profiles (12 major + 12 minor), each circularly shifted.
- **Pearson correlation** between histogram and each profile: `r = (h · P_r) / (||h|| · ||P_r||)`.
- Probabilities via softmax; **confidence via normalized Shannon entropy**: `confidence = 1 - H(P) / log(24)`.
- Key smoothing across time for stability.

### 4.9 Tessitura Analysis

**Module:** `analysis/tessitura/analyzer.py`

The tessitura module computes a weighted statistical profile of pitch usage:

- **Weighted mean (comfort center):** `μ = Σ(w_i · m_i) / Σ(w_i)` — weights combine note duration and detection confidence.
- **Weighted variance (distribution spread):** `σ²_spread = Σ(w_i · (m_i - μ)²) / Σ(w_i)`.
- **Mean variance (estimation uncertainty):** `σ²_mean = Σ(w_i² · σ_i²) / (Σw_i)²` — this is the uncertainty in the center estimate itself, distinct from the distribution spread.
- **Tessitura band:** Weighted percentile range (default 15th–85th percentile).
- **Comfort band:** Smallest contiguous pitch range encompassing 70% of weighted observations.
- **Strain zones:** Regions below/above the comfort band, plus a "high variance" zone if σ > 1.5 semitones.
- **Optional weighted PDF:** Histogram-based density estimate for visualization.

### 4.10 Advanced Voice Features

**Vibrato Detection** (`analysis/advanced/vibrato.py`):

- Extract the longest voiced segment from the f0 trajectory.
- Compute pitch deviation in cents from the segment's moving-average reference.
- Apply FFT to the deviation signal and find the spectral peak in the 3–8 Hz band (physiological vibrato range).
- Report vibrato rate (Hz), depth (cents, single-sided), peak power, and power ratio.

**Formant Estimation** (`analysis/advanced/formants.py`):

- Compute smoothed spectral envelope per frame.
- Detect F1, F2, F3 peaks within physiological formant bands using parabolic peak interpolation.
- Per-formant bandwidth estimation (–3 dB width) and band-confidence scoring.
- Returns time-aligned formant trajectories.

**Phrase Segmentation** (`analysis/advanced/phrase_segmentation.py`):

- Energy-based boundary detection using short-time RMS energy.
- Smoothing via median and moving-average filters.
- Identifies phrase onsets/offsets where energy dips below a configurable dB threshold.
- Reports boundaries with timestamps and confidence scores.

### 4.11 Vocal Source Separation

**Module:** `analysis/dsp/vocal_separation.py`

- Uses **Demucs htdemucs** (hybrid transformer) deep learning model for source separation.
- Thread-safe singleton model loading with lazy initialization.
- SHA-256 file-content caching to avoid re-separating identical files.
- GPU acceleration when CUDA is available; falls back to CPU.
- Extracts the vocal stem to improve pitch tracking accuracy on polyphonic recordings.

### 4.12 Bootstrap Inferential Statistics

For each key metric (f0 mean, f0 min, f0 max, tessitura center, pitch error mean):

1. **Resample with replacement** B=1000 times from voiced frames.
2. Compute the metric reducer on each bootstrap replicate.
3. **Percentile confidence interval:** `CI = [Q_{α/2}, Q_{1-α/2}]` at 95% confidence.
4. **Two-sided bootstrap p-value** against preset-dependent null hypotheses using tail-doubling: `p = min(1, 2 · min(p_left, p_right))`.
5. Three **inferential presets** (casual, intermediate, vocalist) define different null values representing expected performance levels.

---

## 5. Calibration System

The calibration subsystem establishes empirical transfer functions for the analysis engine.

### 5.1 Reference Dataset Generation

**Location:** `calibration/reference_generation/`

- **Latin Hypercube Sampling** (McKay et al., 1979) across the parameter space: f0 (82–2093 Hz, E2–C7), detuning (±50 cents), amplitude (–20 to 0 dBFS), harmonic ratios, note count (1–4), duration, SNR (20–60 dB), vibrato depth/rate.
- **Synthetic signal generation** with known ground truth: multi-harmonic tones with configurable vibrato, detuning, and additive Gaussian noise at specified SNR.
- Uses `pyDOE2` for LHS sampling.

### 5.2 Monte Carlo Uncertainty Quantification

**Location:** `calibration/monte_carlo/`

- N=100–500 realizations per sample with systematic perturbations (Gaussian noise, window misalignment, phase jitter, amplitude drift, resampling error).
- Produces frequency-dependent **pitch bias corrections** `b(f)`, **pitch variance bounds**, **confidence surfaces**, and **detection probability maps**.

### 5.3 Calibration Model Fitting

**Location:** `calibration/models/`

- Pitch bias correction: `f_corrected = f_raw - b(f)`.
- Uncertainty lookup tables indexed by frequency.
- Confidence interpolants for runtime scoring.

---

## 6. Reference Track Comparison

### 6.1 Real-Time WebSocket Streaming

**Module:** `api/streaming.py`

- Client connects to `WS /compare/live?reference_id=<id>`.
- Audio: raw PCM Float32 LE, 44,100 Hz mono.
- Control messages: `playback_sync` (timestamp alignment), `session_end`.
- Server responses: `session_start`, `chunk_feedback` (per-chunk pitch deviation), `running_summary` (every 10 chunks), `session_report` (on end).

### 6.2 Comparison Modules

**Location:** `analysis/comparison/`

| Module | Purpose |
|--------|---------|
| `pitch_comparison.py` | Per-frame pitch deviation in cents, accuracy ratio (% within ±50 cents), systematic bias (signed mean), stability (std dev) |
| `rhythm_comparison.py` | Note event matching; onset timing error (ms), note hit rate |
| `range_comparison.py` | Fraction of reference pitch range voiced by user; tessitura center offset in semitones |
| `formant_comparison.py` | Timbre similarity (offline only) |
| `alignment.py` | DTW-based time alignment with interpolation for reference-to-user mapping |
| `reference_cache.py` | SHA-256 keyed pre-analyzed reference tracks |
| `session_report.py` | Aggregates all comparison metrics into a serializable report |

### 6.3 Comparison Metrics

| Metric | Description |
|--------|-------------|
| **Pitch deviation (cents)** | Real-time offset between sung pitch and reference. Negative = flat, positive = sharp. |
| **Pitch accuracy ratio** | Fraction of voiced frames within ±50 cents of the reference pitch. |
| **Pitch bias (cents)** | Systematic tendency to sing sharp or flat (signed mean deviation). |
| **Pitch stability (cents)** | Consistency of voiced pitch (standard deviation of frame deviations). |
| **Note hit rate** | Fraction of reference note events successfully matched. |
| **Onset timing error (ms)** | Average how early or late notes are sung relative to reference onsets. |
| **Range coverage** | Fraction of the reference track's pitch range that was voiced. |
| **Tessitura center offset** | Difference in semitones between user's comfort zone center and reference's pitch demand center. |

---

## 7. Reporting & Export

**Location:** `reporting/`

| Format | Generator | Description |
|--------|-----------|-------------|
| JSON | `json_generator.py` | Full structured payload with all metrics, frame-level data, uncertainty |
| CSV | `csv_generator.py` | Tabular export of frame data and summary metrics |
| PDF | `pdf_composer.py` | Formatted report with embedded visualizations (via ReportLab) |

**Visualization helpers** (`reporting/visualization.py`):

- `plot_pitch_curve()` — F0 trajectory with confidence bands
- `plot_piano_roll()` — Note events on a MIDI grid
- `plot_tessitura_heatmap()` — Weighted pitch density
- `plot_chord_timeline()` — Chord progression over time
- `plot_key_stability()` — Key confidence across time

Uses both Matplotlib (for PDF embedding) and Plotly (for interactive JSON).

---

## 8. API Layer

See [API_REFERENCE.md](API_REFERENCE.md) for full endpoint documentation.

### Summary

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/analyze` | POST | Upload audio → creates async job |
| `/status/{job_id}` | GET | Poll job state with progress % |
| `/results/{job_id}` | GET | Retrieve results as JSON, CSV, or PDF |
| `/examples` | GET | List available example tracks |
| `/examples/{id}/analyze` | POST | Analyze an example track |
| `/compare/references` | GET | List available reference tracks |
| `/compare/live` | WS | WebSocket for real-time comparison |

### Job Manager

**Module:** `api/job_manager.py`

- **In-memory async job manager** (non-persistent — jobs are lost on restart).
- Jobs run as `asyncio.Task` instances.
- Progress callback allows the analysis pipeline to report incremental status.
- States: `queued` → `processing` → `completed` | `failed`.

---

## 9. Frontend

**Location:** `frontend/`

### Application Shell

React SPA (`frontend/src/App.jsx`) with two-axis navigation:

- **Source selection:** Upload a file, pick from example library, or record live.
- **Mode:** Analyze (full offline analysis) or Compare (live reference comparison).

### Key Components

| Component | File | Purpose |
|-----------|------|---------|
| `AudioUploader` | `components/AudioUploader.jsx` | Drag-and-drop file upload with validation |
| `AnalysisStatus` | `components/AnalysisStatus.jsx` | Progress bar during async analysis |
| `AnalysisResults` | `components/AnalysisResults.jsx` | Full results display: summary, pitch, chords, keys, tessitura, advanced features, inferential statistics |
| `ExampleGallery` | `components/ExampleGallery.jsx` | Browseable demo track library with thumbnails |
| `ReferenceTrackSelector` | `components/ReferenceTrackSelector.jsx` | Pick a reference for comparison |
| `LiveComparisonView` | `components/LiveComparisonView.jsx` | Real-time pitch deviation meter and running metrics |
| `ComparisonResults` | `components/ComparisonResults.jsx` | Post-session comparison report display |
| `PitchCurve` | `components/PitchCurve.jsx` | SVG pitch trajectory visualization |
| `PianoRoll` | `components/PianoRoll.jsx` | SVG note event grid |
| `TessituraHeatmap` | `components/TessituraHeatmap.jsx` | SVG pitch density heatmap |
| `ReportExporter` | `components/ReportExporter.jsx` | Download buttons for CSV/PDF |
| `ComparisonMetricsPanel` | `components/ComparisonMetricsPanel.jsx` | Formatted comparison metrics table |

### Custom Hooks

| Hook | File | Purpose |
|------|------|---------|
| `useComparisonWebSocket` | `hooks/useComparisonWebSocket.js` | WebSocket lifecycle, sends audio chunks, receives feedback/summaries/reports |
| `useMicrophoneCapture` | `hooks/useMicrophoneCapture.js` | Browser mic capture via `getUserMedia` + `ScriptProcessorNode`, Float32 PCM at 44.1 kHz |
| `useExampleThumbnail` | `hooks/useExampleThumbnail.js` | Waveform thumbnail previews for example tracks |

### API Client

**Module:** `frontend/src/api.js`

- Normalizes response shapes so components rely on stable fields.
- Handles status polling, result fetching, file downloading, and error extraction.
- Builds URLs from `VITE_API_BASE_URL` environment variable.

---

## 10. Technology Stack

| Layer | Technology | Version |
|-------|-----------|---------|
| Backend runtime | Python | 3.12 |
| Web framework | FastAPI + Uvicorn | 0.115.8 / 0.34.0 |
| Numerical | NumPy, SciPy | 1.26.4, 1.12.0 |
| Audio I/O | librosa, soundfile, mutagen | 0.10.2 |
| Deep learning | PyTorch, Demucs | 2.2.2, 4.0.1 |
| Statistics | pyDOE2 (LHS) | 1.3.0 |
| PDF generation | ReportLab | 4.2.5 |
| Plotting | Matplotlib, Plotly | 3.8.4, 5.24.1 |
| Frontend framework | React (hooks) | — |
| Build tool | Vite | — |
| Deployment | Docker, docker-compose | — |
| Reverse proxy | Caddy (LAN), Cloudflare Tunnel (internet) | — |

---

## 11. Design Decisions & Constraints

1. **Western 12-TET only** — All pitch math assumes equal temperament. Non-Western tuning systems are not supported.
2. **In-memory jobs** — Jobs are non-persistent; a server restart loses all in-flight and completed jobs.
3. **Headphones required for comparison** — Playing the reference without headphones causes microphone bleed that degrades pitch tracking.
4. **Formant comparison unavailable in streaming** — Only pitch/rhythm/range are computed in real-time; formant analysis requires offline processing.
5. **Single-singer assumption** — The pipeline is optimized for monophonic vocal content; polyphonic separation is available via Demucs but adds latency.
6. **Conservative uncertainty** — The system prefers overestimating uncertainty (via upper-bound σ_f) over underestimating it.
7. **No ML pitch detection** — Pitch estimation uses classical DSP methods (HPS, autocorrelation, harmonic matching) rather than neural networks, keeping the pipeline interpretable and the uncertainty model analytically tractable.
