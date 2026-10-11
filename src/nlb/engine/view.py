"""Shared geometry: full view = deskew(angle)(flip(lin)); crop view = rotate90(crop(full view)).

Every transform is one affine map from sensor pixels to output pixels, so a crop is warped
straight out of the sensor image without materializing the full view. Pixel centers sit at
integer coordinates and deskew turns about ((w - 1) / 2, (h - 1) / 2), which keeps
normalized crops on the same content at any resolution.
"""
import cv2
import numpy as np

Region = tuple[int, int, int, int]  # x0, y0, x1, y1, half-open, in full-view pixels


def full_matrix(shape: tuple, flip: bool, angle: float) -> np.ndarray:
    """3 x 3 affine from sensor pixels to full-view pixels (same canvas size)."""
    h, w = shape[:2]
    m = np.eye(3)
    if flip:
        m = np.array([[-1.0, 0.0, w - 1.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])
    if angle:
        r = np.vstack([cv2.getRotationMatrix2D(((w - 1) / 2, (h - 1) / 2), angle, 1.0), [0, 0, 1]])
        m = r @ m
    return m


def crop_px(shape: tuple, crop) -> Region:
    """Normalized [x, y, w, h] -> pixel region, clamped to the image and at least 1 x 1."""
    h, w = shape[:2]
    x, y, cw, ch = (float(v) for v in crop)
    x0, y0 = int(round(x * w)), int(round(y * h))
    x1, y1 = int(round((x + cw) * w)), int(round((y + ch) * h))
    x0, y0 = min(max(x0, 0), w - 1), min(max(y0, 0), h - 1)
    return x0, y0, max(min(x1, w), x0 + 1), max(min(y1, h), y0 + 1)


def crop_outline(shape: tuple, flip: bool, angle: float, crop) -> np.ndarray:
    """Corners of a full-view crop in the sensor image: 4 x 2 normalized (x, y), clockwise from top left."""
    h, w = shape[:2]
    x, y, cw, ch = (float(v) for v in crop)
    # normalized edges sit half a pixel outside the pixel centers they bound
    xs, ys = (x * w - 0.5, (x + cw) * w - 0.5), (y * h - 0.5, (y + ch) * h - 0.5)
    corners = np.array([[xs[0], ys[0], 1], [xs[1], ys[0], 1], [xs[1], ys[1], 1], [xs[0], ys[1], 1]])
    sensor = corners @ np.linalg.inv(full_matrix(shape, flip, angle)).T
    return (sensor[:, :2] + 0.5) / (w, h)


def warp(img: np.ndarray, flip: bool, angle: float, region: Region | None = None) -> np.ndarray:
    """The full view of `img`, or just `region` of it. Exact slicing when there's no deskew."""
    h, w = img.shape[:2]
    x0, y0, x1, y1 = region or (0, 0, w, h)
    if not angle:
        if flip:
            out = img[y0:y1, w - x1:w - x0][:, ::-1]
        else:
            out = img[y0:y1, x0:x1]
        return np.ascontiguousarray(out)
    m = np.array([[1.0, 0.0, -x0], [0.0, 1.0, -y0], [0.0, 0.0, 1.0]]) @ full_matrix(img.shape, flip, angle)
    return cv2.warpAffine(np.ascontiguousarray(img), m[:2], (x1 - x0, y1 - y0),
                          flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)


def warp_grid(grid: np.ndarray, shape: tuple, flip: bool, angle: float,
              region: Region | None = None) -> np.ndarray:
    """Upsample a coarse sensor-space map (e.g. a flat-field gain grid) straight into the view.

    Grid cell (j, i) covers the sensor area centered on ((i + 0.5) * w / gw - 0.5, ...).
    """
    h, w = shape[:2]
    gh, gw = grid.shape[:2]
    x0, y0, x1, y1 = region or (0, 0, w, h)
    sx, sy = w / gw, h / gh
    to_sensor = np.array([[sx, 0.0, sx / 2 - 0.5], [0.0, sy, sy / 2 - 0.5], [0.0, 0.0, 1.0]])
    m = (np.array([[1.0, 0.0, -x0], [0.0, 1.0, -y0], [0.0, 0.0, 1.0]])
         @ full_matrix(shape, flip, angle) @ to_sensor)
    return cv2.warpAffine(np.ascontiguousarray(grid, np.float32), m[:2], (x1 - x0, y1 - y0),
                          flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)


def rotate90(img: np.ndarray, rotation: int) -> np.ndarray:
    """Clockwise quarter turns."""
    return np.ascontiguousarray(np.rot90(img, k=-(int(rotation) // 90) % 4))
