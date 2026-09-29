# Negative Lab Basic

Turns iPhone photos of B&W negatives (lightbox + mount, HEIC) into cropped 3:2,
flipped, inverted grayscale HEIC positives. A pun on Negative Lab Pro.

    uv run nlb preview <dir>                         # previews + contact sheet + manifest
    uv run nlb render <dir> --rotate IMG_4031=90ccw  # full-res into <dir>-positive/

In Claude Code: `/nlb-invert <dir>` runs preview → agent review → your confirmation → render.
Install the skill: `ln -s "$PWD/skills/nlb-invert" ~/.claude/skills/nlb-invert`

Tests: `uv run pytest` (sample-based tests need `iphone-negatives/`).
