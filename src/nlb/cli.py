"""nlb command line: `preview` for review, `render` for full-resolution output."""
import argparse
import json
import os
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


def _same_dir(a: Path, b: Path) -> bool:
    """True when `a` is the folder `b`, including case variants and firmlinks on macOS."""
    return a.exists() and os.path.samefile(a, b)


def _report(path: Path, flags: list[str]) -> None:
    print(f"{path.name}: {', '.join(flags) if flags else 'ok'}")


def cmd_preview(folder: Path, inputs: list[Path], args) -> int:
    work = args.work or default_out(folder) / ".nlb-work"
    if _same_dir(work, folder):
        _error("work folder is the input folder; refusing to write among originals")
        return 2
    work.mkdir(parents=True, exist_ok=True)
    frames, cells, failed = [], [], 0
    for path in inputs:
        try:
            rgb = load_rgb(path)
            small = _downscale(rgb, PREVIEW_WIDTH)
            result = process(small, gamma=args.gamma)
            preview = work / f"{path.stem}.jpg"
            save_gray(preview, result.image, quality=88)
        except Exception as e:  # corrupt file or processing failure: report and move on
            _error(f"{path.name}: {e}")
            failed += 1
            continue
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
    if _same_dir(out, folder):
        _error("output folder is the input folder; refusing to overwrite originals")
        return 2
    out.mkdir(parents=True, exist_ok=True)
    cells, failed = [], 0
    for path in inputs:
        try:
            rgb = load_rgb(path)
            result = process(rgb, rotation=rotations.get(path.stem, "none"), gamma=args.gamma)
            save_gray(out / path.name, result.image)
        except Exception as e:  # corrupt file or processing failure: report and move on
            _error(f"{path.name}: {e}")
            failed += 1
            continue
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
