# Scientific Review: MASTER_IMPLEMENTATION_PLAN.md

**Review Date:** 2026-02-26  
**Reviewer:** Technical Architecture Team  
**Document Reviewed:** [`MASTER_IMPLEMENTATION_PLAN.md`](MASTER_IMPLEMENTATION_PLAN.md)

---

## Executive Summary

This review examines the mathematical formulas, scientific methodology, and references in the Tessiture Master Implementation Plan. Overall, the plan demonstrates strong technical foundations with accurate mathematical formulations. However, several areas would benefit from additional citations and minor corrections.

**Overall Assessment:** ✅ **APPROVED with recommendations**

---

## 1. Mathematical Formula Review

### 1.1 Frequency to MIDI Conversion ✅ CORRECT

**Formula (Line 45):**
```
m = 69 + 12 * log₂(f / 440 Hz)
```

**Status:** ✅ Mathematically correct  
**Verification:** This is the standard MIDI note number formula where:
- A4 (440 Hz) = MIDI note 69
- Each semitone = factor of 2^(1/12)
- Logarithmic scale properly represents equal temperament

**Recommended Citation:**
- MIDI Manufacturers Association (MMA), "MIDI 1.0 Detailed Specification", 1996
- Benson, D., "Music: A Mathematical Offering", Cambridge University Press, 2006

---

### 1.2 MIDI Uncertainty Propagation ✅ CORRECT

**Formula (Line 233):**
```
σ_m = (12 / ln(2)) * (σ_f / f₀)
```

**Status:** ✅ Mathematically correct  
**Verification:** This is the proper error propagation formula derived from:
- dm/df = 12/(f·ln(2))
- σ_m ≈ |dm/df| · σ_f (first-order Taylor expansion)

**Recommended Citation:**
- Taylor, J.R., "An Introduction to Error Analysis", University Science Books, 1997
- Bevington, P.R. & Robinson, D.K., "Data Reduction and Error Analysis for the Physical Sciences", McGraw-Hill, 2003

---

### 1.3 Harmonic Salience Function ⚠️ NEEDS CLARIFICATION

**Formula (Lines 50, 213):**
```
S(f₀, t) = w_H * H_norm + w_C * C + w_V * V + w_S * S_p
```

**Status:** ⚠️ Correct structure, but weights should be normalized  
**Issue:** The formula doesn't specify that Σw_i = 1 for proper probability interpretation

**Recommendation:** Add constraint:
```
S(f₀, t) = w_H * H_norm + w_C * C + w_V * V + w_S * S_p
where Σ(w_H, w_C, w_V, w_S) = 1
```

**Recommended Citations:**
- Salamon, J. & Gómez, E., "Melody Extraction from Polyphonic Music Signals using Pitch Contour Characteristics", IEEE Transactions on Audio, Speech, and Language Processing, 2012
- Goto, M., "A Predominant-F0 Estimation Method for Polyphonic Musical Audio Signals", Acoustical Science and Technology, 2001

---

### 1.4 Tessitura Variance Formula ❌ ERROR FOUND

**Formula (Line 56, 622):**
```
σ²_tess = Σ(w_i² * σ_i²) / (Σ(w_i))²
```

**Status:** ❌ Incorrect for weighted variance  
**Issue:** This formula is for the variance of a weighted mean, not the weighted variance of the distribution

**Correct Formula for Weighted Mean Variance:**
```
σ²_mean = Σ(w_i² * σ_i²) / (Σ(w_i))²  ✅ (This is what's shown)
```

**Correct Formula for Weighted Variance (if that's the intent):**
```
σ²_weighted = Σ(w_i * (m_i - μ_tess)²) / Σ(w_i)
```

**Clarification Needed:** The document should specify whether this is:
1. Uncertainty in the tessitura center estimate (current formula is correct)
2. Spread/variance of the tessitura distribution (needs different formula)

**Recommended Citation:**
- Cochran, W.G., "Sampling Techniques", 3rd Edition, Wiley, 1977 (Chapter on weighted statistics)
- Gatz, D.F. & Smith, L., "The Standard Error of a Weighted Mean Concentration", Atmospheric Environment, 1995

---

### 1.5 Viterbi Path Optimization ✅ CORRECT

**Formula (Line 225):**
```
E_path = Σ_t S(f₀, t) - λ * Σ_t |m_t - m_{t-1}|
```

**Status:** ✅ Correct structure for dynamic programming  
**Note:** This is a standard Viterbi-style energy minimization with continuity penalty

**Recommended Citations:**
- Viterbi, A., "Error Bounds for Convolutional Codes and an Asymptotically Optimum Decoding Algorithm", IEEE Transactions on Information Theory, 1967
- Mauch, M. & Dixon, S., "pYIN: A Fundamental Frequency Estimator Using Probabilistic Threshold Distributions", ICASSP, 2014

---

### 1.6 Chord Probability (Softmax) ✅ CORRECT

**Formula (Line 246):**
```
P(C_i) = exp(β * score_i) / Σ_j exp(β * score_j)
```

**Status:** ✅ Standard softmax formulation  
**Note:** β is the inverse temperature parameter

**Recommended Citation:**
- Bishop, C.M., "Pattern Recognition and Machine Learning", Springer, 2006 (Chapter 4: Linear Models for Classification)

---

### 1.7 Key Detection Correlation ⚠️ NOTATION ISSUE

**Formula (Line 261):**
```
L_r = (h · roll(PROFILE, r)) / (||h|| * ||roll(PROFILE, r)||)
```

**Status:** ⚠️ Correct concept, notation could be clearer  
**Issue:** `roll(PROFILE, r)` is programming notation, not standard mathematical notation

**Recommended Mathematical Notation:**
```
L_r = (h · P_r) / (||h|| · ||P_r||)
where P_r is the tonal profile circularly shifted by r semitones
```

**Recommended Citations:**
- Krumhansl, C.L. & Kessler, E.J., "Tracing the Dynamic Changes in Perceived Tonal Organization in a Spatial Representation of Musical Keys", Psychological Review, 1982
- Temperley, D., "What's Key for Key? The Krumhansl-Schmuckler Key-Finding Algorithm Reconsidered", Music Perception, 1999

---

### 1.8 Entropy-Based Confidence ✅ CORRECT

**Formula (Lines 288-289):**
```
H(P(K)) = -Σ_i P(K_i) * log(P(K_i))
confidence = 1 - H(P(K)) / log(24)
```

**Status:** ✅ Correct Shannon entropy normalized by maximum entropy  
**Note:** log(24) is the maximum entropy for 24 possible keys (12 major + 12 minor)

**Recommended Citation:**
- Shannon, C.E., "A Mathematical Theory of Communication", Bell System Technical Journal, 1948
- Cover, T.M. & Thomas, J.A., "Elements of Information Theory", Wiley, 2006

---

## 2. Scientific Methodology Review

### 2.1 Latin Hypercube Sampling ✅ CORRECT

**Reference (Line 160):** pyDOE2 library for LHS

**Status:** ✅ Appropriate method for parameter space exploration  
**Justification:** LHS provides better coverage than random sampling with fewer samples

**Recommended Additional Citations:**
- McKay, M.D., Beckman, R.J. & Conover, W.J., "A Comparison of Three Methods for Selecting Values of Input Variables in the Analysis of Output from a Computer Code", Technometrics, 1979
- Iman, R.L. & Conover, W.J., "Small Sample Sensitivity Analysis Techniques for Computer Models", Communications in Statistics, 1980

---

### 2.2 Monte Carlo Uncertainty Quantification ✅ CORRECT

**Approach (Lines 162-177):** Monte Carlo perturbations with N=100-500 realizations

**Status:** ✅ Standard approach for uncertainty propagation  
**Note:** Sample size is adequate for 95% confidence intervals

**Recommended Additional Citations:**
- Metropolis, N. & Ulam, S., "The Monte Carlo Method", Journal of the American Statistical Association, 1949
- Rubinstein, R.Y. & Kroese, D.P., "Simulation and the Monte Carlo Method", 3rd Edition, Wiley, 2016
- JCGM 101:2008, "Evaluation of measurement data — Supplement 1 to the Guide to the expression of uncertainty in measurement — Propagation of distributions using a Monte Carlo method"

---

### 2.3 STFT Parameters ✅ REASONABLE

**Parameters (Line 198):**
- n_fft = 4096
- hop_length = 512

**Status:** ✅ Reasonable for vocal analysis  
**Analysis:**
- At 44.1 kHz: ~93 ms window, ~11.6 ms hop
- Frequency resolution: ~10.8 Hz
- Adequate for pitch detection (lowest note E2 ≈ 82 Hz)

**Recommended Citations:**
- Harris, F.J., "On the Use of Windows for Harmonic Analysis with the Discrete Fourier Transform", Proceedings of the IEEE, 1978
- Oppenheim, A.V. & Schafer, R.W., "Discrete-Time Signal Processing", 3rd Edition, Pearson, 2009

---

### 2.4 Vocal Range (E2-C7) ✅ CORRECT

**Range (Line 149):** 82 Hz → 2093 Hz

**Status:** ✅ Appropriate for vocal analysis  
**Verification:**
- E2 = 82.41 Hz (bass lower limit)
- C7 = 2093.00 Hz (soprano upper limit)
- Covers full vocal range including extended techniques

**Recommended Citation:**
- Sundberg, J., "The Science of the Singing Voice", Northern Illinois University Press, 1987
- Titze, I.R., "Principles of Voice Production", Prentice Hall, 1994

---

### 2.5 Vibrato Parameters ✅ CORRECT

**Parameters (Lines 156-157):**
- Depth: ±20 cents
- Rate: 3-8 Hz

**Status:** ✅ Matches physiological vibrato characteristics  
**Verification:** Typical vocal vibrato is 5-7 Hz with ±50-100 cents depth; conservative range is appropriate

**Recommended Citations:**
- Sundberg, J., "Vibrato", in "The Science of the Singing Voice", 1987
- Prame, E., "Measurements of the Vibrato Rate of Ten Singers", Journal of the Acoustical Society of America, 1994
- Titze, I.R., "Physiologic and Acoustic Differences Between Male and Female Voices", Journal of the Acoustical Society of America, 1989

---

## 3. Missing Citations and Recommendations

### 3.1 Critical Missing Citations

#### Pitch Detection Algorithms
**Current Reference (Line 589):** Boersma, 1993

**Additional Recommended Citations:**
- de Cheveigné, A. & Kawahara, H., "YIN, a Fundamental Frequency Estimator for Speech and Music", Journal of the Acoustical Society of America, 2002
- Mauch, M. & Dixon, S., "pYIN: A Fundamental Frequency Estimator Using Probabilistic Threshold Distributions", ICASSP, 2014
- Klapuri, A., "Multiple Fundamental Frequency Estimation by Summing Harmonic Amplitudes", ISMIR, 2006

#### Harmonic Product Spectrum
**Currently Uncited (Line 207)**

**Recommended Citations:**
- Schroeder, M.R., "Period Histogram and Product Spectrum: New Methods for Fundamental-Frequency Measurement", Journal of the Acoustical Society of America, 1968
- Noll, A.M., "Cepstrum Pitch Determination", Journal of the Acoustical Society of America, 1967

#### Spectral Reassignment
**Currently Uncited (Lines 194, 209)**

**Recommended Citations:**
- Auger, F. & Flandrin, P., "Improving the Readability of Time-Frequency and Time-Scale Representations by the Reassignment Method", IEEE Transactions on Signal Processing, 1995
- Fulop, S.A. & Fitz, K., "Algorithms for Computing the Time-Corrected Instantaneous Frequency of a Signal", Journal of the Acoustical Society of America, 2006

#### Chord Detection
**Currently Uncited (Section 3.1)**

**Recommended Citations:**
- Harte, C., Sandler, M. & Gasser, M., "Detecting Harmonic Change in Musical Audio", ACM Workshop on Audio and Music Computing Multimedia, 2006
- Papadopoulos, H. & Peeters, G., "Large-Scale Study of Chord Estimation Algorithms Based on Chroma Representation and HMM", CBMI, 2007
- Mauch, M. & Dixon, S., "Simultaneous Estimation of Chords and Musical Context from Audio", IEEE Transactions on Audio, Speech, and Language Processing, 2010

#### Hidden Markov Models (HMM)
**Currently Uncited (Lines 248, 264)**

**Recommended Citations:**
- Rabiner, L.R., "A Tutorial on Hidden Markov Models and Selected Applications in Speech Recognition", Proceedings of the IEEE, 1989
- Sheh, A. & Ellis, D.P.W., "Chord Segmentation and Recognition using EM-Trained Hidden Markov Models", ISMIR, 2003

---

### 3.2 Librosa-Specific Citations

**Current Reference (Line 593):** "Librosa documentation"

**Recommended Formal Citation:**
- McFee, B., Raffel, C., Liang, D., Ellis, D.P.W., McVicar, M., Battenberg, E. & Nieto, O., "librosa: Audio and Music Signal Analysis in Python", Proceedings of the 14th Python in Science Conference, 2015

---

### 3.3 Statistical Methods

#### Confidence Intervals
**Currently Uncited (Lines 295-297)**

**Recommended Citations:**
- Efron, B. & Tibshirani, R.J., "An Introduction to the Bootstrap", Chapman & Hall, 1993
- Wilks, S.S., "Determination of Sample Sizes for Setting Tolerance Limits", Annals of Mathematical Statistics, 1941

#### Percentile-Based Tessitura
**Currently Uncited (Lines 269, 274)**

**Recommended Citation:**
- Hyndman, R.J. & Fan, Y., "Sample Quantiles in Statistical Packages", The American Statistician, 1996

---

### 3.4 Audio Processing Standards

**Missing General References:**
- Smith, J.O., "Spectral Audio Signal Processing", W3K Publishing, 2011 (online book)
- Müller, M., "Fundamentals of Music Processing", Springer, 2015
- Lerch, A., "An Introduction to Audio Content Analysis", Wiley-IEEE Press, 2012

---

## 4. Technical Accuracy Issues

### 4.1 Minor Issues

#### Issue 1: Harmonic Ratios Range
**Location:** Line 152  
**Current:** "Harmonic ratios: 0.1 → 1.0"  
**Issue:** Unclear what "harmonic ratios" means  
**Recommendation:** Clarify as "Harmonic amplitude ratios (A_n/A_1): 0.1 → 1.0"

#### Issue 2: SNR Range
**Location:** Line 155  
**Current:** "SNR: 20 → 60 dB"  
**Note:** This is a very clean range; real-world vocals often have SNR < 20 dB  
**Recommendation:** Consider extending lower bound to 10 dB for robustness testing

#### Issue 3: Pitch Accuracy Target
**Location:** Line 438  
**Current:** "Pitch accuracy: ± 3 cents"  
**Note:** This is achievable for clean signals but optimistic for noisy/polyphonic audio  
**Recommendation:** Add qualifier: "± 3 cents (clean monophonic signals)"

---

### 4.2 Terminology Clarifications

#### "Laboratory-grade precision"
**Location:** Line 5  
**Recommendation:** Define what this means quantitatively (e.g., "±3 cents pitch accuracy, 95% confidence intervals")

#### "Acapella audio tracks"
**Location:** Line 5  
**Note:** Should be "a cappella" (two words) in formal writing  
**Recommendation:** Use "unaccompanied vocal" or correct spelling

---

## 5. Recommended Additional Sections

### 5.1 Suggested New Section: "Validation Methodology"

Add a section describing how the system will be validated against:
- Ground truth synthetic signals
- Annotated vocal datasets (e.g., MIR-1K, MIREX datasets)
- Expert human annotations

**Recommended Dataset Citations:**
- Hsu, C.L. & Jang, J.S.R., "On the Improvement of Singing Voice Separation for Monaural Recordings using the MIR-1K Dataset", IEEE Transactions on Audio, Speech, and Language Processing, 2010
- MIREX (Music Information Retrieval Evaluation eXchange) datasets and results

---

### 5.2 Suggested New Section: "Limitations and Assumptions"

Document known limitations:
- Assumes Western 12-tone equal temperament
- Limited to 1-4 simultaneous notes
- Requires relatively clean vocal signals
- May struggle with extreme vocal techniques (growls, screams, etc.)

---

## 6. Summary of Recommendations

### 6.1 Critical Actions

1. ✅ **Clarify tessitura variance formula** (Line 56, 622) - specify if it's uncertainty in mean or weighted variance
2. ✅ **Add weight normalization constraint** to harmonic salience formula (Line 50, 213)
3. ✅ **Correct "acapella" to "a cappella"** (Line 5)

### 6.2 High-Priority Citations to Add

| Topic | Priority | Recommended Citation |
|-------|----------|---------------------|
| Pitch detection (YIN) | High | de Cheveigné & Kawahara, 2002 |
| Librosa formal citation | High | McFee et al., 2015 |
| HMM tutorial | High | Rabiner, 1989 |
| Chord detection | High | Mauch & Dixon, 2010 |
| Spectral reassignment | Medium | Auger & Flandrin, 1995 |
| Monte Carlo methods | Medium | JCGM 101:2008 |
| Music signal processing | Medium | Müller, 2015 |
| Vibrato characteristics | Medium | Prame, 1994 |

### 6.3 Documentation Enhancements

1. Add "Validation Methodology" section
2. Add "Limitations and Assumptions" section
3. Expand mathematical specification with derivations
4. Create bibliography section with full citations

---

## 7. Conclusion

The MASTER_IMPLEMENTATION_PLAN demonstrates strong technical foundations with mathematically sound formulations. The primary issues are:

1. **One mathematical error** (tessitura variance needs clarification)
2. **Missing citations** for key algorithms (pitch detection, chord detection, HMM)
3. **Minor notation improvements** needed for clarity

**Overall Grade:** A- (Excellent with minor revisions needed)

**Recommendation:** Proceed with implementation after addressing the tessitura variance clarification and adding the high-priority citations.

---

## 8. Proposed Citation Format

### Recommended Bibliography Structure

```markdown
## References

### Foundational Music Theory
- Krumhansl, C.L. & Kessler, E.J. (1982). "Tracing the Dynamic Changes in Perceived Tonal Organization in a Spatial Representation of Musical Keys", *Psychological Review*, 89(4), 334-368.
- Benson, D. (2006). *Music: A Mathematical Offering*, Cambridge University Press.

### Pitch Detection & Analysis
- de Cheveigné, A. & Kawahara, H. (2002). "YIN, a Fundamental Frequency Estimator for Speech and Music", *Journal of the Acoustical Society of America*, 111(4), 1917-1930.
- Mauch, M. & Dixon, S. (2014). "pYIN: A Fundamental Frequency Estimator Using Probabilistic Threshold Distributions", *ICASSP*, 659-663.
- Boersma, P. (1993). "Accurate Short-Term Analysis of the Fundamental Frequency and the Harmonics-to-Noise Ratio of a Sampled Sound", *Proceedings of the Institute of Phonetic Sciences*, 17, 97-110.

### Chord & Key Detection
- Mauch, M. & Dixon, S. (2010). "Simultaneous Estimation of Chords and Musical Context from Audio", *IEEE Transactions on Audio, Speech, and Language Processing*, 18(6), 1280-1289.
- Harte, C., Sandler, M. & Gasser, M. (2006). "Detecting Harmonic Change in Musical Audio", *ACM Workshop on Audio and Music Computing Multimedia*, 21-26.

### Signal Processing
- Harris, F.J. (1978). "On the Use of Windows for Harmonic Analysis with the Discrete Fourier Transform", *Proceedings of the IEEE*, 66(1), 51-83.
- Auger, F. & Flandrin, P. (1995). "Improving the Readability of Time-Frequency and Time-Scale Representations by the Reassignment Method", *IEEE Transactions on Signal Processing*, 43(5), 1068-1089.

### Statistical Methods
- McKay, M.D., Beckman, R.J. & Conover, W.J. (1979). "A Comparison of Three Methods for Selecting Values of Input Variables in the Analysis of Output from a Computer Code", *Technometrics*, 21(2), 239-245.
- Taylor, J.R. (1997). *An Introduction to Error Analysis*, 2nd Edition, University Science Books.
- JCGM 101:2008. "Evaluation of Measurement Data — Supplement 1 to the GUM — Propagation of Distributions Using a Monte Carlo Method".

### Machine Learning
- Rabiner, L.R. (1989). "A Tutorial on Hidden Markov Models and Selected Applications in Speech Recognition", *Proceedings of the IEEE*, 77(2), 257-286.
- Bishop, C.M. (2006). *Pattern Recognition and Machine Learning*, Springer.

### Vocal Science
- Sundberg, J. (1987). *The Science of the Singing Voice*, Northern Illinois University Press.
- Titze, I.R. (1994). *Principles of Voice Production*, Prentice Hall.
- Prame, E. (1994). "Measurements of the Vibrato Rate of Ten Singers", *Journal of the Acoustical Society of America*, 96(4), 1979-1984.

### Software Libraries
- McFee, B., Raffel, C., Liang, D., Ellis, D.P.W., McVicar, M., Battenberg, E. & Nieto, O. (2015). "librosa: Audio and Music Signal Analysis in Python", *Proceedings of the 14th Python in Science Conference*, 18-24.

### General Music Information Retrieval
- Müller, M. (2015). *Fundamentals of Music Processing*, Springer.
- Lerch, A. (2012). *An Introduction to Audio Content Analysis*, Wiley-IEEE Press.
- Tzanetakis, G. & Cook, P. (2002). "Musical Genre Classification of Audio Signals", *IEEE Transactions on Speech and Audio Processing*, 10(5), 293-302.
```

---

**Review Complete**  
**Next Steps:** Address critical issues and incorporate high-priority citations into documentation.
