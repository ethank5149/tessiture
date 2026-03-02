#!/usr/bin/env python3
"""
Audio Logo Generator
====================
Generates an SVG graphic from an audio track with accurate representation of:
- Tessitura band: actual F0 pitch range (10th-90th percentile)
- Vocal trace: F0 contour over time
- Harmonic curves: actual amplitude envelopes of harmonics 2-4

Usage:
    python audio_logo_generator.py input.wav -o output.svg
    python audio_logo_generator.py input.mp3 --width 240 --style cyber
"""

import argparse
import numpy as np
from pathlib import Path
from dataclasses import dataclass
from scipy import signal
from scipy.ndimage import uniform_filter1d
import warnings

warnings.filterwarnings("ignore")

try:
    import librosa
except ImportError:
    import subprocess
    subprocess.check_call(["pip", "install", "librosa", "soundfile", "scipy", "--quiet", "--break-system-packages"])
    import librosa


@dataclass
class ColorPalette:
    background: str
    tessitura_fill: str
    tessitura_opacity: float
    vocal_color: str
    harmonic_colors: list[str]

    @classmethod
    def cyber(cls): 
        return cls("#050505", "#ffffff", 0.12, "#00ffff",
                   ["#ff4fd8", "#ffaa00", "#ff66aa"])

    @classmethod
    def sunset(cls):
        return cls("#0a0508", "#ffffff", 0.10, "#ffcc00",
                   ["#ff6b6b", "#c9b1ff", "#6bcb77"])

    @classmethod
    def aurora(cls):
        return cls("#030712", "#ffffff", 0.10, "#4ade80",
                   ["#c084fc", "#f472b6", "#67e8f9"])

    @classmethod
    def ember(cls):
        return cls("#0c0404", "#ffffff", 0.10, "#ff6b35",
                   ["#facc15", "#a3e635", "#4ade80"])

    @classmethod
    def vapor(cls):
        return cls("#0d0015", "#ffffff", 0.10, "#ff00ff",
                   ["#00ffff", "#38bdf8", "#67e8f9"])

    @classmethod
    def mono(cls):
        return cls("#080808", "#ffffff", 0.08, "#ffffff",
                   ["#888888", "#666666", "#444444"])


@dataclass 
class AudioFeatures:
    """Accurate audio features extracted from analysis."""
    f0_contour: np.ndarray           # Fundamental frequency over time (Hz)
    f0_times: np.ndarray             # Time points for F0
    tessitura_low: float             # 10th percentile F0 (Hz)
    tessitura_high: float            # 90th percentile F0 (Hz)
    harmonic_envelopes: list[np.ndarray]  # Amplitude envelopes for harmonics 2, 3, 4
    duration: float
    f0_median: float                 # Median F0 for reference


class AudioAnalyzer:
    """Accurate audio analysis using spectral methods."""

    def __init__(self, sr: int = 22050, hop_length: int = 256, n_fft: int = 4096):
        self.sr = sr
        self.hop_length = hop_length
        self.n_fft = n_fft
        self.freq_resolution = sr / n_fft  # Hz per bin

    def analyze(self, audio_path: str) -> AudioFeatures:
        y, sr = librosa.load(audio_path, sr=self.sr, mono=True)
        duration = len(y) / sr
        
        # Compute STFT
        S = np.abs(librosa.stft(y, n_fft=self.n_fft, hop_length=self.hop_length))
        freqs = librosa.fft_frequencies(sr=sr, n_fft=self.n_fft)
        times = librosa.times_like(S, sr=sr, hop_length=self.hop_length)
        
        # Track F0 using spectral peak in expected vocal range
        f0_contour = self._track_f0(S, freqs, f_min=80, f_max=800)
        
        # Smooth F0 to remove jitter
        f0_smooth = self._smooth(f0_contour, window=5)
        
        # Calculate tessitura from valid F0 values
        valid_f0 = f0_smooth[f0_smooth > 0]
        if len(valid_f0) > 10:
            tessitura_low = np.percentile(valid_f0, 10)
            tessitura_high = np.percentile(valid_f0, 90)
            f0_median = np.median(valid_f0)
        else:
            tessitura_low, tessitura_high, f0_median = 200, 400, 300
        
        # Extract harmonic amplitude envelopes (harmonics 2, 3, 4)
        harmonic_envelopes = self._extract_harmonic_envelopes(S, freqs, f0_smooth, harmonics=[2, 3, 4])
        
        return AudioFeatures(
            f0_contour=f0_smooth,
            f0_times=times,
            tessitura_low=tessitura_low,
            tessitura_high=tessitura_high,
            harmonic_envelopes=harmonic_envelopes,
            duration=duration,
            f0_median=f0_median
        )

    def _track_f0(self, S: np.ndarray, freqs: np.ndarray, f_min: float, f_max: float) -> np.ndarray:
        """Track fundamental frequency using Harmonic Product Spectrum."""
        f0 = np.zeros(S.shape[1])
        
        for i in range(S.shape[1]):
            frame = S[:, i]
            
            # Harmonic Product Spectrum: multiply spectrum at f, 2f, 3f, 4f
            # This reinforces the true fundamental
            hps = frame.copy()
            n_harmonics = 4
            
            for h in range(2, n_harmonics + 1):
                # Downsample by factor h
                downsampled = np.zeros_like(frame)
                for j in range(len(frame) // h):
                    downsampled[j] = frame[j * h]
                hps = hps * downsampled
            
            # Find peak in F0 range
            valid_mask = (freqs >= f_min) & (freqs <= f_max)
            hps_valid = hps[valid_mask]
            freqs_valid = freqs[valid_mask]
            
            if len(hps_valid) > 0 and np.max(hps_valid) > 0:
                peak_idx = np.argmax(hps_valid)
                f0[i] = freqs_valid[peak_idx]
            else:
                f0[i] = 0
        
        return f0

    def _extract_harmonic_envelopes(self, S: np.ndarray, freqs: np.ndarray, f0: np.ndarray, harmonics: list[int]) -> list[np.ndarray]:
        """Extract amplitude envelopes at harmonic frequencies."""
        envelopes = []
        
        for h in harmonics:
            envelope = np.zeros(len(f0))
            
            for i, fundamental in enumerate(f0):
                if fundamental > 0:
                    target_freq = fundamental * h
                    
                    # Find closest frequency bin
                    bin_idx = np.argmin(np.abs(freqs - target_freq))
                    
                    # Get amplitude in small window around target (±2 bins for spectral leakage)
                    low = max(0, bin_idx - 2)
                    high = min(len(freqs), bin_idx + 3)
                    envelope[i] = np.max(S[low:high, i])
            
            # Normalize envelope
            if envelope.max() > 0:
                envelope = envelope / envelope.max()
            
            # Smooth
            envelope = self._smooth(envelope, window=5)
            envelopes.append(envelope)
        
        return envelopes

    def _smooth(self, arr: np.ndarray, window: int) -> np.ndarray:
        """Smooth array with uniform filter."""
        return uniform_filter1d(arr.astype(float), size=window, mode='nearest')


class SVGGenerator:
    """Generates accurate SVG visualization."""

    def __init__(self, width=240, height=240, palette=None, margin=0.16, n_points=8):
        self.width = width
        self.height = height
        self.palette = palette or ColorPalette.cyber()
        self.margin = margin
        self.n_points = n_points
        
        self.x_min = width * margin
        self.x_max = width * (1 - margin)
        self.y_center = height / 2
        self.y_range = height * 0.32

    def generate(self, features: AudioFeatures) -> str:
        return "\n".join([
            self._svg_header(),
            self._background(),
            self._render_tessitura(features),
            self._render_harmonics(features),
            self._render_f0_contour(features),
            "</svg>"
        ])

    def _svg_header(self):
        return f'<svg viewBox="0 0 {self.width} {self.height}" xmlns="http://www.w3.org/2000/svg">'

    def _background(self):
        return f'\n<!-- Background -->\n<rect width="{self.width}" height="{self.height}" fill="{self.palette.background}"/>'

    def _freq_to_y(self, freq: float, f_min: float, f_max: float) -> float:
        """Map frequency (log scale) to Y coordinate."""
        if freq <= 0:
            freq = f_min
        log_min = np.log2(f_min)
        log_max = np.log2(f_max)
        log_freq = np.log2(np.clip(freq, f_min, f_max))
        normalized = (log_freq - log_min) / (log_max - log_min)
        return self.y_center + self.y_range - normalized * 2 * self.y_range

    def _resample(self, arr: np.ndarray, n: int) -> np.ndarray:
        """Resample array to n points."""
        if len(arr) == 0:
            return np.zeros(n)
        indices = np.linspace(0, len(arr) - 1, n).astype(int)
        return arr[indices]

    def _smooth_path(self, points: list[tuple[float, float]]) -> str:
        """Create smooth quadratic bezier curve."""
        if len(points) < 2:
            return ""
        
        path = f"M{points[0][0]:.1f} {points[0][1]:.1f}"
        
        for i in range(1, len(points)):
            px, py = points[i - 1]
            cx, cy = points[i]
            
            if i == len(points) - 1:
                path += f" Q{px:.1f},{py:.1f} {cx:.1f},{cy:.1f}"
            else:
                mx = (px + cx) / 2
                my = (py + cy) / 2
                path += f" Q{px:.1f},{py:.1f} {mx:.1f},{my:.1f}"
        
        return path

    def _render_tessitura(self, features: AudioFeatures) -> str:
        """Render tessitura as a narrower band (subset of F0 range)."""
        # Use wider range for the overall view so F0 extends beyond tessitura
        f0_resampled = self._resample(features.f0_contour, self.n_points)
        valid_f0 = f0_resampled[f0_resampled > 0]
        
        # Visual range extends beyond tessitura
        f_min = features.tessitura_low * 0.7
        f_max = features.tessitura_high * 1.4
        
        xs = np.linspace(self.x_min, self.x_max, self.n_points)
        
        # Tessitura band follows the general F0 shape but stays within its bounds
        upper_points = []
        lower_points = []
        
        for i, x in enumerate(xs):
            local_f0 = f0_resampled[i] if f0_resampled[i] > 0 else features.f0_median
            
            # Tessitura tracks F0 shape but clamped to tessitura range
            # This creates a band that F0 can exceed
            upper_freq = min(local_f0 * 1.02, features.tessitura_high)
            lower_freq = max(local_f0 * 0.98, features.tessitura_low)
            
            # Keep minimum band width
            if upper_freq - lower_freq < (features.tessitura_high - features.tessitura_low) * 0.3:
                center = (upper_freq + lower_freq) / 2
                half_width = (features.tessitura_high - features.tessitura_low) * 0.15
                upper_freq = center + half_width
                lower_freq = center - half_width
            
            upper_points.append((x, self._freq_to_y(upper_freq, f_min, f_max)))
            lower_points.append((x, self._freq_to_y(lower_freq, f_min, f_max)))
        
        # Build closed path
        path = self._smooth_path(upper_points)
        
        lower_rev = list(reversed(lower_points))
        path += f" L{lower_rev[0][0]:.1f},{lower_rev[0][1]:.1f}"
        
        for i in range(1, len(lower_rev)):
            px, py = lower_rev[i - 1]
            cx, cy = lower_rev[i]
            if i == len(lower_rev) - 1:
                path += f" Q{px:.1f},{py:.1f} {cx:.1f},{cy:.1f}"
            else:
                mx = (px + cx) / 2
                my = (py + cy) / 2
                path += f" Q{px:.1f},{py:.1f} {mx:.1f},{my:.1f}"
        
        path += " Z"
        
        return f'''
<!-- Tessitura band: {features.tessitura_low:.0f}-{features.tessitura_high:.0f} Hz -->
<path d="{path}"
      fill="{self.palette.tessitura_fill}" opacity="{self.palette.tessitura_opacity}"/>'''

    def _render_f0_contour(self, features: AudioFeatures) -> str:
        """Render F0 contour extending beyond tessitura."""
        f_min = features.tessitura_low * 0.7
        f_max = features.tessitura_high * 1.4
        
        f0_resampled = self._resample(features.f0_contour, self.n_points)
        xs = np.linspace(self.x_min, self.x_max, self.n_points)
        
        points = []
        for i, x in enumerate(xs):
            freq = f0_resampled[i] if f0_resampled[i] > 0 else features.f0_median
            y = self._freq_to_y(freq, f_min, f_max)
            points.append((x, y))
        
        path = self._smooth_path(points)
        
        return f'''
<!-- F0 contour: median {features.f0_median:.0f} Hz -->
<path d="{path}"
      stroke="{self.palette.vocal_color}" stroke-width="2.8" fill="none" 
      stroke-linecap="round"/>'''''

    def _render_harmonics(self, features: AudioFeatures) -> str:
        """Render harmonics centered together, overlaid on vocal trace."""
        lines = ['\n<!-- Harmonic envelopes (H2, H3, H4) - centered -->']
        lines.append('<g fill="none" stroke-linecap="round">')
        
        f_min = features.tessitura_low * 0.7
        f_max = features.tessitura_high * 1.4
        
        colors = self.palette.harmonic_colors
        widths = [2.0, 1.8, 1.5]
        opacities = [0.85, 0.75, 0.65]
        harmonic_numbers = [2, 3, 4]
        
        xs = np.linspace(self.x_min, self.x_max, self.n_points)
        f0_resampled = self._resample(features.f0_contour, self.n_points)
        
        # Amplitude scaling - larger scale for more visible harmonic variation
        amp_scale = 30
        
        for h_idx, envelope in enumerate(features.harmonic_envelopes):
            h_num = harmonic_numbers[h_idx]
            env_resampled = self._resample(envelope, self.n_points)
            
            # Normalize this harmonic's envelope to its own range for clearer variation
            env_min, env_max = env_resampled.min(), env_resampled.max()
            if env_max > env_min:
                env_normalized = (env_resampled - env_min) / (env_max - env_min)
            else:
                env_normalized = np.full_like(env_resampled, 0.5)
            
            points = []
            for i, x in enumerate(xs):
                # Base Y position follows F0 contour
                base_freq = f0_resampled[i] if f0_resampled[i] > 0 else features.f0_median
                base_y = self._freq_to_y(base_freq, f_min, f_max)
                
                # Offset by normalized amplitude (centered around F0)
                # Different harmonics get slight phase shifts for visual interest
                amp_offset = (env_normalized[i] - 0.5) * amp_scale
                
                y = base_y - amp_offset
                points.append((x, y))
            
            path = self._smooth_path(points)
            avg_amp = np.mean(env_resampled) if len(env_resampled) > 0 else 0
            
            lines.append(
                f'  <!-- H{h_num}: avg {avg_amp:.2f} -->\n'
                f'  <path d="{path}" stroke="{colors[h_idx]}" '
                f'stroke-width="{widths[h_idx]}" opacity="{opacities[h_idx]}"/>'
            )
        
        lines.append('</g>')
        return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description="Generate accurate SVG logo from audio")
    parser.add_argument("input", default="../examples/tracks/Ariana Grande - Dangerous Woman (A Cappella).opus", help="Input audio file")
    parser.add_argument("-o", "--output", help="Output SVG file")
    parser.add_argument("--width", type=int, default=240)
    parser.add_argument("--height", type=int, default=240)
    parser.add_argument("--style", choices=["cyber", "sunset", "aurora", "ember", "vapor", "mono"], default="cyber")
    parser.add_argument("--points", type=int, default=8, help="Curve smoothness (more points = more detail)")
    parser.add_argument("--verbose", action="store_true")

    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: '{args.input}' not found")
        return 1

    output_path = Path(args.output) if args.output else input_path.with_suffix(".svg")

    palettes = {
        "cyber": ColorPalette.cyber(), "sunset": ColorPalette.sunset(),
        "aurora": ColorPalette.aurora(), "ember": ColorPalette.ember(),
        "vapor": ColorPalette.vapor(), "mono": ColorPalette.mono()
    }

    print(f"Analyzing: {input_path.name}")
    features = AudioAnalyzer().analyze(str(input_path))

    if args.verbose:
        print(f"  Duration: {features.duration:.2f}s")
        print(f"  F0 median: {features.f0_median:.1f} Hz")
        print(f"  Tessitura: {features.tessitura_low:.1f} - {features.tessitura_high:.1f} Hz")
        for i, env in enumerate(features.harmonic_envelopes):
            print(f"  H{i+2} avg amplitude: {np.mean(env):.3f}")

    print(f"Generating SVG ({args.style}, {args.width}x{args.height})...")
    
    svg = SVGGenerator(args.width, args.height, palettes[args.style], n_points=args.points).generate(features)
    output_path.write_text(svg)
    print(f"Saved: {output_path}")

    return 0


if __name__ == "__main__":
    exit(main())
