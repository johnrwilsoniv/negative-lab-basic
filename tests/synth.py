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


LIGHT = (0.34, 0.92, 0.48)           # bare light in camera RGB (green-heavy, like the sample lightbox)
BASE_T = (0.38, 0.165, 0.10)         # C-41 orange mask transmittance per channel
LAYER_GAMMA = (0.55, 0.6, 0.68)      # dye-layer contrast, deliberately unequal
FLARE = (0.001, 0.003, 0.0015)
E_REF = 10 ** -1.6                   # scene exposure that leaves the film at base density


def neutral_wedge_scene(h=180, w=440, colors=True):
    """Scene exposure (linear, H x W x 3): a neutral log wedge on top, color bars below.

    The wedge spans 5 stops (1/32 .. 1), so it sets every channel's extremes; the bars sit inside.
    """
    e = np.empty((h, w, 3), np.float32)
    wedge = np.logspace(-1.5, 0, w, dtype=np.float32)
    e[: h // 2] = wedge[None, :, None]
    bars = [(0.40, 0.08, 0.06), (0.06, 0.35, 0.08), (0.06, 0.10, 0.40), (0.15, 0.15, 0.15)]
    if not colors:
        bars = [(0.15, 0.15, 0.15)] * 4
    for i, c in enumerate(bars):
        e[h // 2:, i * w // 4:(i + 1) * w // 4] = c
    return e


def make_raw_negative(scene, size=(600, 400), exposure=1.0, falloff=0.0, flare=FLARE):
    """Sensor-space capture of a C-41 negative of `scene` in a holder on a lightbox.

    Returns (lin, picture_box) with picture_box = (x, y, w, h) in pixels. Layout like the
    samples: dark holder, a film strip with sprocket holes along both long edges, a clean
    rebate between holes and picture. `falloff` dims the light linearly toward the left edge.
    """
    width, height = size
    ph, pw = scene.shape[:2]
    light = np.float32(LIGHT) * exposure
    x_frac = np.linspace(0, 1, width, dtype=np.float32)
    illum = (1.0 - falloff * (1.0 - x_frac))[None, :, None] * light  # H x W x 3 via broadcast
    trans = np.zeros((height, width, 3), np.float32)                  # holder: opaque
    fy0, fy1, fx0, fx1 = 60, height - 60, 30, width - 30
    trans[fy0:fy1, fx0:fx1] = BASE_T
    for hy in (fy0 + 8, fy1 - 8 - 22):
        for hx in range(fx0 + 10, fx1 - 30, 46):
            trans[hy:hy + 22, hx:hx + 28] = 1.0
    px, py = (width - pw) // 2, (height - ph) // 2
    # density above base grows with log exposure; E_REF (below the wedge's darkest step) is base
    dens = np.float32(LAYER_GAMMA) * np.maximum(np.log10(np.maximum(scene, 1e-6) / E_REF), 0.0)
    trans[py:py + ph, px:px + pw] = np.float32(BASE_T) * 10.0 ** -dens
    lin = trans * illum + np.float32(flare) * exposure
    return np.clip(lin, 0, 1).astype(np.float32), (px, py, pw, ph)


def make_carrier_negative(scene, size=(800, 600), rebate=(14, 4, 4, 4), angle=0.0):
    """Sensor-space capture of a C-41 negative of `scene` through a carrier (iPhone rig).

    The carrier masks everything but a window a little larger than the picture, so a thin
    rebate shows around it: `rebate` = (top, bottom, left, right) pixels. Sprocket holes show
    dimly beyond the carrier's edge and its walls catch some light. Nothing is bare light, so
    the thinnest film (rebate, deep shadows) clears the bare-light threshold. `angle` turns the whole
    capture clockwise by that many degrees (deskew must turn it back by +angle).
    Returns (lin, picture_box) with picture_box = (x, y, w, h) in pixels before the turn.
    """
    width, height = size
    ph, pw = scene.shape[:2]
    light = np.float32(LIGHT)
    trans = np.full((height, width, 3), 0.0007, np.float32)          # carrier lip
    px, py = (width - pw) // 2, (height - ph) // 2
    t, b, l, r = rebate
    trans[: py - t - 30] = trans[py + ph + b + 30:] = 0.003          # walls catch a little light
    for hy in (py - t - 26, py + ph + b + 12):                       # holes beyond the carrier
        for hx in range(px, px + pw - 20, 40):
            trans[hy:hy + 14, hx:hx + 20] = 0.1
    trans[py - t:py + ph + b, px - l:px + pw + r] = BASE_T           # rebate around the picture
    dens = np.float32(LAYER_GAMMA) * np.maximum(np.log10(np.maximum(scene, 1e-6) / E_REF), 0.0)
    trans[py:py + ph, px:px + pw] = np.float32(BASE_T) * 10.0 ** -dens
    lin = np.clip(trans * light + np.float32(FLARE), 0, 1).astype(np.float32)
    if angle:
        import cv2

        m = cv2.getRotationMatrix2D(((width - 1) / 2, (height - 1) / 2), -angle, 1.0)
        lin = cv2.warpAffine(lin, m, (width, height), flags=cv2.INTER_LINEAR,
                             borderMode=cv2.BORDER_REPLICATE)
    return lin, (px, py, pw, ph)
