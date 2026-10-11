# Negative Lab Basic

Turns photos of B&W negatives (lightbox + mount; iPhone HEIC or ProRAW/DNG, Sony ARW)
into cropped 3:2, flipped, inverted grayscale HEIC positives (`IMG_1.DNG` → `IMG_1.HEIC`).
A pun on Negative Lab Pro.

    uv run nlb preview <dir>                         # previews + contact sheet + manifest
    uv run nlb render <dir> --rotate IMG_4031=90ccw  # full-res into <dir>-positive/

In Claude Code: `/nlb-invert <dir>` runs preview → agent review → your confirmation → render.
Install the skill: `ln -s "$PWD/skills/nlb-invert" ~/.claude/skills/nlb-invert`

Shooting with a tethered Sony A7 IV: see [sony-capture/](sony-capture/README.md). Raw
captures of C-41 or B&W negatives develop to 16-bit TIFFs with the engine in
`src/nlb/develop.py` (used by `nlb studio`, or headless):

    uv run nlb develop <roll-dir>            # roll.json if present, else auto per frame
    uv run nlb develop <roll-dir> --check    # capture exposure report, renders nothing

Tests: `uv run pytest` (sample-based tests need `iphone-negatives/`).

With Nix (no uv needed; dependencies come from nixpkgs):

    nix run . -- preview <dir>                       # or `nix build` → ./result/bin/nlb
    nix develop -c pytest                            # dev shell puts src/ on PYTHONPATH
