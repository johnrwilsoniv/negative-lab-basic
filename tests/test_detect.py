import cv2
import numpy as np
import pytest
from synth import make_negative

from nlb.detect import Box, detect_frame, longest_run, low_detail_fraction


def test_longest_run():
    assert longest_run(np.array([0, 1, 1, 0, 1, 1, 1, 0], bool)) == (4, 7)
    assert longest_run(np.array([1, 1, 0], bool)) == (0, 2)
    assert longest_run(np.zeros(5, bool)) == (0, 0)


def test_box_scale():
    assert Box(10, 20, 30, 40).scale(2.0) == Box(20, 40, 60, 80)


def _close(box, expected, tol):
    return all(abs(a - b) <= tol for a, b in zip((box.x, box.y, box.w, box.h), expected))


def test_detects_window_ignoring_sprockets():
    det = detect_frame(make_negative())
    assert _close(det.box, (113, 165, 670, 458), tol=3), det.box
    assert det.flags == []


def test_detects_at_higher_resolution():
    neg = make_negative()
    big = cv2.resize(neg, (2016, 1512), interpolation=cv2.INTER_NEAREST)
    det = detect_frame(big)
    assert _close(det.box, (226, 330, 1340, 916), tol=6), det.box


def test_blank_frame_flagged_partial():
    det = detect_frame(make_negative(grain=0))
    assert "partial_or_blank" in det.flags
    assert det.low_detail > 0.5


def test_all_black_is_detect_failed_with_full_box():
    det = detect_frame(np.zeros((300, 400, 3), np.float32))
    assert det.flags[0] == "detect_failed"
    assert det.box == Box(0, 0, 400, 300)


def test_all_bright_is_suspect():
    det = detect_frame(np.full((300, 400, 3), 0.8, np.float32))
    assert "detect_suspect" in det.flags


@pytest.mark.parametrize("sigma,expect_low", [(0.0, True), (8.0, False)])
def test_low_detail_fraction(sigma, expect_low):
    rng = np.random.default_rng(1)
    gray = np.full((256, 256), 128.0) + rng.normal(0, sigma, (256, 256))
    assert (low_detail_fraction(gray) > 0.5) == expect_low
