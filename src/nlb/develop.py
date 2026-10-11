"""Raw negative -> positive, for the studio. Contract: docs/superpowers/plans/2026-10-10-develop-engine.md.

lin (linear camera RGB) -> flat-field -> geometry -> minus flare -> density above the film
base -> per-channel levels (per frame, or locked to the roll) -> saturation, temperature,
tint, exposure -> print-like S-curve -> sRGB. Internals live in `nlb.engine`.
"""
from pathlib import Path

import cv2
import numpy as np
import rawpy

from nlb.engine import calibrate as cal
from nlb.engine import tone
from nlb.engine.view import crop_px, rotate90, warp, warp_grid

PARAMS = [
    {"key": "exposure", "label": "Exposure", "min": -2.0, "max": 2.0, "step": 0.05, "default": 0.0},
    {"key": "contrast", "label": "Contrast", "min": -1.0, "max": 1.0, "step": 0.05, "default": 0.0},
    {"key": "temperature", "label": "Temperature", "min": -1.0, "max": 1.0, "step": 0.02, "default": 0.0},
    {"key": "tint", "label": "Tint", "min": -1.0, "max": 1.0, "step": 0.02, "default": 0.0},
    {"key": "saturation", "label": "Saturation", "min": 0.0, "max": 2.0, "step": 0.05, "default": 1.0},
]
LEVELS_VERSION = 1
CROP_INSET = 0.01      # auto_crop trims this fraction of the picture on each side
BASE_PATCH = 0.005     # sample_base: half-width of the median patch, fraction of the long side
FALLBACK_CROP = [0.05, 0.05, 0.9, 0.9]
MIN_ANGLE = 0.1        # auto_frame leaves smaller tilts alone, degrees
STRIP_ROWS = 256       # develop() works in strips of this many rows


def params_of(frame: dict) -> dict:
    """Every PARAMS value for `frame`, defaults filled in."""
    given = frame.get("params") or {}
    return {p["key"]: float(given.get(p["key"], p["default"])) for p in PARAMS}


def load_linear(path: Path, preview: bool = False) -> np.ndarray:
    """Linear camera RGB in [0, 1]: black subtracted, fixed white-level scale, no WB, sensor orientation."""
    with rawpy.imread(str(path)) as raw:
        rgb = raw.postprocess(half_size=preview, output_color=rawpy.ColorSpace.raw, gamma=(1, 1),
                              user_wb=[1.0, 1.0, 1.0, 1.0], no_auto_bright=True,
                              adjust_maximum_thr=0.0,  # LibRaw would otherwise rescale dim frames
                              output_bps=16, user_flip=0)
    lin = rgb.astype(np.float32)
    del rgb
    lin *= np.float32(1 / 65535)
    return lin


# --- calibration ---

def _film(settings: dict) -> str:
    return "bw" if settings.get("film") == "bw" else "c41"


def _gain(settings: dict) -> np.ndarray | None:
    ff = settings.get("flatfield")
    return np.asarray(ff["gain"], np.float32) if isinstance(ff, dict) and ff.get("gain") else None


def _view(lin: np.ndarray, settings: dict, frame: dict, region=None) -> np.ndarray:
    """Flat-fielded full view of `lin`, or `region` of it (full-view pixels)."""
    flip, angle = bool(settings.get("flip")), float(frame.get("angle", 0.0) or 0.0)
    img = warp(lin, flip, angle, region)
    gain = _gain(settings)
    if gain is not None:
        img = img / np.maximum(warp_grid(gain, lin.shape, flip, angle, region), 0.05)
    return img


_CAL_CACHE: dict[tuple, cal.Calibration] = {}  # the studio re-develops one lin per slider move
_CAL_CACHE_SIZE = 4


def _calibration(lin: np.ndarray, settings: dict) -> cal.Calibration:
    """Light, base, flare and masks, from a flat-fielded sensor-space thumbnail."""
    gain = _gain(settings)
    fingerprint = float(lin[::97, ::89].sum(dtype=np.float64))
    key = (id(lin), lin.ctypes.data, lin.shape, fingerprint, _film(settings),
           None if gain is None else gain.tobytes())
    hit = _CAL_CACHE.get(key)
    if hit is not None:
        return hit
    thumb = cal.thumbnail(lin)
    if gain is not None:
        thumb = thumb / np.maximum(warp_grid(gain, thumb.shape, False, 0.0), 0.05)
    result = cal.calibrate(thumb, _film(settings))
    if len(_CAL_CACHE) >= _CAL_CACHE_SIZE:
        _CAL_CACHE.pop(next(iter(_CAL_CACHE)))
    _CAL_CACHE[key] = result
    return result


def _base_flare(lin: np.ndarray, settings: dict) -> tuple[np.ndarray, np.ndarray]:
    base, flare = settings.get("base"), settings.get("flare")
    c = None if base and flare is not None else _calibration(lin, settings)
    base = np.asarray(base, np.float32) if base else c.base
    flare = np.asarray(flare, np.float32) if flare is not None else c.flare
    return base, np.minimum(flare, 0.5 * base)


def auto_frame(lin: np.ndarray, settings: dict) -> dict:
    """Initial geometry: {"angle": deskew from the sprocket holes, "crop": picture in that view}.

    Proposed contract addition; auto_crop() is the angle-0 version. Never raises.
    """
    try:
        thumb = cal.thumbnail(lin)
        if settings.get("flip"):
            thumb = np.ascontiguousarray(thumb[:, ::-1])
        film = _film(settings)
        c = cal.calibrate(thumb, film)
        angle = cal.film_angle(c.hole) or 0.0
        if abs(angle) >= MIN_ANGLE:
            thumb = warp(thumb, False, angle)
            c = cal.calibrate(thumb, film)
        else:
            angle = 0.0
        box = cal.picture_box(thumb, c)
        if box is None:
            return {"angle": round(angle, 2), "crop": list(FALLBACK_CROP)}
        x, y, w, h = box
        ix, iy = CROP_INSET * w, CROP_INSET * h
        return {"angle": round(angle, 2),
                "crop": [round(v, 4) for v in (x + ix, y + iy, w - 2 * ix, h - 2 * iy)]}
    except Exception:  # a guess the user corrects by dragging; never fail the studio
        return {"angle": 0.0, "crop": list(FALLBACK_CROP)}


def auto_crop(lin: np.ndarray, settings: dict) -> list[float]:
    """Picture area as normalized [x, y, w, h] in full-view space with no deskew.

    For a tilted strip that's the largest box of the same aspect inside the tilted picture.
    """
    geo = auto_frame(lin, settings)
    x, y, w, h = geo["crop"]
    t = abs(np.radians(geo["angle"]))
    if t == 0:
        return geo["crop"]
    ih, iw = lin.shape[:2]
    pw, ph = w * iw, h * ih  # pixels, so the rotation sees the true aspect
    s = min(pw / (pw * np.cos(t) + ph * np.sin(t)), ph / (pw * np.sin(t) + ph * np.cos(t)))
    # the picture center rotates about the image center when the deskew is undone
    cx, cy = (x + w / 2) * iw - (iw - 1) / 2, (y + h / 2) * ih - (ih - 1) / 2
    a = np.radians(geo["angle"])
    ux = cx * np.cos(a) - cy * np.sin(a) + (iw - 1) / 2
    uy = cx * np.sin(a) + cy * np.cos(a) + (ih - 1) / 2
    nw, nh = w * s, h * s
    box = [ux / iw - nw / 2, uy / ih - nh / 2, nw, nh]
    return [round(float(v), 4) for v in box]


def sample_base(lin: np.ndarray, settings: dict, frame: dict, x: float, y: float) -> list[float]:
    """Film-base color under a click at normalized full-view (x, y): median of a small square."""
    h, w = lin.shape[:2]
    r = max(2, round(BASE_PATCH * max(h, w)))
    cx, cy = int(x * w), int(y * h)
    region = (max(cx - r, 0), max(cy - r, 0), min(cx + r + 1, w), min(cy + r + 1, h))
    if region[0] >= region[2] or region[1] >= region[3]:
        raise ValueError(f"({x}, {y}) is outside the image")
    patch = _view(lin, settings, frame, region).reshape(-1, 3)
    return [round(float(v), 6) for v in np.median(patch, axis=0)]


# --- levels ---

def _frame_levels(crop_lin: np.ndarray, base: np.ndarray, flare: np.ndarray, film: str) -> np.ndarray:
    """Per-channel levels over the crop, ignoring anything a sloppy crop drags in: pixels
    thinner than the base (holes, their halo) or as dark as the holder."""
    small = cal.thumbnail(crop_lin, tone.STATS_W)
    px = small.reshape(-1, 3)
    holder = (px[:, 0] < cal.HOLDER_FRAC * base[0]) & (px[:, 1] < cal.HOLDER_FRAC * base[1])
    valid = ~holder & (px < 1.1 * base).all(axis=1)
    if valid.mean() > 0.2:
        px = px[valid]
    return tone.levels(tone.density(px[:, None, :], base, flare, film), film)


def _crop_lin(lin: np.ndarray, settings: dict, frame: dict) -> np.ndarray:
    return _view(lin, settings, frame, crop_px(lin.shape, frame.get("crop") or FALLBACK_CROP))


def analyze_roll(samples: list[tuple[np.ndarray, dict]], settings: dict) -> dict | None:
    """One set of per-channel density levels for the roll: the median of the frames' own levels."""
    film = _film(settings)
    per_frame = []
    for lin, frame in samples:
        base, flare = _base_flare(lin, settings)
        per_frame.append(_frame_levels(_crop_lin(lin, settings, frame), base, flare, film))
    if not per_frame:
        return None
    lv = np.median(np.stack(per_frame), axis=0)
    return {"version": LEVELS_VERSION, "film": film, "frames": len(per_frame),
            "black": lv[0].round(5).tolist(), "white": lv[1].round(5).tolist()}


def _roll_levels(settings: dict, film: str) -> np.ndarray | None:
    lv = settings.get("levels")
    if not isinstance(lv, dict) or lv.get("version") != LEVELS_VERSION or lv.get("film") != film:
        return None  # stale (e.g. analyzed before switching film type): fall back to per-frame
    return np.asarray([lv["black"], lv["white"]], np.float32)


# --- develop ---

def develop(lin: np.ndarray, settings: dict, frame: dict, view: str = "crop") -> np.ndarray:
    """Display-ready sRGB [0, 1], H x W x 3 float32. view: "crop" | "full" | "negative"."""
    if view == "negative":
        img = _view(lin, settings, frame)  # balanced on the bare light: holes white, base orange
        light = np.maximum(_calibration(lin, settings).light, 1e-6)
        return _srgb(np.clip(img * (1.0 / light).astype(np.float32), 0.0, 1.0))
    if view not in ("crop", "full"):
        raise ValueError(f"unknown view {view!r}")
    film = _film(settings)
    base, flare = _base_flare(lin, settings)
    crop = _crop_lin(lin, settings, frame)
    lv = _roll_levels(settings, film)
    if lv is None:
        lv = _frame_levels(crop, base, flare, film)
    if view == "full":
        img, rotation = _view(lin, settings, frame), 0
    else:
        img, rotation = crop, int(frame.get("rotation", 0) or 0)
    del crop
    h, w = img.shape[:2]
    q = rotation // 90 % 4
    out = np.empty((w, h, 3) if q % 2 else (h, w, 3), np.float32)
    upright = np.rot90(out, q)  # a view: strips written here land rotated in `out`
    p = params_of(frame)
    for y in range(0, h, STRIP_ROWS):  # strips bound the full-res temporaries
        upright[y:y + STRIP_ROWS] = tone.render(tone.density(img[y:y + STRIP_ROWS], base, flare, film),
                                                lv, p, film)
    return out


def place(img: np.ndarray, settings: dict, frame: dict, view: str = "crop") -> np.ndarray:
    """The studio's geometry on an image that is already a positive, like darktable's.

    `img` is in sensor orientation and covers the same pixels as `load_linear`; no flat-field
    and no tone. view: "crop" | "full".
    """
    flip, angle = bool(settings.get("flip")), float(frame.get("angle", 0.0) or 0.0)
    if view == "full":
        return warp(img, flip, angle)
    if view != "crop":
        raise ValueError(f"unknown view {view!r}")
    region = crop_px(img.shape, frame.get("crop") or FALLBACK_CROP)
    return rotate90(warp(img, flip, angle, region), int(frame.get("rotation", 0) or 0))


def _srgb(x: np.ndarray) -> np.ndarray:
    x = np.ascontiguousarray(x, np.float32)
    curved = cv2.pow(x, 1 / 2.4) * np.float32(1.055) - np.float32(0.055)
    return np.where(x <= 0.0031308, x * np.float32(12.92), curved)


# --- capture helpers (proposed contract additions) ---

def exposure_report(lin: np.ndarray, settings: dict) -> dict:
    """How well a capture uses the sensor, for display after each shot.

    base_headroom: brightest base channel as a fraction of full scale (aim for 0.6-0.85).
    floor: densest picture value per channel (0.1st percentile of the film), and
    floor_over_flare: how far that sits above the veiling light (below ~3 is noisy and veiled),
    or None when no holder is visible to measure flare on.
    """
    c = _calibration(lin, settings)
    base = np.asarray(settings["base"], np.float32) if settings.get("base") else c.base
    film_px = cal.thumbnail(lin)[c.film] if c.film.any() else lin.reshape(-1, 3)[::97]
    floor = np.percentile(film_px, 0.1, axis=0)
    clipped = float((film_px >= 0.98).any(axis=1).mean())
    headroom = float(base.max())
    stops = float(np.log2(0.75 / max(headroom, 1e-4)))
    if clipped > 0.001 or headroom > 0.9:
        advice = f"film is clipping: shorten exposure by {max(-stops, 0.5):.1f} stops"
    elif headroom < 0.5:
        advice = f"underexposed: lengthen exposure by {stops:.1f} stops (holes may clip; that's fine)"
    else:
        advice = "ok"
    return {
        "base": [round(float(v), 5) for v in base],
        "base_headroom": round(headroom, 3),
        "light": [round(float(v), 4) for v in c.light],
        "flare": [round(float(v), 5) for v in c.flare],
        "floor": [round(float(v), 5) for v in floor],
        "floor_over_flare": ([round(float(f / fl), 1) for f, fl in zip(floor, c.flare)]
                             if (c.flare > 0).all() else None),  # None: no holder visible to measure
        "film_clipped": round(clipped, 4),
        "advice": advice,
    }


def make_flatfield(lin: np.ndarray) -> dict:
    """Bare-light frame (no film, not clipped) -> settings["flatfield"] value (add "file" alongside)."""
    return {"gain": cal.flatfield_grid(lin).round(4).tolist()}


# --- output ---

def write_tiff(path: Path, img: np.ndarray) -> None:
    """16-bit RGB TIFF with an embedded sRGB ICC profile."""
    import tifffile
    from PIL import ImageCms

    icc = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    u16 = (np.clip(img, 0.0, 1.0) * 65535.0 + 0.5).astype(np.uint16)
    tifffile.imwrite(path, u16, photometric="rgb", compression="zlib", predictor=True,
                     compressionargs={"level": 4}, extratags=[(34675, "B", len(icc), icc, True)])
