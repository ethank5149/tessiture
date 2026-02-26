# Tessiture - Vocal Analysis Toolkit
## Overview

In music, **tessitura** (English: /ˌtɛsɪˈtʊərə/ TESS-ih-TOOR-ə, UK also /-ˈtjʊər-/ -⁠TURE-, Italian: [tessiˈtuːra]; pl. tessiture; lit. 'weaving' or 'texture') is the most acceptable and comfortable vocal range for a given singer (or, less frequently, musical instrument). It represents the range in which a voice or instrument produces its best timbre.

**Tessiture** is a web-based toolkit designed to analyze vocal and acoustic audio tracks with laboratory-grade precision. It computes comprehensive musical features, including:

* **Pitch trajectories** of single notes and harmonics
* **Chord and key detection**
* **Tessitura and vocal range**
* **Advanced vocal features** such as vibrato, formants, and phrase segmentation
* **Quantified uncertainties** using Monte Carlo simulations and calibration data

The toolkit is designed for **vocal recording, arrangement, and analysis**, providing actionable insights to both musicians and audio engineers.

---

## Versioning and Codenames

Tessiture releases use semantic versioning (`MAJOR.MINOR.PATCH`).

Major releases may include internal codenames used for dataset,
calibration, and development milestones.

| Version | Codename | Description |
|---|---|---|
| v0.x | **Synth** | Experimental development releases. Heavily rely on synthetic reference datasets for calibration, Monte Carlo testing, and uncertainty evaluation. |
| v1.x | **Tessa** | First official release. Incorporates real-world evaluation using the Tessa test dataset, fully calibrated and validated. |


---

## Dataset Conventions

Dataset identifiers represent semantic roles rather than fixed files.
- `REFERENCE_DATASET` designates calibration data with known ground truth.
- `TESSA_DATASET` designates real-world evaluation data.

These roles remain distinct even if currently implemented by single datasets.