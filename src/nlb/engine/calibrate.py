"""Measurements on a small sensor-space thumbnail: bare light, film base, flare, picture area.

A capture shows four things: the dark holder, the bare light through the sprocket holes,
the clear film base (rebate) and the picture. All measurements run on an INTER_AREA
thumbnail of fixed width, so preview and full-resolution decodes measure the same values.
"""
from dataclasses import dataclass

import cv2
import numpy as np

THUMB_W = 800
HOLE_FRAC = {"c41": 0.5, "bw": 0.9}  # bare light: every channel above this fraction of the light
HOLDER_FRAC = 0.08                    # holder: R and G below this fraction of the base
FLARE_BAND = (0.0125, 0.025)          # holder band sampled for flare, in image widths from the film
PICTURE_DENSITY = 0.05                # picture vs rebate, density above base
EPS = 1e-6


@dataclass
class Calibration:
    light: np.ndarray     # (3,) bare light (sprocket holes), 99.9th percentile
    base: np.ndarray      # (3,) film base, before flare subtraction
    flare: np.ndarray     # (3,) veiling light, measured on the holder next to the film
    film: np.ndarray      # thumbnail mask: film (picture + rebate), away from holes and holder
    hole: np.ndarray      # thumbnail mask: bare light
    holder: np.ndarray    # thumbnail mask: holder


def thumbnail(img: np.ndarray, width: int = THUMB_W) -> np.ndarray:
    if img.shape[1] <= width:
        return np.ascontiguousarray(img, np.float32)
    h = max(1, round(img.shape[0] * width / img.shape[1]))
    return cv2.resize(img, (width, h), interpolation=cv2.INTER_AREA)


def _largest_component(mask: np.ndarray) -> np.ndarray:
    n, lab, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=4)
    if n <= 1:
        return np.zeros_like(mask)
    return lab == 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))


def _disk(r: int) -> np.ndarray:
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))


def calibrate(thumb: np.ndarray, film_type: str = "c41") -> Calibration:
    """Thumbnail of the flat-fielded sensor image -> light, base, flare and masks."""
    r, g, b = cv2.split(thumb)
    light = np.maximum(np.percentile(thumb.reshape(-1, 3)[::4], 99.9, axis=0), EPS).astype(np.float32)
    f = HOLE_FRAC.get(film_type, 0.5)
    hole = (r > f * light[0]) & (g > f * light[1]) & (b > f * light[2])
    k = max(1, round(0.006 * thumb.shape[1]))
    near_hole = cv2.dilate(hole.astype(np.uint8), _disk(2 * k)).astype(bool)
    film = _largest_component(~(g < 0.05 * light[1]) & ~hole)
    film = cv2.erode(film.astype(np.uint8), _disk(k)).astype(bool) & ~near_hole
    base = _brightest_plateau(thumb, film) if film.sum() > 100 else light.copy()

    holder = (r < HOLDER_FRAC * base[0]) & (g < HOLDER_FRAC * base[1])
    flare = np.zeros(3, np.float32)
    if holder.any() and not holder.all():
        dist = cv2.distanceTransform(holder.astype(np.uint8), cv2.DIST_L2, 5) / thumb.shape[1]
        band = holder & (dist >= FLARE_BAND[0]) & (dist < FLARE_BAND[1])
        if band.sum() > 0.002 * holder.size:
            flare = np.median(thumb[band], axis=0).astype(np.float32)
    return Calibration(light, base, np.minimum(flare, 0.5 * base), film, hole, holder)


def _brightest_plateau(thumb: np.ndarray, film: np.ndarray) -> np.ndarray:
    """Film base: median color of the brightest 2% of film pixels (the rebate is the thinnest film)."""
    px = thumb[film]
    bright = px[:, 0] * px[:, 1] * px[:, 2]
    return np.median(px[bright >= np.percentile(bright, 98)], axis=0).astype(np.float32)


def picture_box(thumb: np.ndarray, cal: Calibration) -> tuple[float, float, float, float] | None:
    """Normalized sensor-space [x, y, w, h] of the picture area, or None if nothing fits.

    Picture pixels are film at least PICTURE_DENSITY above the base in some channel (the
    rebate sits at the base; holes and holder are excluded). The box is the longest run of
    mostly-picture rows and columns, refined once inside the first guess.
    """
    dens = np.log10(np.maximum(cal.base - cal.flare, EPS) / np.maximum(thumb - cal.flare, EPS))
    picture = ~cal.hole & ~cal.holder & (dens.max(axis=2) > PICTURE_DENSITY)
    picture = cv2.morphologyEx(picture.astype(np.uint8), cv2.MORPH_OPEN, _disk(1)).astype(bool)
    h, w = picture.shape
    r0, r1, c0, c1 = 0, h, 0, w
    for _ in range(2):
        r0, r1 = _run(picture[:, c0:c1].mean(axis=1) > 0.5)
        if r1 - r0 < 0.1 * h:
            return None
        c0, c1 = _run(picture[r0:r1].mean(axis=0) > 0.5)
        if c1 - c0 < 0.1 * w:
            return None
    return c0 / w, r0 / h, (c1 - c0) / w, (r1 - r0) / h


def _run(mask: np.ndarray) -> tuple[int, int]:
    """Half-open (start, end) of the longest run of True; (0, 0) if none."""
    edges = np.flatnonzero(np.diff(np.concatenate([[0], mask.astype(np.int8), [0]])))
    if edges.size == 0:
        return 0, 0
    starts, ends = edges[::2], edges[1::2]
    i = int(np.argmax(ends - starts))
    return int(starts[i]), int(ends[i])


FLATFIELD_GRID = (32, 48)  # rows, columns


def flatfield_grid(lin: np.ndarray) -> np.ndarray:
    """Bare-light frame -> coarse per-channel gain grid, 1.0 at the brightest cell."""
    clipped = (lin.reshape(-1, 3)[::97] >= 0.99).any(axis=1).mean()
    if clipped > 0.005:
        raise ValueError(f"flat-field frame is clipped ({clipped:.1%} of pixels); shoot it darker")
    gh, gw = FLATFIELD_GRID
    if lin.shape[0] > lin.shape[1]:
        gh, gw = gw, gh
    grid = cv2.GaussianBlur(cv2.resize(lin, (gw, gh), interpolation=cv2.INTER_AREA), (3, 3), 0)
    peak = grid.reshape(-1, 3).max(axis=0)
    if (peak < 0.02).any():
        raise ValueError("flat-field frame is too dark to use")
    return (grid / peak).astype(np.float32)


def film_angle(hole: np.ndarray) -> float | None:
    """Deskew angle in degrees (counter-clockwise positive) that levels the sprocket-hole rows.

    Holes are blobs of similar size strung along the film's two long edges. Their centroids
    give the strip direction; a line fitted through each row gives the tilt. None when fewer
    than 4 holes are visible.
    """
    n, _, stats, cents = cv2.connectedComponentsWithStats(hole.astype(np.uint8), connectivity=8)
    area = stats[1:, cv2.CC_STAT_AREA].astype(float)
    cents = cents[1:]
    if area.size < 4:
        return None
    keep = (area > 0.3 * np.median(area)) & (area < 3.0 * np.median(area)) & (area >= 6)
    pts = cents[keep]
    if len(pts) < 4:
        return None
    vertical = np.ptp(pts[:, 1]) > np.ptp(pts[:, 0])  # strip runs top to bottom
    along, across = (pts[:, 1], pts[:, 0]) if vertical else (pts[:, 0], pts[:, 1])
    # two rows: split the cross-strip coordinate at its largest gap
    order = np.argsort(across)
    gaps = np.diff(across[order])
    rows = [order]
    if gaps.size and gaps.max() > 0.1 * hole.shape[0 if not vertical else 1]:
        cut = int(np.argmax(gaps)) + 1
        rows = [order[:cut], order[cut:]]
    slopes, weights = [], []
    for idx in rows:
        if len(idx) >= 3 and np.ptp(along[idx]) > 0:
            slopes.append(np.polyfit(along[idx], across[idx], 1)[0])
            weights.append(len(idx))
    if not slopes:
        return None
    angle = float(np.degrees(np.arctan(np.average(slopes, weights=weights))))
    # horizontal strip sloping down to the right needs a counter-clockwise turn (+);
    # a vertical strip leaning right at the bottom (x grows with y) needs a clockwise one (-)
    return -angle if vertical else angle
