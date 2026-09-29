"""Checks against the real sample negatives. Skipped when they're absent."""
from pathlib import Path

import cv2
import pytest

from nlb.detect import detect_frame
from nlb.heic import load_rgb
from nlb.pipeline import process

SAMPLES = Path(__file__).resolve().parent.parent / "iphone-negatives"
pytestmark = pytest.mark.skipif(not SAMPLES.is_dir(), reason="sample negatives not present")

# Frame windows measured at 1008px working width (x, y, w, h).
EXPECTED = {
    "IMG_4025": (120, 161, 670, 463), "IMG_4026": (113, 165, 669, 458),
    "IMG_4027": (113, 165, 670, 458), "IMG_4028": (113, 165, 670, 458),
    "IMG_4029": (113, 165, 670, 458), "IMG_4030": (113, 165, 671, 458),
    "IMG_4031": (112, 155, 674, 483), "IMG_4032": (114, 165, 669, 456),
    "IMG_4033": (111, 167, 670, 459),
}


def _small(name):
    rgb = load_rgb(SAMPLES / f"{name}.HEIC")
    return cv2.resize(rgb, (1512, 1134), interpolation=cv2.INTER_AREA)


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_sample_detection(name):
    rgb = load_rgb(SAMPLES / f"{name}.HEIC")
    det = detect_frame(rgb)
    b = det.box.scale(1008 / rgb.shape[1])
    assert all(abs(a - e) <= 6 for a, e in zip((b.x, b.y, b.w, b.h), EXPECTED[name])), b
    assert not any(f.startswith("detect_") for f in det.flags)
    assert ("partial_or_blank" in det.flags) == (name == "IMG_4033")


@pytest.mark.parametrize("name", ["IMG_4025", "IMG_4031", "IMG_4026"])
def test_sample_no_rebate_stripe(name):
    img = process(_small(name)).image
    assert img[:4].mean() > 0.08, "black rebate stripe along the top edge"
