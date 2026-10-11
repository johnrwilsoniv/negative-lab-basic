"""In-memory caches: preview-res linear decodes, darktable positives and rendered JPEGs."""
import hashlib
import io
import json
import threading
from collections import OrderedDict
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from nlb import darktable, develop

PREVIEW_WIDTH = 1600
THUMB_WIDTH = 400


class LRU:
    def __init__(self, size: int):
        self.size, self.items, self.lock = size, OrderedDict(), threading.Lock()

    def get(self, key):
        with self.lock:
            if key in self.items:
                self.items.move_to_end(key)
                return self.items[key]
        return None

    def put(self, key, value):
        with self.lock:
            self.items[key] = value
            self.items.move_to_end(key)
            while len(self.items) > self.size:
                self.items.popitem(last=False)

    def drop(self, pred):
        with self.lock:
            for k in [k for k in self.items if pred(k)]:
                del self.items[k]


class Previews:
    """Linear decodes at preview and thumbnail width, keyed by file path + mtime."""

    def __init__(self):
        self.full = LRU(12)     # ~20 MB each at 1600 px
        self.thumb = LRU(400)   # ~1.2 MB each
        self.key_locks: dict = {}
        self.lock = threading.Lock()

    def linear(self, path: Path, thumb: bool = False) -> np.ndarray:
        key = (str(path), path.stat().st_mtime_ns)
        cache = self.thumb if thumb else self.full
        hit = cache.get(key)
        if hit is not None:
            return hit
        with self._key_lock(key):  # one decode per file even with concurrent requests
            hit = cache.get(key)
            if hit is not None:
                return hit
            big = self.full.get(key)
            if big is None:
                big = _resize(develop.load_linear(path, preview=True), PREVIEW_WIDTH)
                self.full.put(key, big)
            small = _resize(big, THUMB_WIDTH)
            self.thumb.put(key, small)
            return small if thumb else big

    def seed(self, path: Path, decoded: np.ndarray) -> np.ndarray:
        """Cache a decode made elsewhere (e.g. a half-size one); returns the preview-width copy."""
        key = (str(path), path.stat().st_mtime_ns)
        big = _resize(decoded, PREVIEW_WIDTH)
        self.full.put(key, big)
        self.thumb.put(key, _resize(big, THUMB_WIDTH))
        return big

    def _key_lock(self, key) -> threading.Lock:
        with self.lock:
            return self.key_locks.setdefault(key, threading.Lock())


class DarktablePreviews:
    """darktable positives at preview and thumbnail size, pixel-aligned with `Previews` of the same file.

    A darktable run takes seconds, so results are also cached on disk (see `darktable.render`).
    """

    def __init__(self, previews: Previews):
        self.previews = previews
        self.full = LRU(12)
        self.thumb = LRU(400)
        self.key_locks: dict = {}
        self.lock = threading.Lock()

    def positive(self, path: Path, film: str, base: list[float] | None = None,
                 thumb: bool = False) -> np.ndarray:
        """`base` is the roll's picked film base (negadoctor's Dmin); None keeps the style's."""
        key = (str(path), path.stat().st_mtime_ns, film, tuple(base) if base else None)
        cache = self.thumb if thumb else self.full
        hit = cache.get(key)
        if hit is not None:
            return hit
        with self._key_lock(key):
            hit = cache.get(key)
            if hit is not None:
                return hit
            big = self.full.get(key)
            if big is None:
                shape = self.previews.linear(path).shape[:2]
                big = darktable.render(path, film, shape, width=PREVIEW_WIDTH, base=base)
                self.full.put(key, big)
            small = cv2.resize(big, self.previews.linear(path, thumb=True).shape[1::-1],
                               interpolation=cv2.INTER_AREA)
            self.thumb.put(key, small)
            return small if thumb else big

    def _key_lock(self, key) -> threading.Lock:
        with self.lock:
            return self.key_locks.setdefault(key, threading.Lock())


def _resize(img: np.ndarray, width: int) -> np.ndarray:
    if img.shape[1] <= width:
        return img
    height = max(1, round(img.shape[0] * width / img.shape[1]))
    return cv2.resize(img, (width, height), interpolation=cv2.INTER_AREA)


def edit_hash(settings: dict, frame: dict) -> str:
    """Short, stable hash of everything that affects a frame's rendering."""
    blob = json.dumps([settings, {k: v for k, v in frame.items() if k != "rejected"}], sort_keys=True)
    return hashlib.sha1(blob.encode()).hexdigest()[:12]


def to_jpeg(img: np.ndarray, quality: int = 88) -> bytes:
    u8 = (np.clip(img, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)
    buf = io.BytesIO()
    Image.fromarray(u8).save(buf, format="JPEG", quality=quality)
    return buf.getvalue()
