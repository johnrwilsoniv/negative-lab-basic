"""Checks against real captures of C-41 negatives. Skipped when they're absent.

Sony A7 IV strips in a holder and on a bare lightbox, and iPhone ProRAW frames through a carrier
(Kodak Gold 200).
"""
from functools import cache
from pathlib import Path

import cv2
import numpy as np
import pytest
import rawpy

from nlb import develop as d
from nlb.engine import calibrate as cal

REPO = Path(__file__).resolve().parent.parent
ROLLS = next((p for p in (REPO / "sony-capture" / "rolls", REPO / "nextcloud") if (p / "roll01").is_dir()),
             REPO / "sony-capture" / "rolls")
IPHONE = REPO / "nextcloud" / "italy-kodak-gold-200"
FILES = {"DSC06699": ROLLS / "roll01" / "DSC06699.ARW", "DSC06700": ROLLS / "roll01" / "DSC06700.ARW",
         "frame-001": ROLLS / "test" / "frame-001.ARW",
         **{f"frame-00{i}": ROLLS / "test" / f"frame-00{i}.ARW" for i in range(2, 6)},
         **{n: IPHONE / f"{n}.DNG" for n in ("IMG_4199", "IMG_4214", "IMG_4221", "IMG_4228")},
         **{f"bw-{i}": REPO / "nextcloud" / "claude-in-charge" / f"frame-{i}.ARW" for i in ("002", "003", "006", "007")}}
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


@pytest.mark.parametrize("name", ["DSC06699", "DSC06700", "frame-001"])
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


# iPhone through a carrier: no bare light, holes beyond the carrier's edge, a thin rebate around
# the picture (wider along the top). Crops checked by eye on 30 frames of the roll.
IPHONE_CROP = {"IMG_4199": [0.2053, 0.2442, 0.6431, 0.5717], "IMG_4214": [0.2103, 0.2392, 0.6419, 0.5782],
               "IMG_4221": [0.2079, 0.2393, 0.6468, 0.5798], "IMG_4228": [0.2115, 0.2458, 0.6382, 0.5684]}


@pytest.mark.parametrize("name", sorted(IPHONE_CROP))
def test_iphone_carrier_frame(name):
    _need(name)
    lin = _preview(name)
    geo = d.auto_frame(lin, C41)
    assert 0.4 < geo["angle"] < 1.1  # the phone sat a little crooked on every frame
    np.testing.assert_allclose(geo["crop"], IPHONE_CROP[name], atol=0.008)
    thumb = cal.thumbnail(lin)
    c = cal.calibrate(thumb)
    if name == "IMG_4228":  # the film sat high: a row of holes shows along the window's top edge
        assert cal.holes_on_film(thumb, c.hole)
        np.testing.assert_allclose(c.base, [0.0169, 0.0123, 0.0103], rtol=0.03)  # what the rebate reads
    else:
        assert cal.window_rebate(thumb, c.hole) is not None


# A7 IV, a Kodak GC 400 strip straight on a round lightbox: no holder, bare light past the end of
# the strip outshines the film, the gap to the next frame and the rebate between the holes sit
# only ~0.05 above the base, and the left of the picture is dark trees nearly as thin as the gap.
# 002/003 and 004/005 are the same framing a stop apart. Crops checked by eye.
LIGHTBOX_CROP = {"frame-002": [0.1078, 0.0844, 0.7595, 0.7506], "frame-003": [0.1078, 0.0826, 0.7595, 0.7524],
                 "frame-004": [0.1893, 0.1734, 0.6627, 0.657], "frame-005": [0.1967, 0.1733, 0.6578, 0.6533]}


@pytest.mark.parametrize("name", sorted(LIGHTBOX_CROP))
def test_strip_on_bare_lightbox(name):
    _need(name)
    lin = _preview(name)
    thumb = cal.thumbnail(lin)
    c = cal.calibrate(thumb)
    assert cal.holes_on_film(thumb, c.hole)  # a strip, though the bare light wins the lit window
    geo = d.auto_frame(lin, C41)
    assert geo["angle"] == pytest.approx(0.0, abs=0.15)
    np.testing.assert_allclose(geo["crop"], LIGHTBOX_CROP[name], atol=0.008)
    x, y, w, h = geo["crop"]
    flipped = d.auto_frame(lin, {**C41, "flip": True})["crop"]
    np.testing.assert_allclose(flipped, [1 - x - w, y, w, h], atol=0.003)


# A7 IV, a B&W strip in a holder whose window is a little longer than a frame: the gap to the
# next frame shows at one end (with a sliver of that frame on bw-006), the picture runs on under
# the holder at the other, and the holder cuts the holes down to slivers along one edge. Inside
# the pictures are vertical lines (a shop window on bw-003) as sharp as a frame's end, and dark
# trees on bw-006 nearly as thin as the gap. bw-002 is underexposed. Crops checked by eye.
BW = {"film": "bw", "flip": False, "base": None, "levels": None}
HOLDER_CROP = {"bw-002": [0.1504, 0.1416, 0.6505, 0.6607], "bw-003": [0.1868, 0.1884, 0.664, 0.6625],
               "bw-006": [0.1892, 0.1434, 0.6542, 0.6607], "bw-007": [0.138, 0.2128, 0.6627, 0.6625]}


@pytest.mark.parametrize("name", sorted(HOLDER_CROP))
def test_bw_strip_in_holder(name):
    _need(name)
    lin = _preview(name)
    thumb = cal.thumbnail(lin)
    c = cal.calibrate(thumb, "bw")
    assert cal.sprocket_rows(c.hole) is not None and cal.holes_on_film(thumb, c.hole)
    geo = d.auto_frame(lin, BW)
    np.testing.assert_allclose(geo["crop"], HOLDER_CROP[name], atol=0.008)
    x, y, w, h = geo["crop"]
    flipped = d.auto_frame(lin, {**BW, "flip": True})["crop"]
    np.testing.assert_allclose(flipped, [1 - x - w, y, w, h], atol=0.003)
