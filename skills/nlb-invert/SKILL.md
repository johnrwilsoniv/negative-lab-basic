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
