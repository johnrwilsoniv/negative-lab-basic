"""Headless darktable: develop a raw negative with the A7 IV lightbox negadoctor styles.

The styles live in sony-capture/darktable (packaged as nlb/darktable_styles). darktable-cli
develops the whole frame; the studio's geometry (flip, deskew, crop, rotation) is applied to the
result with `develop.place`. The styles' negadoctor values are fixed rather than measured from
the image, so cropping before or after darktable gives the same pixels.

A picked film base becomes negadoctor's Dmin, the per-roll step of the styles' workflow. Dmin
lives in negadoctor's input space (darktable's linear Rec2020 working RGB, after the style's white balance,
exposure and, for B&W, monochrome mixer), which is an affine map of `load_linear`'s camera RGB.
`input_transform` measures that map once per camera and style by rendering a frame with
negadoctor off and fitting it against the linear decode.

darktable-cli only applies styles from its library database, so each run writes the style it
needs (the .dtstyle's items, Dmin patched in) into a private config dir under
~/.cache/nlb/darktable, leaving the user's own darktable library alone. One darktable-cli runs
at a time per config dir; a file lock serializes them, across processes too.
"""
import base64
import fcntl
import hashlib
import json
import os
import shutil
import sqlite3
import struct
import subprocess
import tempfile
import threading
import xml.etree.ElementTree as ET
import zlib
from pathlib import Path

import cv2
import numpy as np
import rawpy

STYLE_FILES = {"c41": "negative-c41.dtstyle", "bw": "negative-bw.dtstyle"}
TIMEOUT = 300           # seconds per darktable-cli run
PREVIEW_CACHE_FILES = 400
RUN_STYLE = "nlb | run"  # the style each run writes and applies
PROBE_WIDTH = 1200       # input_transform renders at this width
TRANSFORM_VERSION = 1
# darktable's Dmin slider stops at 1.5 but the parameter takes more, and a lightbox capture
# exposed to the right puts the base well above it (red ~3 for the A7 IV); clipping there
# skews the channel ratios into a cyan-green cast
DMIN_RANGE = (1e-4, 20.0)


class DarktableError(RuntimeError):
    pass


def styles_dir() -> Path | None:
    """Folder holding both .dtstyle files: $NLB_DARKTABLE_STYLES, the packaged copy, or the repo's."""
    env = os.environ.get("NLB_DARKTABLE_STYLES")
    here = Path(__file__).resolve().parent
    candidates = [Path(env)] if env else [here / "darktable_styles",
                                          here.parents[1] / "sony-capture" / "darktable"]
    for d in candidates:
        if all((d / f).is_file() for f in STYLE_FILES.values()):
            return d
    return None


def executable() -> str | None:
    return shutil.which(os.environ.get("NLB_DARKTABLE_CLI", "darktable-cli"))


def style_name(film: str) -> str:
    return _read_style(_style_path(film))["name"]


def status() -> dict:
    """{"available", "error", "styles": {film: style name}} for the studio UI."""
    d = styles_dir()
    if executable() is None:
        return {"available": False, "error": "darktable-cli not found on PATH", "styles": {}}
    if d is None:
        return {"available": False, "error": "darktable styles not found (set NLB_DARKTABLE_STYLES)",
                "styles": {}}
    return {"available": True, "error": None, "styles": {f: style_name(f) for f in STYLE_FILES}}


# --- rendering ---

def render(raw: Path, film: str, shape: tuple[int, int], width: int = 0,
           base: list[float] | None = None) -> np.ndarray:
    """darktable's positive of `raw` as sRGB [0, 1] float32, H x W x 3 with (H, W) = `shape`.

    The result is in sensor orientation and covers the same pixels as `develop.load_linear`
    (`shape` is that decode's size, or a downscaled preview's). `width` > 0 renders at most that
    wide (fast, cached on disk); 0 is full resolution, 16-bit. `base` (film base in
    `load_linear` RGB, the studio's pick) sets negadoctor's Dmin; None keeps the style's.
    """
    raw = Path(raw)
    items = style_items(film, dmin=film_base_dmin(raw, film, base) if base else None)
    cache = None
    if width:
        st = raw.stat()
        key = hashlib.sha1(repr((str(raw.resolve()), st.st_mtime_ns, st.st_size, width,
                                 _digest(items))).encode()).hexdigest()
        cache = cache_root() / "previews" / f"{key}.png"
        if cache.is_file():
            img = cv2.imread(str(cache), cv2.IMREAD_UNCHANGED)
            if img is not None:
                return fit(img[..., ::-1].astype(np.float32) / np.float32(65535), shape)
    img = to_sensor(_run(raw, items, width), _raw_flip(raw))
    if cache is not None:
        _store(cache, img)
    return fit(img, shape)


def film_base_dmin(raw: Path, film: str, base) -> list[float]:
    """negadoctor's Dmin for a film base given in `load_linear` camera RGB."""
    m = input_transform(raw, film)
    dmin = m[:, :3] @ np.asarray(base, np.float64) + m[:, 3]
    return [round(float(v), 6) for v in np.clip(dmin, *DMIN_RANGE)]


def input_transform(raw: Path, film: str) -> np.ndarray:
    """3 x 4 affine from `load_linear` camera RGB to negadoctor's input, for `raw`'s camera.

    Fitted on `raw` rendered with negadoctor off and exported as linear Rec2020. It depends
    on the camera and the style only, so it is cached under that key.
    """
    with rawpy.imread(str(raw)) as r:
        camera = (np.asarray(r.rgb_xyz_matrix).round(6).tolist(), list(r.black_level_per_channel),
                  int(r.white_level))
    probe_items = style_items(film, negadoctor=False)
    key = hashlib.sha1(repr((camera, _digest(probe_items), TRANSFORM_VERSION)).encode()).hexdigest()
    store = cache_root() / "transforms.json"
    try:
        known = json.loads(store.read_text())
    except (OSError, ValueError):
        known = {}
    if key in known:
        return np.asarray(known[key], np.float64)

    from nlb import develop  # heavy; only needed for this one-time fit
    lin = develop.load_linear(raw, preview=True)
    probe = _run(raw, probe_items, PROBE_WIDTH, linear=True)
    probe = fit(to_sensor(probe, _raw_flip(raw)), _scaled(lin.shape, PROBE_WIDTH))
    lin = cv2.resize(lin, probe.shape[1::-1], interpolation=cv2.INTER_AREA)
    m = fit_affine(lin, probe)
    known[key] = m.round(8).tolist()
    store.parent.mkdir(parents=True, exist_ok=True)
    tmp = store.with_suffix(".tmp")
    tmp.write_text(json.dumps(known, indent=1))
    os.replace(tmp, store)
    return m


def fit_affine(src: np.ndarray, dst: np.ndarray) -> np.ndarray:
    """Least-squares 3 x 4 map with dst ~ M @ [src, 1], from two aligned H x W x 3 images.

    Blurred first (demosaic and resampling differ), skipping near-clipped and black pixels,
    then refitted without the worst residuals.
    """
    a = cv2.GaussianBlur(np.ascontiguousarray(src, np.float32), (0, 0), 2).reshape(-1, 3)
    b = cv2.GaussianBlur(np.ascontiguousarray(dst, np.float32), (0, 0), 2).reshape(-1, 3)
    ok = (a.max(axis=1) < 0.9) & (a.min(axis=1) > 1e-3) & np.isfinite(b).all(axis=1)
    a, b = a[ok][::max(1, ok.sum() // 60000)], b[ok][::max(1, ok.sum() // 60000)]
    if len(a) < 100:
        raise DarktableError("too few usable pixels to relate darktable to the raw decode")
    x = np.hstack([a, np.ones((len(a), 1), np.float32)]).astype(np.float64)
    for _ in range(2):
        m, *_ = np.linalg.lstsq(x, b, rcond=None)
        err = np.abs(x @ m - b).max(axis=1)
        keep = err <= np.percentile(err, 95)
        x, b = x[keep], b[keep]
    return m.T


def style_items(film: str, dmin: list[float] | None = None, negadoctor: bool = True) -> list[tuple]:
    """The film's .dtstyle items, with negadoctor's Dmin replaced or negadoctor switched off."""
    items = []
    for item in _read_style(_style_path(film))["items"]:
        num, module, op, params, enabled, *rest = item
        if op == "negadoctor":
            if not negadoctor:
                enabled = 0
            elif dmin is not None:  # struct: int film_stock, float Dmin[4], ...
                params = params[:4] + struct.pack("<4f", *dmin, 0.0) + params[20:]
        items.append((num, module, op, params, enabled, *rest))
    return items


def sensor_shape(raw: Path) -> tuple[int, int]:
    """(H, W) of `develop.load_linear(raw)` at full resolution, without decoding it."""
    with rawpy.imread(str(raw)) as r:
        return r.sizes.height, r.sizes.width


def to_sensor(img: np.ndarray, flip: int) -> np.ndarray:
    """Undo the EXIF orientation darktable applied (LibRaw flip code: 3 = 180, 5 = 90 CCW, 6 = 90 CW)."""
    k = {3: 2, 5: -1, 6: 1}.get(int(flip), 0)
    return np.ascontiguousarray(np.rot90(img, k)) if k else img


def fit(img: np.ndarray, shape: tuple[int, int]) -> np.ndarray:
    """Trim darktable's extra sensor margin, then scale to `shape`.

    darktable (rawspeed) keeps a few more edge pixels than LibRaw, on the right/bottom: the two
    agree at the top-left corner. Trimming to LibRaw's aspect from there lines them up.
    """
    h, w = shape
    ih, iw = img.shape[:2]
    if iw * h > ih * w:      # wider than LibRaw's frame: extra columns
        img = img[:, :max(1, round(ih * w / h))]
    elif iw * h < ih * w:    # taller: extra rows
        img = img[:max(1, round(iw * h / w))]
    if img.shape[:2] != (h, w):
        shrink = img.shape[0] > h
        img = cv2.resize(np.ascontiguousarray(img), (w, h),
                         interpolation=cv2.INTER_AREA if shrink else cv2.INTER_CUBIC)
    return np.ascontiguousarray(img, np.float32)


def _scaled(shape: tuple, width: int) -> tuple[int, int]:
    h, w = shape[:2]
    return (h, w) if w <= width else (max(1, round(h * width / w)), width)


def _run(raw: Path, items: list[tuple], width: int, linear: bool = False) -> np.ndarray:
    """One darktable-cli export of `raw` with `items` as the style: sRGB 16-bit, or with
    `linear`, 32-bit float linear Rec2020 (darktable's default working profile)."""
    exe = executable()
    if exe is None:
        raise DarktableError("darktable-cli not found on PATH")
    with _lock():
        config = _config()
        put_style(config / "data.db", RUN_STYLE, "written by nlb for each darktable-cli run", items)
        with tempfile.TemporaryDirectory(prefix="nlb-dt-") as tmp:
            out = Path(tmp) / "out.tif"
            cmd = [exe, str(raw), str(out), "--style", RUN_STYLE,
                   "--width", str(width), "--height", str(width), "--hq", "false" if width else "true",
                   "--core", "--configdir", str(config), "--library", ":memory:",
                   "--conf", f"plugins/imageio/format/tiff/bpp={32 if linear else 16}"]
            if linear:  # uncompressed: darktable's float predictor needs imagecodecs to read
                cmd[cmd.index("--core"):cmd.index("--core")] = ["--icc-type", "LIN_REC2020"]
                cmd += ["--conf", "plugins/imageio/format/tiff/compress=0"]
            try:
                p = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT)
            except subprocess.TimeoutExpired:
                raise DarktableError(f"darktable-cli timed out after {TIMEOUT} s on {raw.name}")
            if not out.is_file():
                log = (p.stdout + p.stderr).strip().splitlines()
                raise DarktableError(f"darktable-cli failed on {raw.name}: " + " | ".join(log[-3:]))
            import tifffile
            img = tifffile.imread(out)
    if img.ndim != 3 or img.shape[2] < 3:
        raise DarktableError(f"unexpected darktable output {img.shape} for {raw.name}")
    img = img[..., :3]
    if img.dtype.kind == "f":
        return img.astype(np.float32)
    return img.astype(np.float32) * np.float32(1 / 65535 if img.dtype == np.uint16 else 1 / 255)


def _raw_flip(raw: Path) -> int:
    with rawpy.imread(str(raw)) as r:
        return r.sizes.flip


def _store(path: Path, img: np.ndarray) -> None:
    """16-bit PNG in the preview cache; keeps the newest PREVIEW_CACHE_FILES."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp.png")
    u16 = (np.clip(img, 0.0, 1.0) * 65535.0 + 0.5).astype(np.uint16)
    if cv2.imwrite(str(tmp), np.ascontiguousarray(u16[..., ::-1])):
        os.replace(tmp, path)
    files = sorted(path.parent.glob("*.png"), key=lambda p: p.stat().st_mtime)
    for old in files[:-PREVIEW_CACHE_FILES]:
        old.unlink(missing_ok=True)


# --- config dir and styles ---

_THREAD_LOCK = threading.Lock()  # flock is per open file; this covers threads of one process


def cache_root() -> Path:
    base = os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache"
    return Path(base) / "nlb" / "darktable"


class _lock:
    def __enter__(self):
        _THREAD_LOCK.acquire()
        try:
            cache_root().mkdir(parents=True, exist_ok=True)
            self.f = open(cache_root() / "lock", "w")
            fcntl.flock(self.f, fcntl.LOCK_EX)
        except BaseException:
            _THREAD_LOCK.release()
            raise
        return self

    def __exit__(self, *exc):
        try:
            fcntl.flock(self.f, fcntl.LOCK_UN)
            self.f.close()
        finally:
            _THREAD_LOCK.release()


def _config() -> Path:
    """The private config dir, with data.db created. Call under _lock."""
    config = cache_root() / "config"
    db = config / "data.db"
    if not db.is_file():
        # darktable creates (and migrates) its databases on startup, even with nothing to export
        config.mkdir(parents=True, exist_ok=True)
        subprocess.run([executable(), str(config / "none.ARW"), str(config / "none.jpg"),
                        "--core", "--configdir", str(config), "--library", ":memory:"],
                       capture_output=True, timeout=TIMEOUT)
        (config / "data.db.lock").unlink(missing_ok=True)
        if not db.is_file():
            raise DarktableError(f"darktable-cli did not create {db}")
    return config


def put_style(db: Path, name: str, description: str, items: list[tuple]) -> None:
    """Write a style into a darktable data.db, replacing any style of the same name."""
    con = sqlite3.connect(db)
    try:
        with con:
            con.execute("DELETE FROM style_items WHERE styleid IN (SELECT id FROM styles WHERE name = ?)", (name,))
            con.execute("DELETE FROM styles WHERE name = ?", (name,))
            sid = con.execute("INSERT INTO styles (name, description) VALUES (?, ?)", (name, description)).lastrowid
            con.executemany(
                "INSERT INTO style_items (styleid, num, module, operation, op_params, enabled,"
                " blendop_params, blendop_version, multi_priority, multi_name, multi_name_hand_edited)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [(sid, *item) for item in items])
    finally:
        con.close()


def _read_style(path: Path) -> dict:
    root = ET.parse(path).getroot()
    items = []
    for p in root.iter("plugin"):
        t = lambda k: (p.findtext(k) or "").strip()  # noqa: E731
        items.append((int(t("num")), int(t("module")), t("operation"), _blob(t("op_params")),
                      int(t("enabled")), _blob(t("blendop_params")), int(t("blendop_version")),
                      int(t("multi_priority") or 0), t("multi_name"), int(t("multi_name_hand_edited") or 0)))
    return {"name": root.findtext("info/name"), "description": root.findtext("info/description") or "",
            "items": items}


def _blob(text: str) -> bytes:
    """darktable's XMP encoding of a params blob: hex, or "gz" + 2 digits + base64(zlib)."""
    if text.startswith("gz"):
        return zlib.decompress(base64.b64decode(text[4:]))
    return bytes.fromhex(text)


def _style_path(film: str) -> Path:
    d = styles_dir()
    if d is None:
        raise DarktableError("darktable styles not found (set NLB_DARKTABLE_STYLES)")
    return d / STYLE_FILES["bw" if film == "bw" else "c41"]


def _digest(items: list[tuple]) -> str:
    return hashlib.sha1(repr(items).encode()).hexdigest()
