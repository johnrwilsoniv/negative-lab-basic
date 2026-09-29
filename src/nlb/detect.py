"""Locate the film frame in a phone photo of a negative on a lightbox.

The lightbox shows through the film as the largest bright rectangle; the mount
is dark and the sprocket strips are only ~50% bright, so row/column projection
profiles of a brightness mask isolate the frame window.
"""
from dataclasses import dataclass, field

import cv2
import numpy as np

WORK_WIDTH = 1008
LUMA_WEIGHTS = np.array([0.299, 0.587, 0.114], np.float32)


@dataclass(frozen=True)
class Box:
    x: int
    y: int
    w: int
    h: int

    def scale(self, s: float) -> "Box":
        return Box(round(self.x * s), round(self.y * s), round(self.w * s), round(self.h * s))


@dataclass
class Detection:
    box: Box
    flags: list[str] = field(default_factory=list)
    low_detail: float = 0.0


def luma(rgb: np.ndarray) -> np.ndarray:
    return rgb @ LUMA_WEIGHTS


def longest_run(mask: np.ndarray) -> tuple[int, int]:
    """Half-open (start, end) of the longest run of True; (0, 0) if none."""
    edges = np.flatnonzero(np.diff(np.concatenate([[0], mask.astype(np.int8), [0]])))
    if edges.size == 0:
        return 0, 0
    starts, ends = edges[::2], edges[1::2]
    i = int(np.argmax(ends - starts))
    return int(starts[i]), int(ends[i])


def low_detail_fraction(gray: np.ndarray) -> float:
    """Fraction of 32px blocks with no grain/detail (mean |Laplacian| < 2 on 0-255 gray)."""
    b = 32
    lap = np.abs(cv2.Laplacian(gray.astype(np.float64), cv2.CV_64F))
    h, w = lap.shape
    if h < b or w < b:
        return 1.0
    blocks = lap[: h // b * b, : w // b * b].reshape(h // b, b, w // b, b).mean(axis=(1, 3))
    return float((blocks < 2.0).mean())


def _window(mask: np.ndarray) -> Box | None:
    r0, r1 = longest_run(mask.mean(axis=1) > 0.5)
    if r1 <= r0:
        return None
    c0, c1 = longest_run(mask[r0:r1].mean(axis=0) > 0.6)
    if c1 <= c0:
        return None
    r0, r1 = longest_run(mask[:, c0:c1].mean(axis=1) > 0.9)
    if r1 <= r0:
        return None
    c0, c1 = longest_run(mask[r0:r1].mean(axis=0) > 0.75)
    if c1 <= c0:
        return None
    return Box(c0, r0, c1 - c0, r1 - r0)


def detect_frame(rgb: np.ndarray) -> Detection:
    height, width = rgb.shape[:2]
    scale = WORK_WIDTH / width
    gray8 = (np.clip(luma(rgb), 0, 1) * 255 + 0.5).astype(np.uint8)
    small = cv2.resize(gray8, (WORK_WIDTH, round(height * scale)), interpolation=cv2.INTER_AREA)
    gray = cv2.GaussianBlur(small, (5, 5), 0)
    otsu, _ = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    found = _window(gray > otsu * 0.5)
    if found is None:
        return Detection(Box(0, 0, width, height), ["detect_failed"], low_detail_fraction(gray))

    flags = []
    aspect = max(found.w, found.h) / min(found.w, found.h)
    area = found.w * found.h / gray.size
    if not (1.3 <= aspect <= 1.6) or not (0.20 <= area <= 0.75):
        flags.append("detect_suspect")
    low = low_detail_fraction(gray[found.y:found.y + found.h, found.x:found.x + found.w])
    if low > 0.5:
        flags.append("partial_or_blank")
    box = found.scale(1 / scale)
    box = Box(box.x, box.y, min(box.w, width - box.x), min(box.h, height - box.y))
    return Detection(box, flags, low)


def _edge_trim(profile: np.ndarray, threshold: float, limit: int, skip: int) -> int:
    """Lines to trim from the start of `profile`: skip a short dark remnant, then eat clear base."""
    i = 0
    while i < skip and profile[i] <= threshold:
        i += 1
    if i >= skip:
        return 0
    j = i
    while j < limit and profile[j] > threshold:
        j += 1
    return j


REBATE_SEGMENTS = 8


def _side_trim(lines: np.ndarray, threshold: float, limit: int, skip: int) -> int:
    """Median over segments along the edge, so a slightly tilted band still gets trimmed.

    `lines` is (depth, along): row 0 is the outermost line of this side.
    """
    n = lines.shape[1]
    trims = [
        _edge_trim(np.percentile(lines[:, k * n // REBATE_SEGMENTS:(k + 1) * n // REBATE_SEGMENTS],
                                 10, axis=1), threshold, limit, skip)
        for k in range(REBATE_SEGMENTS)
    ]
    return int(np.median(trims))


def trim_rebate(gray: np.ndarray, box: Box) -> Box:
    """Shrink `box` past bands of clear film base (bright, uniform) along its edges."""
    crop = gray[box.y:box.y + box.h, box.x:box.x + box.w]
    threshold = 0.75 * float(np.percentile(crop, 99.5))
    lh, lw = int(0.08 * box.h), int(0.08 * box.w)
    sh, sw = int(0.03 * box.h), int(0.03 * box.w)
    top = _side_trim(crop, threshold, lh, sh)
    bottom = _side_trim(crop[::-1], threshold, lh, sh)
    left = _side_trim(crop.T, threshold, lw, sw)
    right = _side_trim(crop.T[::-1], threshold, lw, sw)
    return Box(box.x + left, box.y + top, box.w - left - right, box.h - top - bottom)
