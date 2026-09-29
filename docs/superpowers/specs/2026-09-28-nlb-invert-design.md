# Negative Lab Basic — `nlb-invert` design

Date: 2026-09-28

## Goal

Turn iPhone photos of Ilford XP2 negatives (shot on an iPad lightbox through a
3D-printed mount) into clean, neutral B&W positives, invoked as a Claude Code
skill: `/nlb-invert <dir>`.

## Inputs (observed from `iphone-negatives/` samples)

- HEIC, 4032×3024 landscape, no EXIF orientation.
- Each shot shows one film frame as the largest bright rectangle, surrounded
  by the dark mount and a strip of sprocket holes top and bottom. Frame
  position is roughly consistent but offset left of center.
- XP2 is chromogenic (C-41): pinkish/mauve base cast.
- Film is photographed through the base, so images are mirrored.
- HEIC is 8-bit RGB (no 16-bit data to preserve).
- Some frames need rotation (IMG_4031, the church, needs 90° CCW after the flip).
- Each frame has a band of clear film rebate along one edge (usually the top)
  that is inside the mount window; after inversion it would be a black stripe.
- Frame tilt measured ≤0.5°.
- Edge cases: IMG_4033 is partial/light-struck; IMG_4028–4030 are near-duplicates.

## Decisions

| Topic | Decision |
|---|---|
| Color | Grayscale output (removes base cast) |
| Crop | Tight 3:2 just inside the exposed image area; no rebate/border |
| Flip | Always flip horizontally |
| Rotation | Claude proposes per frame from previews; user confirms before render |
| Tone | Per-frame auto levels (0.1% / 99.9% percentiles), gamma default 1.0 (`--gamma` flag) |
| Output | Grayscale HEIC, same filenames, in sibling dir `<dir>-positive/` |
| Originals | Never modified |
| Bad frames | Always processed; flagged in review, never auto-skipped |
| Frame detection | Automatic per image (approach A), axis-aligned; no deskew (tilt ≤0.5° is absorbed by the inset) |

## Architecture

### 1. `nlb` Python package + CLI

uv project in this repo. Dependencies: `pillow-heif`, `pillow`, `numpy`,
`opencv-python-headless`; `pytest` for dev.

Modules, each small and independently testable:

- `heic` — list inputs (`*.heic`/`*.heif`, case-insensitive, skipping
  dotfiles such as `._IMG_4025.HEIC`); read HEIC → float32 RGB in [0, 1];
  write 8-bit grayscale HEIC/JPEG.
- `detect` — find the film frame on a 1008px-wide working copy (blurred
  grayscale): mask = pixels brighter than 0.5 × Otsu threshold; then
  projection profiles — longest run of rows with >50% mask, longest run of
  columns (within those rows) with >60%, then refine rows with >90% and
  columns with >75%. This rejects the sprocket strips (≈50% bright) while
  tolerating dense picture content. Box scaled back to source pixels.
  Flags: `detect_failed` (no run found → whole-image fallback),
  `detect_suspect` (box aspect outside 1.3–1.6 or area outside 20–75% of
  image), `partial_or_blank` (>50% of 32px blocks in the box have mean
  |Laplacian| < 2.0, i.e. no grain/detail — IMG_4033 scores 0.74, the rest
  ≤0.39).
  Rebate trim: per side, scan inward up to 8% of the box; skip up to 3% of
  dark mount remnant, then trim lines whose 10th-percentile brightness
  exceeds 0.75 × the box's 99.5th percentile (clear film base).
- `geometry` — inset the trimmed box by 2% of its height per side, then the
  largest centered 3:2 box within it (orientation follows the long side);
  horizontal flip; 90° rotations.
- `tone` — luminance grayscale, invert, auto levels: black/white points at
  0.1% / 99.9% percentiles of the cropped frame, stretch to full range, apply
  gamma.
- `pipeline` — composes the above for one file: `process(path, rotation) →
  (image, FrameReport)`.
- `sheet` — contact sheet: labeled thumbnails in a grid, flagged frames
  marked.
- `cli` — two subcommands:
  - `nlb preview <dir> [--work <workdir>]` — processes every `*.HEIC`
    (case-insensitive) at reduced size; writes previews, `contact.jpg`, and
    `manifest.json` (per file: crop box, flags, low-detail score) to the work dir
    (default: `<dir>-positive/.nlb-work/`).
  - `nlb render <dir> [--rotate NAME=90cw|90ccw|180 ...] [--out <dir>]` —
    full-resolution processing, writes grayscale HEIC to `<dir>-positive/`,
    then writes a final `contact.jpg` there.

Rotation is applied last (after crop/flip/invert/levels), in 90° steps only.

### 2. `nlb-invert` skill

`SKILL.md` lives in the repo at `skills/nlb-invert/SKILL.md` and is symlinked
into `~/.claude/skills/nlb-invert` so it works from any directory. It calls the
CLI via `uv run --project <abs repo path> nlb ...`.

Skill flow:

1. Resolve the input dir (argument, default cwd). Run `nlb preview`.
2. Dispatch one review subagent with the contact sheet, previews and manifest.
   It returns per frame: proposed rotation (none/90cw/90ccw/180), and
   flags — bad crop (mount/sprockets visible or image clipped), blank/partial
   frame, mirrored text visible after flip, near-duplicate of another frame.
3. Show the user the contact sheet and a table of proposals/flags. User
   confirms or edits rotations.
4. Run `nlb render` with the confirmed `--rotate` args.
5. Show the final contact sheet and summarize outputs + anything flagged.

## Error handling

- Unreadable file → report, continue with the rest, non-zero exit at end.
- Detection failure (no plausible contour) → fall back to center crop of the
  whole image at 3:2, mark `flags: ["detect_failed"]`.
- Output dir exists → overwrite same-named files only; never delete others.
- Output dir resolving to the input dir → refuse (exit 2) so originals can't
  be overwritten.
- Bad `--rotate` value or unknown frame name → exit 2 before processing.

## Testing

- Unit: 3:2 fit math (landscape/portrait, inset), percentile levels on
  synthetic arrays, flip/rotate correctness on small asymmetric arrays,
  `--rotate` arg parsing.
- Detection on the 9 samples (skipped if `iphone-negatives/` is absent):
  boxes match the measured windows; only IMG_4033 is flagged
  `partial_or_blank`; no rebate stripe remains on the top edge.
- End-to-end: `nlb render` on a sample produces a readable grayscale HEIC
  with 3:2 dimensions.

## Out of scope

Dust/scratch removal, color negative film, multi-frame strips per shot,
GUI, batch across nested folders.
