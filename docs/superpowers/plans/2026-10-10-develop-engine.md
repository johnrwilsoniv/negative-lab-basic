# Develop engine: color (C-41) and B&W negative conversion for Sony ARW

Date: 2026-10-10. Hand-off plan for the agent that owns the processing pipeline.
A separate effort is building `nlb studio`, a local web app for tethered capture and
review, in parallel. The app calls this engine through the contract below. Read
`README.md`, `sony-capture/README.md` and `docs/superpowers/specs/2026-09-28-nlb-invert-design.md`
first for context.

## Goal

Turn Sony A7 IV raw captures of 35 mm negatives (macro lens and film holder on a lightbox)
into 16-bit TIFF positives, for **C-41 color** and **B&W** film. The look should be a sane
starting point for a lab-style scan: neutral, consistent across a roll, no orange cast,
no clipped highlights. The ARW plus `roll.json` is the archive, so any render must be
reproducible from those two alone.

## What you own and what you must not break

- You own `src/nlb/develop.py` and anything you add under `src/nlb/` for it (for example
  `src/nlb/color/`), plus `tests/test_develop*.py`.
- The studio work (on another branch) includes a deliberately simple **v0 `develop.py`**
  so the UI has something to call. You work in a separate worktree, so create
  `develop.py` from this contract if your checkout doesn't have it. On merge your
  version replaces v0. **Keep every public name and signature below**, or flag the change
  so `src/nlb/studio/` can be updated to match.
- Do not edit `src/nlb/studio/` except for contract changes. That code is under active work.
- The existing phone/HEIC pipeline (`pipeline.py`, `detect.py`, `tone.py`, `nlb preview|render`)
  must keep working and keep its tests green. You can reuse pieces of it.
- If you want a headless CLI (`nlb develop <roll-dir>` rendering from `roll.json`), add
  it as a new subcommand in `cli.py`. `cli.py` already has a `studio` subcommand, so don't
  restructure `main()`.

## The contract (`nlb.develop`)

All images are `float32` numpy arrays, H x W x 3, C-contiguous.

```python
PARAMS: list[dict]
    # Per-frame adjustment sliders. The UI renders one slider per entry, so adding an
    # entry here makes it show up in the studio with no UI change.
    # {"key": "exposure", "label": "Exposure", "min": -2.0, "max": 2.0, "step": 0.05, "default": 0.0}
    # Values live in frame["params"][key]; missing keys mean "default".

def load_linear(path: Path, preview: bool = False) -> np.ndarray
    # Raw -> linear, scene-referred camera RGB in [0, 1]. Black is subtracted and the scale
    # is fixed per camera (no auto-brightening, no white balance, no gamma), so values
    # are comparable across frames and rolls. Use sensor orientation, ignoring EXIF
    # rotation (user_flip=0); the copy stand makes the orientation sensor meaningless.
    # preview=True may trade quality for speed (half_size demosaic, ~0.3 s per frame).
    # The studio further downsizes previews to ~1600 px wide with cv2.INTER_AREA.

def auto_crop(lin: np.ndarray, settings: dict) -> list[float]
    # Initial crop of the picture area as normalized [x, y, w, h] in FULL-VIEW space
    # (see Geometry). Must exclude holder, sprocket holes and rebate. The user can
    # fix it by dragging, so a decent guess is enough; never raise.

def sample_base(lin: np.ndarray, settings: dict, frame: dict, x: float, y: float) -> list[float]
    # The user clicked the film base (the clear rebate) at normalized (x, y) in full-view
    # space on the NEGATIVE view. Return the linear RGB of the base for settings["base"].
    # A robust patch statistic, e.g. median of a ~1% square.

def analyze_roll(samples: list[tuple[np.ndarray, dict]], settings: dict) -> dict
    # "Lock levels to roll": given (preview-res lin, frame dict) for every kept frame,
    # return a JSON-serializable dict stored as settings["levels"]. When that is non-null,
    # develop() must use it instead of per-frame auto levels. The shape is yours.

def develop(lin: np.ndarray, settings: dict, frame: dict, view: str = "crop") -> np.ndarray
    # The whole conversion. Returns display-ready, sRGB-encoded RGB in [0, 1]
    # (B&W returns 3 equal channels).
    #   view="crop":     geometry -> crop -> invert/tone -> 90-degree rotation. Final image.
    #   view="full":     geometry only (no crop, no rotation), inverted with the SAME tone
    #                    and levels as "crop" (computed from the crop region). The UI draws
    #                    the crop rectangle on this.
    #   view="negative": geometry only, NOT inverted, just a viewable encoding of lin
    #                    (used for picking the film base).
    # Must work on preview-sized and full-resolution lin and give the same look on both,
    # because the user approves previews and the TIFF must match.

def write_tiff(path: Path, img: np.ndarray) -> None
    # 16-bit RGB TIFF of a develop() result. Embed an sRGB ICC profile (Pillow's
    # ImageCms can produce the bytes; tifffile can write tag 34675). v0 uses cv2 with no ICC.
```

### `roll.json` (owned by the studio, read by you)

It lives at `<roll-dir>/roll.json`. The studio writes it and passes you the
`settings` dict and one entry of `frames`.

```json
{
  "version": 1,
  "settings": {
    "film": "c41",            // "c41" | "bw"
    "flip": false,            // mirror horizontally (film loaded base-up)
    "base": null,             // [r, g, b] linear film-base color, or null = auto
    "levels": null            // analyze_roll() output, or null = per-frame auto
  },
  "frames": {
    "DSC06699": {
      "file": "DSC06699.ARW",
      "crop": [0.08, 0.11, 0.86, 0.8],   // normalized, full-view space; always set before develop()
      "rotation": 0,                      // 0 | 90 | 180 | 270, clockwise, applied after crop
      "angle": 0.0,                       // fine deskew in degrees, counter-clockwise positive, [-5, 5]
      "rejected": false,
      "params": {"exposure": 0.0}         // keys from PARAMS
    }
  }
}
```

You may add keys under `settings` (for example `"flatfield": "<file>"` or
`"light": [r, g, b]`). Tell the studio side which keys you add and whether they need UI.
Unknown keys pass through untouched.

### Geometry (shared convention, do not change without updating the UI)

`full view = deskew(angle)( flip(lin) )`. Crop coordinates are normalized in full-view
space. `crop view = rotate90(rotation)( crop(full view) )`. Deskew rotates about the
image center and keeps the original canvas size (border: replicate).

## Sample data and what it tells us

`sony-capture/rolls/roll01/` (gitignored) has two C-41 frames, DSC06699 and DSC06700:
7040x4688, 14-bit, black level 512, white level 16383, RGGB, manual lens (EXIF has no
aperture). DSC06699 is a landscape frame filling most of the image. The holder is
visible at the edges, sprocket holes on both long edges let the bare light through,
and there's a clean rebate strip between the holes and the picture. DSC06700 is a
portrait frame, tilted about 1 degree, with the left side darker and a dark blob
lower left (a finger or dust shadow). More rolls are coming; ask for B&W samples.

Linear camera RGB measured on DSC06699 (half-size decode, `user_wb=[1,1,1,1]`):

| Region                  | R      | G      | B      |
|-------------------------|--------|--------|--------|
| Sprocket hole (light)   | 0.34   | 0.88–0.94 | 0.47–0.50 |
| Rebate (film base)      | 0.131  | 0.152  | 0.049  |
| Sky (densest negative)  | 0.032  | 0.022  | 0.006  |
| Building wall           | 0.102  | 0.116  | 0.039  |
| Holder (flare floor)    | 0.001–0.004 | 0.004–0.009 | 0.002–0.004 |

Implications:

1. **Underexposed for this purpose.** The base sits at 5–15% of full scale, and blue
   in the densest areas is about 0.006, roughly 100 raw counts above black and only
   2–3x the flare floor. Blue highlights will be noisy and veiled. The fix is on the
   capture side: expose so the brightest base channel sits near 0.8, which means
   letting the sprocket holes clip. That's fine, since the holes are only a light
   reference. Shoot at ISO 100 with a longer shutter. Write this into
   `sony-capture/README.md` as capture guidance. The engine should also offer an
   **exposure check** helper reporting base headroom (base max channel / white
   level) and channel floors, which the studio can show after each capture. Propose
   it as a contract addition, e.g. `exposure_report(lin, settings) -> dict`.
2. **The light is green-heavy in camera space** (holes R:G:B ≈ 0.36:1:0.53), and the orange
   mask then cuts blue to about a third of red. Dividing by the base handles the
   white balance, but noise is set by blue. Note in the README that a light with more
   blue, or an RGB light, will help.
3. **Flare floor.** The holder reads 0.002–0.009, which is light scattered from the lightbox
   around the holder. Subtract an estimate of it (for example a low percentile of the
   holder/border region, or a `settings["flare"]` value) before taking logs. Otherwise
   dense highlights get compressed, and blue suffers first.
4. **A per-frame base and light reference is available in every frame** (rebate and holes),
   so separate calibration frames are optional. Still support an optional flat-field
   frame of the bare light to correct falloff, which is visible on DSC06700's left side.

## Algorithm (C-41)

Start simple and measure. Each step should be a small, separately testable function.

1. **Decode** (`load_linear`). rawpy `postprocess(output_color=raw, gamma=(1,1), user_wb=[1,1,1,1],
   no_auto_bright=True, output_bps=16, user_flip=0)`, then /65535. Check that no hidden
   scaling remains: the 99.9th percentile of the sprocket-hole green in DSC06699
   (about 0.95) should match the raw-domain figure ((15815-512)/(16383-512)).
2. **Flat-field** (optional). Divide by a blurred, normalized bare-light frame.
3. **Flare.** `lin = max(lin - flare, eps)`.
4. **Base.** `settings["base"]` if set, otherwise automatic: the rebate is a large plateau of
   the brightest film-coloured pixels that are not light. One approach: exclude pixels
   brighter than about 0.6x the light level (holes) and darker than the flare floor x 5
   (holder), then take a high percentile per channel, or better, the mode of a 2D
   chromaticity histogram restricted to the brightest film pixels. Validate against the
   table above (rebate 0.131 / 0.152 / 0.049).
5. **Density.** `D_c = log10(base_c / lin_c)`. Zero means clear base, which becomes
   positive black.
6. **Levels.** Per channel, the black point is the thinnest picture area and the white
   point the densest highlight. Use robust percentiles over the crop (subsample to
   about 1 Mpx so preview and full-res agree). With per-channel independent levels,
   white balance and the orange-mask residual neutralize automatically (what NLP and
   negadoctor do by default). `analyze_roll` pools the frames' statistics (for example
   per-channel medians of the frames' points) so the whole roll shares one mapping.
   That's the right default for consistent color, and it's toggled from the UI.
7. **Tone.** Normalized density is roughly log exposure, so map it with a print-like
   curve: a filmic S-curve with a soft toe and shoulder, not a linear stretch. Then
   encode as sRGB. Expose `exposure` (density offset, in stops) and `contrast` (curve slope).
8. **Color.** Camera RGB is not sRGB. After inversion, apply a sensible matrix
   (rawpy exposes `rgb_xyz_matrix`, and camera→XYZ→sRGB is the obvious start). Check
   whether this beats leaving channels as they are plus a saturation control on the
   samples. Expose `temperature` and `tint` as per-channel density shifts
   (R−B and G vs. magenta), and `saturation`.
9. **Geometry.** Flip and deskew before cropping, rotate last (see Geometry).

## Algorithm (B&W)

Same path with one channel. Use transmittance luma (or the green channel, since it has
the best SNR) divided by the base luma, take density, set levels from the crop, apply
the tone curve, and output 3 equal channels. Skip the base-color step and the color
matrix. The existing `tone.py` percentile approach (0.1 / 99.9) is a known-good baseline.

## Performance budget

- `develop()` on a ~1600 x 1066 preview: **≤ 150 ms**. The UI re-renders on every slider release.
- `load_linear(preview=True)`: about 0.3 s (measured, half-size).
- A full-res render (7040 x 4688) may take seconds, but keep peak memory under about 2 GB:
  crop before the log/tone math, and work in float32.

## Tests

- Synthetic: build a fake negative from a known positive (apply a base color, densities and
  flare), check that develop() recovers it within tolerance, and that a neutral grey wedge
  comes out neutral.
- Geometry: crop, flip, deskew and rotation on small asymmetric arrays; normalized crops
  map to the same content at preview and full resolution.
- Preview/full-res parity: develop at both scales and compare the mean and percentiles of the
  downscaled full-res result against the preview (tight tolerance).
- Sample-based (skip if `sony-capture/rolls/roll01/` is absent): auto-base lands near the
  measured rebate; auto_crop on DSC06699 excludes the holes and rebate; output has no
  orange cast (mean chroma of the frame below a threshold).
- `write_tiff`: round-trip as 16-bit RGB, and the ICC profile is present.

## Deliverables

1. `develop.py` meeting the contract, the performance budget and the tests above.
2. Dependency changes in both `pyproject.toml` and `flake.nix` (`runtimeDeps`). `tifffile`
   is currently dev-only. uv isn't installed on this machine, so if `uv.lock` can't be
   regenerated, say so.
3. Capture guidance (exposure, light, flare masking) in `sony-capture/README.md`.
4. A short note to the studio side listing new `settings` keys, new `PARAMS` and any
   proposed contract additions (exposure report, flat-field frame).

## Out of scope

E-6 slides, dust and scratch removal, multi-frame stitching, HEIC/JPEG outputs (TIFF + ARW only).
