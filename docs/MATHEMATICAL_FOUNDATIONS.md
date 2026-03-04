# Mathematical Foundations of Tessiture

**Last updated:** 2026-03-04

This document provides complete mathematical derivations, proofs, and citations for every formula used in the Tessiture analysis system. Each section includes the problem statement, step-by-step derivation, numerical validation, and original references.

For how these formulas are implemented in code, see [ARCHITECTURE.md](ARCHITECTURE.md).

---

## Table of Contents

1. [Frequency to MIDI Conversion](#1-frequency-to-midi-conversion)
2. [MIDI Uncertainty Propagation](#2-midi-uncertainty-propagation)
3. [Weighted Mean and Variance](#3-weighted-mean-and-variance)
4. [Softmax Probability Distribution](#4-softmax-probability-distribution)
5. [Entropy-Based Confidence](#5-entropy-based-confidence)
6. [Viterbi Path Optimization](#6-viterbi-path-optimization)
7. [Correlation Coefficient for Key Detection](#7-correlation-coefficient-for-key-detection)
8. [Bootstrap Inferential Statistics](#8-bootstrap-inferential-statistics)
9. [Harmonic Salience Function](#9-harmonic-salience-function)
10. [STFT Frequency Uncertainty](#10-stft-frequency-uncertainty)
11. [Bibliography](#11-bibliography)

---

## 1. Frequency to MIDI Conversion

### Problem Statement

Convert a frequency `f` (in Hz) to a MIDI note number `m`.

### Background

- MIDI note 69 corresponds to A4 = 440 Hz
- Each semitone is a frequency ratio of 2^(1/12) (equal temperament)
- MIDI numbers are logarithmically spaced

### Derivation

**Step 1:** Express frequency ratio

```
f / 440 = 2^((m - 69)/12)
```

**Step 2:** Take logarithm base 2 of both sides

```
log₂(f / 440) = (m - 69) / 12
```

**Step 3:** Solve for m

```
12 · log₂(f / 440) = m - 69
m = 69 + 12 · log₂(f / 440)
```

**Alternative form using natural logarithm:**

```
m = 69 + 12 · ln(f / 440) / ln(2)
```

### Validation

**Test 1:** A4 (440 Hz)

```
m = 69 + 12 · log₂(440 / 440) = 69 + 12 · 0 = 69 ✓
```

**Test 2:** A5 (880 Hz, one octave up)

```
m = 69 + 12 · log₂(880 / 440) = 69 + 12 · 1 = 81 ✓
```

**Test 3:** C4 (261.63 Hz)

```
m = 69 + 12 · log₂(261.63 / 440) = 69 + 12 · (-0.7492) = 60.01 ≈ 60 ✓
```

**References:** MIDI Manufacturers Association (1996); Benson (2006)

---

## 2. MIDI Uncertainty Propagation

### Problem Statement

Given frequency `f₀` with uncertainty `σ_f`, derive the uncertainty `σ_m` in MIDI note number.

### Background

- Error propagation uses first-order Taylor expansion
- For function y = g(x), uncertainty is σ_y ≈ |dg/dx| · σ_x

### Derivation

**Step 1:** Start with MIDI formula

```
m = 69 + 12 · ln(f₀ / 440) / ln(2)
```

**Step 2:** Simplify

```
m = 69 + (12 / ln(2)) · ln(f₀ / 440)
m = 69 + (12 / ln(2)) · (ln(f₀) - ln(440))
```

**Step 3:** Compute partial derivative with respect to f₀

```
∂m/∂f₀ = (12 / ln(2)) · (1 / f₀)
∂m/∂f₀ = 12 / (ln(2) · f₀)
```

**Step 4:** Apply first-order error propagation

```
σ_m ≈ |∂m/∂f₀| · σ_f
σ_m = (12 / (ln(2) · f₀)) · σ_f
σ_m = (12 / ln(2)) · (σ_f / f₀)
```

**Step 5:** Numerical constant

```
12 / ln(2) = 12 / 0.6931 = 17.312
σ_m = 17.312 · (σ_f / f₀)
```

### Validation

**Test 1:** A4 (440 Hz) with σ_f = 1 Hz

```
σ_m = 17.312 · (1 / 440) = 0.0393 semitones = 3.93 cents ✓
```

**Test 2:** C4 (261.63 Hz) with σ_f = 1 Hz

```
σ_m = 17.312 · (1 / 261.63) = 0.0662 semitones = 6.62 cents ✓
```

**Observation:** Lower frequencies have larger MIDI uncertainty for the same Hz uncertainty.

### Conversion to Cents

```
cents = semitones · 100
σ_cents = σ_m · 100 = 1731.2 · (σ_f / f₀)
```

**References:** Taylor (1997); Bevington & Robinson (2003)

---

## 3. Weighted Mean and Variance

### Problem Statement

Given N measurements `m_i` with weights `w_i` and individual uncertainties `σ_i`, compute:
1. Weighted mean `μ`
2. Uncertainty in the mean `σ_mean`
3. Weighted variance of the distribution `σ²_spread`

### 3.1 Weighted Mean

**Formula:**

```
μ = Σ(w_i · m_i) / Σ(w_i)
```

**Derivation:** Minimize weighted squared deviations

```
Minimize: S = Σ w_i · (m_i - μ)²
∂S/∂μ = -2 · Σ w_i · (m_i - μ) = 0
Σ w_i · m_i = μ · Σ w_i
μ = Σ(w_i · m_i) / Σ(w_i)
```

### 3.2 Uncertainty in Weighted Mean

**Formula:**

```
σ²_mean = Σ(w_i² · σ_i²) / (Σ w_i)²
```

**Derivation:** Error propagation for weighted sum

```
μ = Σ(w_i · m_i) / W    where W = Σ w_i

∂μ/∂m_i = w_i / W

σ²_mean = Σ (∂μ/∂m_i)² · σ_i²
σ²_mean = Σ (w_i / W)² · σ_i²
σ²_mean = (1 / W²) · Σ(w_i² · σ_i²)
σ²_mean = Σ(w_i² · σ_i²) / (Σ w_i)²
```

**Note:** This formula is exact when weights are fixed constants. If weights were inverse-variance optimal (w_i ∝ 1/σ_i²), use 1/Σ(1/σ_i²) instead.

### 3.3 Weighted Variance (Spread)

**Formula:**

```
σ²_spread = Σ(w_i · (m_i - μ)²) / Σ(w_i)
```

**Derivation:** Weighted second moment about the mean

```
Variance = E[(X - μ)²]

For weighted distribution:
σ²_spread = Σ w_i · (m_i - μ)² / Σ w_i
```

**Alternative (unbiased estimator):**

```
σ²_unbiased = Σ(w_i · (m_i - μ)²) / (Σ w_i - Σ(w_i²) / Σ w_i)
```

### Clarification: Two Distinct Quantities

The tessitura module computes **both** quantities:

1. **σ²_mean** (uncertainty in the center estimate) — How precisely can we locate the tessitura center? Depends on measurement uncertainties σ_i.
2. **σ²_spread** (weighted variance of the distribution) — How wide is the singer's pitch usage? Depends on the spread of pitch values m_i.

These are fundamentally different: σ²_mean shrinks with more data, while σ²_spread characterizes the distribution itself.

### Example: Tessitura Calculation

**Given:** 5 pitch measurements

```
m = [60, 62, 64, 65, 67]  (MIDI notes)
w = [0.3, 0.2, 0.25, 0.15, 0.1]  (duration weights)
σ = [0.02, 0.03, 0.02, 0.04, 0.03]  (uncertainties in semitones)
```

**Weighted Mean:**

```
μ = (0.3·60 + 0.2·62 + 0.25·64 + 0.15·65 + 0.1·67) / (0.3 + 0.2 + 0.25 + 0.15 + 0.1)
μ = (18 + 12.4 + 16 + 9.75 + 6.7) / 1.0
μ = 62.85 (approximately D4)
```

**Uncertainty in Mean:**

```
σ²_mean = (0.3²·0.02² + 0.2²·0.03² + 0.25²·0.02² + 0.15²·0.04² + 0.1²·0.03²) / 1.0²
σ²_mean = (0.000036 + 0.000036 + 0.000025 + 0.000036 + 0.000009) / 1.0
σ²_mean = 0.000142
σ_mean = 0.012 semitones = 1.2 cents
```

**Weighted Variance:**

```
σ²_spread = (0.3·(60-62.85)² + 0.2·(62-62.85)² + 0.25·(64-62.85)² + 0.15·(65-62.85)² + 0.1·(67-62.85)²) / 1.0
σ²_spread = (0.3·8.12 + 0.2·0.72 + 0.25·1.32 + 0.15·4.62 + 0.1·17.22) / 1.0
σ²_spread = (2.436 + 0.144 + 0.330 + 0.693 + 1.722) / 1.0
σ²_spread = 5.325
σ_spread = 2.31 semitones
```

**Interpretation:**
- Tessitura center: D4 (MIDI 62.85) ± 1.2 cents
- Tessitura spread: ±2.31 semitones (comfortable range)

**References:** Gatz & Smith (1995); Cochran (1977)

---

## 4. Softmax Probability Distribution

### Problem Statement

Convert raw scores `s_i` to probabilities `P_i` that sum to 1.

### Background

- Softmax ensures probabilities are positive and normalized
- Temperature parameter `β` controls sharpness of distribution

### Derivation

**Step 1:** Exponential transformation (ensures positivity)

```
z_i = exp(β · s_i)
```

**Step 2:** Normalization (ensures sum to 1)

```
P_i = z_i / Σ_j z_j
P_i = exp(β · s_i) / Σ_j exp(β · s_j)
```

### Properties

**Property 1:** Probabilities sum to 1

```
Σ_i P_i = Σ_i (exp(β · s_i) / Z) = (1/Z) · Σ_i exp(β · s_i) = Z / Z = 1 ✓
```

**Property 2:** Temperature effect

```
β → ∞: P_i → 1 for max(s_i), 0 otherwise (deterministic)
β → 0: P_i → 1/N for all i (uniform)
```

**Property 3:** Invariance to constant shift

```
P_i(s + c) = exp(β · (s_i + c)) / Σ_j exp(β · (s_j + c))
           = exp(β · c) · exp(β · s_i) / (exp(β · c) · Σ_j exp(β · s_j))
           = exp(β · s_i) / Σ_j exp(β · s_j)
           = P_i(s) ✓
```

### Example: Chord Probabilities

**Given:** Chord matching scores

```
s_major = 0.95
s_minor = 0.12
s_dim = 0.03
β = 1.0
```

**Computation:**

```
z_major = exp(1.0 · 0.95) = 2.586
z_minor = exp(1.0 · 0.12) = 1.127
z_dim = exp(1.0 · 0.03) = 1.030
Z = 2.586 + 1.127 + 1.030 = 4.743

P_major = 2.586 / 4.743 = 0.545
P_minor = 1.127 / 4.743 = 0.238
P_dim = 1.030 / 4.743 = 0.217
```

**Verification:** 0.545 + 0.238 + 0.217 = 1.000 ✓

**References:** Bishop (2006)

---

## 5. Entropy-Based Confidence

### Problem Statement

Quantify confidence in a probability distribution using Shannon entropy.

### Background

- Entropy measures uncertainty in a distribution
- Maximum entropy = maximum uncertainty (uniform distribution)
- Minimum entropy = minimum uncertainty (deterministic)

### Derivation

**Step 1:** Shannon entropy

```
H(P) = -Σ_i P_i · log(P_i)
```

**Step 2:** Maximum entropy for N outcomes

```
H_max = log(N)    (achieved when P_i = 1/N for all i)
```

**Step 3:** Normalized confidence

```
confidence = 1 - H(P) / H_max
confidence = 1 - H(P) / log(N)
```

### Properties

**Property 1:** Range [0, 1]

```
H(P) ∈ [0, log(N)]
confidence ∈ [0, 1]
```

**Property 2:** Deterministic distribution (one P_i = 1)

```
H(P) = -1 · log(1) = 0
confidence = 1 - 0 / log(N) = 1 ✓
```

**Property 3:** Uniform distribution (all P_i = 1/N)

```
H(P) = -N · (1/N) · log(1/N) = log(N)
confidence = 1 - log(N) / log(N) = 0 ✓
```

### Example: Key Detection Confidence

**Given:** Key probabilities (24 possible keys)

```
P(C major) = 0.94
P(A minor) = 0.04
P(others) = 0.02 / 22 ≈ 0.0009 each
```

**Entropy Calculation:**

```
H(P) = -0.94 · log(0.94) - 0.04 · log(0.04) - 22 · 0.0009 · log(0.0009)
H(P) = -0.94 · (-0.062) - 0.04 · (-3.219) - 22 · 0.0009 · (-7.013)
H(P) = 0.058 + 0.129 + 0.139
H(P) = 0.326
```

**Confidence:**

```
H_max = log(24) = 3.178
confidence = 1 - 0.326 / 3.178 = 1 - 0.103 = 0.897 ≈ 90%
```

**Interpretation:** High confidence (90%) indicates strong certainty in C major detection.

**References:** Shannon (1948); Cover & Thomas (2006)

---

## 6. Viterbi Path Optimization

### Problem Statement

Find the optimal sequence of states that maximizes a score function with continuity penalty.

### Background

- Dynamic programming algorithm
- Balances local salience with temporal smoothness
- Used for pitch tracking and key detection

### Formulation

**Objective:**

```
Maximize: E_path = Σ_t S(f_t, t) - λ · Σ_t |f_t - f_{t-1}|
```

Where:
- `S(f_t, t)` = salience score for frequency `f_t` at time `t`
- `λ` = continuity penalty weight
- `|f_t - f_{t-1}|` = transition cost (frequency jump)

### Algorithm

**Step 1:** Initialize DP table

```
cost[0, f] = S(f, 0)    for all frequencies f
```

**Step 2:** Forward pass (compute optimal costs)

```
For t = 1 to T-1:
    For each frequency f:
        cost[t, f] = S(f, t) + max_{f'} (cost[t-1, f'] - λ · |f - f'|)
        backpointer[t, f] = argmax_{f'} (cost[t-1, f'] - λ · |f - f'|)
```

**Step 3:** Backward pass (reconstruct path)

```
path[T-1] = argmax_f cost[T-1, f]
For t = T-2 down to 0:
    path[t] = backpointer[t+1, path[t+1]]
```

### Complexity

- Time: O(T · F²) where T = time frames, F = frequency bins
- Space: O(T · F)

### Example: Pitch Tracking

**Given:** 3 time frames, 4 frequency candidates

```
Salience matrix S:
       f1   f2   f3   f4
t=0: [0.8, 0.3, 0.2, 0.1]
t=1: [0.7, 0.9, 0.3, 0.2]
t=2: [0.6, 0.8, 0.9, 0.3]

λ = 0.5
Frequency distances: |f_i - f_j| = |i - j|
```

**Forward Pass:**

*t=0:*

```
cost[0, :] = [0.8, 0.3, 0.2, 0.1]
```

*t=1:*

```
cost[1, f1] = 0.7 + max(0.8-0.5·0, 0.3-0.5·1, 0.2-0.5·2, 0.1-0.5·3)
            = 0.7 + max(0.8, -0.2, -0.3, -1.4) = 0.7 + 0.8 = 1.5
backpointer[1, f1] = f1

cost[1, f2] = 0.9 + max(0.8-0.5·1, 0.3-0.5·0, 0.2-0.5·1, 0.1-0.5·2)
            = 0.9 + max(0.3, 0.3, -0.3, -0.9) = 0.9 + 0.3 = 1.2
backpointer[1, f2] = f1 or f2 (tie, choose f2)

cost[1, f3] = 0.3 + max(0.8-0.5·2, 0.3-0.5·1, 0.2-0.5·0, 0.1-0.5·1)
            = 0.3 + max(-0.2, -0.2, 0.2, -0.4) = 0.3 + 0.2 = 0.5
backpointer[1, f3] = f3

cost[1, f4] = 0.2 + max(0.8-0.5·3, 0.3-0.5·2, 0.2-0.5·1, 0.1-0.5·0)
            = 0.2 + max(-0.7, -0.7, -0.3, 0.1) = 0.2 + 0.1 = 0.3
backpointer[1, f4] = f4
```

*t=2:*

```
cost[2, f1] = 0.6 + max(1.5-0.5·0, 1.2-0.5·1, 0.5-0.5·2, 0.3-0.5·3)
            = 0.6 + max(1.5, 0.7, -0.5, -1.2) = 0.6 + 1.5 = 2.1
backpointer[2, f1] = f1

cost[2, f2] = 0.8 + max(1.5-0.5·1, 1.2-0.5·0, 0.5-0.5·1, 0.3-0.5·2)
            = 0.8 + max(1.0, 1.2, 0.0, -0.7) = 0.8 + 1.2 = 2.0
backpointer[2, f2] = f2

cost[2, f3] = 0.9 + max(1.5-0.5·2, 1.2-0.5·1, 0.5-0.5·0, 0.3-0.5·1)
            = 0.9 + max(0.5, 0.7, 0.5, -0.2) = 0.9 + 0.7 = 1.6
backpointer[2, f3] = f2

cost[2, f4] = 0.3 + max(1.5-0.5·3, 1.2-0.5·2, 0.5-0.5·1, 0.3-0.5·0)
            = 0.3 + max(0.0, 0.2, 0.0, 0.3) = 0.3 + 0.3 = 0.6
backpointer[2, f4] = f4
```

**Backward Pass:**

```
path[2] = argmax(2.1, 2.0, 1.6, 0.6) = f1
path[1] = backpointer[2, f1] = f1
path[0] = backpointer[1, f1] = f1

Optimal path: [f1, f1, f1]
Total score: 2.1
```

**Interpretation:** Despite f3 having highest salience at t=2 (0.9), the algorithm chooses f1 for continuity.

**References:** Viterbi (1967); Mauch & Dixon (2014)

---

## 7. Correlation Coefficient for Key Detection

### Problem Statement

Measure similarity between two vectors (e.g., pitch class histogram and tonal profile).

### Background

- Pearson correlation coefficient
- Range: [-1, 1] where 1 = perfect positive correlation
- Used in Krumhansl-Schmuckler key detection

### Derivation

**Step 1:** Dot product (unnormalized correlation)

```
h · P = Σ_i h_i · P_i
```

**Step 2:** Normalize by magnitudes

```
r = (h · P) / (||h|| · ||P||)
```

Where:

```
||h|| = sqrt(Σ_i h_i²)
||P|| = sqrt(Σ_i P_i²)
```

### Properties

**Property 1:** Range [-1, 1]

```
By Cauchy-Schwarz inequality: |h · P| ≤ ||h|| · ||P||
Therefore: -1 ≤ r ≤ 1
```

**Property 2:** Perfect correlation

```
If h = c · P for some constant c > 0:
r = (c · P · P) / (||c · P|| · ||P||)
r = (c · ||P||²) / (c · ||P|| · ||P||)
r = 1 ✓
```

**Property 3:** Orthogonal vectors

```
If h · P = 0:
r = 0 / (||h|| · ||P||) = 0 ✓
```

### Example: Key Detection

**Given:**

```
h = [0.25, 0.00, 0.12, 0.00, 0.18, 0.15, 0.00, 0.20, 0.00, 0.08, 0.00, 0.02]  (pitch class histogram)
P = [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]  (C major profile)
```

**Dot Product:**

```
h · P = 0.25·6.35 + 0.12·3.48 + 0.18·4.38 + 0.15·4.09 + 0.20·5.19 + 0.08·3.66 + 0.02·2.88
h · P = 1.588 + 0.418 + 0.788 + 0.614 + 1.038 + 0.293 + 0.058
h · P = 4.797
```

**Magnitudes:**

```
||h|| = 0.423
||P|| = 12.83
```

**Correlation:**

```
r = 4.797 / (0.423 · 12.83)
r = 4.797 / 5.427
r = 0.884
```

**Interpretation:** Strong positive correlation (0.884) indicates the pitch class distribution matches the C major profile well.

**References:** Krumhansl & Kessler (1982); Temperley (1999)

---

## 8. Bootstrap Inferential Statistics

### 8.1 Setup and Notation

For a metric-specific sample vector:

```
x_m = (x_1, x_2, ..., x_n)
```

let the metric reducer be `T_m(·)`, and define the point estimate:

```
θ̂_m = T_m(x_m)
```

The implemented reducers are:

| Metric | Reducer |
|--------|---------|
| `f0_mean_hz` | `mean(x)` on voiced F0 values (Hz) |
| `f0_min_hz` | `min(x)` on voiced F0 values (Hz) |
| `f0_max_hz` | `max(x)` on voiced F0 values (Hz) |
| `tessitura_center_midi` | `mean(x)` on voiced MIDI values |
| `pitch_error_mean_cents` | `mean(x)` on per-frame pitch error values (cents) |

Bootstrap replicates are generated by sampling with replacement:

```
for b = 1, 2, ..., B:
    x_m*(b) = sample_with_replacement(x_m, size=n)
    θ̂_m*(b) = T_m(x_m*(b))
```

Implementation defaults:
- `B = max(200, TESSITURE_BOOTSTRAP_SAMPLES)` (default 1000)
- Confidence level `c = clip(TESSITURE_BOOTSTRAP_CONFIDENCE_LEVEL, 0.5, 0.999)` (default 0.95)
- Non-finite values are removed before inference
- If `n = 0`: all outputs are `null`
- If `n = 1`: bootstrap distribution is degenerate, CI low = high = estimate

### 8.2 Percentile Confidence Interval

Let confidence level be `c = 1 - α`. For a two-sided percentile interval:

```
CI_(1-α) = [Q_(α/2)(θ̂_m*), Q_(1-α/2)(θ̂_m*)]
```

where `Q_p` denotes the `p`-quantile of `{θ̂_m*(1), ..., θ̂_m*(B)}`.

At the default level `c = 0.95`:

```
α = 0.05
CI_0.95 = [Q_0.025, Q_0.975]
```

### 8.3 Two-Sided Bootstrap p-Value

For each metric, define null hypothesis:

```
H0,m: θ_m = θ0,m
```

where `θ0,m` is selected from the active inferential preset.

Given bootstrap replicates `{θ̂_m*(b)}`, compute empirical tail probabilities:

```
p_left  = (1/B) · Σ I(θ̂_m*(b) ≤ θ0,m)
p_right = (1/B) · Σ I(θ̂_m*(b) ≥ θ0,m)
```

Then form the two-sided bootstrap p-value:

```
p_m = min(1, 2 · min(p_left, p_right))
```

This is the tail-doubling rule with clipping to [0, 1].

### 8.4 Null Hypotheses by Preset

| Metric | Casual | Intermediate | Vocalist |
|--------|-------:|-------------:|---------:|
| `f0_mean_hz` | 196.0 | 220.0 | 246.94 |
| `f0_min_hz` | 130.81 | 130.81 | 146.83 |
| `f0_max_hz` | 440.0 | 523.25 | 659.25 |
| `tessitura_center_midi` | 57.0 | 60.0 | 64.0 |
| `pitch_error_mean_cents` | 0.0 | 0.0 | 0.0 |

Changing preset changes null-hypothesis values and therefore p-values, but does **not** change observed estimates or bootstrap CI construction.

### 8.5 Interpretation

- **Estimate** is the observed sample statistic.
- **Confidence interval** summarizes sampling uncertainty under bootstrap resampling; narrower intervals imply more stable estimates.
- **p-value** quantifies how extreme the preset null value is relative to the bootstrap distribution.
- Metrics are interpreted independently; no multiple-testing correction is applied.
- For small `n_samples`, especially extrema metrics (`f0_min_hz`, `f0_max_hz`), inferential outputs can be unstable.

**References:** Efron & Tibshirani (1993)

---

## 9. Harmonic Salience Function

### Formulation

```
S(f₀, t) = w_H · H_norm + w_C · C + w_S · S_p
where w_H + w_C + w_S = 1 (normalized weights)
```

| Component | Description | Default Weight |
|-----------|-------------|---------------|
| H_norm | Harmonic matching score (glottal model weighted) | 0.474 |
| C | Continuity score (log-frequency distance to previous frame) | 0.263 |
| S_p | Spectral prominence (local-to-global energy ratio) | 0.263 |

### Harmonic Matching Score

For a candidate f0 with matched harmonics at h=1..N:

```
H_norm = Σ(w_h · A_h) / Σ(w_h)
where w_h = 1/h²
```

The 1/h² weighting reflects the glottal source model: vocal harmonic energy naturally falls as 1/h².

### Continuity Score

```
C = exp(-4 · octave_residual)
where octave_residual = |log₂(f_curr/f_prev) - round(log₂(f_curr/f_prev))|
```

This penalizes non-octave deviations strongly while allowing octave jumps with light penalty.

**References:** Salamon & Gómez (2012); Goto (2001)

---

## 10. STFT Frequency Uncertainty

### Bin Quantization Model

For an FFT of size N at sample rate fs, the bin spacing is:

```
Δf = fs / N
```

Assuming the true frequency is uniformly distributed within a bin, the standard deviation is:

```
σ_f = Δf / √12
```

This is the standard result for a uniform distribution on interval [0, Δf].

### Numerical Example

At fs = 44100 Hz, N = 4096:

```
Δf = 44100 / 4096 = 10.77 Hz
σ_f = 10.77 / √12 = 3.11 Hz
```

**Note:** This is a conservative upper bound. Parabolic peak interpolation (used in the peak detection module) reduces the effective frequency error by approximately 10–20×.

### Uncertainty Combination

When both analytic (bin quantization) and calibration uncertainties are available, they are combined in quadrature:

```
σ_total = √(σ_analytic² + σ_calibration²)
```

This assumes the two error sources are independent, which is justified because bin quantization is a property of the DFT while calibration uncertainty is an empirical measurement of the full pipeline.

**References:** Harris (1978); Oppenheim & Schafer (2009); Smith (2011)

---

## 11. Bibliography

### Foundational Music Theory

- Benson, D. (2006). *Music: A Mathematical Offering*, Cambridge University Press.
- Krumhansl, C.L. & Kessler, E.J. (1982). "Tracing the Dynamic Changes in Perceived Tonal Organization in a Spatial Representation of Musical Keys", *Psychological Review*, 89(4), 334–368.
- MIDI Manufacturers Association (1996). *MIDI 1.0 Detailed Specification*.
- Temperley, D. (1999). "What's Key for Key? The Krumhansl-Schmuckler Key-Finding Algorithm Reconsidered", *Music Perception*, 17(1), 65–100.

### Pitch Detection & Analysis

- Boersma, P. (1993). "Accurate Short-Term Analysis of the Fundamental Frequency and the Harmonics-to-Noise Ratio of a Sampled Sound", *Proceedings of the Institute of Phonetic Sciences*, 17, 97–110.
- de Cheveigné, A. & Kawahara, H. (2002). "YIN, a Fundamental Frequency Estimator for Speech and Music", *Journal of the Acoustical Society of America*, 111(4), 1917–1930.
- Mauch, M. & Dixon, S. (2014). "pYIN: A Fundamental Frequency Estimator Using Probabilistic Threshold Distributions", *ICASSP*, 659–663.
- Salamon, J. & Gómez, E. (2012). "Melody Extraction from Polyphonic Music Signals using Pitch Contour Characteristics", *IEEE Transactions on Audio, Speech, and Language Processing*.
- Schroeder, M.R. (1968). "Period Histogram and Product Spectrum: New Methods for Fundamental-Frequency Measurement", *Journal of the Acoustical Society of America*.

### Chord & Key Detection

- Harte, C., Sandler, M. & Gasser, M. (2006). "Detecting Harmonic Change in Musical Audio", *ACM Workshop on Audio and Music Computing Multimedia*, 21–26.
- Mauch, M. & Dixon, S. (2010). "Simultaneous Estimation of Chords and Musical Context from Audio", *IEEE Transactions on Audio, Speech, and Language Processing*, 18(6), 1280–1289.
- Rabiner, L.R. (1989). "A Tutorial on Hidden Markov Models and Selected Applications in Speech Recognition", *Proceedings of the IEEE*, 77(2), 257–286.

### Signal Processing

- Auger, F. & Flandrin, P. (1995). "Improving the Readability of Time-Frequency and Time-Scale Representations by the Reassignment Method", *IEEE Transactions on Signal Processing*, 43(5), 1068–1089.
- Harris, F.J. (1978). "On the Use of Windows for Harmonic Analysis with the Discrete Fourier Transform", *Proceedings of the IEEE*, 66(1), 51–83.
- Noll, A.M. (1967). "Cepstrum Pitch Determination", *Journal of the Acoustical Society of America*.
- Oppenheim, A.V. & Schafer, R.W. (2009). *Discrete-Time Signal Processing*, 3rd Edition, Pearson.
- Smith, J.O. (2011). *Spectral Audio Signal Processing*, W3K Publishing.

### Statistical Methods

- Bevington, P.R. & Robinson, D.K. (2003). *Data Reduction and Error Analysis for the Physical Sciences*, McGraw-Hill.
- Cochran, W.G. (1977). *Sampling Techniques*, 3rd Edition, Wiley.
- Efron, B. & Tibshirani, R.J. (1993). *An Introduction to the Bootstrap*, Chapman & Hall.
- Gatz, D.F. & Smith, L. (1995). "The Standard Error of a Weighted Mean Concentration", *Atmospheric Environment*.
- Hyndman, R.J. & Fan, Y. (1996). "Sample Quantiles in Statistical Packages", *The American Statistician*.
- McKay, M.D., Beckman, R.J. & Conover, W.J. (1979). "A Comparison of Three Methods for Selecting Values of Input Variables in the Analysis of Output from a Computer Code", *Technometrics*, 21(2), 239–245.
- Taylor, J.R. (1997). *An Introduction to Error Analysis*, 2nd Edition, University Science Books.
- JCGM 101:2008. "Evaluation of Measurement Data — Supplement 1 to the GUM — Propagation of Distributions Using a Monte Carlo Method".

### Machine Learning

- Bishop, C.M. (2006). *Pattern Recognition and Machine Learning*, Springer.

### Vocal Science

- Goto, M. (2001). "A Predominant-F0 Estimation Method for Polyphonic Musical Audio Signals", *Acoustical Science and Technology*.
- Prame, E. (1994). "Measurements of the Vibrato Rate of Ten Singers", *Journal of the Acoustical Society of America*, 96(4), 1979–1984.
- Sundberg, J. (1987). *The Science of the Singing Voice*, Northern Illinois University Press.
- Titze, I.R. (1994). *Principles of Voice Production*, Prentice Hall.

### Information Theory

- Cover, T.M. & Thomas, J.A. (2006). *Elements of Information Theory*, Wiley.
- Shannon, C.E. (1948). "A Mathematical Theory of Communication", *Bell System Technical Journal*.
- Viterbi, A. (1967). "Error Bounds for Convolutional Codes and an Asymptotically Optimum Decoding Algorithm", *IEEE Transactions on Information Theory*.

### Software Libraries

- McFee, B., Raffel, C., Liang, D., Ellis, D.P.W., McVicar, M., Battenberg, E. & Nieto, O. (2015). "librosa: Audio and Music Signal Analysis in Python", *Proceedings of the 14th Python in Science Conference*, 18–24.

### General Music Information Retrieval

- Lerch, A. (2012). *An Introduction to Audio Content Analysis*, Wiley-IEEE Press.
- Müller, M. (2015). *Fundamentals of Music Processing*, Springer.

### Monte Carlo Methods

- Metropolis, N. & Ulam, S. (1949). "The Monte Carlo Method", *Journal of the American Statistical Association*.
- Rubinstein, R.Y. & Kroese, D.P. (2016). *Simulation and the Monte Carlo Method*, 3rd Edition, Wiley.
