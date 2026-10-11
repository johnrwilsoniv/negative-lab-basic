"""Capture-quality measurements for test shots: framing, tilt, light falloff, sharpness.

Everything is in sensor space (what live view shows), not the mirrored or deskewed view.
"""
import cv2
import numpy as np

from nlb.engine import calibrate as cal

MIN_HOLES = 2


def layout(thumb: np.ndarray, c: cal.Calibration) -> dict:
    """Where the picture, holes and holder are, and how the strip is tilted."""
    return {"picture": cal.strip_box(thumb, c), "angle": cal.film_angle(c.hole),
            "holes": float(c.hole.mean()), "holder": float(c.holder.mean()), "film": float(c.film.mean())}


def falloff(thumb: np.ndarray, c: cal.Calibration) -> dict | None:
    """Brightness of the clearest film (the rebate) in thirds along the strip and halves across it.

    The rebate runs the length of the strip on both sides, so the 98th percentile of the
    film in each slice is the base there: under an even light every slice reads the same.
    Values are relative to the brightest slice; axis "x" means the strip runs left to right.
    """
    ys, xs = np.nonzero(c.film)
    if ys.size < 2000:
        return None
    horizontal = np.ptp(xs) >= np.ptp(ys)
    v = thumb[..., int(np.argmax(c.base))][c.film]
    along, across = (xs, ys) if horizontal else (ys, xs)

    def slices(coord: np.ndarray, n: int) -> list[float] | None:
        idx = np.minimum(((coord - coord.min()) * n) // (np.ptp(coord) + 1), n - 1)
        out = []
        for i in range(n):
            part = v[idx == i]
            if part.size < 200:
                return None
            out.append(float(np.percentile(part, 98)))
        return out

    a, b = slices(along, 3), slices(across, 2)
    if a is None or b is None:
        return None
    top = max(a + b)
    return {"axis": "x" if horizontal else "y",
            "along": [round(x / top, 3) for x in a], "across": [round(x / top, 3) for x in b]}


def edge_width(lin: np.ndarray, light: np.ndarray, film_type: str) -> float | None:
    """Width in pixels of `lin` over which a sprocket-hole edge rises: smaller is sharper.

    The film is cut cleanly, so the hole edges are the one sharp, high-contrast detail every
    capture has. Width = step height / steepest slope (a ramp's width). Holes clip at a good
    exposure, which makes the edge read sharper than it is, so compare shots at the same
    exposure only. None when fewer than MIN_HOLES whole holes are in view.
    """
    f = cal.HOLE_FRAC.get(film_type, 0.5)
    hole = (lin > f * light).all(axis=2).astype(np.uint8)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(hole, connectivity=8)
    if n <= 1:
        return None
    h, w = hole.shape
    area = stats[1:, cv2.CC_STAT_AREA].astype(float)
    x0, y0 = stats[1:, cv2.CC_STAT_LEFT], stats[1:, cv2.CC_STAT_TOP]
    x1, y1 = x0 + stats[1:, cv2.CC_STAT_WIDTH], y0 + stats[1:, cv2.CC_STAT_HEIGHT]
    med = np.median(area)
    keep = ((area > 0.3 * med) & (area < 3.0 * med) & (area >= 50)
            & (x0 > 2) & (y0 > 2) & (x1 < w - 2) & (y1 < h - 2))  # whole holes only
    if keep.sum() < MIN_HOLES:
        return None
    holes = np.isin(lab, 1 + np.flatnonzero(keep)).astype(np.uint8)
    # the least clipped channel keeps the most of the edge's shape
    ch = int(np.argmin(np.percentile(lin[holes.astype(bool)][::7], 50, axis=0)))
    g = np.ascontiguousarray(lin[..., ch])
    inside = cv2.erode(holes, cal._disk(4)).astype(bool)
    ring = cv2.dilate(holes, cal._disk(10)).astype(bool) & ~cv2.dilate(holes, cal._disk(6)).astype(bool)
    if not inside.any() or not ring.any():
        return None
    step = float(np.median(g[inside]) - np.median(g[ring]))
    if step < 0.02:
        return None
    gx = cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3)
    grad = cv2.magnitude(gx, gy) / 8.0
    band = cv2.dilate(holes, cal._disk(3)).astype(bool) & ~cv2.erode(holes, cal._disk(3)).astype(bool)
    slope = float(np.percentile(grad[band], 90))
    return round(step / slope, 2) if slope > 0 else None
