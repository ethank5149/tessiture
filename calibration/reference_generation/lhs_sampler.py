"""Latin hypercube sampling utilities for calibration reference generation."""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np

ParameterRanges = Dict[str, Tuple[float, float]]

try:  # Optional dependency
    from pyDOE2 import lhs as _pydoe_lhs
except Exception:  # pragma: no cover - optional import
    _pydoe_lhs = None


def _latin_hypercube_numpy(n_samples: int, n_dims: int, seed: Optional[int]) -> np.ndarray:
    """Generate a Latin hypercube sample in [0, 1] using numpy only."""

    rng = np.random.default_rng(seed)
    cut = np.linspace(0.0, 1.0, n_samples + 1)
    u = rng.uniform(size=(n_samples, n_dims))
    a = cut[:n_samples]
    b = cut[1:]
    rdpoints = u * (b - a)[:, None] + a[:, None]
    sample = np.empty_like(rdpoints)
    for j in range(n_dims):
        order = rng.permutation(n_samples)
        sample[:, j] = rdpoints[order, j]
    return sample


def _normalize_ranges(ranges: ParameterRanges) -> List[Tuple[str, float, float]]:
    """Normalize and validate parameter ranges."""

    normalized: List[Tuple[str, float, float]] = []
    for name, bounds in ranges.items():
        if len(bounds) != 2:
            raise ValueError(f"Range for {name} must be (min, max).")
        low, high = float(bounds[0]), float(bounds[1])
        if high < low:
            raise ValueError(f"Range for {name} must satisfy min <= max.")
        normalized.append((name, low, high))
    return normalized


def lhs_sample(
    n_samples: int,
    ranges: ParameterRanges,
    seed: Optional[int] = None,
) -> List[Dict[str, float]]:
    """Sample parameters using Latin hypercube sampling.

    Args:
        n_samples: Number of samples to generate.
        ranges: Mapping of parameter name to (min, max).
        seed: Optional seed for reproducibility.

    Returns:
        List of parameter dictionaries with sampled float values.
    """

    if n_samples <= 0:
        raise ValueError("n_samples must be positive.")

    normalized = _normalize_ranges(ranges)
    names = [item[0] for item in normalized]
    lows = np.array([item[1] for item in normalized], dtype=float)
    highs = np.array([item[2] for item in normalized], dtype=float)

    if _pydoe_lhs is not None:
        unit = _pydoe_lhs(len(names), samples=n_samples, random_state=seed)
    else:
        unit = _latin_hypercube_numpy(n_samples, len(names), seed)

    scaled = lows + unit * (highs - lows)
    return [dict(zip(names, row.tolist())) for row in scaled]
