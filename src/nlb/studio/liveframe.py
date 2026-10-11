"""Live-view auto frame: the crop auto_frame would pick, drawn over live view while laying the strip.

Live view sends the camera's JPEGs, white balanced and tone curved, not raw. A steep power
curve brings them close enough to linear for auto_frame: a plain sRGB decode leaves the base
so bright and neutral after white balance that film passes for bare light, mostly when the
light is bright. Checked against the raw auto frame on the sample captures' embedded JPEGs.
"""
import cv2
import numpy as np

from nlb import develop
from nlb.engine.view import crop_outline

JPEG_GAMMA = 3.0   # JPEG -> about linear; steeper than sRGB to undo the camera's tone curve
MAX_W = 1600       # live view is ~1024 wide; larger JPEGs (the fake camera's) are shrunk first


def linear(jpeg: bytes) -> np.ndarray | None:
    """Approximately linear RGB in [0, 1] from a live-view JPEG, or None if it does not decode."""
    bgr = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
    if bgr is None:
        return None
    if bgr.shape[1] > MAX_W:
        bgr = cv2.resize(bgr, (MAX_W, round(bgr.shape[0] * MAX_W / bgr.shape[1])), interpolation=cv2.INTER_AREA)
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB).astype(np.float32) * np.float32(1 / 255)
    return cv2.pow(rgb, JPEG_GAMMA)


def outline(jpeg: bytes, film: str) -> dict | None:
    """{"outline": 4 corners [x, y] normalized in the live view, "angle": strip tilt in degrees},
    or None when the JPEG does not decode or no picture is found."""
    lin = linear(jpeg)
    if lin is None:
        return None
    geo = develop.auto_frame(lin, {"film": film, "flip": False})  # live view is in sensor orientation
    if geo["crop"] == develop.FALLBACK_CROP:
        return None
    corners = crop_outline(lin.shape, False, geo["angle"], geo["crop"])
    return {"outline": corners.round(4).tolist(), "angle": geo["angle"]}
