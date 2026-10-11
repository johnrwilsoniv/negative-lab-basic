import json

import cv2
import numpy as np
import pytest
from synth import (BASE_T, FLARE, LIGHT, make_carrier_negative, make_raw_negative, neutral_wedge_scene,
                   write_dng)

from nlb import develop as d
from nlb.engine import calibrate as cal
from nlb.engine.view import crop_px, rotate90, warp, warp_grid

C41 = {"film": "c41", "flip": False, "base": None, "levels": None}


def _frame(box, size, **kw):
    x, y, w, h = box
    W, H = size
    return {"crop": [x / W, y / H, w / W, h / H], "rotation": 0, "angle": 0.0, "params": {}, **kw}


def _negative(**kw):
    scene = neutral_wedge_scene()
    lin, box = make_raw_negative(scene, **kw)
    return scene, lin, box


def _wedge(out, rows=slice(10, 70)):
    """Mean output color per column across the neutral wedge (top half of the picture)."""
    return out[rows].mean(axis=0)


# --- synthetic negatives ---

def test_neutral_wedge_comes_out_neutral_and_monotonic():
    _, lin, box = _negative()
    out = d.develop(lin, C41, _frame(box, (600, 400)))
    assert out.shape == (180, 440, 3) and out.dtype == np.float32
    wedge = _wedge(out)
    assert np.ptp(wedge, axis=1).max() < 0.03          # neutral despite unequal layer gammas
    luma = wedge.mean(axis=1)
    assert luma[0] < 0.1 and luma[-1] > 0.85            # full range, no clipping to 1.0 wall
    assert (np.diff(luma[::10]) > 0).all()              # brighter scene -> brighter positive


def test_color_bars_keep_their_hue():
    _, lin, box = _negative()
    out = d.develop(lin, C41, _frame(box, (600, 400)))
    bars = [out[120:170, i * 110 + 20:(i + 1) * 110 - 20].reshape(-1, 3).mean(axis=0) for i in range(4)]
    red, green, blue, gray = bars
    assert red[0] > red[1] + 0.15 and red[0] > red[2] + 0.15
    assert green[1] > green[0] + 0.1 and green[1] > green[2] + 0.1
    assert blue[2] > blue[0] + 0.15 and blue[2] > blue[1] + 0.1
    assert np.ptp(gray) < 0.03


def test_flare_is_measured_and_subtracted():
    _, lin, box = _negative()
    c = cal.calibrate(cal.thumbnail(lin))
    np.testing.assert_allclose(c.flare, FLARE, rtol=0.05)
    np.testing.assert_allclose(c.base, np.float32(BASE_T) * LIGHT + FLARE, rtol=0.03)
    no_flare = d.develop(lin, {**C41, "flare": [0, 0, 0]}, _frame(box, (600, 400)))
    with_flare = d.develop(lin, C41, _frame(box, (600, 400)))
    # without flare removal the dense end (bright highlights) is compressed: mid-wedge too bright
    assert _wedge(no_flare)[300].mean() > _wedge(with_flare)[300].mean() + 0.01


def test_capture_exposure_does_not_change_the_result():
    _, lin1, box = _negative(exposure=1.0)
    _, lin2, _ = _negative(exposure=0.4)
    a = d.develop(lin1, C41, _frame(box, (600, 400)))
    b = d.develop(lin2, C41, _frame(box, (600, 400)))
    assert np.abs(a - b).mean() < 0.01


def test_flatfield_removes_light_falloff():
    _, lin, box = _negative(falloff=0.4)
    bare = make_raw_negative(neutral_wedge_scene(), falloff=0.4)[0]
    bare[:] = (1.0 - 0.4 * (1.0 - np.linspace(0, 1, 600, dtype=np.float32)))[None, :, None] * np.float32(LIGHT) * 0.9
    ff = d.make_flatfield(bare)
    json.dumps(ff)
    gray_bar = lambda out: out[120:170, 3 * 110 + 20:4 * 110 - 20]  # noqa: E731
    flat = gray_bar(d.develop(lin, {**C41, "flatfield": ff}, _frame(box, (600, 400))))
    tilted = gray_bar(d.develop(lin, C41, _frame(box, (600, 400))))
    spread = lambda bar: np.ptp(bar.mean(axis=(0, 2))[[0, -1]])  # noqa: E731
    assert spread(flat) < 0.01 < spread(tilted)


def test_flatfield_rejects_clipped_frame():
    with pytest.raises(ValueError, match="clipped"):
        d.make_flatfield(np.ones((200, 300, 3), np.float32))


def test_bw_returns_equal_channels():
    _, lin, box = _negative()
    out = d.develop(lin, {**C41, "film": "bw"}, _frame(box, (600, 400)))
    assert np.array_equal(out[..., 0], out[..., 1]) and np.array_equal(out[..., 1], out[..., 2])
    luma = _wedge(out).mean(axis=1)
    assert luma[0] < 0.1 and luma[-1] > 0.85


# --- params ---

def test_params_have_unique_keys_and_valid_defaults():
    keys = [p["key"] for p in d.PARAMS]
    assert len(keys) == len(set(keys))
    for p in d.PARAMS:
        assert p["min"] <= p["default"] <= p["max"] and p["step"] > 0 and p["label"]


@pytest.mark.parametrize("key, value, check", [
    ("exposure", 1.0, lambda a, b: b.mean() > a.mean() + 0.05),
    ("exposure", -1.0, lambda a, b: b.mean() < a.mean() - 0.05),
    ("temperature", 1.0, lambda a, b: (b[..., 0] - b[..., 2]).mean() > (a[..., 0] - a[..., 2]).mean() + 0.05),
    ("tint", 1.0, lambda a, b: b[..., 1].mean() < a[..., 1].mean() - 0.02),
    ("saturation", 0.0, lambda a, b: np.ptp(b, axis=2).max() < 1e-4),
    ("contrast", 1.0, lambda a, b: b.std() > a.std() + 0.02),
])
def test_params_move_the_image(key, value, check):
    _, lin, box = _negative()
    frame = _frame(box, (600, 400))
    a = d.develop(lin, C41, frame)
    b = d.develop(lin, C41, {**frame, "params": {key: value}})
    assert check(a, b)


# --- views and geometry ---

def test_views_shapes_and_rotation():
    _, lin, box = _negative()
    frame = _frame(box, (600, 400), rotation=90)
    crop = d.develop(lin, C41, frame)
    assert crop.shape == (440, 180, 3)
    np.testing.assert_array_equal(crop, rotate90(d.develop(lin, C41, {**frame, "rotation": 0}), 90))
    full = d.develop(lin, C41, frame, view="full")
    neg = d.develop(lin, C41, frame, view="negative")
    assert full.shape == neg.shape == (400, 600, 3)
    # full view uses the crop's levels: its crop region equals the crop view
    x, y, w, h = box
    np.testing.assert_allclose(full[y:y + h, x:x + w], d.develop(lin, C41, {**frame, "rotation": 0}), atol=1e-5)
    # negative view isn't inverted: holes are white, holder is black
    assert neg[75:85, 50:60].min() > 0.95 and neg[5:20, 5:20].max() < 0.1
    assert full[5:20, 5:20].min() > 0.95  # holder is dense-looking -> white in the positive


def test_rotate90_is_clockwise():
    a = np.arange(6).reshape(2, 3)
    assert rotate90(a, 90).tolist() == [[3, 0], [4, 1], [5, 2]]
    assert rotate90(a, 270).tolist() == [[2, 5], [1, 4], [0, 3]]
    assert rotate90(a, 180).tolist() == [[5, 4, 3], [2, 1, 0]]


def test_warp_region_matches_full_view_then_crop():
    rng = np.random.default_rng(0)
    img = cv2.GaussianBlur(rng.random((90, 130, 3)).astype(np.float32), (7, 7), 0)
    for flip in (False, True):
        for angle in (0.0, 3.0):
            full = warp(img, flip, angle)
            region = (20, 10, 95, 70)
            # OpenCV snaps sub-pixel positions to 1/32 px, so a shifted region rounds a little differently
            np.testing.assert_allclose(warp(img, flip, angle, region), full[10:70, 20:95], atol=5e-3)
    np.testing.assert_array_equal(warp(img, True, 0.0), img[:, ::-1])


def test_deskew_is_counter_clockwise_about_center():
    img = np.zeros((101, 101, 3), np.float32)
    img[50, 80] = 1.0                                    # right of center
    out = warp(img, False, 90.0)
    y, x = np.unravel_index(out[..., 0].argmax(), out.shape[:2])
    assert (y, x) == (20, 50)                            # counter-clockwise: now above center


def _pattern(h, w):
    """Smooth, asymmetric content defined in normalized coordinates."""
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    u, v = (x + 0.5) / w, (y + 0.5) / h
    return np.stack([u, v, 0.5 + 0.5 * np.sin(6 * u + 3 * v)], axis=2).astype(np.float32)


def test_normalized_crop_is_resolution_independent():
    crop, angle = [0.2, 0.15, 0.5, 0.6], 2.5
    small, big = _pattern(300, 450), _pattern(1200, 1800)
    a = warp(small, True, angle, crop_px(small.shape, crop))
    b = warp(big, True, angle, crop_px(big.shape, crop))
    b = cv2.resize(b, (a.shape[1], a.shape[0]), interpolation=cv2.INTER_AREA)
    assert np.abs(a - b)[2:-2, 2:-2].max() < 0.01


def test_warp_grid_upsamples_into_view():
    grid = np.ones((4, 6, 3), np.float32)
    grid[:, :3] = 0.5
    out = warp_grid(grid, (400, 600), flip=True, angle=0.0)
    assert out.shape == (400, 600, 3)
    assert out[:, :250].mean() > 0.99 and out[:, 350:].mean() < 0.51  # flipped: dim half on the right


def test_preview_and_full_resolution_look_the_same():
    scene = neutral_wedge_scene(360, 880)
    big, box = make_raw_negative(scene, size=(1200, 800))
    big = cv2.GaussianBlur(big, (3, 3), 0)
    small = cv2.resize(big, (600, 400), interpolation=cv2.INTER_AREA)
    frame = _frame(box, (1200, 800), angle=1.5, params={"exposure": 0.4})
    a = d.develop(small, C41, frame)
    b = cv2.resize(d.develop(big, C41, frame), (a.shape[1], a.shape[0]), interpolation=cv2.INTER_AREA)
    np.testing.assert_allclose(a.reshape(-1, 3).mean(0), b.reshape(-1, 3).mean(0), atol=0.005)
    for q in (5, 50, 95):
        np.testing.assert_allclose(np.percentile(a, q, axis=(0, 1)), np.percentile(b, q, axis=(0, 1)), atol=0.01)


# --- calibration helpers ---

def test_auto_crop_finds_picture_and_excludes_holes_and_rebate():
    _, lin, (x, y, w, h) = _negative()
    cx, cy, cw, ch = d.auto_crop(lin, C41)
    W, H = 600, 400
    assert x / W <= cx < (x + 0.05 * w) / W and y / H <= cy < (y + 0.05 * h) / H
    assert (x + 0.95 * w) / W < cx + cw <= (x + w) / W and (y + 0.95 * h) / H < cy + ch <= (y + h) / H


def test_auto_crop_respects_flip():
    _, lin, _ = _negative()
    a, b = d.auto_crop(lin, C41), d.auto_crop(lin, {**C41, "flip": True})
    assert b[0] == pytest.approx(1 - a[0] - a[2], abs=0.003) and b[1:] == pytest.approx(a[1:], abs=0.003)


def test_auto_frame_measures_tilt():
    _, lin, box = _negative()
    tilted = warp(lin, False, -3.0)  # turn the capture clockwise; deskew must turn it back
    geo = d.auto_frame(tilted, C41)
    assert geo["angle"] == pytest.approx(3.0, abs=0.3)
    straight = d.auto_crop(lin, C41)
    assert geo["crop"] == pytest.approx(straight, abs=0.02)
    inscribed = d.auto_crop(tilted, C41)  # angle-0 box must fit inside the tilted picture
    assert inscribed[2] < straight[2] and inscribed[3] < straight[3]


def _carrier_scene(h=330, w=500):
    """A scene with big deep shadows (film as thin as the rebate) and a bright sky band on top."""
    rng = np.random.default_rng(1)
    e = np.full((h, w, 3), 1 / 40, np.float32)          # shadows: barely above base
    e[: h // 3] = (0.6, 0.7, 0.9)                        # sky
    e[h // 3:] *= np.exp(rng.normal(0, 0.6, (h - h // 3, w, 1))).astype(np.float32)
    return e


def test_auto_frame_finds_carrier_window_and_skips_rebate():
    lin, (x, y, w, h) = make_carrier_negative(_carrier_scene(), angle=1.2)
    geo = d.auto_frame(lin, C41)
    assert geo["angle"] == pytest.approx(1.2, abs=0.2)
    cx, cy, cw, ch = geo["crop"]
    W, H = 800, 600
    assert x / W <= cx < (x + 0.04 * w) / W and y / H <= cy < (y + 0.04 * h) / H
    assert (x + 0.96 * w) / W < cx + cw <= (x + w + 1) / W and (y + 0.96 * h) / H < cy + ch <= (y + h + 1) / H


def test_carrier_base_comes_from_the_rebate():
    lin, _ = make_carrier_negative(_carrier_scene(), angle=0.8)
    c = cal.calibrate(cal.thumbnail(lin))
    np.testing.assert_allclose(c.base, np.float32(BASE_T) * LIGHT + FLARE, rtol=0.05)
    _, strip, _ = _negative()  # a strip with holes on the film keeps its own base
    assert cal.window_rebate(cal.thumbnail(strip), cal.calibrate(cal.thumbnail(strip)).hole) is None


def test_scene_highlights_are_not_sprocket_holes():
    lin, _ = make_carrier_negative(_carrier_scene())
    c = cal.calibrate(cal.thumbnail(lin))
    assert c.hole.mean() > 0.05                          # thin shadows clear the bare-light threshold
    assert cal.film_angle(c.hole) is None or not cal.holes_on_film(c.hole, cal.lit_region(cal.thumbnail(lin)))
    _, strip, _ = _negative()
    assert cal.sprocket_rows(cal.calibrate(cal.thumbnail(strip)).hole) is not None


def test_auto_crop_never_raises():
    assert d.auto_crop(np.zeros((50, 80, 3), np.float32), C41) == d.FALLBACK_CROP
    assert len(d.auto_crop(np.full((50, 80, 3), 0.3, np.float32), C41)) == 4


def test_sample_base_on_rebate():
    _, lin, _ = _negative()
    base = d.sample_base(lin, C41, {"angle": 0.0}, x=300 / 600, y=100 / 400)  # rebate between holes and picture
    np.testing.assert_allclose(base, np.float32(BASE_T) * LIGHT + FLARE, rtol=1e-3)
    flipped = d.sample_base(lin, {**C41, "flip": True}, {"angle": 0.0}, x=300 / 600, y=100 / 400)
    np.testing.assert_allclose(flipped, base, rtol=1e-3)


def test_set_base_overrides_auto():
    _, lin, box = _negative()
    frame = _frame(box, (600, 400))
    auto = d.develop(lin, C41, frame)
    sampled = d.sample_base(lin, C41, frame, x=0.5, y=0.25)
    same = d.develop(lin, {**C41, "base": sampled}, frame)
    assert np.abs(auto - same).mean() < 0.01
    off = d.develop(lin, {**C41, "base": (np.float32(sampled) * [1.2, 0.9, 1.1]).tolist()}, frame)
    assert np.abs(auto - off).mean() < 0.01  # per-frame levels absorb a moderate base error


def test_analyze_roll_locks_levels():
    _, lin1, box = _negative()
    scene2 = neutral_wedge_scene()
    scene2[..., 2] *= 0.5                     # a frame with a strong yellow cast
    lin2, _ = make_raw_negative(scene2)
    frame = _frame(box, (600, 400))
    levels = d.analyze_roll([(lin1, frame), (lin2, frame)], C41)
    json.dumps(levels)
    assert levels["frames"] == 2 and levels["film"] == "c41"
    auto = d.develop(lin2, C41, frame)
    locked = d.develop(lin2, {**C41, "levels": levels}, frame)
    assert locked[..., 2].mean() < auto[..., 2].mean() - 0.02   # locked keeps some of the cast
    stale = d.develop(lin2, {**C41, "levels": {**levels, "film": "bw"}}, frame)
    np.testing.assert_array_equal(stale, auto)                   # stale levels are ignored
    assert d.analyze_roll([], C41) is None


def test_exposure_report():
    _, lin, _ = _negative()
    rep = d.exposure_report(lin, C41)
    json.dumps(rep)
    assert rep["base_headroom"] == pytest.approx(max(np.float32(BASE_T) * LIGHT + FLARE), rel=0.03)
    assert rep["advice"].startswith("underexposed")
    bright = d.exposure_report(np.clip(lin * 5, 0, 1), C41)
    assert bright["advice"] == "ok" or bright["advice"].startswith("film is clipping")


# --- I/O ---

def test_write_tiff_roundtrip_with_icc(tmp_path):
    import tifffile
    from PIL import Image, ImageCms

    img = np.random.default_rng(1).random((20, 30, 3)).astype(np.float32)
    path = tmp_path / "out.tif"
    d.write_tiff(path, img)
    back = tifffile.imread(path)
    assert back.dtype == np.uint16 and back.shape == (20, 30, 3)
    np.testing.assert_allclose(back / 65535.0, img, atol=1 / 65535)
    with tifffile.TiffFile(path) as tf:
        icc = tf.pages[0].tags[34675].value
    profile = ImageCms.ImageCmsProfile(__import__("io").BytesIO(icc))
    assert "sRGB" in ImageCms.getProfileDescription(profile)
    with Image.open(path) as im:
        assert im.info.get("icc_profile")


def test_load_linear_has_fixed_scale(tmp_path):
    """No auto-brightening or max adjustment: a dim frame stays dim."""
    srgb = np.full((40, 60, 3), 0.5, np.float32)
    srgb[:, :30] = 0.2
    write_dng(tmp_path / "dim.dng", srgb)
    lin = d.load_linear(tmp_path / "dim.dng")
    expect = ((0.5 + 0.055) / 1.055) ** 2.4, ((0.2 + 0.055) / 1.055) ** 2.4
    assert lin.dtype == np.float32
    assert lin[20, 45].mean() == pytest.approx(expect[0], rel=0.02)
    assert lin[20, 10].mean() == pytest.approx(expect[1], rel=0.03)
