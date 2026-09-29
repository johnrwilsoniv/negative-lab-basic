"""Synthetic 'phone photo of a negative on a lightbox' for tests."""
import numpy as np


def make_negative(window=(113, 165, 670, 458), size=(1008, 756), grain=0.08, rebate=0, seed=0):
    """Dark mount, sprocket dashes above/below, bright film window.

    Window content is a left-to-right ramp (0.4 -> 0.8) so flips are detectable.
    `rebate` rows at the top of the window are clear film base (0.95).
    """
    rng = np.random.default_rng(seed)
    width, height = size
    img = np.full((height, width), 0.04, np.float32)
    x, y, w, h = window
    for sy in (y - 60, y + h + 25):
        for sx in range(x, x + w, 60):
            img[max(sy, 0):max(sy + 35, 0), sx:sx + 30] = 0.9
    patch = np.tile(np.linspace(0.4, 0.8, w, dtype=np.float32), (h, 1))
    if grain:
        patch += rng.normal(0, grain, (h, w)).astype(np.float32)
    if rebate:
        patch[:rebate] = 0.95
    img[y:y + h, x:x + w] = np.clip(patch, 0, 1)
    return np.repeat(img[..., None], 3, axis=2)
