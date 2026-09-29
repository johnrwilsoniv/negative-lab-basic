"""HEIC input discovery, reading and grayscale writing."""
from pathlib import Path

import numpy as np
import pillow_heif
from PIL import Image

pillow_heif.register_heif_opener()

HEIF_SUFFIXES = (".heic", ".heif")


def list_inputs(folder: Path) -> list[Path]:
    """HEIC/HEIF files directly in `folder`, sorted, skipping dotfiles like `._IMG.HEIC`."""
    return sorted(
        p for p in folder.iterdir()
        if p.is_file() and not p.name.startswith(".") and p.suffix.lower() in HEIF_SUFFIXES
    )


def load_rgb(path: Path) -> np.ndarray:
    """Read an image as H x W x 3 float32 in [0, 1]."""
    with Image.open(path) as im:
        return np.asarray(im.convert("RGB"), dtype=np.float32) / 255.0


def to_u8(img: np.ndarray) -> np.ndarray:
    return (np.clip(img, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)


def save_gray(path: Path, gray: np.ndarray, quality: int = 92) -> None:
    """Write an H x W float image in [0, 1]; HEIF for .heic/.heif, else by suffix."""
    im = Image.fromarray(to_u8(gray))
    if path.suffix.lower() in HEIF_SUFFIXES:
        im.save(path, format="HEIF", quality=quality)
    else:
        im.save(path, quality=quality)
