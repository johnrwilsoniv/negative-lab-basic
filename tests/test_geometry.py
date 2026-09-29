import numpy as np
import pytest

from nlb.detect import Box
from nlb.geometry import ROTATIONS, fit_3x2, flip_h, inset, rotate


def test_inset_uses_short_side():
    assert inset(Box(100, 100, 600, 400), 0.02) == Box(108, 108, 584, 384)


@pytest.mark.parametrize("box", [Box(0, 0, 670, 458), Box(5, 7, 1000, 1000), Box(0, 0, 6, 4)])
def test_fit_3x2_landscape_exact_and_inside(box):
    out = fit_3x2(box)
    assert out.w * 2 == out.h * 3 and out.w % 2 == 0 and out.h % 2 == 0
    assert box.x <= out.x and out.x + out.w <= box.x + box.w
    assert box.y <= out.y and out.y + out.h <= box.y + box.h


def test_fit_3x2_is_maximal_and_centered():
    assert fit_3x2(Box(0, 0, 670, 458)) == Box(2, 7, 666, 444)


def test_fit_3x2_portrait():
    out = fit_3x2(Box(0, 0, 458, 670))
    assert out.w * 3 == out.h * 2 and out.h > out.w


def test_flip_h():
    img = np.array([[1, 2, 3]])
    assert flip_h(img).tolist() == [[3, 2, 1]]


@pytest.mark.parametrize("rot,expected", [
    ("none", [[1, 2], [3, 4]]),
    ("90cw", [[3, 1], [4, 2]]),
    ("90ccw", [[2, 4], [1, 3]]),
    ("180", [[4, 3], [2, 1]]),
])
def test_rotate(rot, expected):
    assert rotate(np.array([[1, 2], [3, 4]]), rot).tolist() == expected


def test_rotate_rejects_unknown():
    with pytest.raises(ValueError):
        rotate(np.zeros((2, 2)), "45")


def test_rotations_constant():
    assert ROTATIONS == ("none", "90cw", "90ccw", "180")
