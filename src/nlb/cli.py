"""nlb command line: `preview` for review, `render` for full-resolution output, `develop` for raw rolls."""
import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path

import cv2
import numpy as np

from nlb.geometry import ROTATIONS
from nlb.heic import list_inputs, load_rgb, output_name, save_gray
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
            save_gray(out / output_name(path), result.image)
        except Exception as e:  # corrupt file or processing failure: report and move on
            _error(f"{path.name}: {e}")
            failed += 1
            continue
        cells.append((path.stem, _downscale(result.image, SHEET_WIDTH), result.flags))
        _report(path, result.flags)
    contact_sheet(cells).save(out / "contact.jpg", quality=88)
    print(f"positives: {out}")
    return 1 if failed else 0


def cmd_develop(args) -> int:
    """Render a roll of raw negatives to 16-bit TIFFs from <dir>/roll.json (or auto settings)."""
    from nlb import develop

    folder = args.dir.resolve()
    if not folder.is_dir():
        _error(f"not a folder: {args.dir}")
        return 2
    roll_file = folder / "roll.json"
    if roll_file.is_file():
        roll = json.loads(roll_file.read_text())
        settings, frames = roll.get("settings", {}), roll.get("frames", {})
    else:
        settings = {"film": args.film, "flip": True, "base": None, "levels": None}
        frames = {p.stem: {"file": p.name} for p in sorted(folder.glob("*.[Aa][Rr][Ww]"))
                  if not p.name.startswith("._")}
    if args.film:
        settings = {**settings, "film": args.film}
    names = [n for n, f in frames.items() if not f.get("rejected")]
    if args.frames:
        wanted = set(args.frames.split(","))
        unknown = wanted - set(frames)
        if unknown:
            _error(f"frames not in the roll: {', '.join(sorted(unknown))}")
            return 2
        names = [n for n in names if n in wanted]
    if not names:
        _error(f"no frames to develop in {folder}")
        return 2
    if args.check:
        return _check_exposure(folder, frames, names, settings)
    out = (args.out or default_out(folder)).resolve()
    if _same_dir(out, folder):
        _error("output folder is the input folder; refusing to write among originals")
        return 2
    out.mkdir(parents=True, exist_ok=True)
    failed = 0
    for name in names:
        frame = frames[name]
        path = folder / frame.get("file", f"{name}.ARW")
        try:
            lin = develop.load_linear(path, preview=args.preview)
            if not frame.get("crop"):
                frame = {**frame, **develop.auto_frame(lin, settings)}
            develop.write_tiff(out / f"{name}.tif", develop.develop(lin, settings, frame))
        except Exception as e:  # corrupt file or processing failure: report and move on
            _error(f"{path.name}: {e}")
            failed += 1
            continue
        print(f"{name}: ok")
    print(f"positives: {out}")
    return 1 if failed else 0


def _check_exposure(folder: Path, frames: dict, names: list[str], settings: dict) -> int:
    from nlb import develop

    failed = 0
    for name in names:
        path = folder / frames[name].get("file", f"{name}.ARW")
        try:
            rep = develop.exposure_report(develop.load_linear(path, preview=True), settings)
        except Exception as e:  # corrupt file: report and move on
            _error(f"{path.name}: {e}")
            failed += 1
            continue
        ratio = rep["floor_over_flare"]
        print(f"{name}: base at {rep['base_headroom']:.0%} of full scale, "
              f"floor/flare {f'{min(ratio):.1f}' if ratio else 'n/a'}: {rep['advice']}")
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
    dv = sub.add_parser("develop", help="16-bit TIFF positives from raw captures and roll.json")
    dv.add_argument("dir", type=Path)
    dv.add_argument("--out", type=Path, help="default: <dir>-positive")
    dv.add_argument("--frames", help="comma-separated frame names (default: all kept frames)")
    dv.add_argument("--film", choices=["c41", "bw"], help="override settings.film (default c41 without roll.json)")
    dv.add_argument("--preview", action="store_true", help="half-size decode, for a quick look")
    dv.add_argument("--check", action="store_true", help="report capture exposure per frame; render nothing")
    st = sub.add_parser("studio", help="web app: tethered capture, review and 16-bit TIFF render")
    st.add_argument("dir", type=Path, help="roll folder (created if missing)")
    st.add_argument("--port", type=int, default=8765)
    st.add_argument("--host", default="127.0.0.1")
    st.add_argument("--prefix", default="frame", help="new captures are <prefix>-NNN (default: frame)")
    st.add_argument("--fake-camera", type=Path, metavar="DIR",
                    help="no camera: replay the raw files in DIR as captures")
    st.add_argument("--no-open", action="store_true", help="don't open a browser")
    args = ap.parse_args(argv)

    if args.cmd == "develop":
        if args.film is None and not (args.dir / "roll.json").is_file():
            args.film = "c41"
        return cmd_develop(args)

    if args.cmd == "studio":
        from nlb.studio.server import serve
        if args.fake_camera and not args.fake_camera.is_dir():
            _error(f"not a folder: {args.fake_camera}")
            return 2
        return serve(args.dir, host=args.host, port=args.port, prefix=args.prefix,
                     fake_camera=args.fake_camera, open_browser=not args.no_open)

    folder = args.dir.resolve()
    if not folder.is_dir():
        _error(f"not a folder: {args.dir}")
        return 2
    if args.gamma <= 0:
        _error("--gamma must be > 0")
        return 2
    inputs = list_inputs(folder)
    if not inputs:
        _error(f"no HEIC, DNG or ARW files in {folder}")
        return 2
    stems = Counter(p.stem for p in inputs)
    clashes = sorted(stem for stem, n in stems.items() if n > 1)
    if clashes:
        _error(f"several files share a name (e.g. HEIC + DNG/ARW); keep one of each: {', '.join(clashes)}")
        return 2
    return (cmd_preview if args.cmd == "preview" else cmd_render)(folder, inputs, args)
