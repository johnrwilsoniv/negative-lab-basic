"""Checks against real Sony A7 IV captures of C-41 negatives. Skipped when they're absent."""
from functools import cache
from pathlib import Path

import cv2
import numpy as np
import pytest
import rawpy

from nlb import develop as d
from nlb.engine import calibrate as cal

ROLLS = Path(__file__).resolve().parent.parent / "sony-capture" / "rolls"
FILES = {"DSC06699": ROLLS / "roll01" / "DSC06699.ARW", "DSC06700": ROLLS / "roll01" / "DSC06700.ARW",
         "frame-001": ROLLS / "test" / "frame-001.ARW"}
C41 = {"film": "c41", "flip": False, "base": None, "levels": None}


def _need(name):
    if not FILES[name].is_file():
        pytest.skip(f"{FILES[name]} not present")


@cache
def _preview(name):
    """Like the studio: half-size decode, then ~1600 px wide."""
    lin = d.load_linear(FILES[name], preview=True)
    return cv2.resize(lin, (1600, round(lin.shape[0] * 1600 / lin.shape[1])), interpolation=cv2.INTER_AREA)


@pytest.mark.parametrize("name", ["DSC06699", "frame-001"])
def test_decode_keeps_raw_scale(name):
    _need(name)
    with rawpy.imread(str(FILES[name])) as raw:
        green = raw.raw_image_visible[0::2, 1::2]  # RGGB: G sites on even rows, odd columns
        black, white = raw.black_level_per_channel[1], raw.white_level
        expect = (np.percentile(green, 99.9) - black) / (white - black)
    lin = d.load_linear(FILES[name], preview=True)
    assert np.percentile(lin[..., 1], 99.9) == pytest.approx(expect, rel=0.02)


def test_auto_base_matches_measured_rebate():
    _need("DSC06699")
    c = cal.calibrate(cal.thumbnail(_preview("DSC06699")))
    np.testing.assert_allclose(c.base, [0.131, 0.152, 0.049], rtol=0.1)
    assert (c.flare < 0.01).all() and (c.flare > 0).all()


@pytest.mark.parametrize("name, angle", [("DSC06699", 0.26), ("DSC06700", 1.0), ("frame-001", 5.8)])
def test_auto_frame_angle(name, angle):
    _need(name)
    assert d.auto_frame(_preview(name), C41)["angle"] == pytest.approx(angle, abs=0.3)


# picture areas checked by eye (normalized, deskewed full view)
PICTURE = {"DSC06699": [0.165, 0.116, 0.761, 0.734], "DSC06700": [0.243, 0.057, 0.743, 0.737],
           "frame-001": [0.095, 0.115, 0.717, 0.774]}


@pytest.mark.parametrize("name", sorted(PICTURE))
def test_auto_frame_crop_inside_picture(name):
    _need(name)
    lin = _preview(name)
    geo = d.auto_frame(lin, C41)
    x, y, w, h = geo["crop"]
    px, py, pw, ph = PICTURE[name]
    assert px - 0.005 <= x and py - 0.005 <= y and x + w <= px + pw + 0.005 and y + h <= py + ph + 0.005
    assert w * h > 0.9 * pw * ph
    # nothing in the crop is bare light or holder
    thumb = d.warp(cal.thumbnail(lin), False, geo["angle"])
    c = cal.calibrate(thumb)
    x0, y0, x1, y1 = d.crop_px(thumb.shape, geo["crop"])
    assert not c.hole[y0:y1, x0:x1].any() and c.holder[y0:y1, x0:x1].mean() < 0.002


def test_auto_crop_on_dsc06699_excludes_holes_and_rebate():
    _need("DSC06699")
    lin = _preview("DSC06699")
    c = cal.calibrate(cal.thumbnail(lin))
    x0, y0, x1, y1 = d.crop_px(c.hole.shape, d.auto_crop(lin, C41))
    assert not c.hole[y0:y1, x0:x1].any()
    dens = np.log10(c.base / np.maximum(cal.thumbnail(lin)[y0:y1, x0:x1], 1e-6)).max(axis=2)
    for edge in (dens[:3], dens[-3:], dens[:, :3], dens[:, -3:]):  # no rebate strip along an edge
        assert (edge > cal.PICTURE_DENSITY).mean() > 0.5


@pytest.mark.parametrize("name", sorted(FILES))
def test_no_orange_cast_and_sane_exposure(name):
    _need(name)
    lin = _preview(name)
    geo = d.auto_frame(lin, C41)
    out = d.develop(lin, C41, {"crop": geo["crop"], "angle": geo["angle"]})
    mean = out.reshape(-1, 3).mean(axis=0)
    assert np.ptp(mean) < 0.08, mean
    assert 0.2 < mean.mean() < 0.6
    assert (out >= 0.995).mean() < 0.01  # highlights roll off, not clip


def test_frame001_preview_matches_full_resolution():
    _need("frame-001")
    small = _preview("frame-001")
    geo = d.auto_frame(small, C41)
    frame = {"crop": geo["crop"], "angle": geo["angle"], "rotation": 90}
    a = d.develop(small, C41, frame)
    b = d.develop(d.load_linear(FILES["frame-001"]), C41, frame)
    b = cv2.resize(b, (a.shape[1], a.shape[0]), interpolation=cv2.INTER_AREA)
    np.testing.assert_allclose(a.reshape(-1, 3).mean(0), b.reshape(-1, 3).mean(0), atol=0.01)
    for q in (5, 50, 95):
        np.testing.assert_allclose(np.percentile(a, q, axis=(0, 1)), np.percentile(b, q, axis=(0, 1)), atol=0.03)


def test_exposure_report_flags_underexposed_samples():
    _need("frame-001")
    rep = d.exposure_report(_preview("frame-001"), C41)
    assert rep["base_headroom"] < 0.2 and rep["advice"].startswith("underexposed")
