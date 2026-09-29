from synth import make_negative

from nlb.pipeline import process


def test_output_is_exact_3x2_inside_window():
    r = process(make_negative())
    h, w = r.image.shape
    assert w * 2 == h * 3
    assert 113 <= r.crop.x and r.crop.x + r.crop.w <= 113 + 670
    assert 165 <= r.crop.y and r.crop.y + r.crop.h <= 165 + 458
    assert r.flags == []


def test_flipped_horizontally():
    # negative ramps thin->dense left->right; positive is bright->dark; flip -> dark->bright
    r = process(make_negative())
    h, w = r.image.shape
    assert r.image[:, : w // 4].mean() + 0.3 < r.image[:, -w // 4:].mean()


def test_rebate_band_is_trimmed():
    r = process(make_negative(rebate=30))
    assert r.image[:3].mean() > 0.1


def test_rotation_applied_last():
    r = process(make_negative(), rotation="90cw")
    h, w = r.image.shape
    assert h * 2 == w * 3


def test_partial_frame_is_flagged_not_skipped():
    r = process(make_negative(grain=0))
    assert "partial_or_blank" in r.flags
    assert r.image.size > 0
