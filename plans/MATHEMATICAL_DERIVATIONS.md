# Mathematical Derivations for Tessiture

**Document:** Supporting mathematical derivations for [`MASTER_IMPLEMENTATION_PLAN.md`](MASTER_IMPLEMENTATION_PLAN.md)  
**Date:** 2026-02-26  
**Purpose:** Provide step-by-step derivations for all formulas used in the Tessiture system

---

## Table of Contents

1. [Frequency to MIDI Conversion](#1-frequency-to-midi-conversion)
2. [MIDI Uncertainty Propagation](#2-midi-uncertainty-propagation)
3. [Weighted Mean and Variance](#3-weighted-mean-and-variance)
4. [Softmax Probability Distribution](#4-softmax-probability-distribution)
5. [Entropy-Based Confidence](#5-entropy-based-confidence)
6. [Viterbi Path Optimization](#6-viterbi-path-optimization)
7. [Correlation Coefficient](#7-correlation-coefficient)

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
12 * log₂(f / 440) = m - 69
m = 69 + 12 * log₂(f / 440)
```

**Alternative form using natural logarithm:**
```
m = 69 + 12 * ln(f / 440) / ln(2)
```

### Validation

**Test 1:** A4 (440 Hz)
```
m = 69 + 12 * log₂(440 / 440) = 69 + 12 * 0 = 69 ✓
```

**Test 2:** A5 (880 Hz, one octave up)
```
m = 69 + 12 * log₂(880 / 440) = 69 + 12 * 1 = 81 ✓
```

**Test 3:** C4 (261.63 Hz)
```
m = 69 + 12 * log₂(261.63 / 440) = 69 + 12 * (-0.7492) = 60.01 ≈ 60 ✓
```

---

## 2. MIDI Uncertainty Propagation

### Problem Statement
Given frequency `f₀` with uncertainty `σ_f`, derive the uncertainty `σ_m` in MIDI note number.

### Background
- Error propagation uses first-order Taylor expansion
- For function y = g(x), uncertainty is σ_y ≈ |dg/dx| * σ_x

### Derivation

**Step 1:** Start with MIDI formula
```
m = 69 + 12 * ln(f₀ / 440) / ln(2)
```

**Step 2:** Simplify
```
m = 69 + (12 / ln(2)) * ln(f₀ / 440)
m = 69 + (12 / ln(2)) * (ln(f₀) - ln(440))
```

**Step 3:** Compute partial derivative with respect to f₀
```
∂m/∂f₀ = (12 / ln(2)) * (1 / f₀)
∂m/∂f₀ = 12 / (ln(2) * f₀)
```

**Step 4:** Apply first-order error propagation
```
σ_m ≈ |∂m/∂f₀| * σ_f
σ_m = (12 / (ln(2) * f₀)) * σ_f
σ_m = (12 / ln(2)) * (σ_f / f₀)
```

**Step 5:** Numerical constant
```
12 / ln(2) = 12 / 0.6931 = 17.312
σ_m = 17.312 * (σ_f / f₀)
```

### Validation

**Test 1:** A4 (440 Hz) with σ_f = 1 Hz
```
σ_m = 17.312 * (1 / 440) = 0.0393 semitones = 3.93 cents ✓
```

**Test 2:** C4 (261.63 Hz) with σ_f = 1 Hz
```
σ_m = 17.312 * (1 / 261.63) = 0.0662 semitones = 6.62 cents ✓
```

**Observation:** Lower frequencies have larger MIDI uncertainty for the same Hz uncertainty.

### Conversion to Cents
```
cents = semitones * 100
σ_cents = σ_m * 100 = 1731.2 * (σ_f / f₀)
```

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
μ = Σ(w_i * m_i) / Σ(w_i)
```

**Derivation:** Minimize weighted squared deviations
```
Minimize: S = Σ w_i * (m_i - μ)²
∂S/∂μ = -2 * Σ w_i * (m_i - μ) = 0
Σ w_i * m_i = μ * Σ w_i
μ = Σ(w_i * m_i) / Σ(w_i)
```

### 3.2 Uncertainty in Weighted Mean

**Formula:**
```
σ²_mean = Σ(w_i² * σ_i²) / (Σ w_i)²
```

**Derivation:** Error propagation for weighted sum
```
μ = Σ(w_i * m_i) / W    where W = Σ w_i

∂μ/∂m_i = w_i / W

σ²_mean = Σ (∂μ/∂m_i)² * σ_i²
σ²_mean = Σ (w_i / W)² * σ_i²
σ²_mean = (1 / W²) * Σ(w_i² * σ_i²)
σ²_mean = Σ(w_i² * σ_i²) / (Σ w_i)²
```

**Citation:** Gatz, D.F. & Smith, L. (1995). "The Standard Error of a Weighted Mean Concentration"

### 3.3 Weighted Variance (Spread)

**Formula:**
```
σ²_spread = Σ(w_i * (m_i - μ)²) / Σ(w_i)
```

**Derivation:** Weighted second moment about the mean
```
Variance = E[(X - μ)²]

For weighted distribution:
σ²_spread = Σ w_i * (m_i - μ)² / Σ w_i
```

**Alternative (unbiased estimator):**
```
σ²_unbiased = Σ(w_i * (m_i - μ)²) / (Σ w_i - Σ(w_i²) / Σ w_i)
```

**Citation:** Cochran, W.G. (1977). *Sampling Techniques*, 3rd Edition

### Example: Tessitura Calculation

**Given:** 5 pitch measurements
```
m = [60, 62, 64, 65, 67]  (MIDI notes)
w = [0.3, 0.2, 0.25, 0.15, 0.1]  (duration weights)
σ = [0.02, 0.03, 0.02, 0.04, 0.03]  (uncertainties in semitones)
```

**Weighted Mean:**
```
μ = (0.3*60 + 0.2*62 + 0.25*64 + 0.15*65 + 0.1*67) / (0.3 + 0.2 + 0.25 + 0.15 + 0.1)
μ = (18 + 12.4 + 16 + 9.75 + 6.7) / 1.0
μ = 62.85 (approximately D4)
```

**Uncertainty in Mean:**
```
σ²_mean = (0.3²*0.02² + 0.2²*0.03² + 0.25²*0.02² + 0.15²*0.04² + 0.1²*0.03²) / 1.0²
σ²_mean = (0.000036 + 0.000036 + 0.000025 + 0.000036 + 0.000009) / 1.0
σ²_mean = 0.000142
σ_mean = 0.012 semitones = 1.2 cents
```

**Weighted Variance:**
```
σ²_spread = (0.3*(60-62.85)² + 0.2*(62-62.85)² + 0.25*(64-62.85)² + 0.15*(65-62.85)² + 0.1*(67-62.85)²) / 1.0
σ²_spread = (0.3*8.12 + 0.2*0.72 + 0.25*1.32 + 0.15*4.62 + 0.1*17.22) / 1.0
σ²_spread = (2.436 + 0.144 + 0.330 + 0.693 + 1.722) / 1.0
σ²_spread = 5.325
σ_spread = 2.31 semitones
```

**Interpretation:**
- Tessitura center: D4 (MIDI 62.85) ± 1.2 cents
- Tessitura spread: ±2.31 semitones (comfortable range)

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
z_i = exp(β * s_i)
```

**Step 2:** Normalization (ensures sum to 1)
```
P_i = z_i / Σ_j z_j
P_i = exp(β * s_i) / Σ_j exp(β * s_j)
```

### Properties

**Property 1:** Probabilities sum to 1
```
Σ_i P_i = Σ_i (exp(β * s_i) / Z) = (1/Z) * Σ_i exp(β * s_i) = Z / Z = 1 ✓
```

**Property 2:** Temperature effect
```
β → ∞: P_i → 1 for max(s_i), 0 otherwise (deterministic)
β → 0: P_i → 1/N for all i (uniform)
```

**Property 3:** Invariance to constant shift
```
P_i(s + c) = exp(β * (s_i + c)) / Σ_j exp(β * (s_j + c))
           = exp(β * c) * exp(β * s_i) / (exp(β * c) * Σ_j exp(β * s_j))
           = exp(β * s_i) / Σ_j exp(β * s_j)
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
z_major = exp(1.0 * 0.95) = 2.586
z_minor = exp(1.0 * 0.12) = 1.127
z_dim = exp(1.0 * 0.03) = 1.030
Z = 2.586 + 1.127 + 1.030 = 4.743

P_major = 2.586 / 4.743 = 0.545
P_minor = 1.127 / 4.743 = 0.238
P_dim = 1.030 / 4.743 = 0.217
```

**Verification:** 0.545 + 0.238 + 0.217 = 1.000 ✓

**Citation:** Bishop, C.M. (2006). *Pattern Recognition and Machine Learning*, Chapter 4

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
H(P) = -Σ_i P_i * log(P_i)
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
H(P) = -1 * log(1) = 0
confidence = 1 - 0 / log(N) = 1 ✓
```

**Property 3:** Uniform distribution (all P_i = 1/N)
```
H(P) = -N * (1/N) * log(1/N) = log(N)
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
H(P) = -0.94 * log(0.94) - 0.04 * log(0.04) - 22 * 0.0009 * log(0.0009)
H(P) = -0.94 * (-0.062) - 0.04 * (-3.219) - 22 * 0.0009 * (-7.013)
H(P) = 0.058 + 0.129 + 0.139
H(P) = 0.326
```

**Confidence:**
```
H_max = log(24) = 3.178
confidence = 1 - 0.326 / 3.178 = 1 - 0.103 = 0.897 ≈ 90%
```

**Interpretation:** High confidence (90%) indicates strong certainty in C major detection.

**Citation:** Shannon, C.E. (1948). "A Mathematical Theory of Communication"

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
Maximize: E_path = Σ_t S(f_t, t) - λ * Σ_t |f_t - f_{t-1}|
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
        cost[t, f] = S(f, t) + max_{f'} (cost[t-1, f'] - λ * |f - f'|)
        backpointer[t, f] = argmax_{f'} (cost[t-1, f'] - λ * |f - f'|)
```

**Step 3:** Backward pass (reconstruct path)
```
path[T-1] = argmax_f cost[T-1, f]
For t = T-2 down to 0:
    path[t] = backpointer[t+1, path[t+1]]
```

### Complexity
- Time: O(T * F²) where T = time frames, F = frequency bins
- Space: O(T * F)

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
cost[1, f1] = 0.7 + max(0.8-0.5*0, 0.3-0.5*1, 0.2-0.5*2, 0.1-0.5*3)
            = 0.7 + max(0.8, -0.2, -0.3, -1.4) = 0.7 + 0.8 = 1.5
backpointer[1, f1] = f1

cost[1, f2] = 0.9 + max(0.8-0.5*1, 0.3-0.5*0, 0.2-0.5*1, 0.1-0.5*2)
            = 0.9 + max(0.3, 0.3, -0.3, -0.9) = 0.9 + 0.3 = 1.2
backpointer[1, f2] = f1 or f2 (tie, choose f2)

cost[1, f3] = 0.3 + max(0.8-0.5*2, 0.3-0.5*1, 0.2-0.5*0, 0.1-0.5*1)
            = 0.3 + max(-0.2, -0.2, 0.2, -0.4) = 0.3 + 0.2 = 0.5
backpointer[1, f3] = f3

cost[1, f4] = 0.2 + max(0.8-0.5*3, 0.3-0.5*2, 0.2-0.5*1, 0.1-0.5*0)
            = 0.2 + max(-0.7, -0.7, -0.3, 0.1) = 0.2 + 0.1 = 0.3
backpointer[1, f4] = f4
```

*t=2:*
```
cost[2, f1] = 0.6 + max(1.5-0.5*0, 1.2-0.5*1, 0.5-0.5*2, 0.3-0.5*3)
            = 0.6 + max(1.5, 0.7, -0.5, -1.2) = 0.6 + 1.5 = 2.1
backpointer[2, f1] = f1

cost[2, f2] = 0.8 + max(1.5-0.5*1, 1.2-0.5*0, 0.5-0.5*1, 0.3-0.5*2)
            = 0.8 + max(1.0, 1.2, 0.0, -0.7) = 0.8 + 1.2 = 2.0
backpointer[2, f2] = f2

cost[2, f3] = 0.9 + max(1.5-0.5*2, 1.2-0.5*1, 0.5-0.5*0, 0.3-0.5*1)
            = 0.9 + max(0.5, 0.7, 0.5, -0.2) = 0.9 + 0.7 = 1.6
backpointer[2, f3] = f2

cost[2, f4] = 0.3 + max(1.5-0.5*3, 1.2-0.5*2, 0.5-0.5*1, 0.3-0.5*0)
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

**Citation:** Viterbi, A. (1967). "Error Bounds for Convolutional Codes and an Asymptotically Optimum Decoding Algorithm"

---

## 7. Correlation Coefficient

### Problem Statement
Measure similarity between two vectors (e.g., pitch class histogram and tonal profile).

### Background
- Pearson correlation coefficient
- Range: [-1, 1] where 1 = perfect positive correlation
- Used in Krumhansl-Schmuckler key detection

### Derivation

**Step 1:** Dot product (unnormalized correlation)
```
h · P = Σ_i h_i * P_i
```

**Step 2:** Normalize by magnitudes
```
r = (h · P) / (||h|| * ||P||)
```

Where:
```
||h|| = sqrt(Σ_i h_i²)
||P|| = sqrt(Σ_i P_i²)
```

### Properties

**Property 1:** Range [-1, 1]
```
By Cauchy-Schwarz inequality: |h · P| ≤ ||h|| * ||P||
Therefore: -1 ≤ r ≤ 1
```

**Property 2:** Perfect correlation
```
If h = c * P for some constant c > 0:
r = (c * P · P) / (||c * P|| * ||P||)
r = (c * ||P||²) / (c * ||P|| * ||P||)
r = 1 ✓
```

**Property 3:** Orthogonal vectors
```
If h · P = 0:
r = 0 / (||h|| * ||P||) = 0 ✓
```

### Example: Key Detection

**Given:**
```
h = [0.25, 0.00, 0.12, 0.00, 0.18, 0.15, 0.00, 0.20, 0.00, 0.08, 0.00, 0.02]  (pitch class histogram)
P = [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]  (C major profile)
```

**Dot Product:**
```
h · P = 0.25*6.35 + 0.12*3.48 + 0.18*4.38 + 0.15*4.09 + 0.20*5.19 + 0.08*3.66 + 0.02*2.88
h · P = 1.588 + 0.418 + 0.788 + 0.614 + 1.038 + 0.293 + 0.058
h · P = 4.797
```

**Magnitudes:**
```
||h||² = 0.25² + 0.12² + 0.18² + 0.15² + 0.20² + 0.08² + 0.02²
||h||² = 0.0625 + 0.0144 + 0.0324 + 0.0225 + 0.0400 + 0.0064 + 0.0004
||h||² = 0.1786
||h|| = 0.423

||P||² = 6.35² + 2.23² + 3.48² + 2.33² + 4.38² + 4.09² + 2.52² + 5.19² + 2.39² + 3.66² + 2.29² + 2.88²
||P||² = 40.32 + 4.97 + 12.11 + 5.43 + 19.18 + 16.73 + 6.35 + 26.94 + 5.71 + 13.40 + 5.24 + 8.29
||P||² = 164.67
||P|| = 12.83
```

**Correlation:**
```
r = 4.797 / (0.423 * 12.83)
r = 4.797 / 5.427
r = 0.884
```

**Interpretation:** Strong positive correlation (0.884) indicates the pitch class distribution matches the C major profile well.

**Citation:** Krumhansl, C.L. & Kessler, E.J. (1982). "Tracing the Dynamic Changes in Perceived Tonal Organization"

---

## Summary

This document provides complete mathematical derivations for all formulas used in the Tessiture system. Each derivation includes:

1. **Problem statement** - What we're trying to compute
2. **Background** - Context and assumptions
3. **Step-by-step derivation** - Mathematical development
4. **Validation** - Numerical examples and sanity checks
5. **Citations** - Original sources

These derivations enable independent verification of the system's mathematical correctness and provide a foundation for future enhancements.

---

**Document Status:** Complete  
**Last Updated:** 2026-02-26  
**Maintained By:** Tessiture Development Team
