"""Live-view focus meter: a sharpness score per live-view frame, for racking focus by eye.

The score only means something relative to other frames of the same scene and region, so the
UI shows it against the best score seen so far (peak hold) rather than as an absolute verdict.
Test shots get the absolute check (sprocket-hole edge width, `engine.check.edge_width`).
"""
import cv2
import numpy as np

NOISE_SIGMA = 1.0   # live-view pixels: blur away sensor and JPEG noise, which would read as detail
MIN_SIDE = 16       # pixels: smaller regions are all noise


def sharpness(jpeg: bytes, region=(0.0, 0.0, 1.0, 1.0)) -> float | None:
    """Focus score of a live-view JPEG within `region` (x, y, w, h as fractions): higher is sharper.

    Mean squared gradient over squared mean brightness, so a brighter or dimmer frame of the
    same detail scores the same. None if the JPEG does not decode or the region is too small.
    """
    gray = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_GRAYSCALE)
    if gray is None:
        return None
    h, w = gray.shape
    x, y, rw, rh = (min(max(float(v), 0.0), 1.0) for v in region)
    x0, y0 = int(x * w), int(y * h)
    x1, y1 = min(w, int(round((x + rw) * w))), min(h, int(round((y + rh) * h)))
    if x1 - x0 < MIN_SIDE or y1 - y0 < MIN_SIDE:
        return None
    g = cv2.GaussianBlur(gray[y0:y1, x0:x1].astype(np.float32), (0, 0), NOISE_SIGMA)
    gx, gy = cv2.Sobel(g, cv2.CV_32F, 1, 0), cv2.Sobel(g, cv2.CV_32F, 0, 1)
    mean = float(g.mean())
    return float((gx * gx + gy * gy).mean()) / max(mean * mean, 1.0)
