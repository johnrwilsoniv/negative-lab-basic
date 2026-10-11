# Develop engine: notes for the studio side

Date: 2026-10-10. Companion to `plans/2026-10-10-develop-engine.md`. The engine replaces
v0 `src/nlb/develop.py`. Every public name and signature in the contract is unchanged,
so `src/nlb/studio/` works as is. The internals live in `src/nlb/engine/`.

## What changed behind the contract

- `load_linear`: also passes `adjust_maximum_thr=0`, so LibRaw never rescales a dim frame.
  Scale is fixed: the raw green 99.9th percentile matches the decode within 2%.
- `develop`:
  - Subtracts flare, measured on the holder next to the film. It never removes more than
    75% of a pixel, so the densest blue doesn't blow up.
  - Levels are per-channel density percentiles on a 512 px copy of the crop, so the
    preview and the TIFF agree. They ignore holder and hole pixels, so a sloppy crop
    doesn't wreck the levels.
  - The tone curve is a print-like S-curve with a soft shoulder, so highlights roll off.
  - Full-res output is processed in strips: about 1.5 s and about 1 GB peak for a 7028 x 4688 frame.
- Preview timings (1600 px wide `lin`): crop 75-95 ms, full 95-110 ms, negative 50-80 ms.
  Calibration (base, flare, light) is cached for the last 4 `lin` arrays, so repeat
  renders of the same cached preview array skip it.
- `view="negative"` is now balanced on the bare light: holes white, base orange. That's
  easier to read when picking the base.
- `analyze_roll` returns `{"version", "film", "frames", "black", "white"}`. `develop`
  ignores levels whose `film` doesn't match `settings["film"]` (stale after a film switch).

## PARAMS

Same five keys and ranges as v0. Meanings:

| key         | effect                                                                  |
|-------------|-------------------------------------------------------------------------|
| exposure    | stops; shifts density by 0.18 per stop (C-41 / B&W gamma ~0.6)          |
| contrast    | doubles (+1) or halves (-1) the S-curve slope                           |
| temperature | +1 = warmer: R +0.1, B -0.1 density                                     |
| tint        | +1 = magenta: G -0.1 density                                            |
| saturation  | about the channel mean, in log density (1 = as scanned)                 |

## New `settings` keys (all optional; missing = automatic)

| key         | value                              | UI needed?                                       |
|-------------|------------------------------------|--------------------------------------------------|
| `flare`     | `[r, g, b]` linear, or absent      | no. Auto per frame. Expose only as an expert override. |
| `flatfield` | `{"file": ..., "gain": [[[r,g,b]...]...]}` | yes: "use this frame as flat-field" (see below) |

## Proposed contract additions (implemented, unused by the studio so far)

1. `auto_frame(lin, settings) -> {"angle": float, "crop": [x, y, w, h]}`.
   Deskews from the sprocket-hole rows, then finds the picture in the deskewed full view.
   Prefer it over `auto_crop` in `Studio.prepare` and in the render job, setting both
   `angle` and `crop`. `auto_crop` stays as the angle-0 version (the largest same-aspect
   box inside the tilted picture). Measured: DSC06699 0.26°, DSC06700 1.0°, frame-001 5.8°.
   **Please widen the angle clamp in `roll.py` and the "Straighten" slider in `app.js`
   from ±5° to ±10°**, since frame-001 needs 5.8°.
2. `exposure_report(lin, settings) -> dict`. Shown after each capture:
   `base_headroom` (target 0.6-0.85), `floor_over_flare` (None if no holder is visible),
   `film_clipped`, and a one-line `advice`. Every capture so far is 2.2-3 stops under.
   The CLI equivalent is `nlb develop <dir> --check`.
3. `make_flatfield(lin) -> dict`. Turns a bare-light frame into the
   `settings["flatfield"]` value; the studio adds `"file"`. It raises `ValueError` if the
   frame is clipped or too dark. Suggested UI: a frame action, "Use as flat-field", that
   also marks that frame rejected.

## Known limits

- Per-frame auto levels assume the frame's extremes are neutral. Frames dominated by one
  color (a big blue sky) come out a little cyan. "Lock levels to roll" fixes most of it,
  and temperature and tint fix the rest.
- The camera→sRGB matrix was tried and rejected. It amplifies noise in the weak blue
  channel into speckle and over-saturates. Saturation in log-density space stays clean.
- B&W is tested on synthetic negatives only. Real B&W samples are wanted.
