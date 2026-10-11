"""Density -> display: per-channel levels, color, print-like tone curve, sRGB encoding.

Density D = log10(base / lin) is linear in log exposure on the film's straight-line
section, so a per-channel affine map of D (the levels) is a white balance plus a per-layer
contrast match, and the S-curve on top plays the part of the printing paper.
"""
import cv2
import numpy as np

EPS = 1e-6
LN10 = float(np.log(10.0))
STATS_W = 512                             # levels are measured on a crop resized to this width
LEVEL_PCT = {"c41": (0.2, 99.8), "bw": (0.1, 99.9)}
STOP = 0.6 * float(np.log10(2.0))         # density per stop at a C-41 / B&W negative gamma of ~0.6
COLOR_SHIFT = 0.1                         # density per unit of temperature or tint
CURVE_SLOPE = 5.0                         # logistic steepness at contrast 0
CURVE_MARGIN = 0.06                       # n reaches 0 and 1 this far outside the levels
BW_WEIGHTS = np.float32([0.25, 0.5, 0.25])
FLARE_MAX_CUT = 0.75                      # flare subtraction removes at most this much of a pixel


def density(lin: np.ndarray, base: np.ndarray, flare: np.ndarray, film_type: str) -> np.ndarray:
    """H x W x 3 linear camera RGB -> density above base (H x W x 1 for B&W).

    Flare comes off every pixel, but never more than FLARE_MAX_CUT of it: in the densest
    areas the signal sits near the flare level and noise would otherwise blow up to EPS.
    """
    flare = np.asarray(flare, np.float32)
    base = np.maximum(np.asarray(base, np.float32) - flare, EPS)
    lin = np.maximum(lin - flare, lin * np.float32(1 - FLARE_MAX_CUT))
    if film_type == "bw":
        lin = (lin @ BW_WEIGHTS)[..., None]
        base = np.float32([float(base @ BW_WEIGHTS)])
    t = cv2.log(np.maximum(lin, EPS)).reshape(lin.shape)  # keeps a trailing 1-channel axis
    return ((np.log(base).astype(np.float32) - t) * np.float32(1 / LN10)).astype(np.float32)


def levels(dens_small: np.ndarray, film_type: str) -> np.ndarray:
    """2 x C: per-channel (black, white) density points, from robust percentiles."""
    lo_pct, hi_pct = LEVEL_PCT.get(film_type, LEVEL_PCT["c41"])
    px = dens_small.reshape(-1, dens_small.shape[-1])
    lv = np.percentile(px, (lo_pct, hi_pct), axis=0).astype(np.float32)
    lv[1] = np.maximum(lv[1], lv[0] + 0.05)  # flat frame: don't blow noise up into full range
    return lv


def render(dens: np.ndarray, lv: np.ndarray, p: dict, film_type: str) -> np.ndarray:
    """Density -> sRGB-encoded [0, 1]. `p` holds the PARAMS values."""
    lo, hi = lv[0].astype(np.float64), lv[1].astype(np.float64)
    shift = np.zeros(dens.shape[-1])
    shift += p["exposure"] * STOP
    if film_type != "bw":
        t, g = p["temperature"] * COLOR_SHIFT, p["tint"] * COLOR_SHIFT
        shift += np.array([t, -g, -t])
    # n = (D + shift - lo) / (hi - lo): normalized log exposure, 0 = black point, 1 = white point
    scale = 1.0 / (hi - lo)
    offset = (shift - lo) * scale
    c = dens.shape[-1]
    if c == 3:
        sat = np.float64(p["saturation"])
        m = np.full((3, 3), (1.0 - sat) / 3.0) + np.eye(3) * sat  # saturation about the channel mean
        a = np.hstack([m * scale[None, :], (m @ offset)[:, None]])
        n = cv2.transform(dens, a.astype(np.float32))
    else:
        n = dens[..., 0] * np.float32(scale[0]) + np.float32(offset[0])
    out = curve(n, p["contrast"])
    if c == 1:
        out = cv2.merge([out, out, out])
    return out


def curve(n: np.ndarray, contrast: float) -> np.ndarray:
    """Print-like S-curve on normalized log exposure, straight to sRGB-encoded output.

    A logistic around n = 0.5, rescaled so n = -CURVE_MARGIN -> 0 and 1 + CURVE_MARGIN -> 1:
    soft toe and shoulder, highlights roll off instead of clipping at the white point.
    """
    k = CURVE_SLOPE * float(2.0 ** contrast)
    lo_v = 1.0 / (1.0 + np.exp(k * (0.5 + CURVE_MARGIN)))
    hi_v = 1.0 / (1.0 + np.exp(-k * (0.5 + CURVE_MARGIN)))
    e = cv2.exp(np.float32(-k) * (n - np.float32(0.5)))
    v = 1.0 / (1.0 + e)
    return np.clip((v - np.float32(lo_v)) * np.float32(1.0 / (hi_v - lo_v)), 0.0, 1.0)
