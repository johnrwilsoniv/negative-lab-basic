# nlb-invert Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A `nlb` CLI plus a `/nlb-invert` Claude Code skill that turns iPhone photos of Ilford XP2 negatives into cropped 3:2, flipped, rotated, inverted grayscale HEIC positives.

**Architecture:** A small uv-managed Python package (`src/nlb/`) of pure-function modules: `heic` (I/O), `detect` (frame box + rebate trim + flags), `geometry` (inset, 3:2 fit, flip, rotate), `tone` (luma, invert, levels), `pipeline` (composition), `sheet` (contact sheet), and `cli` (`preview` and `render`). The skill runs `preview`, has a review subagent propose rotations and flags, confirms with the user, then runs `render`.

**Tech Stack:** Python ≥3.12, uv, numpy, opencv-python-headless, pillow, pillow-heif, pytest.

**Spec:** `docs/superpowers/specs/2026-09-28-nlb-invert-design.md`

## Global Constraints

- Repo root: `/Users/jrwiv/Developer/Experiments/claude/negative-lab-basic`. All commands run from there.
- Python via `uv` only (`uv run ...`). Never `pip install` into system python3.
- Originals are never modified. Output goes to `<dir>-positive/` (sibling of the input dir) with the same filenames; previews go to `<dir>-positive/.nlb-work/`.
- Output is 8-bit grayscale HEIC with quality 92.
- The crop is exactly 3:2 with even sides (`w*2 == h*3` landscape, `w*3 == h*2` portrait).
- Always flip horizontally. Rotation happens last, in 90° steps: `none | 90cw | 90ccw | 180`.
- Levels use the 0.1 / 99.9 percentiles, and gamma defaults to 1.0 (`out = in ** (1/gamma)`, so >1 brightens).
- Detection constants, measured on the samples, used verbatim: working width 1008; mask `gray > 0.5 × Otsu`; run thresholds rows>0.5 → cols>0.6 → rows>0.9 → cols>0.75; `detect_suspect` if aspect ∉ [1.3, 1.6] or area ∉ [0.20, 0.75]; `partial_or_blank` if low-detail fraction > 0.5 (32px blocks, mean |Laplacian| < 2.0, on the 5×5-blurred working gray).
- Rebate trim constants: limit 8% of the box dimension, skip ≤3% dark remnant, line profile = 10th percentile, threshold = 0.75 × the box's 99.5th percentile.
- Inset: 2% of `min(w, h)` per side.
- Sample photos live in `iphone-negatives/` and are gitignored (personal photos). Tests that need them skip when the folder is absent.
- Every commit message ends with:
  ```
  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01QwexqA7REMwEP2bz6Vwooj
  ```

## Review Focus

1. **`--out` pointing at the input folder.** The user expects a refusal, not overwritten originals. Pinned in Task 8 (`test_render_refuses_input_dir_as_output`).
2. **AppleDouble `._IMG_xxxx.HEIC` files, lowercase `.heic`, `.DS_Store`, `.MOV` and subfolders in the input folder.** Only real HEIC/HEIF files should be processed. Pinned in Task 1 (`test_list_inputs_filters`).
3. **One corrupt or unreadable HEIC in a roll.** The other frames should still be processed, with a non-zero exit at the end. Pinned in Task 8 (`test_preview_continues_past_bad_file`, `test_render_continues_past_bad_file`).
4. **Re-running render into an existing output folder that holds the user's other files.** Only same-named files should be overwritten. Pinned in Task 8 (`test_render_preserves_other_files`).
5. **Typo in `--rotate` (unknown frame name or bad value).** It should fail fast with a clear message before any processing. Pinned in Task 8 (`test_render_rejects_bad_rotation`).

---

## File Structure

```
negative-lab-basic/
├── .gitignore
├── pyproject.toml
├── src/nlb/
│   ├── __init__.py
│   ├── heic.py        # list_inputs, load_rgb, save_gray, to_u8
│   ├── detect.py      # Box, Detection, longest_run, detect_frame, low_detail_fraction, trim_rebate
│   ├── geometry.py    # inset, fit_3x2, flip_h, rotate, ROTATIONS
│   ├── tone.py        # luma, to_positive
│   ├── pipeline.py    # FrameResult, process
│   ├── sheet.py       # contact_sheet
│   └── cli.py         # main, preview/render subcommands, parse_rotations
├── tests/
│   ├── synth.py       # make_negative() synthetic test image
│   ├── test_heic.py
│   ├── test_detect.py
│   ├── test_geometry.py
│   ├── test_tone.py
│   ├── test_pipeline.py
│   ├── test_samples.py
│   ├── test_sheet.py
│   └── test_cli.py
└── skills/nlb-invert/SKILL.md   # symlinked to ~/.claude/skills/nlb-invert
```

---

### Task 1: Project scaffold + HEIC I/O

**Files:**
- Create: `.gitignore`, `pyproject.toml`, `src/nlb/__init__.py`, `src/nlb/heic.py`, `tests/synth.py`
- Test: `tests/test_heic.py`

**Interfaces:**
- Produces:
  - `nlb.heic.list_inputs(folder: Path) -> list[Path]`
  - `nlb.heic.load_rgb(path: Path) -> np.ndarray` (H×W×3 float32 in [0, 1])
  - `nlb.heic.to_u8(img: np.ndarray) -> np.ndarray` (uint8, clipped)
  - `nlb.heic.save_gray(path: Path, gray: np.ndarray, quality: int = 92) -> None` (HEIF for `.heic`/`.heif`, else Pillow infers from the suffix)
  - `tests/synth.py: make_negative(window=(113,165,670,458), size=(1008,756), grain=0.08, rebate=0, seed=0) -> np.ndarray` (H×W×3 float32)

- [ ] **Step 1: Initialize the repo and scaffold**

```bash
git init
```

`.gitignore`:
```
.venv/
__pycache__/
*.pyc
.pytest_cache/
iphone-negatives/
*-positive/
```

`pyproject.toml`:
```toml
[project]
name = "nlb"
version = "0.1.0"
description = "Negative Lab Basic: invert phone photos of B&W film negatives"
requires-python = ">=3.12"
dependencies = [
    "numpy>=2",
    "opencv-python-headless>=4.10",
    "pillow>=11",
    "pillow-heif>=0.21",
]

[project.scripts]
nlb = "nlb.cli:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[dependency-groups]
dev = ["pytest>=8"]

[tool.pytest.ini_options]
pythonpath = ["tests"]
testpaths = ["tests"]
```

`src/nlb/__init__.py`:
```python
"""Negative Lab Basic."""
```

`tests/synth.py`:
```python
"""Synthetic 'phone photo of a negative on a lightbox' for tests."""
import numpy as np


def make_negative(window=(113, 165, 670, 458), size=(1008, 756), grain=0.08, rebate=0, seed=0):
    """Dark mount, sprocket dashes above/below, bright film window.

    Window content is a left-to-right ramp (0.4 -> 0.8) so flips are detectable.
    `rebate` rows at the top of the window are clear film base (0.95).
    """
    rng = np.random.default_rng(seed)
    width, height = size
    img = np.full((height, width), 0.04, np.float32)
    x, y, w, h = window
    for sy in (y - 60, y + h + 25):
        for sx in range(x, x + w, 60):
            img[max(sy, 0):max(sy + 35, 0), sx:sx + 30] = 0.9
    patch = np.tile(np.linspace(0.4, 0.8, w, dtype=np.float32), (h, 1))
    if grain:
        patch += rng.normal(0, grain, (h, w)).astype(np.float32)
    if rebate:
        patch[:rebate] = 0.95
    img[y:y + h, x:x + w] = np.clip(patch, 0, 1)
    return np.repeat(img[..., None], 3, axis=2)
```

Run: `uv sync`
Expected: creates `.venv`, installs deps and pytest.

- [ ] **Step 2: Write the failing tests**

`tests/test_heic.py`:
```python
import numpy as np
from nlb.heic import list_inputs, load_rgb, save_gray, to_u8


def test_list_inputs_filters(tmp_path):
    for name in ["b.heic", "a.HEIC", "c.HEIF", "d.jpg", "e.MOV", ".DS_Store", "._a.HEIC"]:
        (tmp_path / name).write_bytes(b"x")
    (tmp_path / "sub.heic").mkdir()
    assert [p.name for p in list_inputs(tmp_path)] == ["a.HEIC", "b.heic", "c.HEIF"]


def test_to_u8_clips_and_rounds():
    out = to_u8(np.array([-0.5, 0.0, 0.5, 1.0, 2.0]))
    assert out.dtype == np.uint8
    assert out.tolist() == [0, 0, 128, 255, 255]


def test_gray_heic_roundtrip(tmp_path):
    gray = np.tile(np.linspace(0, 1, 300, dtype=np.float32), (200, 1))
    path = tmp_path / "x.HEIC"
    save_gray(path, gray)
    rgb = load_rgb(path)
    assert rgb.shape == (200, 300, 3)
    assert rgb.dtype == np.float32
    assert np.abs(rgb[..., 0] - gray).mean() < 0.02
    assert np.allclose(rgb[..., 0], rgb[..., 1], atol=0.02)


def test_save_gray_jpeg(tmp_path):
    path = tmp_path / "p.jpg"
    save_gray(path, np.full((10, 15), 0.5, np.float32))
    assert load_rgb(path).shape == (10, 15, 3)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_heic.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'nlb.heic'`

- [ ] **Step 4: Implement `src/nlb/heic.py`**

```python
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
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/test_heic.py -v`
Expected: 4 passed

- [ ] **Step 6: Commit**

```bash
git add .gitignore pyproject.toml uv.lock src tests docs
git commit -m "feat: scaffold nlb package with HEIC I/O"
```

---

### Task 2: Frame detection + flags

**Files:**
- Create: `src/nlb/detect.py`
- Test: `tests/test_detect.py`

**Interfaces:**
- Consumes: `tests/synth.make_negative`
- Produces:
  - `Box(x: int, y: int, w: int, h: int)`, a frozen dataclass with `Box.scale(s: float) -> Box`
  - `Detection(box: Box, flags: list[str], low_detail: float)`
  - `longest_run(mask: np.ndarray) -> tuple[int, int]` (half-open `(start, end)`, `(0, 0)` if none)
  - `low_detail_fraction(gray: np.ndarray) -> float`
  - `detect_frame(rgb: np.ndarray) -> Detection` (box in the input's own pixel coordinates)
  - `luma(rgb) -> np.ndarray` (Rec.601 weights 0.299/0.587/0.114; defined here, re-exported by `tone`)

- [ ] **Step 1: Write the failing tests**

`tests/test_detect.py`:
```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_detect.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'nlb.detect'`

- [ ] **Step 3: Implement `src/nlb/detect.py`**

```python
"""Locate the film frame in a phone photo of a negative on a lightbox.

The lightbox shows through the film as the largest bright rectangle; the mount
is dark and the sprocket strips are only ~50% bright, so row/column projection
profiles of a brightness mask isolate the frame window.
"""
from dataclasses import dataclass, field

import cv2
import numpy as np

WORK_WIDTH = 1008
LUMA_WEIGHTS = np.array([0.299, 0.587, 0.114], np.float32)


@dataclass(frozen=True)
class Box:
    x: int
    y: int
    w: int
    h: int

    def scale(self, s: float) -> "Box":
        return Box(round(self.x * s), round(self.y * s), round(self.w * s), round(self.h * s))


@dataclass
class Detection:
    box: Box
    flags: list[str] = field(default_factory=list)
    low_detail: float = 0.0


def luma(rgb: np.ndarray) -> np.ndarray:
    return rgb @ LUMA_WEIGHTS


def longest_run(mask: np.ndarray) -> tuple[int, int]:
    """Half-open (start, end) of the longest run of True; (0, 0) if none."""
    edges = np.flatnonzero(np.diff(np.concatenate([[0], mask.astype(np.int8), [0]])))
    if edges.size == 0:
        return 0, 0
    starts, ends = edges[::2], edges[1::2]
    i = int(np.argmax(ends - starts))
    return int(starts[i]), int(ends[i])


def low_detail_fraction(gray: np.ndarray) -> float:
    """Fraction of 32px blocks with no grain/detail (mean |Laplacian| < 2 on 0-255 gray)."""
    b = 32
    lap = np.abs(cv2.Laplacian(gray.astype(np.float64), cv2.CV_64F))
    h, w = lap.shape
    if h < b or w < b:
        return 1.0
    blocks = lap[: h // b * b, : w // b * b].reshape(h // b, b, w // b, b).mean(axis=(1, 3))
    return float((blocks < 2.0).mean())


def _window(mask: np.ndarray) -> Box | None:
    r0, r1 = longest_run(mask.mean(axis=1) > 0.5)
    if r1 <= r0:
        return None
    c0, c1 = longest_run(mask[r0:r1].mean(axis=0) > 0.6)
    if c1 <= c0:
        return None
    r0, r1 = longest_run(mask[:, c0:c1].mean(axis=1) > 0.9)
    if r1 <= r0:
        return None
    c0, c1 = longest_run(mask[r0:r1].mean(axis=0) > 0.75)
    if c1 <= c0:
        return None
    return Box(c0, r0, c1 - c0, r1 - r0)


def detect_frame(rgb: np.ndarray) -> Detection:
    height, width = rgb.shape[:2]
    scale = WORK_WIDTH / width
    gray8 = (np.clip(luma(rgb), 0, 1) * 255 + 0.5).astype(np.uint8)
    small = cv2.resize(gray8, (WORK_WIDTH, round(height * scale)), interpolation=cv2.INTER_AREA)
    gray = cv2.GaussianBlur(small, (5, 5), 0)
    otsu, _ = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    found = _window(gray > otsu * 0.5)
    if found is None:
        return Detection(Box(0, 0, width, height), ["detect_failed"], low_detail_fraction(gray))

    flags = []
    aspect = max(found.w, found.h) / min(found.w, found.h)
    area = found.w * found.h / gray.size
    if not (1.3 <= aspect <= 1.6) or not (0.20 <= area <= 0.75):
        flags.append("detect_suspect")
    low = low_detail_fraction(gray[found.y:found.y + found.h, found.x:found.x + found.w])
    if low > 0.5:
        flags.append("partial_or_blank")
    box = found.scale(1 / scale)
    box = Box(box.x, box.y, min(box.w, width - box.x), min(box.h, height - box.y))
    return Detection(box, flags, low)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_detect.py -v`
Expected: 9 passed. If `test_detects_window_ignoring_sprockets` fails only on `flags` with `partial_or_blank`, the synthetic grain is too weak after blur. Raise the `make_negative` default `grain` to 0.12. Do not change the detector constants, which were measured on real samples.

- [ ] **Step 5: Commit**

```bash
git add src/nlb/detect.py tests/test_detect.py
git commit -m "feat: detect film frame window via projection profiles"
```

---

### Task 3: Rebate trim

**Files:**
- Modify: `src/nlb/detect.py` (append)
- Test: `tests/test_detect.py` (append)

**Interfaces:**
- Consumes: `Box`
- Produces: `trim_rebate(gray: np.ndarray, box: Box) -> Box`, where `gray` is the un-inverted negative luma (float in [0, 1]) at the same resolution as `box`

- [ ] **Step 1: Write the failing tests** (append to `tests/test_detect.py`)

```python
from nlb.detect import trim_rebate


def _box_image(h=500, w=600, seed=2):
    rng = np.random.default_rng(seed)
    return np.clip(0.45 + rng.normal(0, 0.08, (h, w)), 0, 1).astype(np.float32)


def test_trim_rebate_removes_clear_base_after_mount_remnant():
    g = _box_image()
    g[:10] = 0.05       # dark mount remnant (within 3% skip = 15 rows)
    g[10:32] = 0.95     # clear film base
    assert trim_rebate(g, Box(0, 0, 600, 500)) == Box(0, 32, 600, 468)


def test_trim_rebate_bottom_and_right():
    g = _box_image()
    g[-20:] = 0.95
    g[:, -12:] = 0.95
    assert trim_rebate(g, Box(0, 0, 600, 500)) == Box(0, 0, 588, 480)


def test_trim_rebate_ignores_bright_content_beyond_skip():
    g = _box_image()
    g[:, 30:45] = 0.95  # bright pole in the picture; 30 > 3% of 600 = 18
    assert trim_rebate(g, Box(0, 0, 600, 500)) == Box(0, 0, 600, 500)


def test_trim_rebate_caps_at_limit():
    g = _box_image()
    g[:100] = 0.95      # limit is 8% of 500 = 40
    assert trim_rebate(g, Box(0, 0, 600, 500)).y == 40


def test_trim_rebate_respects_box_offset():
    g = np.zeros((700, 900), np.float32)
    g[100:600, 200:800] = _box_image()
    g[100:120, 200:800] = 0.95
    assert trim_rebate(g, Box(200, 100, 600, 500)) == Box(200, 120, 600, 480)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_detect.py -v -k trim`
Expected: FAIL with `ImportError: cannot import name 'trim_rebate'`

- [ ] **Step 3: Implement** (append to `src/nlb/detect.py`)

```python
def _edge_trim(profile: np.ndarray, threshold: float, limit: int, skip: int) -> int:
    """Lines to trim from the start of `profile`: skip a short dark remnant, then eat clear base."""
    i = 0
    while i < skip and profile[i] <= threshold:
        i += 1
    if i >= skip:
        return 0
    j = i
    while j < limit and profile[j] > threshold:
        j += 1
    return j


def trim_rebate(gray: np.ndarray, box: Box) -> Box:
    """Shrink `box` past bands of clear film base (bright, uniform) along its edges."""
    crop = gray[box.y:box.y + box.h, box.x:box.x + box.w]
    threshold = 0.75 * float(np.percentile(crop, 99.5))
    rows = np.percentile(crop, 10, axis=1)
    cols = np.percentile(crop, 10, axis=0)
    lh, lw = int(0.08 * box.h), int(0.08 * box.w)
    sh, sw = int(0.03 * box.h), int(0.03 * box.w)
    top = _edge_trim(rows, threshold, lh, sh)
    bottom = _edge_trim(rows[::-1], threshold, lh, sh)
    left = _edge_trim(cols, threshold, lw, sw)
    right = _edge_trim(cols[::-1], threshold, lw, sw)
    return Box(box.x + left, box.y + top, box.w - left - right, box.h - top - bottom)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_detect.py -v`
Expected: 14 passed

- [ ] **Step 5: Commit**

```bash
git add src/nlb/detect.py tests/test_detect.py
git commit -m "feat: trim clear film rebate from frame edges"
```

---

### Task 4: Geometry (inset, 3:2 fit, flip, rotate)

**Files:**
- Create: `src/nlb/geometry.py`
- Test: `tests/test_geometry.py`

**Interfaces:**
- Consumes: `nlb.detect.Box`
- Produces:
  - `ROTATIONS = ("none", "90cw", "90ccw", "180")`
  - `inset(box: Box, frac: float) -> Box` (shrinks each side by `round(min(w, h) * frac)`)
  - `fit_3x2(box: Box) -> Box` (largest centered exact 3:2 box with even sides; portrait if `h > w`)
  - `flip_h(img) -> np.ndarray`, `rotate(img, rotation: str) -> np.ndarray` (contiguous copies; `ValueError` on an unknown rotation)

- [ ] **Step 1: Write the failing tests**

`tests/test_geometry.py`:
```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_geometry.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'nlb.geometry'`

- [ ] **Step 3: Implement `src/nlb/geometry.py`**

```python
"""Crop box math and orientation transforms."""
import numpy as np

from nlb.detect import Box

ROTATIONS = ("none", "90cw", "90ccw", "180")
_ROT90_K = {"none": 0, "90cw": -1, "90ccw": 1, "180": 2}


def inset(box: Box, frac: float) -> Box:
    d = round(min(box.w, box.h) * frac)
    return Box(box.x + d, box.y + d, box.w - 2 * d, box.h - 2 * d)


def fit_3x2(box: Box) -> Box:
    """Largest exact 3:2 box with even sides, centered in `box`, oriented like `box`.

    Even sides keep HEIC encoders from padding the image.
    """
    if box.w >= box.h:
        u = min(box.w // 3, box.h // 2) // 2 * 2
        w, h = 3 * u, 2 * u
    else:
        u = min(box.w // 2, box.h // 3) // 2 * 2
        w, h = 2 * u, 3 * u
    return Box(box.x + (box.w - w) // 2, box.y + (box.h - h) // 2, w, h)


def flip_h(img: np.ndarray) -> np.ndarray:
    return np.ascontiguousarray(img[:, ::-1])


def rotate(img: np.ndarray, rotation: str) -> np.ndarray:
    if rotation not in _ROT90_K:
        raise ValueError(f"rotation must be one of {', '.join(ROTATIONS)}; got {rotation!r}")
    return np.ascontiguousarray(np.rot90(img, _ROT90_K[rotation]))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_geometry.py -v`
Expected: 13 passed

- [ ] **Step 5: Commit**

```bash
git add src/nlb/geometry.py tests/test_geometry.py
git commit -m "feat: add 3:2 crop fit, inset, flip and rotation"
```

---

### Task 5: Tone (invert + levels)

**Files:**
- Create: `src/nlb/tone.py`
- Test: `tests/test_tone.py`

**Interfaces:**
- Consumes: `nlb.detect.luma`
- Produces: `to_positive(neg_rgb: np.ndarray, low_pct=0.1, high_pct=99.9, gamma=1.0) -> np.ndarray` (H×W float32 in [0, 1]); `luma` re-exported

- [ ] **Step 1: Write the failing tests**

`tests/test_tone.py`:
```python
import numpy as np

from nlb.tone import to_positive


def _rgb(gray):
    return np.repeat(np.asarray(gray, np.float32)[..., None], 3, axis=2)


def test_inverts_and_stretches_to_full_range():
    neg = _rgb(np.tile(np.linspace(0.3, 0.7, 1000), (10, 1)))
    pos = to_positive(neg)
    assert pos.shape == (10, 1000) and pos.dtype == np.float32
    assert pos[:, 0].mean() > 0.99      # thin negative -> white
    assert pos[:, -1].mean() < 0.01     # dense negative -> black
    assert pos.min() >= 0 and pos.max() <= 1


def test_gamma_above_one_brightens_midtones():
    neg = _rgb(np.tile(np.linspace(0.3, 0.7, 1000), (10, 1)))
    assert to_positive(neg, gamma=2.0)[:, 500].mean() > to_positive(neg)[:, 500].mean() + 0.1


def test_flat_input_returns_black_not_nan():
    pos = to_positive(_rgb(np.full((5, 5), 0.5)))
    assert np.isfinite(pos).all() and pos.max() == 0


def test_uses_luma_not_single_channel():
    neg = np.zeros((4, 4, 3), np.float32)
    neg[:2, :, 1] = 1.0                   # green-bright top half
    pos = to_positive(neg)
    assert pos[:2].mean() < pos[2:].mean()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_tone.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'nlb.tone'`

- [ ] **Step 3: Implement `src/nlb/tone.py`**

```python
"""Negative -> neutral grayscale positive."""
import numpy as np

from nlb.detect import luma

__all__ = ["luma", "to_positive"]


def to_positive(neg_rgb: np.ndarray, low_pct: float = 0.1, high_pct: float = 99.9,
                gamma: float = 1.0) -> np.ndarray:
    """Luma, invert, stretch percentiles to [0, 1], then out ** (1 / gamma)."""
    g = (1.0 - luma(neg_rgb)).astype(np.float32)
    lo, hi = np.percentile(g, [low_pct, high_pct])
    if hi - lo < 1e-6:
        return np.zeros_like(g)
    out = np.clip((g - lo) / (hi - lo), 0.0, 1.0)
    if gamma != 1.0:
        out = out ** np.float32(1.0 / gamma)
    return out
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_tone.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add src/nlb/tone.py tests/test_tone.py
git commit -m "feat: invert negatives to grayscale with auto levels"
```

---

### Task 6: Pipeline + real-sample verification

**Files:**
- Create: `src/nlb/pipeline.py`
- Test: `tests/test_pipeline.py`, `tests/test_samples.py`

**Interfaces:**
- Consumes: `detect_frame`, `trim_rebate`, `Box`, `inset`, `fit_3x2`, `flip_h`, `rotate`, `to_positive`, `luma`
- Produces:
  - `FrameResult(image: np.ndarray, crop: Box, flags: list[str], low_detail: float)`, with `crop` in the input array's pixels
  - `process(rgb: np.ndarray, rotation: str = "none", gamma: float = 1.0, inset_frac: float = 0.02) -> FrameResult`

- [ ] **Step 1: Write the failing tests**

`tests/test_pipeline.py`:
```python
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
```

`tests/test_samples.py`:
```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_pipeline.py tests/test_samples.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'nlb.pipeline'`

- [ ] **Step 3: Implement `src/nlb/pipeline.py`**

```python
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest -v`
Expected: all pass. If a `test_sample_no_rebate_stripe` case fails, look at the frame before changing anything. Run `uv run nlb preview iphone-negatives` (after Task 8), or before then:
  ```bash
  uv run python -c "
  import cv2; from pathlib import Path
  from nlb.heic import load_rgb, save_gray; from nlb.pipeline import process
  rgb = cv2.resize(load_rgb(Path('iphone-negatives/IMG_4025.HEIC')), (1512, 1134), interpolation=cv2.INTER_AREA)
  save_gray(Path('/private/tmp/claude-501/-Users-jrwiv-Developer-Experiments-claude-negative-lab-basic/12286c26-2fea-4abb-bf87-88a188b0620c/scratchpad/check.jpg'), process(rgb).image)"
  ```
  Then Read the JPEG. Report the finding instead of loosening the assertion.

- [ ] **Step 5: Commit**

```bash
git add src/nlb/pipeline.py tests/test_pipeline.py tests/test_samples.py
git commit -m "feat: compose detect, trim, crop, flip, invert pipeline"
```

---

### Task 7: Contact sheet

**Files:**
- Create: `src/nlb/sheet.py`
- Test: `tests/test_sheet.py`

**Interfaces:**
- Consumes: `nlb.heic.to_u8`
- Produces: `contact_sheet(items: list[tuple[str, np.ndarray, list[str]]], thumb: int = 400, cols: int = 3) -> PIL.Image.Image` (RGB; each cell is a thumbnail that fits `thumb×thumb`, with a label under it: the name plus `[!] flag,flag` in red when flagged)

- [ ] **Step 1: Write the failing tests**

`tests/test_sheet.py`:
```python
import numpy as np

from nlb.sheet import CELL_PAD, LABEL_H, contact_sheet


def test_grid_size():
    items = [(f"IMG_{i}", np.full((200, 300), 0.5, np.float32), []) for i in range(4)]
    sheet = contact_sheet(items, thumb=150, cols=3)
    cell_w, cell_h = 150 + 2 * CELL_PAD, 150 + LABEL_H + 2 * CELL_PAD
    assert sheet.size == (3 * cell_w, 2 * cell_h)
    assert sheet.mode == "RGB"


def test_flagged_label_is_red():
    items = [("ok", np.ones((100, 150), np.float32), []),
             ("bad", np.ones((100, 150), np.float32), ["partial_or_blank"])]
    arr = np.asarray(contact_sheet(items, thumb=150, cols=2)).astype(int)
    cell_w = 150 + 2 * CELL_PAD
    label_rows = arr[150 + CELL_PAD:]
    def red(a):
        return ((a[..., 0] > 150) & (a[..., 1] < 80) & (a[..., 2] < 80)).sum()
    assert red(label_rows[:, :cell_w]) == 0
    assert red(label_rows[:, cell_w:]) > 0


def test_empty_items_gives_small_blank_sheet():
    assert contact_sheet([]).size[0] > 0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_sheet.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'nlb.sheet'`

- [ ] **Step 3: Implement `src/nlb/sheet.py`**

```python
"""Labeled contact sheet for review."""
import math

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from nlb.heic import to_u8

CELL_PAD = 8
LABEL_H = 26


def contact_sheet(items: list[tuple[str, np.ndarray, list[str]]], thumb: int = 400,
                  cols: int = 3) -> Image.Image:
    rows = max(1, math.ceil(len(items) / cols))
    cell_w, cell_h = thumb + 2 * CELL_PAD, thumb + LABEL_H + 2 * CELL_PAD
    sheet = Image.new("RGB", (cols * cell_w, rows * cell_h), "white")
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default(size=16)
    for i, (name, img, flags) in enumerate(items):
        cx, cy = (i % cols) * cell_w, (i // cols) * cell_h
        pic = Image.fromarray(to_u8(img)).convert("RGB")
        pic.thumbnail((thumb, thumb))
        sheet.paste(pic, (cx + CELL_PAD + (thumb - pic.width) // 2,
                          cy + CELL_PAD + (thumb - pic.height) // 2))
        label = f"{name}  [!] {','.join(flags)}" if flags else name
        draw.text((cx + CELL_PAD, cy + CELL_PAD + thumb + 4), label,
                  fill=(220, 0, 0) if flags else (0, 0, 0), font=font)
    return sheet
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_sheet.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add src/nlb/sheet.py tests/test_sheet.py
git commit -m "feat: labeled contact sheet"
```

---

### Task 8: CLI (`preview`, `render`)

**Files:**
- Create: `src/nlb/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `list_inputs`, `load_rgb`, `save_gray`, `process`, `contact_sheet`, `ROTATIONS`
- Produces:
  - `main(argv: list[str] | None = None) -> int`: exit 0 ok, 1 if any file failed, 2 on usage errors
  - `parse_rotations(items: list[str]) -> dict[str, str]` (keys are file stems; `ValueError` on bad input)
  - `default_out(folder: Path) -> Path` (`folder.parent / f"{folder.name}-positive"`)
  - Work-dir files: `<stem>.jpg` previews, `contact.jpg`, and `manifest.json` = `{"source": str, "frames": [{"name", "file", "preview", "crop": [x, y, w, h] in source px, "flags", "low_detail"}]}`

- [ ] **Step 1: Write the failing tests**

`tests/test_cli.py`:
```python
import json

import pytest
from synth import make_negative

from nlb.cli import default_out, main, parse_rotations
from nlb.heic import load_rgb, save_gray
from nlb.tone import luma


@pytest.fixture
def roll(tmp_path):
    folder = tmp_path / "roll"
    folder.mkdir()
    save_gray(folder / "IMG_0001.HEIC", luma(make_negative()))
    save_gray(folder / "IMG_0002.HEIC", luma(make_negative(seed=5)))
    return folder


def test_parse_rotations():
    assert parse_rotations(["IMG_1=90cw", "IMG_2.HEIC=180"]) == {"IMG_1": "90cw", "IMG_2": "180"}
    for bad in ["IMG_1", "IMG_1=45", "=90cw"]:
        with pytest.raises(ValueError):
            parse_rotations([bad])


def test_default_out(tmp_path):
    assert default_out(tmp_path / "roll") == tmp_path / "roll-positive"


def test_preview_writes_previews_sheet_manifest(roll):
    assert main(["preview", str(roll)]) == 0
    work = default_out(roll) / ".nlb-work"
    manifest = json.loads((work / "manifest.json").read_text())
    assert [f["name"] for f in manifest["frames"]] == ["IMG_0001", "IMG_0002"]
    frame = manifest["frames"][0]
    assert frame["preview"] == "IMG_0001.jpg" and (work / "IMG_0001.jpg").exists()
    assert len(frame["crop"]) == 4 and frame["flags"] == []
    assert (work / "contact.jpg").exists()
    assert sorted(p.name for p in roll.iterdir()) == ["IMG_0001.HEIC", "IMG_0002.HEIC"]


def test_render_writes_rotated_heic(roll):
    assert main(["render", str(roll), "--rotate", "IMG_0002=90ccw"]) == 0
    out = default_out(roll)
    a = load_rgb(out / "IMG_0001.HEIC")
    b = load_rgb(out / "IMG_0002.HEIC")
    assert a.shape[1] * 2 == a.shape[0] * 3          # landscape 3:2
    assert b.shape[0] * 2 == b.shape[1] * 3          # rotated to portrait
    assert (out / "contact.jpg").exists()


def test_render_refuses_input_dir_as_output(roll):
    before = (roll / "IMG_0001.HEIC").read_bytes()
    assert main(["render", str(roll), "--out", str(roll)]) == 2
    assert (roll / "IMG_0001.HEIC").read_bytes() == before


def test_render_rejects_bad_rotation(roll):
    assert main(["render", str(roll), "--rotate", "IMG_9999=90cw"]) == 2
    assert main(["render", str(roll), "--rotate", "IMG_0001=sideways"]) == 2
    assert not default_out(roll).exists()


def test_render_preserves_other_files(roll):
    out = default_out(roll)
    out.mkdir()
    (out / "keep.txt").write_text("mine")
    assert main(["render", str(roll)]) == 0
    assert (out / "keep.txt").read_text() == "mine"


def test_preview_continues_past_bad_file(roll):
    (roll / "IMG_0000.HEIC").write_bytes(b"not an image")
    assert main(["preview", str(roll)]) == 1
    manifest = json.loads((default_out(roll) / ".nlb-work" / "manifest.json").read_text())
    assert [f["name"] for f in manifest["frames"]] == ["IMG_0001", "IMG_0002"]


def test_render_continues_past_bad_file(roll):
    (roll / "IMG_0000.HEIC").write_bytes(b"not an image")
    assert main(["render", str(roll)]) == 1
    assert (default_out(roll) / "IMG_0002.HEIC").exists()


def test_missing_dir_and_empty_dir(tmp_path):
    assert main(["preview", str(tmp_path / "nope")]) == 2
    assert main(["preview", str(tmp_path)]) == 2


def test_bad_gamma(roll):
    assert main(["preview", str(roll), "--gamma", "0"]) == 2
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_cli.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'nlb.cli'`

- [ ] **Step 3: Implement `src/nlb/cli.py`**

```python
"""nlb command line: `preview` for review, `render` for full-resolution output."""
import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

from nlb.geometry import ROTATIONS
from nlb.heic import list_inputs, load_rgb, save_gray
from nlb.pipeline import process
from nlb.sheet import contact_sheet

PREVIEW_WIDTH = 1512
SHEET_WIDTH = 800


def default_out(folder: Path) -> Path:
    return folder.parent / f"{folder.name}-positive"


def parse_rotations(items: list[str]) -> dict[str, str]:
    rotations = {}
    for item in items:
        name, sep, rot = item.partition("=")
        stem = Path(name).stem
        if not sep or not stem or rot not in ROTATIONS:
            raise ValueError(f"bad --rotate {item!r}; expected NAME={'|'.join(ROTATIONS)}")
        rotations[stem] = rot
    return rotations


def _downscale(img: np.ndarray, width: int) -> np.ndarray:
    if img.shape[1] <= width:
        return img
    height = round(img.shape[0] * width / img.shape[1])
    return cv2.resize(img, (width, height), interpolation=cv2.INTER_AREA)


def _error(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)


def _load(path: Path) -> np.ndarray | None:
    try:
        return load_rgb(path)
    except Exception as e:  # corrupt or unsupported file: report and move on
        _error(f"{path.name}: {e}")
        return None


def _report(path: Path, flags: list[str]) -> None:
    print(f"{path.name}: {', '.join(flags) if flags else 'ok'}")


def cmd_preview(folder: Path, inputs: list[Path], args) -> int:
    work = args.work or default_out(folder) / ".nlb-work"
    work.mkdir(parents=True, exist_ok=True)
    frames, cells, failed = [], [], 0
    for path in inputs:
        rgb = _load(path)
        if rgb is None:
            failed += 1
            continue
        small = _downscale(rgb, PREVIEW_WIDTH)
        result = process(small, gamma=args.gamma)
        preview = work / f"{path.stem}.jpg"
        save_gray(preview, result.image, quality=88)
        crop = result.crop.scale(rgb.shape[1] / small.shape[1])
        frames.append({
            "name": path.stem, "file": path.name, "preview": preview.name,
            "crop": [crop.x, crop.y, crop.w, crop.h],
            "flags": result.flags, "low_detail": round(result.low_detail, 3),
        })
        cells.append((path.stem, result.image, result.flags))
        _report(path, result.flags)
    contact_sheet(cells).save(work / "contact.jpg", quality=88)
    (work / "manifest.json").write_text(json.dumps({"source": str(folder), "frames": frames}, indent=2))
    print(f"previews: {work}")
    return 1 if failed else 0


def cmd_render(folder: Path, inputs: list[Path], args) -> int:
    try:
        rotations = parse_rotations(args.rotate)
    except ValueError as e:
        _error(str(e))
        return 2
    unknown = set(rotations) - {p.stem for p in inputs}
    if unknown:
        _error(f"--rotate names not in {folder}: {', '.join(sorted(unknown))}")
        return 2
    out = (args.out or default_out(folder)).resolve()
    if out == folder:
        _error("output folder is the input folder; refusing to overwrite originals")
        return 2
    out.mkdir(parents=True, exist_ok=True)
    cells, failed = [], 0
    for path in inputs:
        rgb = _load(path)
        if rgb is None:
            failed += 1
            continue
        result = process(rgb, rotation=rotations.get(path.stem, "none"), gamma=args.gamma)
        save_gray(out / path.name, result.image)
        cells.append((path.stem, _downscale(result.image, SHEET_WIDTH), result.flags))
        _report(path, result.flags)
    contact_sheet(cells).save(out / "contact.jpg", quality=88)
    print(f"positives: {out}")
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="nlb", description="Negative Lab Basic")
    sub = ap.add_subparsers(dest="cmd", required=True)
    pv = sub.add_parser("preview", help="low-res positives, contact sheet and manifest for review")
    pv.add_argument("dir", type=Path)
    pv.add_argument("--work", type=Path, help="default: <dir>-positive/.nlb-work")
    rd = sub.add_parser("render", help="full-resolution grayscale HEIC positives")
    rd.add_argument("dir", type=Path)
    rd.add_argument("--rotate", action="append", default=[], metavar="NAME=ROT",
                    help=f"ROT is one of {', '.join(ROTATIONS)}; repeatable")
    rd.add_argument("--out", type=Path, help="default: <dir>-positive")
    for p in (pv, rd):
        p.add_argument("--gamma", type=float, default=1.0, help=">1 brightens midtones")
    args = ap.parse_args(argv)

    folder = args.dir.resolve()
    if not folder.is_dir():
        _error(f"not a folder: {args.dir}")
        return 2
    if args.gamma <= 0:
        _error("--gamma must be > 0")
        return 2
    inputs = list_inputs(folder)
    if not inputs:
        _error(f"no HEIC files in {folder}")
        return 2
    return (cmd_preview if args.cmd == "preview" else cmd_render)(folder, inputs, args)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest -v`
Expected: all pass

- [ ] **Step 5: Smoke-test on the real samples**

Run: `uv run nlb preview iphone-negatives`
Expected: 9 lines with `IMG_4033.HEIC: partial_or_blank` and the rest `ok`, then `previews: .../iphone-negatives-positive/.nlb-work`. Read `iphone-negatives-positive/.nlb-work/contact.jpg` and confirm that every frame is a clean positive with no mount, sprockets or black edge stripe, and that IMG_4031 (church) is sideways.

- [ ] **Step 6: Commit**

```bash
git add src/nlb/cli.py tests/test_cli.py
git commit -m "feat: nlb preview and render commands"
```

---

### Task 9: `/nlb-invert` skill + end-to-end run

**Files:**
- Create: `skills/nlb-invert/SKILL.md`, `README.md`
- Symlink: `~/.claude/skills/nlb-invert` → `<repo>/skills/nlb-invert`

**Interfaces:**
- Consumes: `nlb preview`, `nlb render`, manifest format from Task 8

- [ ] **Step 1: Write `skills/nlb-invert/SKILL.md`**

````markdown
---
name: nlb-invert
description: Negative Lab Basic. Convert iPhone photos of B&W film negatives (HEIC, shot on a lightbox) into cropped 3:2, flipped, rotated, inverted grayscale HEIC positives. Use when the user runs /nlb-invert or asks to invert or convert phone scans of negatives.
argument-hint: "[folder of HEIC negatives]"
---

# nlb-invert

CLI: `uv run --project /Users/jrwiv/Developer/Experiments/claude/negative-lab-basic nlb ...`
(called `NLB` below). Originals are never modified. Output goes to `<dir>-positive/`.

## 1. Preview

Resolve the input folder from `$ARGUMENTS` (default: cwd) to an absolute path. Run:

    NLB preview "<dir>"

It prints one line per frame (`ok` or flags) and the work dir
(`<dir>-positive/.nlb-work/`), which holds `<name>.jpg` previews, `contact.jpg` and
`manifest.json`. Exit 1 means some files were unreadable, so list them for the user and continue.

## 2. Review (one subagent)

Dispatch ONE general-purpose subagent with this prompt, filling in the work dir:

> You are reviewing film-negative conversions. Work dir: `<work>`. Read `manifest.json`,
> then Read EVERY `<name>.jpg` preview individually (the contact sheet is too small
> for detail). Each preview is already cropped, flipped horizontally and inverted.
> For each frame, report:
> - rotation: which rotation makes it upright: `none`, `90cw` (turn clockwise), `90ccw`, or `180`.
>   Judge by sky, horizon, gravity, faces and buildings. Say `none` when unsure and note why.
> - issues: any of `bad_crop` (mount, sprockets, black/white stripe along an edge, or
>   picture visibly cut off), `partial_or_blank` (confirm or dispute the manifest flag),
>   `mirrored` (text reads backwards), `duplicate_of:<name>`, `exposure` (badly
>   under- or over-exposed), `soft` (out of focus or motion blur).
> Reply with ONLY a markdown table: `| frame | rotation | issues | note |`, one row per
> manifest frame, notes ≤ 12 words.

## 3. Confirm with the user

Read `<work>/contact.jpg` yourself. Show the user the subagent's table and the contact
sheet path. Ask them to confirm or edit the rotations (AskUserQuestion when ≤4 frames
need rotating, otherwise ask in plain text). Do NOT render until they confirm.
If `mirrored` is reported, stop and tell the user: the flip is always on by design,
so a mirrored frame means that negative was loaded differently.

## 4. Render

    NLB render "<dir>" --rotate <name>=<rot> [--rotate ...]

Pass only rotations other than `none`. Add `--gamma` only if the user asked for it.

## 5. Verify and report

Read `<dir>-positive/contact.jpg` and check that the rotations took effect. Report
the output folder, the number of frames written, and every frame still flagged
(`partial_or_blank`, `detect_*`, or issues from review).
````

- [ ] **Step 2: Write `README.md`**

```markdown
# Negative Lab Basic

Turns iPhone photos of B&W negatives (lightbox + mount, HEIC) into cropped 3:2,
flipped, inverted grayscale HEIC positives. A pun on Negative Lab Pro.

    uv run nlb preview <dir>                         # previews + contact sheet + manifest
    uv run nlb render <dir> --rotate IMG_4031=90ccw  # full-res into <dir>-positive/

In Claude Code: `/nlb-invert <dir>` runs preview → agent review → your confirmation → render.
Install the skill: `ln -s "$PWD/skills/nlb-invert" ~/.claude/skills/nlb-invert`

Tests: `uv run pytest` (sample-based tests need `iphone-negatives/`).
```

- [ ] **Step 3: Install the skill symlink**

```bash
mkdir -p ~/.claude/skills
ln -sfn /Users/jrwiv/Developer/Experiments/claude/negative-lab-basic/skills/nlb-invert ~/.claude/skills/nlb-invert
ls -l ~/.claude/skills/nlb-invert/SKILL.md
```
Expected: the symlink resolves and `SKILL.md` is listed.

- [ ] **Step 4: End-to-end run following SKILL.md on the samples**

Follow sections 1–5 of the skill against `iphone-negatives/`. Expected: the review proposes `90ccw` (or `90cw`, whichever makes the steeple point up) for IMG_4031, flags IMG_4033 as partial, and marks IMG_4028–4030 as near-duplicates. After the user confirms, `iphone-negatives-positive/` holds 9 grayscale HEICs and `contact.jpg`. Then run `sips -g pixelWidth -g pixelHeight -g space iphone-negatives-positive/IMG_4031.HEIC` and check that it's portrait and in a Gray color space.

- [ ] **Step 5: Commit**

```bash
git add skills README.md
git commit -m "feat: nlb-invert skill"
```
