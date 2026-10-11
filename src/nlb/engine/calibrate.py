"""Measurements on a small sensor-space thumbnail: bare light, film base, flare, picture area.

A capture shows four things: the dark holder, the bare light through the sprocket holes,
the clear film base (rebate) and the picture. All measurements run on an INTER_AREA
thumbnail of fixed width, so preview and full-resolution decodes measure the same values.
"""
from dataclasses import dataclass

import cv2
import numpy as np

from nlb.engine.view import warp

THUMB_W = 800
HOLE_FRAC = {"c41": 0.5, "bw": 0.9}  # bare light: every channel above this fraction of the light
HOLDER_FRAC = 0.08                    # holder: R and G below this fraction of the base
FLARE_BAND = (0.0125, 0.025)          # holder band sampled for flare, in image widths from the film
PICTURE_DENSITY = 0.05                # picture vs rebate, density above base
EPS = 1e-6
HOLE_ROW_MIN = 5                      # sprocket_rows: holes needed in a row
HOLE_ROW_OFF = 0.003                  # ... median distance from the row's line, in image widths
HOLE_PITCH_CV = 0.1                   # ... spread of the hole pitch, relative to the pitch
EDGE_SPAN = 0.7                       # outline fits use the central part of each side
REBATE_MAX = (0.06, 0.025)            # trim_rebate: deepest band along the long, short sides
REBATE_STEP = 0.03                    # ... density rise across 2 px that marks the picture edge
REBATE_COLS = 0.6                     # ... fraction of the side that must rise together
REBATE_MIN_PX = 150                   # window_rebate: rebate pixels needed to trust it as the base
REBATE_THINNER = 0.02                 # ... most picture allowed to be thinner than that rebate


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
    """Thumbnail of the flat-fielded sensor image -> light, base, flare and masks.

    The base is the brightest film away from the holes, or, through a carrier that shows
    no bare light, the rebate at the window's edges (see window_rebate).
    """
    r, g, b = cv2.split(thumb)
    light = np.maximum(np.percentile(thumb.reshape(-1, 3)[::4], 99.9, axis=0), EPS).astype(np.float32)
    f = HOLE_FRAC.get(film_type, 0.5)
    hole = (r > f * light[0]) & (g > f * light[1]) & (b > f * light[2])
    k = max(1, round(0.006 * thumb.shape[1]))
    near_hole = cv2.dilate(hole.astype(np.uint8), _disk(2 * k)).astype(bool)
    film = _largest_component(~(g < 0.05 * light[1]) & ~hole)
    film = cv2.erode(film.astype(np.uint8), _disk(k)).astype(bool) & ~near_hole
    base = _brightest_plateau(thumb, film) if film.sum() > 100 else light.copy()
    rebate = window_rebate(thumb, hole)
    if rebate is not None:  # a carrier capture: rebate and thin picture pass for bare light
        base = rebate

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


def sprocket_rows(hole: np.ndarray) -> tuple[bool, list[np.ndarray]] | None:
    """(vertical, rows of (along, across) hole centroids) for a credible strip of sprocket holes.

    Holes are blobs of similar size strung along the film's long edges at a fixed pitch. Bright
    picture detail that clears the hole threshold (a carrier that masks the holes, a frame with
    no bare light to compare against) makes blobs too, but never a straight, evenly spaced row.
    None unless at least one row of HOLE_ROW_MIN holes passes that test.
    """
    n, _, stats, cents = cv2.connectedComponentsWithStats(hole.astype(np.uint8), connectivity=8)
    area = stats[1:, cv2.CC_STAT_AREA].astype(float)
    cents = cents[1:]
    if area.size < HOLE_ROW_MIN:
        return None
    keep = (area > 0.3 * np.median(area)) & (area < 3.0 * np.median(area)) & (area >= 6)
    pts = cents[keep]
    if len(pts) < HOLE_ROW_MIN:
        return None
    vertical = np.ptp(pts[:, 1]) > np.ptp(pts[:, 0])  # strip runs top to bottom
    along, across = (pts[:, 1], pts[:, 0]) if vertical else (pts[:, 0], pts[:, 1])
    # two rows: split the cross-strip coordinate at its largest gap
    order = np.argsort(across)
    gaps = np.diff(across[order])
    groups = [order]
    if gaps.size and gaps.max() > 0.1 * hole.shape[0 if not vertical else 1]:
        cut = int(np.argmax(gaps)) + 1
        groups = [order[:cut], order[cut:]]
    rows = []
    for idx in groups:
        if len(idx) < HOLE_ROW_MIN or np.ptp(along[idx]) == 0:
            continue
        a, c = along[idx], across[idx]
        off = np.abs(c - np.polyval(np.polyfit(a, c, 1), a))
        pitch = np.diff(np.sort(a))
        if np.median(off) < HOLE_ROW_OFF * hole.shape[1] and pitch.std() < HOLE_PITCH_CV * pitch.mean():
            rows.append(np.stack([a, c], axis=1))
    return (bool(vertical), rows) if rows else None


def film_angle(hole: np.ndarray) -> float | None:
    """Deskew angle in degrees (counter-clockwise positive) that levels the sprocket-hole rows.

    A line fitted through each credible row of holes (see sprocket_rows) gives the tilt.
    None when no such row is visible.
    """
    found = sprocket_rows(hole)
    if found is None:
        return None
    vertical, rows = found
    slopes = [np.polyfit(r[:, 0], r[:, 1], 1)[0] for r in rows]
    angle = float(np.degrees(np.arctan(np.average(slopes, weights=[len(r) for r in rows]))))
    # horizontal strip sloping down to the right needs a counter-clockwise turn (+);
    # a vertical strip leaning right at the bottom (x grows with y) needs a clockwise one (-)
    return -angle if vertical else angle


# --- lit window: the bright area the holder or carrier leaves open ---

def lit_region(thumb: np.ndarray) -> np.ndarray:
    """Mask of the largest lit area (the film strip, or the window a carrier leaves open).

    Otsu on log brightness splits the dark holder from anything the light comes through.
    A small opening cuts thin bridges to stray lit bits (holes beyond a carrier's edge,
    glints on its walls); enclosed dark picture detail is filled in.
    """
    g = cv2.log(np.maximum(thumb.mean(axis=2), EPS).astype(np.float32))
    lo, hi = np.percentile(g, (1, 99.5))
    if hi - lo < 1e-3:
        return np.zeros(g.shape, bool)
    u8 = np.clip((g - lo) * (255 / (hi - lo)), 0, 255).astype(np.uint8)
    _, lit = cv2.threshold(u8, 0, 1, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    lit = cv2.morphologyEx(lit, cv2.MORPH_OPEN, _disk(max(1, round(0.004 * thumb.shape[1]))))
    region = _largest_component(lit.astype(bool))
    n, lab = cv2.connectedComponents((~region).astype(np.uint8), connectivity=4)
    outside = np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))
    return region | ((lab > 0) & ~np.isin(lab, outside))


def _sides(region: np.ndarray) -> dict:
    """side -> (positions, edge coordinate per position, valid) over the central EDGE_SPAN.

    top/bottom are first/last lit rows per column, left/right first/last lit columns per row.
    An edge that touches the image border isn't the region's own edge, so it's not valid.
    """
    h, w = region.shape
    ys, xs = np.nonzero(region)
    m = (1 - EDGE_SPAN) / 2
    cx = np.arange(int(xs.min() + m * np.ptp(xs)), int(xs.max() - m * np.ptp(xs)) + 1)
    cy = np.arange(int(ys.min() + m * np.ptp(ys)), int(ys.max() - m * np.ptp(ys)) + 1)
    cols, rows = region[:, cx], region[cy, :]
    top = np.argmax(cols, axis=0)
    bottom = h - 1 - np.argmax(cols[::-1], axis=0)
    left = np.argmax(rows, axis=1)
    right = w - 1 - np.argmax(rows[:, ::-1], axis=1)
    hc, hr = cols.any(axis=0), rows.any(axis=1)
    return {"top": (cx, top, hc & (top > 0)), "bottom": (cx, bottom, hc & (bottom < h - 1)),
            "left": (cy, left, hr & (left > 0)), "right": (cy, right, hr & (right < w - 1))}


def _robust_line(t: np.ndarray, v: np.ndarray) -> tuple[float, float, int]:
    """Line v = a t + b after dropping outliers (notches, glints); and the inlier count."""
    keep = np.ones(t.size, bool)
    for _ in range(3):
        a, b = np.polyfit(t[keep], v[keep], 1)
        r = np.abs(v - (a * t + b))
        keep = r < 3 * (np.median(r[keep]) + 0.5)
    return float(a), float(b), int(keep.sum())


def _edge_lines(region: np.ndarray) -> dict:
    """side -> (slope, intercept, inliers, (t_min, t_max)) for each side with enough clean edge."""
    lines = {}
    if not region.any():
        return lines
    for side, (t, v, ok) in _sides(region).items():
        if ok.sum() >= 20:
            tt = t[ok].astype(float)
            lines[side] = (*_robust_line(tt, v[ok].astype(float)), (tt.min(), tt.max()))
    return lines


def outline_angle(region: np.ndarray) -> float | None:
    """Deskew angle (degrees, counter-clockwise positive) that squares up the region's edges.

    Lines through the four sides, weighted by how much of each side is a clean edge. None
    when no side has enough of an edge to fit.
    """
    lines = _edge_lines(region)
    angles = [-np.degrees(np.arctan(a)) if side in ("left", "right") else np.degrees(np.arctan(a))
              for side, (a, _, _, _) in lines.items()]
    weights = [n for _, _, n, _ in lines.values()]
    return float(np.average(angles, weights=weights)) if angles else None


def window_box(region: np.ndarray) -> tuple[float, float, float, float] | None:
    """Normalized [x, y, w, h] of the axis-aligned box inside a squared-up lit region.

    Each side is a robust line through that edge, so a notch (dense picture at the edge, a
    glint) that covers less than half of it is ignored; the box takes the line's inner end,
    which keeps slight keystone outside. None unless all four sides are found.
    """
    lines = _edge_lines(region)
    if len(lines) < 4:
        return None
    inner = {}
    for side, (a, b, _, ends) in lines.items():
        at_ends = [a * t + b for t in ends]
        inner[side] = max(at_ends) if side in ("top", "left") else min(at_ends)
    h, w = region.shape
    x0, x1, y0, y1 = inner["left"] + 1, inner["right"], inner["top"] + 1, inner["bottom"]
    if x1 - x0 < 0.1 * w or y1 - y0 < 0.1 * h:
        return None
    return x0 / w, y0 / h, (x1 - x0) / w, (y1 - y0) / h


def holes_on_film(hole: np.ndarray, region: np.ndarray) -> bool:
    """True when credible sprocket-hole rows lie on the lit film (not beyond a carrier's edge)."""
    found = sprocket_rows(hole)
    if found is None:
        return False
    vertical, rows = found
    pts = np.concatenate(rows).round().astype(int)
    x, y = (pts[:, 1], pts[:, 0]) if vertical else (pts[:, 0], pts[:, 1])
    return bool(region[y, x].mean() > 0.5)


def _px_box(shape: tuple, box) -> tuple[int, int, int, int]:
    h, w = shape[:2]
    x, y, bw, bh = box
    return round(x * w), round(y * h), round((x + bw) * w), round((y + bh) * h)


def _rebate_cuts(thumb: np.ndarray, box) -> dict:
    """side -> (rim, cut): rows from the box edge that are the carrier's soft edge, and that are
    trimmed in all (soft edge plus rebate). Each side's band is its central 80%."""
    x0, y0, x1, y1 = _px_box(thumb.shape, box)
    dens = -np.log10(np.maximum(thumb.mean(axis=2), EPS))
    landscape = x1 - x0 >= y1 - y0
    dx, dy = REBATE_MAX[1 if landscape else 0], REBATE_MAX[0 if landscape else 1]
    nx, ny = max(3, round(dx * (x1 - x0))), max(3, round(dy * (y1 - y0)))
    mx, my = round(0.1 * (x1 - x0)), round(0.1 * (y1 - y0))
    bands = {  # inward rows of each side
        "top": dens[y0:y0 + ny, x0 + mx:x1 - mx],
        "bottom": dens[y1 - 1:max(y1 - 1 - ny, 0):-1, x0 + mx:x1 - mx],
        "left": dens[y0 + my:y1 - my, x0:x0 + nx].T,
        "right": dens[y0 + my:y1 - my, x1 - 1:max(x1 - 1 - nx, 0):-1].T,
    }
    cuts = {}
    for side, band in bands.items():
        rim = cut = 0
        if band.shape[0] >= 3 and band.shape[1] > 0:
            step = band[2:] - band[:-2]
            # the soft edge of the carrier itself: thinner going inward, from the very first row
            falling = (step < -REBATE_STEP).mean(axis=1) > REBATE_COLS
            rim = int(np.argmin(falling)) if not falling.all() else falling.size
            cut = rim + 2 if rim else 0
            rising = (step[rim:] > REBATE_STEP).mean(axis=1)
            if rising.size and rising.max() > REBATE_COLS:
                cut = rim + int(np.argmax(rising)) + 2
        cuts[side] = (rim, cut)
    return cuts


def trim_rebate(thumb: np.ndarray, box: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    """Shrink a window box past the thin rebate a carrier's window may show around the picture.

    Rebate is the thinnest film, so going inward every column (or row) steps up in density
    where the picture starts, whatever the picture is. Each side moves past its strongest such
    step, if one is close enough to the edge: the film's long edges can show a band of rebate
    toward the sprocket holes, the gap between frames only a sliver. Rows still on the
    carrier's soft edge (getting thinner inward) are skipped first. No clear step: no trim.
    """
    h, w = thumb.shape[:2]
    c = {side: cut for side, (_, cut) in _rebate_cuts(thumb, box).items()}
    x0, y0, x1, y1 = _px_box(thumb.shape, box)
    x0, x1, y0, y1 = x0 + c["left"], x1 - c["right"], y0 + c["top"], y1 - c["bottom"]
    return x0 / w, y0 / h, (x1 - x0) / w, (y1 - y0) / h


def window_rebate(thumb: np.ndarray, hole: np.ndarray) -> np.ndarray | None:
    """Film base color from the rebate showing at a carrier window's edges, or None.

    None for a strip with its sprocket holes on the lit film (calibrate's own base is right
    there), when too little rebate shows, or when much of the picture is thinner than it
    (then it wasn't rebate).
    """
    region = lit_region(thumb)
    if not region.any() or holes_on_film(hole, region):
        return None
    angle = outline_angle(region)
    if angle:
        thumb = warp(thumb, False, angle)
        region = lit_region(thumb)
    box = window_box(region)
    if box is None:
        return None
    x0, y0, x1, y1 = _px_box(thumb.shape, box)
    mx, my = round(0.1 * (x1 - x0)), round(0.1 * (y1 - y0))
    px = []
    for side, (rim, cut) in _rebate_cuts(thumb, box).items():
        a, b = rim + 1, cut - 2  # clear of both transitions
        if b - a < 1:
            continue
        if side == "top":
            px.append(thumb[y0 + a:y0 + b, x0 + mx:x1 - mx])
        elif side == "bottom":
            px.append(thumb[y1 - b:y1 - a, x0 + mx:x1 - mx])
        elif side == "left":
            px.append(thumb[y0 + my:y1 - my, x0 + a:x0 + b])
        else:
            px.append(thumb[y0 + my:y1 - my, x1 - b:x1 - a])
    px = np.concatenate([p.reshape(-1, 3) for p in px]) if px else np.empty((0, 3), np.float32)
    if len(px) < REBATE_MIN_PX:
        return None
    rebate = np.median(px, axis=0).astype(np.float32)
    tx0, ty0, tx1, ty1 = _px_box(thumb.shape, trim_rebate(thumb, box))
    picture = thumb[ty0:ty1, tx0:tx1].reshape(-1, 3)
    if picture.size == 0 or (picture > 1.05 * rebate).all(axis=1).mean() > REBATE_THINNER:
        return None
    return rebate
