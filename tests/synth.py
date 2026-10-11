"""Synthetic 'phone photo of a negative on a lightbox' for tests."""
import numpy as np


def make_negative(window=(113, 165, 670, 458), size=(1008, 756), grain=0.08, rebate=0, seed=0):
    """Dark mount, sprocket dashes above/below, bright film window.

    Window content is a left-to-right ramp (0.4 -> 0.8) so flips are detectable.
    `rebate` rows at the top of the window are clear film base (0.95).
    """
    rng = np.random.default_rng(seed)
    width, height = size
    img = np.full((height, width), 0.04, np.float32)
    x, y, w, h = window
    for sy in (y - 60, y + h + 25):
        for sx in range(x, x + w, 60):
            img[max(sy, 0):max(sy + 35, 0), sx:sx + 30] = 0.9
    patch = np.tile(np.linspace(0.4, 0.8, w, dtype=np.float32), (h, 1))
    if grain:
        patch += rng.normal(0, grain, (h, w)).astype(np.float32)
    if rebate:
        patch[:rebate] = 0.95
    img[y:y + h, x:x + w] = np.clip(patch, 0, 1)
    return np.repeat(img[..., None], 3, axis=2)


XYZ_TO_SRGB = (3.2406, -1.5372, -0.4986, -0.9689, 1.8758, 0.0415, 0.0557, -0.2040, 1.0570)


def write_dng(path, srgb):
    """Save an H x W x 3 sRGB float image as a 16-bit linear DNG whose camera space is linear sRGB."""
    import tifffile

    lin = np.where(srgb <= 0.04045, srgb / 12.92, ((srgb + 0.055) / 1.055) ** 2.4)
    rationals = [v for m in XYZ_TO_SRGB for v in (round(m * 10000), 10000)]
    tifffile.imwrite(path, (lin * 65535 + 0.5).astype(np.uint16), photometric=34892,
                     planarconfig="contig", extratags=[
        (50706, "B", 4, (1, 4, 0, 0), True),        # DNGVersion
        (50708, "s", 0, "nlb synth", True),         # UniqueCameraModel
        (50717, "I", 1, (65535,), True),            # WhiteLevel
        (50721, "2i", 9, rationals, True),          # ColorMatrix1 (XYZ -> camera)
        (50728, "2I", 3, (1, 1) * 3, True),         # AsShotNeutral
        (50778, "H", 1, (21,), True),               # CalibrationIlluminant1 = D65
    ])
