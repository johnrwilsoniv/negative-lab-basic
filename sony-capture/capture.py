#!/usr/bin/env python3
"""Tethered RAW capture: connect to the camera, shoot a frame on every Enter.

    python3 capture.py rolls/roll01

Frames land in the given directory as frame-001.ARW, frame-002.ARW, ...,
continuing after the highest number already there. Only RAW files are kept.
Needs python-gphoto2 (in the repo's Nix dev shell) and the camera in PC Remote
mode; see README.md.
"""

import argparse
import re
import sys
import time
from pathlib import Path

import gphoto2 as gp

RAW_EXTS = {".arw"}
FRAME_RE = re.compile(r"^frame-(\d+)\.", re.IGNORECASE)

# Without pcsaveimgsize=Original the camera sends a 1616x1080 proxy JPEG.
SETTINGS = {"imagequality": "RAW", "pcsaveimgsize": "Original"}


def configure(camera):
    config = camera.get_config()
    for name, value in SETTINGS.items():
        try:
            widget = config.get_child_by_name(name)
        except gp.GPhoto2Error:
            sys.exit(f"camera has no '{name}' setting; is it in PC Remote mode?")
        if widget.get_value() != value:
            widget.set_value(value)
            camera.set_single_config(name, widget)
    # Read back: some settings silently refuse to change.
    config = camera.get_config()
    for name, value in SETTINGS.items():
        actual = config.get_child_by_name(name).get_value()
        if actual != value:
            sys.exit(f"could not set {name}={value} (camera reports {actual!r})")


def next_frame_number(outdir):
    nums = [int(m.group(1)) for p in outdir.iterdir() if (m := FRAME_RE.match(p.name))]
    return max(nums, default=0) + 1


def captured_files(camera, timeout_ms=3000):
    """Capture one frame; return the camera paths of every file it produced."""
    path = camera.capture(gp.GP_CAPTURE_IMAGE)
    files = [(path.folder, path.name)]
    # RAW+JPEG and some Sony firmware deliver additional files as events.
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        event, data = camera.wait_for_event(100)
        if event == gp.GP_EVENT_FILE_ADDED:
            files.append((data.folder, data.name))
        elif event == gp.GP_EVENT_CAPTURE_COMPLETE:
            break
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("outdir", type=Path, help="directory to save RAW frames in")
    args = parser.parse_args()
    args.outdir.mkdir(parents=True, exist_ok=True)

    camera = gp.Camera()
    try:
        camera.init()
    except gp.GPhoto2Error as e:
        sys.exit(f"could not connect to camera: {e}")
    try:
        configure(camera)
        print(f"Connected: {camera.get_summary().text.splitlines()[0]}")
        print(f"Saving RAWs to {args.outdir}/. Enter to shoot, Ctrl-D to quit.")
        frame = next_frame_number(args.outdir)
        while True:
            try:
                input()
            except EOFError:
                break
            try:
                files = captured_files(camera)
            except gp.GPhoto2Error as e:
                print(f"capture failed: {e}", file=sys.stderr)
                continue
            raws = [(f, n) for f, n in files if Path(n).suffix.lower() in RAW_EXTS]
            if not raws:
                names = ", ".join(n for _, n in files)
                print(f"no RAW in capture (got {names}); check imagequality", file=sys.stderr)
                continue
            for folder, name in raws:
                dest = args.outdir / f"frame-{frame:03d}{Path(name).suffix.upper()}"
                camera.file_get(folder, name, gp.GP_FILE_TYPE_NORMAL).save(str(dest))
                print(dest)
                frame += 1
    except KeyboardInterrupt:
        pass
    finally:
        camera.exit()


if __name__ == "__main__":
    main()
