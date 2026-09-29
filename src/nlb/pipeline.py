"""One negative photo -> one positive frame."""
from dataclasses import dataclass

import numpy as np

from nlb.detect import Box, detect_frame, luma, trim_rebate
from nlb.geometry import fit_3x2, flip_h, inset, rotate
from nlb.tone import to_positive


@dataclass
class FrameResult:
    image: np.ndarray       # H x W float32 in [0, 1], final orientation
    crop: Box               # crop in the input array's pixels
    flags: list[str]
    low_detail: float


def process(rgb: np.ndarray, rotation: str = "none", gamma: float = 1.0,
            inset_frac: float = 0.02) -> FrameResult:
    det = detect_frame(rgb)
    box = det.box
    if "detect_failed" not in det.flags:
        region = rgb[box.y:box.y + box.h, box.x:box.x + box.w]
        trimmed = trim_rebate(luma(region), Box(0, 0, box.w, box.h))
        box = Box(box.x + trimmed.x, box.y + trimmed.y, trimmed.w, trimmed.h)
    crop = fit_3x2(inset(box, inset_frac))
    neg = rgb[crop.y:crop.y + crop.h, crop.x:crop.x + crop.w]
    positive = to_positive(flip_h(neg), gamma=gamma)
    return FrameResult(rotate(positive, rotation), crop, det.flags, det.low_detail)
