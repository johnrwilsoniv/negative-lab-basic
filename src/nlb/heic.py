"""HEIC/DNG/ARW input discovery, reading and grayscale HEIC writing."""
from pathlib import Path

import numpy as np
import pillow_heif
import rawpy
from PIL import Image

pillow_heif.register_heif_opener()

HEIF_SUFFIXES = (".heic", ".heif")
RAW_SUFFIXES = (".dng", ".arw")  # ProRAW, Sony
INPUT_SUFFIXES = HEIF_SUFFIXES + RAW_SUFFIXES


def list_inputs(folder: Path) -> list[Path]:
    """HEIC/HEIF/DNG/ARW files directly in `folder`, sorted, skipping dotfiles like `._IMG.HEIC`."""
    return sorted(
        p for p in folder.iterdir()
        if p.is_file() and not p.name.startswith(".") and p.suffix.lower() in INPUT_SUFFIXES
    )


def output_name(path: Path) -> str:
    """HEIC inputs keep their name; raw inputs become `<stem>.HEIC`."""
    return path.name if path.suffix.lower() in HEIF_SUFFIXES else f"{path.stem}.HEIC"


def load_rgb(path: Path) -> np.ndarray:
    """Read an image as H x W x 3 float32 in [0, 1] (sRGB-encoded, upright)."""
    if path.suffix.lower() in RAW_SUFFIXES:
        return _load_raw(path)
    with Image.open(path) as im:
        return np.asarray(im.convert("RGB"), dtype=np.float32) / 255.0


def _load_raw(path: Path) -> np.ndarray:
    """Demosaic a raw file (DNG, ARW) at 16 bits with as-shot white balance and the sRGB curve.

    No auto-brightening: the tone stretch normalises exposure later, and an unscaled
    decode keeps the film base from clipping.
    """
    with rawpy.imread(str(path)) as raw:
        rgb = raw.postprocess(use_camera_wb=True, no_auto_bright=True,
                              gamma=(2.4, 12.92), output_bps=16)
    return rgb.astype(np.float32) / 65535.0


def to_u8(img: np.ndarray) -> np.ndarray:
    return (np.clip(img, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)


def save_gray(path: Path, gray: np.ndarray, quality: int = 92) -> None:
    """Write an H x W float image in [0, 1]; HEIF for .heic/.heif, else by suffix."""
    im = Image.fromarray(to_u8(gray))
    if path.suffix.lower() in HEIF_SUFFIXES:
        im.save(path, format="HEIF", quality=quality)
    else:
        im.save(path, quality=quality)
