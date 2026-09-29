"""Negative -> neutral grayscale positive."""
import numpy as np

from nlb.detect import luma

__all__ = ["luma", "to_positive"]


def to_positive(neg_rgb: np.ndarray, low_pct: float = 0.1, high_pct: float = 99.9,
                gamma: float = 1.0) -> np.ndarray:
    """Luma, invert, stretch percentiles to [0, 1], then out ** (1 / gamma)."""
    g = (1.0 - luma(neg_rgb)).astype(np.float32)
    lo, hi = (float(v) for v in np.percentile(g, [low_pct, high_pct]))  # py floats keep float32
    if hi - lo < 1e-6:
        return np.zeros_like(g)
    out = np.clip((g - lo) / (hi - lo), 0.0, 1.0)
    if gamma != 1.0:
        out = out ** np.float32(1.0 / gamma)
    return out
