"""Raw negative -> positive, for the studio. Contract: docs/superpowers/plans/2026-10-10-develop-engine.md.

v0: deliberately simple (density inversion with per-channel percentile levels); the
develop-engine work replaces the internals behind the same public names.
"""
from pathlib import Path

import cv2
import numpy as np
import rawpy

PARAMS = [
    {"key": "exposure", "label": "Exposure", "min": -2.0, "max": 2.0, "step": 0.05, "default": 0.0},
    {"key": "contrast", "label": "Contrast", "min": -1.0, "max": 1.0, "step": 0.05, "default": 0.0},
    {"key": "temperature", "label": "Temperature", "min": -1.0, "max": 1.0, "step": 0.02, "default": 0.0},
    {"key": "tint", "label": "Tint", "min": -1.0, "max": 1.0, "step": 0.02, "default": 0.0},
    {"key": "saturation", "label": "Saturation", "min": 0.0, "max": 2.0, "step": 0.05, "default": 1.0},
]
EPS = 1e-5
LEVEL_PCT = (0.5, 99.5)
LEVEL_SAMPLES = 1_000_000


def param(frame: dict, key: str) -> float:
    default = next(p["default"] for p in PARAMS if p["key"] == key)
    return float(frame.get("params", {}).get(key, default))


def load_linear(path: Path, preview: bool = False) -> np.ndarray:
    """Linear camera RGB in [0, 1]: no white balance, no gamma, sensor orientation."""
    with rawpy.imread(str(path)) as raw:
        rgb = raw.postprocess(half_size=preview, output_color=rawpy.ColorSpace.raw, gamma=(1, 1),
                              user_wb=[1.0, 1.0, 1.0, 1.0], no_auto_bright=True,
                              output_bps=16, user_flip=0)
    return rgb.astype(np.float32) / 65535.0


# --- geometry: full view = deskew(flip(lin)); crop view = rotate90(crop(full view)) ---

def full_view(img: np.ndarray, settings: dict, frame: dict) -> np.ndarray:
    if settings.get("flip"):
        img = img[:, ::-1]
    angle = float(frame.get("angle", 0.0))
    if angle:
        h, w = img.shape[:2]
        m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
        img = cv2.warpAffine(np.ascontiguousarray(img), m, (w, h), flags=cv2.INTER_LINEAR,
                             borderMode=cv2.BORDER_REPLICATE)
    return np.ascontiguousarray(img)


def crop_px(shape: tuple, crop: list[float]) -> tuple[int, int, int, int]:
    h, w = shape[:2]
    x, y, cw, ch = crop
    x0, y0 = int(round(x * w)), int(round(y * h))
    x1, y1 = int(round((x + cw) * w)), int(round((y + ch) * h))
    x0, y0 = min(max(x0, 0), w - 1), min(max(y0, 0), h - 1)
    return x0, y0, max(min(x1, w), x0 + 1), max(min(y1, h), y0 + 1)


def rotate90(img: np.ndarray, rotation: int) -> np.ndarray:
    """Clockwise quarter turns."""
    return np.ascontiguousarray(np.rot90(img, k=-(int(rotation) // 90) % 4))


# --- calibration ---

def light_level(lin: np.ndarray) -> np.ndarray:
    return np.percentile(lin.reshape(-1, 3)[:: _stride(lin)], 99.9, axis=0).astype(np.float32)


def auto_base(lin: np.ndarray) -> np.ndarray:
    """Brightest film that isn't bare light: excludes sprocket holes (> 0.6 x light) and holder."""
    px = lin.reshape(-1, 3)[:: _stride(lin)]
    light = light_level(lin)
    film = (px[:, 1] < 0.6 * light[1]) & (px[:, 0] > 0.05 * light[0])
    if film.sum() < 100:
        return light
    return np.percentile(px[film], 99, axis=0).astype(np.float32)


def base_of(lin: np.ndarray, settings: dict) -> np.ndarray:
    base = settings.get("base")
    return np.asarray(base, np.float32) if base else auto_base(lin)


def sample_base(lin: np.ndarray, settings: dict, frame: dict, x: float, y: float) -> list[float]:
    img = full_view(lin, settings, frame)
    h, w = img.shape[:2]
    r = max(2, round(0.005 * max(h, w)))
    cx, cy = int(x * w), int(y * h)
    patch = img[max(cy - r, 0):cy + r + 1, max(cx - r, 0):cx + r + 1].reshape(-1, 3)
    return [round(float(v), 6) for v in np.median(patch, axis=0)]


def auto_crop(lin: np.ndarray, settings: dict) -> list[float]:
    """Picture area: rows/columns mostly made of film denser than the base, minus a small inset."""
    fallback = [0.05, 0.05, 0.9, 0.9]
    try:
        img = full_view(lin, settings, {})
        small = cv2.resize(img, (400, max(1, round(img.shape[0] * 400 / img.shape[1]))),
                           interpolation=cv2.INTER_AREA)
        dens = _density(small, base_of(lin, settings), settings)
        # Red stays transmissive through the orange mask even in dense highlights, so red
        # density separates the picture (< ~1) from the holder (> ~1.5).
        picture = (dens.mean(axis=2) > 0.04) & (dens[..., 0] < 1.2)
        r0, r1 = _run(picture.mean(axis=1) > 0.5)
        if r1 - r0 < 10:
            return fallback
        c0, c1 = _run(picture[r0:r1].mean(axis=0) > 0.6)
        if c1 - c0 < 10:
            return fallback
        r0b, r1b = _run(picture[r0:r1, c0:c1].mean(axis=1) > 0.8)
        r0, r1 = r0 + r0b, r0 + r1b
        h, w = picture.shape
        x, y, cw, ch = c0 / w, r0 / h, (c1 - c0) / w, (r1 - r0) / h
        ix, iy = 0.01 * cw, 0.01 * ch
        return [round(v, 4) for v in (x + ix, y + iy, cw - 2 * ix, ch - 2 * iy)]
    except Exception:
        return fallback


def _run(mask: np.ndarray) -> tuple[int, int]:
    edges = np.flatnonzero(np.diff(np.concatenate([[0], mask.astype(np.int8), [0]])))
    if edges.size == 0:
        return 0, 0
    starts, ends = edges[::2], edges[1::2]
    i = int(np.argmax(ends - starts))
    return int(starts[i]), int(ends[i])


def _stride(img: np.ndarray) -> int:
    return max(1, img.shape[0] * img.shape[1] // LEVEL_SAMPLES)


# --- tone ---

def _density(lin: np.ndarray, base: np.ndarray, settings: dict) -> np.ndarray:
    if settings.get("film") == "bw":
        t = (np.maximum(lin, EPS) @ np.float32([0.25, 0.5, 0.25])) / float(base @ np.float32([0.25, 0.5, 0.25]))
        return np.repeat(-np.log10(np.maximum(t, EPS))[..., None], 3, axis=2)
    return np.log10(base / np.maximum(lin, EPS)).astype(np.float32)


def frame_levels(dens_crop: np.ndarray) -> np.ndarray:
    """2 x 3: per-channel (black, white) density points."""
    px = dens_crop.reshape(-1, 3)[:: _stride(dens_crop)]
    return np.percentile(px, LEVEL_PCT, axis=0).astype(np.float32)


def analyze_roll(samples: list[tuple[np.ndarray, dict]], settings: dict) -> dict:
    levels = []
    for lin, frame in samples:
        img = full_view(lin, settings, frame)
        x0, y0, x1, y1 = crop_px(img.shape, frame["crop"])
        levels.append(frame_levels(_density(img[y0:y1, x0:x1], base_of(lin, settings), settings)))
    if not levels:
        return None
    return {"density": np.median(np.stack(levels), axis=0).round(5).tolist()}


def _tone(dens: np.ndarray, levels: np.ndarray, settings: dict, frame: dict) -> np.ndarray:
    lo, hi = levels[0], levels[1]
    n = (dens - lo) / np.maximum(hi - lo, 1e-3)
    n = n + 0.1 * param(frame, "exposure")
    n = 0.5 + (n - 0.5) * (1.0 + param(frame, "contrast"))
    t, g = 0.05 * param(frame, "temperature"), 0.05 * param(frame, "tint")
    if settings.get("film") != "bw":
        n = n + np.float32([t, -g, -t])
        y = n.mean(axis=2, keepdims=True)
        n = y + (n - y) * param(frame, "saturation")
    return np.clip(n, 0.0, 1.0).astype(np.float32)


def develop(lin: np.ndarray, settings: dict, frame: dict, view: str = "crop") -> np.ndarray:
    img = full_view(lin, settings, frame)
    if view == "negative":
        # white-balanced on the light so the negative looks like it does on the lightbox
        return np.clip(img / np.maximum(light_level(img), EPS), 0, 1) ** np.float32(1 / 2.2)
    base = base_of(lin, settings)
    x0, y0, x1, y1 = crop_px(img.shape, frame["crop"])
    if view == "crop":
        img = img[y0:y1, x0:x1]
        dens = _density(img, base, settings)
        crop_dens = dens
    else:
        dens = _density(img, base, settings)
        crop_dens = dens[y0:y1, x0:x1]
    roll_levels = (settings.get("levels") or {}).get("density")
    levels = np.asarray(roll_levels, np.float32) if roll_levels else frame_levels(crop_dens)
    out = _tone(dens, levels, settings, frame)
    return rotate90(out, frame.get("rotation", 0)) if view == "crop" else out


def write_tiff(path: Path, img: np.ndarray) -> None:
    u16 = (np.clip(img, 0.0, 1.0) * 65535.0 + 0.5).astype(np.uint16)
    if not cv2.imwrite(str(path), cv2.cvtColor(u16, cv2.COLOR_RGB2BGR)):
        raise OSError(f"could not write {path}")
