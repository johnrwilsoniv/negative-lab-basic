"""Crop box math and orientation transforms."""
import numpy as np

from nlb.detect import Box

ROTATIONS = ("none", "90cw", "90ccw", "180")
_ROT90_K = {"none": 0, "90cw": -1, "90ccw": 1, "180": 2}


def inset(box: Box, frac: float) -> Box:
    d = round(min(box.w, box.h) * frac)
    return Box(box.x + d, box.y + d, box.w - 2 * d, box.h - 2 * d)


def fit_3x2(box: Box) -> Box:
    """Largest exact 3:2 box with even sides, centered in `box`, oriented like `box`.

    Even sides keep HEIC encoders from padding the image.
    """
    if box.w >= box.h:
        u = min(box.w // 3, box.h // 2) // 2 * 2
        w, h = 3 * u, 2 * u
    else:
        u = min(box.w // 2, box.h // 3) // 2 * 2
        w, h = 2 * u, 3 * u
    return Box(box.x + (box.w - w) // 2, box.y + (box.h - h) // 2, w, h)


def flip_h(img: np.ndarray) -> np.ndarray:
    return np.ascontiguousarray(img[:, ::-1])


def rotate(img: np.ndarray, rotation: str) -> np.ndarray:
    if rotation not in _ROT90_K:
        raise ValueError(f"rotation must be one of {', '.join(ROTATIONS)}; got {rotation!r}")
    return np.ascontiguousarray(np.rot90(img, _ROT90_K[rotation]))
