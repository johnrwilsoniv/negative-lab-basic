# Negative Lab Basic

Turns photos of B&W negatives (lightbox + mount; iPhone HEIC or ProRAW/DNG, Sony ARW)
into cropped 3:2, flipped, inverted grayscale HEIC positives (`IMG_1.DNG` → `IMG_1.HEIC`).
A pun on Negative Lab Pro.

    uv run nlb preview <dir>                         # previews + contact sheet + manifest
    uv run nlb render <dir> --rotate IMG_4031=90ccw  # full-res into <dir>-positive/

In Claude Code: `/nlb-invert <dir>` runs preview → agent review → your confirmation → render.
Install the skill: `ln -s "$PWD/skills/nlb-invert" ~/.claude/skills/nlb-invert`

## Studio: tethered capture, review and color

`nlb studio` is a local web app for camera scanning (Sony A7 IV + macro lens + film
holder): capture, review and render a roll, C-41 color or B&W, to 16-bit TIFF.

    nix run . -- studio sony-capture/rolls/roll02    # opens http://127.0.0.1:8765/

- **Capture**: inverted live view (2×/4× focus zoom, focus meter, and a dashed box where
  auto-frame finds the picture, with the strip's tilt), `Space` to shoot, `R` to reshoot
  the last frame. The camera's own shutter button works too. Frames land in the roll
  folder as `frame-001.ARW`, `frame-002.ARW`, … and numbering resumes across sessions.
  On connect it sets `imagequality=RAW` and `pcsaveimgsize=Original`.
- **Test shots** (Shoot mode *Test first*, the default): a capture doesn't go into the roll.
  It gets checked first: exposure (film base vs the 60–85% target, with the shutter speed
  to set), clipping, framing and centering, strip tilt, even light, stray light, focus
  (sprocket-hole edge sharpness vs your earlier test shots) and whether it matches the
  roll's earlier frames. Look at it as *Frame*, *Result* or *Exposure* (clipped pixels in
  red), then `Enter` keeps it as the next frame, *Replace* swaps it for the last frame, and
  `Del` throws it away. A new test shot replaces (deletes) the previous one. `L` flips
  between live view and the test shot. *Direct* mode sends captures straight to the roll.
- **Review**: per frame crop (drag; `C`), rotate (`[` `]`), straighten, exposure / contrast /
  color sliders, reject (`X`); `←` `→` to move. Per roll: film type, mirror, film base
  (*Pick from rebate* on the negative view) and *Lock levels to roll* for consistent color.
- **Process** (per frame, `D` toggles): nlb's own engine, or darktable. The darktable
  option runs `darktable-cli` headless with the negadoctor styles in
  [sony-capture/darktable/](sony-capture/darktable/README.md) (C-41 or B&W, following the
  roll's film type), then applies the frame's crop, rotation and straighten. A picked film
  base (*Pick from rebate*) becomes negadoctor's Dmin for the roll; on *Auto* the style's own
  Dmin is used. The sliders and levels only affect nlb. A darktable preview takes a few seconds the first time
  and is cached in `~/.cache/nlb/darktable/`. *Copy* / *Paste to all* include this setting, and
  new captures inherit it from the previous frame.
- **Render roll**: full-res 16-bit TIFFs of the kept frames into `<roll>-positive/`.

Edits live in `<roll>/roll.json`; originals are never modified (reshoots move the old
raw to `<roll>/.nlb/trash/`). No camera handy? `--fake-camera <dir>` replays raw files
from `<dir>` as captures. Capture needs the gphoto2 Python module (`pip install 'nlb[camera]'`,
or `nix develop`); without it the studio still runs with Capture grayed out. With no camera
plugged in, it connects as soon as one is. Camera setup and troubleshooting:
[sony-capture/](sony-capture/README.md).
The conversion engine is `src/nlb/develop.py`; see
[its plan](docs/superpowers/plans/2026-10-10-develop-engine.md).

Headless, the same engine renders a roll from its `roll.json` (or picks crop, deskew, film
base and levels per frame without one). Auto-framing handles a whole strip in a holder or
straight on a lightbox (sprocket holes visible; their pitch sizes the 36 × 24 mm frame) and a carrier that masks all but the picture, like the iPhone ProRAW
rig; turn on mirror (`flip`) for film shot emulsion side up.

    uv run nlb develop <roll-dir>            # 16-bit TIFFs into <roll-dir>-positive/
    uv run nlb develop <roll-dir> --check    # capture exposure report, renders nothing

Tests: `uv run pytest` (sample-based tests need `iphone-negatives/` or the rolls in `nextcloud/`).

With Nix (no uv needed; dependencies come from nixpkgs):

    nix run . -- preview <dir>                       # or `nix build` → ./result/bin/nlb
    nix develop -c pytest                            # dev shell puts src/ on PYTHONPATH
