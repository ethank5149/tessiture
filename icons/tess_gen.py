#!/usr/bin/env python3

"""
Vocal Tessitura + Harmonic Analysis Plotter

Usage:
    python icons/tess_gen.py [audio_path]

If `audio_path` is omitted, the default path used by `load_audio()` is used.

Output:
    Saves the generated plot to `icons/tess_gen.png`.
"""

import argparse
import sys
from pathlib import Path

import matplotlib

# Prefer a non-interactive backend suitable for headless environments.
# This must be set before importing pyplot (and before modules that may import it).
matplotlib.use("Agg")

import numpy as np
import librosa
import librosa.display
import matplotlib.pyplot as plt


# --------------------------------------------------
# PARAMETERS
# --------------------------------------------------

SR = 22050
FMIN = librosa.note_to_hz("C2")
FMAX = librosa.note_to_hz("C6")

DEFAULT_OUTPUT_PATH = Path(__file__).resolve().parent / "tess_gen.png"


# --------------------------------------------------
# LOAD AUDIO
# --------------------------------------------------

def load_audio(path="examples/tracks/Ariana Grande - Dangerous Woman (A Cappella).opus"):
    y, sr = librosa.load(path, sr=SR, mono=True)
    y = librosa.util.normalize(y)
    return y, sr


# --------------------------------------------------
# PITCH TRACKING (VOCAL TRACE)
# --------------------------------------------------

def extract_pitch(y, sr):

    f0, voiced_flag, voiced_prob = librosa.pyin(
        y,
        fmin=FMIN,
        fmax=FMAX,
        sr=sr,
        frame_length=2048,
        hop_length=256
    )

    times = librosa.times_like(f0, sr=sr, hop_length=256)

    return f0, times, voiced_flag


# --------------------------------------------------
# HARMONIC SPECTROGRAM
# --------------------------------------------------

def compute_spectrogram(y):

    S = np.abs(
        librosa.stft(
            y,
            n_fft=4096,
            hop_length=256
        )
    )

    S_db = librosa.amplitude_to_db(S, ref=np.max)

    return S_db


# --------------------------------------------------
# TESSITURA ESTIMATION
# --------------------------------------------------

def tessitura_band(f0):

    valid = f0[~np.isnan(f0)]

    if len(valid) < 10:
        return None

    low = np.percentile(valid, 20)
    high = np.percentile(valid, 80)

    return low, high


# --------------------------------------------------
# HARMONIC OVERLAY CURVES
# --------------------------------------------------

def harmonic_tracks(f0, num_harmonics=6):

    harmonics = []

    for n in range(1, num_harmonics + 1):
        harmonics.append(f0 * n)

    return harmonics


# --------------------------------------------------
# PLOTTING
# --------------------------------------------------

def plot_analysis(y, sr, f0, times, S_db, tessitura, output_path=DEFAULT_OUTPUT_PATH):

    fig = plt.figure(figsize=(14, 8))

    # Spectrogram
    librosa.display.specshow(
        S_db,
        sr=sr,
        hop_length=256,
        x_axis="time",
        y_axis="hz",
        cmap="magma"
    )

    # Vocal pitch trace
    plt.plot(
        times,
        f0,
        linewidth=2,
        label="Vocal Trace (F0)"
    )

    # Harmonics
    for h in harmonic_tracks(f0):
        plt.plot(times, h, linewidth=0.7, alpha=0.6)

    # Tessitura band
    if tessitura:
        low, high = tessitura

        plt.fill_between(
            times,
            low,
            high,
            alpha=0.2,
            label="Tessitura Band"
        )

        plt.axhline(low, linestyle="--")
        plt.axhline(high, linestyle="--")

    plt.ylim(50, 2000)

    plt.title("Vocal Trace + Harmonic Structure + Tessitura")
    plt.legend()
    plt.tight_layout()

    output_path = Path(output_path)
    if not output_path.parent.exists():
        raise FileNotFoundError(f"Output directory does not exist: {output_path.parent}")

    fig.savefig(output_path)
    plt.close(fig)


# --------------------------------------------------
# MAIN
# --------------------------------------------------

def main(argv=None):

    default_audio_path = load_audio.__defaults__[0]

    parser = argparse.ArgumentParser(
        description="Vocal tessitura + harmonic analysis plotter",
    )
    parser.add_argument(
        "audio_path",
        nargs="?",
        default=default_audio_path,
        help=f"Path to audio file (default: {default_audio_path})",
    )

    args = parser.parse_args(argv)

    y, sr = load_audio(args.audio_path)

    f0, times, voiced = extract_pitch(y, sr)

    S_db = compute_spectrogram(y)

    tessitura = tessitura_band(f0)

    plot_analysis(y, sr, f0, times, S_db, tessitura, output_path=DEFAULT_OUTPUT_PATH)


if __name__ == "__main__":
    main()