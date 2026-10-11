# darktable styles for the A7 IV lightbox rig

Two styles for inverting negatives in darktable 5.6 with `negadoctor`:

| File                    | Style name                           | For                         |
|-------------------------|--------------------------------------|-----------------------------|
| `negative-c41.dtstyle`  | `negative \| C-41 (A7 IV lightbox)`  | colour negative (orange mask) |
| `negative-bw.dtstyle`   | `negative \| B&W (A7 IV lightbox)`   | B&W negative                |

Import: lighttable → styles → import. Apply in either mode (append or overwrite).
Regenerate after changing a value: `python3 make_styles.py`.

## What the styles do

| Module | Setting | Why |
|---|---|---|
| white balance | user: 2.611 / 1 / 1.876 | makes this lightbox neutral (measured through the sprocket holes) |
| exposure (default instance) | off | the scene-referred +0.7 EV would move Dmin around |
| exposure "negative scan" | +0.72 EV, black 0.003 | backlight lands at 1.0, so Dmin = film-base transmittance; black removes veiling flare (below) |
| color calibration | off (C-41) / gray from green, no CAT (B&W) | a per-image CAT re-balances each frame from the camera's auto WB |
| AgX / sigmoid / filmic | off | negadoctor already prints to a display-referred 0–1; the manual says disable tone mappers |
| negadoctor | fitted on `test/frame-001.ARW` (C-41); darktable's B&W preset (B&W) | |

Exposure and color calibration need two entries each. In append mode, an enabled
style entry for a multi-instance module is added as a new instance (only disabled
entries replace the existing one), so the style switches off the auto-applied
instance and adds its own named one.

## Per-roll workflow

The C-41 values are a starting point from one frame. For a new roll, in negadoctor's order:

1. **Crop** to the image first (crop runs before negadoctor, so the pickers only see the frame).
2. **Dmin**: picker on clear rebate between frames or next to the sprockets. With the
   exposure above it should read ~37 / 18 / 9 % for this stock.
3. **D max**: picker over the whole image, **offset**: same; avoid dust and sprocket holes.
4. Corrections tab only if a neutral is off: shadows picker on a neutral dark, then highlights on a neutral light.
5. **Paper black**, **grade**, **gloss**, **print exposure** to taste.
6. Copy the negadoctor history from that frame and paste it to the rest of the roll.

For B&W: pick Dmin on the rebate (the 0.75 in the style is a placeholder), then D max and offset.

## Calibration (frame-001, ISO 125, 1/5 s)

- Backlight raw ratios R/G 0.383, B/G 0.533: warmer than daylight (B/G 0.72), so blue is the weak channel.
- Film base relative to the light: 0.367 / 0.177 / 0.086 (densities 0.44 / 0.75 / 1.07),
  the same on all three roll01 / test frames.
- The opaque surround next to the film reads ~0.5 % of the light instead of 0: veiling flare.
  In dense areas blue is only ~1.5 % of the light, so uncorrected flare compresses the blue
  density range by a third and turns shadows blue. Exposure's black level runs before
  negadoctor and subtracts it.
- negadoctor's tone/colour values come from a two-point fit on the image's 0.5 / 99.5 %
  densities, rewritten so every slider stays inside its GUI range.

## Capture notes that matter for processing

- **Keep exposure fixed for the roll** (manual ISO 125 or 100, fixed shutter). If you change it,
  change the "negative scan" EV by the opposite amount so the sprocket holes still read 1.0, or re-pick Dmin.
  The roll01 frames were auto-ISO (6400 / 5000) and won't match these values.
- frame-001 has ~0.7 EV of headroom on the sprocket holes (the film base is ~2 EV below
  clipping), so ~+0.5 EV more exposure buys blue SNR; then set the "negative scan" EV to 0.22.
- **Mask stray light** around the film: less flare means truer blues. Raise `FLARE_BLACK` if
  shadows go blue, lower it if they block up.
- No flat-field in darktable; the base varies ~±5 % across the frame from light falloff.

## References

- negadoctor manual: https://docs.darktable.org/usermanual/development/en/module-reference/processing-modules/negadoctor/
- whole-roll workflow (disable color calibration and tone mappers, paste per roll): https://discuss.pixls.us/t/advice-on-speeding-up-negadoctor-workflow-for-whole-film-roll/55435
- B&W colour cast needs a monochrome step: https://discuss.pixls.us/t/converting-black-and-white-negatives-to-positives/27817
- flat-field via composite/divide, if falloff bothers you: https://bog.0b.ee/2025/06/11/correcting-negatives.html
