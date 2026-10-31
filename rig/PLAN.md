# NLB Scan Rig: CAD plan

Status (2026-10-27): **the CAD exists; nothing has been printed yet.** Every printed part is
modelled in CadQuery from the three.js mockup, put together in an assembly, and checked: one
STEP file per printed part that the user can import into Onshape and edit, plus STL files for
slicing. Some mechanisms are still undesigned (each part's "Not designed yet" below). Until
the wedge-plate grooves exist, LOCK can't clamp.

Run it from `rig/`:
- `uv run pytest`: the checks on the built solids (about a minute).
- `uv run python build.py [--wd W] [--axis A]`: builds every part, writes `exports/`, and prints
  the sizes and volumes, the interference check at SLIDE and LOCK, the fit numbers and the bed
  margins. It exits non-zero if a check fails. An axis below 39 is refused with a one-line message.

`exports/step/` and `exports/stl/` hold one STEP and one STL per printed solid, plus the thread
coupon, in print pose. `exports/step/nlb-scan-rig-assembly.step` has every part in place at
SLIDE, in the Onshape frame (R10), with the film and the CS-Lite as grey reference solids.

## What the rig is

A light-tight path for scanning 35mm B&W strips with a camera:

    Sony A7 + Laowa 90mm f/2.8 2X ── 1 lens adapter ── 2 tube ── 3 film gate ── 4 light dock + CineStill CS-Lite
                                                                     └ 5 lock switch on the gate lid

- Everything rests on one flat table. The camera sits on its own base. There's no cradle;
  the gate box carries the front end of the lens.
- Strips lie flat and slide sideways through the gate.
- The README in this repo says the camera is an **A7 IV**, but the mockup says "A7". Confirm
  with the user before any part depends on body dimensions. Currently none do: the camera
  and lens are reference geometry only.

## Source of truth

`rig/mockup/nlb-scan-rig.html` is a copy of the live mockup at
https://tmp.jrwiv.com/a/nlb-scan-rig-zh2mb48s. Every dimension below comes from its script.

| Lines | What |
|---|---|
| 216–229 | Constants |
| 231 | Defaults |
| 366+ | `rebuild()`, the geometry for each part |
| 396 | Adapter |
| 410 | Tube |
| 415 | Gate |
| 425 | Lock mechanism |
| 446 | Lid |
| 473 | Dock |

Read `rebuild()` before modelling a part: the CAD should reproduce it. When CAD and mockup
disagree on purpose, change the mockup too and republish it. The differences the build made
are listed under "Mockup differences to republish"; they wait for the user.

**Republishing:** use the `jta` skill and keep the same filename (`nlb-scan-rig.html`) so
the URL stays the same. The skill pushes with `tmp-push`; it's not a claude.ai Artifact.

**Mockup coordinates:**
- `x`: the optical axis, running from the camera (−) to the light (+). `x = 0` is the
  lens mount, and `x = 125` is the lens front.
- `y`: up from the table.
- `z`: across the gate. This is the direction the film travels.

All units are mm.

## Parameters

Put these in `rig/params.py`. Every part reads from there, so nothing hard-codes a derived
size.

**User inputs.** The user set these defaults this session. The mockup still tags them
"guess": ask whether they were measured.

| Parameter | Default |
|---|---|
| `wd`: lens front to film | 130 |
| `axis`: table to lens centre | 42.5 |

**Known values** (from datasheets):

| Item | Size |
|---|---|
| Laowa filter thread | M67 × 0.75 |
| CS-Lite body | 165 × 112 × 20 |
| CS-Lite lit area | 149 × 95 |
| 35mm film | 35 wide, frame 36 × 24, ~0.13 thick |

**Guesses:** the lens barrel is Ø74 × 125 (mockup `LENS_R=37`, `LENS_LEN=125`).

**My picks** (chosen in this session, not measured):

| Constant | Value | Meaning |
|---|---|---|
| `GW` | 92 | Gate width |
| `GATE_D` | 30 | Gate depth |
| `GATE_FRONT` | 14 | Gate front wall to film |
| `WALL` | 3 | Wall thickness |
| Window | 38 × 26 | Gate window |
| `GAP` | 25 | Film to light face |
| `TUBE_RO` / `TUBE_RI` | 36 / 32 | Tube outer / inner radius |
| `FLANGE` | 3 | Adapter flange thickness |
| `THREAD_LEN` | 4.5 | Thread length |
| `CHANNEL` | 0.6 | Film channel in slide mode |
| `SW_TRAVEL` | 10 | Switch travel |
| Ramps | 12 long, 0.1 → 0.8 thick | Rise 0.7 over 12 |
| Clamp | 0.58 | Closes the 0.6 channel onto the film with ~0.11 preload |

**Derived values** at the defaults:

| Value | Formula | Result |
|---|---|---|
| Film plane | `xFilm = 125 + wd` | 255 |
| Gate box height | `GH = axis + 36` | 78.5 |
| Tube length | `wd − 13` | 117 |
| Dock width | `DOCK_W = 165 + 16` | 181 |

The mockup's rail shows these live, and `updateText()` has the formulas.

## Parts

Each part gets `rig/parts/<part>/model.py`, which exposes `build(p, lock=False)`: a dict of the
part's solids, in mockup coordinates, at SLIDE or LOCK. `PRINT_UP` says which side of each faces up
on the bed. Folder numbers follow the mockup's labels.

### 1 · Lens adapter (`parts/lens_adapter/`): build first

Screws into the Laowa's 67mm filter thread. The tube slides into the other end.

- **Male thread:** M67 × 0.75, 4.5 long.
  - Make it a real modelled helical thread, not a cosmetic one. The user will print it and
    screw it in.
  - Give it about 0.1–0.2 radial clearance for FDM.
- **Flange:** 3 thick, Ø78 OD, Ø62 bore. The bore must clear the lens front element; check
  it against the mockup's 31 inner radius.
- **Socket:** 9 deep, Ø78 OD. Its ID is `2·TUBE_RO + 0.6` = 72.6, so the tube is a slip fit.
- **Overall:** Ø78 × 16.5.
- **Printing:** flat, with the thread axis vertical, at 0.12–0.16 layers.
- **Thread test coupon:** also export a short version (thread plus a thin grip ring) so the
  thread fit can be checked before the full part is printed. This is the riskiest geometry
  in the rig. At 0.75 pitch, FDM is marginal.

### 2 · Tube (`parts/tube/`)

- **Size:** Ø72 OD / Ø64 ID. Length is `wd − 13` (117 at the default).
- **Ends:** one end slides into the adapter socket and the other into the gate's front-wall
  hole (Ø72.6, 4 deep).
- **Inside:** blocks room light and should cut flare. Consider internal baffle ribs or a
  matte texture.
- **Printing:** upright.
- **Bed size:** 117 tall is fine. If `wd` grows past roughly 200, split the tube with a
  spigot joint.

### 3 · Film gate (`parts/film_gate/`)

Several printed pieces. Model each as its own solid.

**Box:**
- Front wall: 4 thick, with a Ø72.6 hole on the lens axis.
- Floor and lid: 3 thick.
- Side walls: 3 thick, each with a film slot 3.2 (along x) × 37 (along y) centred on `axis`,
  running from the front plate's rear face toward the light (F3).
- Rear wall: 3 thick, with a 46 × 34 window toward the light.
- Outside: 92 wide × 78.5 tall × 30 deep.
- Lid slot: 3 × 16 for the lock switch's tab.
- Lid lettering: SLIDE at one end of the slot and LOCK at the other, reading along z, in
  front of the knob. In the mockup it's a texture; in CAD, engrave it about 0.4 deep.

**Front plate:**
- Fixed. It sets the focus plane.
- 1.8 thick, with a 38 × 26 window.
- Its rear face is `CHANNEL/2` (0.3) in front of the film plane.
- Can be part of the box. Decide based on print orientation. (Decided: part of the box, R5.)

**Pressure plate:**
- 1.8 thick, with a 38 × 26 window. Floats along x only. 0.25 clearance to the floor, the
  lid and the side walls (F1).
- Sits `CHANNEL/2` behind the film plane.
- Four pads on its back face, 4 × 4, at z = ±22 and y = axis ± 15.5. Pad thickness is
  computed in the mockup (`padT`).

**Not designed yet. Brainstorm these with the user before modelling:**
- Two **leaf springs** that pull the pressure plate back toward the light in slide mode.
  They should be printed flexures, probably in PETG. They are what returns the plate to
  SLIDE: nothing else pulls it off the film.
- **Guides** that let the pressure plate move along x but stop it moving along y or z.
- **Grooves** that guide the wedge plate along z. They must also carry the clamp's reaction
  in x. Today the wedge plate has 8 free behind it, and its tab has 0.5 play each side in the
  lid slot. Both are more than the 0.47 stroke, so LOCK can't clamp until the grooves exist.
  Their x play must be well under ~0.05.
- **Lid retention.** Nothing holds the lid on yet.
- **Gate position along the tube.** Nothing locates the gate along the tube. The front-wall
  hole is a slip fit, so the film plane sits wherever the gate is pushed.
- **Light seal at the lid's front end.** The lid's 0.2 end clearance leaves a 0.2 × 86 slit
  from the top into the chamber between the front wall and the front plate, on the lens side.
  It needs a lip over the front wall's top, or tape.

### 4 · Light dock (`parts/light_dock/`)

Holds the CS-Lite standing on its long edge, lit face toward the film, `GAP` (25) behind
the film plane.

- **Floor:** 4 thick, 181 wide. It runs along x from the back of the gate to 6 past the
  slot's back edge (35.5 at the default).
- **Lips:** front and back, 12 tall. Together they make a 20.5 wide slot for the light: its
  20 plus 0.5 clearance, all behind it, so the lit face stays at the front lip.
- **Side cheeks:** 62 tall.
- **Shroud:** a 60 × 46 tunnel from the gate's rear window to the light face.
- **Bed size:** at 181 wide it is the largest part. The mockup says it fits a 220 bed, but
  the 220 bed was my assumption. **Confirm the printer's bed size.**

**Not designed yet:**
- How the dock locates against the gate: pins, a dovetail or a shared baseplate.
- Keeping light from leaking at the gate/shroud joint.
- Holding the CS-Lite against the front lip. The slot has 0.5 play behind it.

### 5 · Lock switch (`parts/lock_switch/`)

**Knob:** 10 (x) × 12 (z) × 5, with three grip ridges on top.

**Tab:** 2 × 4, running down through the lid slot.

**Wedge plate:**
- 2 thick, 70 wide (z), and as tall as the gate interior (about 70).
- Window 52 × 26. Shifted ±5, it still clears the 38 wide frame window.
- Four ramps on its front face, one under each pressure-plate pad. Each is 12 long and goes
  from 0.8 thick at the −z end to 0.1 at the +z end.

**How it works:**
- Travel is ±5 along z. At SLIDE (knob at −z) each pad sits on the thin end of its ramp.
- At LOCK, the pressure plate moves forward by
  `min(rampT(−s) − rampT(SW_TRAVEL/2), CHANNEL − FILM_T)`.
- The ramp slope (about 1:17) should be self-locking. Still add a detent bump at each end
  of the slot. Not designed yet: a working detent needs a compliant member, and the tab is
  rigid with 0.5 play, so design it with the knob snap. The detents are what hold LOCK; the
  leaf springs are what return the plate to SLIDE.

**Assembly:** the knob can't go through the lid slot already attached. Make it a separate
print that snaps onto the tab after the wedge plate is in place. The snap feature is not
designed yet. The tab ends flush with the lid top today, so the snap needs the tab
lengthened above the lid.

**Tuning:** if the grip is wrong after a test print, change the ramp rise (about 0.6–0.8
only: see "Tuning and print notes"). Don't change `CHANNEL`.

## Folder layout

```
rig/
├── PLAN.md                 this file
├── pyproject.toml          its own uv project (cadquery, pytest), kept out of the nlb package
├── params.py               every dimension above, defaults plus derived values
├── cadutil.py              shared helpers: measuring, print pose, export (ruling R11)
├── build.py                builds every part, writes exports/, prints sizes and checks
├── assembly.py             places all parts at mockup coordinates, interference check, assembly STEP
├── fits.py                 the mating fits, measured on the assembled solids
├── mockup/
│   └── nlb-scan-rig.html   copy of the published mockup (source of the numbers)
├── parts/
│   ├── lens_adapter/       model.py (+ thread_coupon in the same file)
│   ├── tube/               model.py
│   ├── film_gate/          model.py: box (with the front plate), lid, pressure_plate
│   ├── light_dock/         model.py
│   └── lock_switch/        model.py: knob, wedge_plate
├── tests/                  pytest on the built solids
└── exports/
    ├── step/               one STEP per printed solid + nlb-scan-rig-assembly.step (for Onshape)
    └── stl/                one STL per printed solid (for the slicer)
```

**Why this layout:**
- The folder names are importable (no hyphens and no leading digits); the numbers live in
  this plan.
- Exports sit in one folder so they're easy to share.
- `rig/` is a separate uv project because CadQuery (OCP) is a heavy dependency that the
  `nlb` CLI doesn't need. Per `CLAUDE.md`, use `uv`, never pip into the system python.
- CadQuery wheels on macOS arm64 can lag new Python versions. If 3.12 has trouble, pin the
  project's Python version.

## Formats

| Format | Use | Notes |
|---|---|---|
| **STEP** | Sharing and Onshape | Onshape imports it as solid parts that can be measured, sketched on and edited by moving faces. It does not carry history, so parametric changes come from re-running `build.py` with new params. |
| **STL** | Slicing only | A mesh. Don't share it as the editable form. |

A fully parametric Onshape version would mean writing FeatureScript. That can't be tested
from this machine, so it's deferred.

## Build order

1. **Set up.** Create `pyproject.toml`, then `params.py` with every constant and derived
   value. Check the derived values against the mockup's rail at the defaults: tube 117,
   gate 92 × 78.5 × 30, dock 181 wide.
2. **Lens adapter and thread coupon.** Export both. Stop and hand the coupon to the user
   for a test print before going further on threaded geometry.
3. **Tube.**
4. **Film gate box and plates.** Before modelling the springs and guides, brainstorm those
   open items with the user.
5. **Lock switch.**
6. **Light dock.** Settle the gate/dock joint with the user first.
7. **Assembly.** Write `assembly.py` and the assembly STEP, then an interference check
   across all parts.

## Checks before calling a part done

Write these as pytest checks against the built solids:

- Every solid is valid and closed (`shape.isValid()`) and its volume is greater than 0.
- Bounding boxes match the dimensions above at the default params, within 0.05.
- Mating fits:
  - tube OD vs adapter socket ID and gate hole: 0.3 radial clearance
  - pressure plate face to front plate: `CHANNEL` (0.6)
  - drop-in and sliding fits: pressure plate 0.25 to the floor, lid and side walls; lid 0.2
    to the front and rear walls; CS-Lite slot 0.5 wider than the panel
- At the assembly level:
  - no two solids intersect in either switch position (SLIDE, LOCK)
  - except at LOCK, where the plate clamps the film; the film isn't a printed part
- Every printed part fits the bed. 220 × 220 is assumed until the user confirms.
- STEP round-trip: re-import each exported STEP and check its volume matches.
- Every solid manifold: each edge between exactly two faces. OCC's `isValid()` misses a solid
  whose pieces meet only along an edge; Onshape marks it faulty (`cadutil.is_valid` checks both).
- Report the numbers (sizes, clearances, volumes) to the user. They check the look in
  Onshape.

## Decisions made while building

Each was a ruling made during the build (numbers at the defaults). The code cites them by
number.

- **Not modelled yet (R3):** leaf springs, pressure-plate guides, wedge-plate grooves, knob
  snap, gate/dock joint, lid-slot detents. The surfaces where they'd attach are left plain.
- **Open-top box with a separate lid (R4).** The lid sits between the front and rear walls,
  on the side walls. A closed box can't take the plates in or print without an 86 bridge.
- **Front plate is part of the box (R5).** It's a vertical wall inside the box, which prints
  floor down.
- **Sloped pads (R6).** The pads' back faces slope like the ramps, `padT` thick at the
  centre. At SLIDE pads and ramps just touch; at LOCK they overlap by the 0.113 preload.
- **The clamp in a rigid model (R7).** At LOCK the only overlap allowed is the pads in the
  ramps, 0.113 deep. The film lies on the front plate and is only touched.
- **Gate height kept at `axis + 36` (R8).** The Ø72.6 hole then breaks 0.3 through the top
  edge of the front wall. `gate_above_axis` ≥ 39.3 closes it with 3 of wall over the hole.
- **Dock 67.5 tall (R9).** The shroud top (axis + 25) stands above the 62 cheeks.
- **Exports (R10).** Per-part STEP and STL are in print pose: `PRINT_UP` side up, on the bed,
  centred. The assembly STEP is in the Onshape frame (`assembly.to_onshape`): Z up, so the
  Top plane is the table; Y = mockup x − `x_film` (the camera end toward −Y), so the Front
  plane is the film plane and the Front view and the default isometric look into the adapter;
  X = mockup z, so the Right plane is the vertical plane through the optical axis and the
  Right view is the side profile. The origin is on the table under the film's centre.
- **Tube baffles (R12).** Sawtooth ribs inside the tube, 1 tall every 8, down to r 31 (the
  adapter bore, so they can't vignette). 45° lower flanks, so the tube prints upright without
  supports. `baffle_h = 0` removes them.
- **Thread (R13).** ISO 60° M67 × 0.75, right-hand, moved in 0.15 radially (`thread_clear`),
  with a 45° lead-in. The coupon is the same thread on a 2 thick Ø78/Ø62 ring.
- **Assembly references (R14).** The film strip and the CS-Lite only. No camera or lens: the
  body isn't confirmed, and a solid lens would collide with the adapter thread.
- **Clearances on the drop-in and sliding fits (F1).** Pressure plate 0.25 inside the floor,
  lid and side walls (`plate_clear`). Lid 0.2 short of the front and rear walls (`lid_clear`).
  CS-Lite slot 20.5 (`csl_clear` 0.5, all behind the panel), so the dock is 35.5 long. This
  reverses R16, which kept the slot at exactly 20. `fits.py` measures each one.
- **Lowest axis 39 (F2).** `Params` refuses an `axis` below `adapter_r`: the Ø78 adapter would
  hit the table, and the dock's front lip would reach into the shroud opening. Lower still,
  the tube (36) and the gate hole (36.3) reach the table too.
- **Film slots start at the front plate (F3).** Each side-wall slot runs from the front
  plate's rear face (`film_slot_x0`) to x 257.9, 3.2 along x. Centred on the film, as in the
  mockup, it opened a 0.4 × 37 slit into the lens-side chamber. Started at the plate's front
  face (5 along x), the side wall and the plate met only along an edge: a non-manifold solid
  that Onshape marked faulty. From the rear face the side wall covers the plate's end, and the
  film lies against the plane the slot starts from.
- **Clamp plates print on edge (F4).** The pressure plate and the wedge plate stand on their
  bottom edge (`PRINT_UP` +y). Printed flat, the ramp and pad slopes would be stepped by
  0.12–0.16 layers, about the size of the 0.113 preload.

## Mockup differences to republish

The CAD differs from the mockup on purpose here. The mockup hasn't been changed: republishing
it is the user's call.

| What | Mockup | CAD |
|---|---|---|
| Gate lid | full gate depth, over the front and rear walls (it overlaps the tube) | between the front and rear walls, 0.2 short of each |
| Gate floor | full gate depth, under the front and rear walls | between the front and rear walls |
| Pressure plate | 86 × 72.5, flat pads `padT` thick | 85.5 × 72 (0.25 clearance), pads sloped like the ramps |
| Tube | plain ring | baffle ribs inside |
| Film slots | centred on the film plane, x 252.5–257.5 | from the front plate's front face, x 252.9–257.9 |
| CS-Lite slot | 20, dock 35 long | 20.5, dock 35.5 long |
| `axis` | slider 30–60 | 39 at least |

## Tuning and print notes

- **`ramp_rise`** works only from about 0.6 to 0.8 (0.7 gives the 0.113 preload). Below about
  0.56 the ramps run out before the plate reaches the film. `build.py` then fails with
  "pressure_plate and wedge_plate should overlap … and do not touch" at LOCK, and FAIL on
  "film / pressure plate, LOCK". Above 0.8 the ramps' thick ends are thicker than `wedge_gap`
  (0.9) and hit the pressure plate's body: "pressure_plate and wedge_plate intersect" at
  SLIDE. At 0.57 the preload is only 0.005.
- **`thread_clear`** builds valid solids from 0.05 to 0.3. Print the coupon to choose.
- **Supports:** the adapter's socket ledge (a 5.3 wide annular overhang in the thread-up
  pose), the upper arc of the gate's front-wall hole, and the dock shroud's 56 bridge.
- **Brim** for the pressure plate and the wedge plate: they stand 72 and 75 tall on edges
  1.8 and 2 thick.
- **Wedge window:** 26 tall, the same as the frame window, so there's no y margin. The ramps
  cap it at ±13.5 from the axis.
- **Lettering font:** if Arial is missing, CadQuery silently uses another font. It's fine on
  this Mac.
- **Stale exports:** an invalid solid isn't exported, so the previous STEP/STL stays in
  `exports/`.

## Questions for the user

- **Printer:** bed size and build height. 220 × 220 is assumed. `tube_max_len` borrows the
  220 footprint as the height. The plan wants a spigot split past `wd` ≈ 200; that isn't built.
- **`wd` and `axis`:** were they measured? The mockup still tags them "guess".
- **Camera:** A7 or A7 IV? Nothing depends on it yet.
- **Gate height (R8):** keep `gate_above_axis` at 36, or raise it to 39.3 to close the hole?
- **Mockup:** republish it with the differences above?

## Conventions from this session

- **Temp files:** put scratch work in the session scratchpad, not `~` or `/tmp`.
- **Confirmation:** don't commit or push unless the user asks.
- **Memory:** no MEMORY files. Durable context goes in `CLAUDE.md` or here.
- **Mockup previews:** headless Chrome via `uvx --with playwright python -I <script>`
  (`channel="chrome"`, swiftshader args) works for screenshots. Use a mobile context, since
  plain `--window-size` can't go narrower than about 500px.

## Suggested skills

- `superpowers:brainstorming`: before designing the open mechanisms (leaf springs, guides,
  gate/dock joint, knob snap). These are design decisions for the user.
- `superpowers:test-driven-development`: write the geometry checks before each `model.py`.
- `superpowers:verification-before-completion`: run `build.py` and the tests and quote the
  output before saying a part is done.
- `jta`: republish the mockup to the same URL whenever a dimension or mechanism changes.
