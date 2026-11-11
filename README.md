# Negative Lab Basic

Scan 35mm film with a camera, then turn the negatives into positives. It has three parts: a 3D-printed
scanning rig, a local web app for tethered capture and editing, and a command-line tool for batch
conversion. The name is a pun on Negative Lab Pro.

## The rig

A light-tight path from camera to film: Sony A7 IV + Laowa 90mm 2X macro → lens adapter → tube → film
gate → light dock holding a CineStill CS-Lite. Strips slide sideways through the gate, and a switch on
the lid clamps them flat. It's modelled in CadQuery; nothing has been printed yet.

**See it at [nlb.jrwiv.com](https://nlb.jrwiv.com)**: the assembled model, a print preview, and
every STL and STEP file.

Build the STLs yourself, from `rig/`:

    uv run python build.py [--wd W] [--axis A]   # STEP + STL per part into rig/exports/
    uv run pytest                                # checks on the built solids

`--wd` (working distance) and `--axis` (table to lens centre) default to the measured 111 and 40.5.
The design notes, rulings and pre-print checklist are in [rig/PLAN.md](rig/PLAN.md).

## Studio

A local web app for scanning a roll with a tethered Sony: capture, review, and render C-41 color
or B&W to 16-bit TIFF.

    nix run . -- studio sony-capture/rolls/roll02    # opens http://127.0.0.1:8765/

- **Capture**: inverted live view with a focus aid and auto-framing. Test shots are checked for
  exposure, focus and framing before they go into the roll.
- **Review**: crop, rotate, straighten, exposure and color, and film-base pick, per frame or locked
  to the roll.
- **Process**: nlb's own engine or darktable's negadoctor.
- **Render**: full-res TIFFs of the kept frames into `<roll>-positive/`.

Edits live in `<roll>/roll.json`, and originals are never modified. `--fake-camera <dir>` replays
raw files when there's no camera. Camera setup: [sony-capture/](sony-capture/README.md).

## Command line

    uv run nlb preview <dir>                         # low-res positives, contact sheet, manifest
    uv run nlb render <dir> --rotate IMG_4031=90ccw  # full-res grayscale HEIC into <dir>-positive/
    uv run nlb develop <roll-dir>                    # 16-bit TIFFs from raws + roll.json
    uv run nlb develop <roll-dir> --check            # exposure report only
    uv run nlb studio <roll-dir>                     # the studio, above

`preview` and `render` take iPhone HEIC, ProRAW/DNG or Sony ARW shot on a lightbox. Each output is
cropped to 3:2, mirrored, inverted and rotated (`IMG_1.DNG` → `IMG_1.HEIC`).

Tests: `uv run pytest`. With Nix: `nix run . -- <command>`, or `nix develop -c pytest`.

## Skills

- **`/nlb-invert <dir>`** (Claude Code): preview → agent review → your OK → render. Install it with
  `ln -s "$PWD/skills/nlb-invert" ~/.claude/skills/nlb-invert`.
