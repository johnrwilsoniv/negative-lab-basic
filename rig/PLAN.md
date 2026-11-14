# NLB Scan Rig: CAD plan

**2026-11-09, branch `claude/rig-sprocket-drive`: the film transport is redesigned (D1–D5).** The rig
now takes a whole uncut 36 exposure roll. Two 8 tooth sprockets drive the film by its perforations through a
fixed 0.3 channel between the gate front and the gate body. Three 30 tooth gears on a deck on top of the gate
link them, and one turn of the knob on the idler moves the film one frame. Spools on pins beside the gate feed
it and take it up, by hand. The pressure plate, wedge plate, lid, lock switch, gate screws and the dock's front
wall are gone. The gate front presses onto four pegs on the body. 16 printed solids plus the thread coupon;
nothing intersects with a frame centred or half a sprocket tooth on, every fit measures as designed, and only
the gate front's four tooth grooves (2.8 wide) print as bridges. The sections below describe the new design;
the rulings before D1 are history, and D1 lists which it supersedes.

Status (2026-10-27): **the CAD exists; nothing has been printed yet.** Every printed part is
modelled in CadQuery from the three.js mockup, put together in an assembly, and checked: one
STEP file per printed part that the user can import into Onshape and edit, plus STL files for
slicing. Some mechanisms are still undesigned (each part's "Not designed yet" below). Until
the wedge-plate grooves exist, LOCK can't clamp.

2026-11-07: redesigned for printing (F5–F8). The gate is now a gate front and a gate body joined
by four M3 screws, the light dock's shroud is its own print, and every face that touches the film
prints on the bed. The wedge plate now prints flat (F9). Apart from the adapter's socket ledge,
no part prints over air (`cadutil.overhangs` checks it).

2026-11-07, later: no shroud (F10). The gate is 39 deep, so the gate body's rear face lies flush on
the CS-Lite's lit face, and the body stands in a notch in the dock's floor and front lip. Then the
dock grew a front wall (F11), so the whole gate is held between it and the CS-Lite. And the gate
body got a backer behind the wedge plate (F12), so LOCK wedges the plate instead of bending it.

Run it from `rig/`:
- `uv run pytest`: the checks on the built solids (about three minutes).
- `uv run python build.py [--wd W] [--axis A]`: builds every part, writes `exports/`, and prints
  the sizes and volumes, the interference check with the knob at each of its two positions
  (`assembly.TURNS`: a frame centred, half a sprocket tooth on), the fit numbers and the bed
  margins. It exits non-zero if a check fails. An axis below 39 is refused with a one-line message.
- `uv run python print_preview.py`: writes `exports/nlb-rig-print-preview.html`. **Whenever the
  print preview changes** (the template, `print_preview.py`, or the parts it shows), rebuild it and
  republish the webpage with `../../tmp-artifacts/bin/tmp-push exports/nlb-rig-print-preview.html`.
  Keep the filename: re-pushing the same name replaces the page and keeps its URL
  (https://tmp.jrwiv.com/a/nlb-rig-print-preview-a5yj677u).

`exports/step/` and `exports/stl/` hold one STEP and one STL per printed solid, plus the thread
coupon, in print pose. `exports/step/nlb-scan-rig-assembly.step` has every part in place with a
frame centred, in the Onshape frame (R10), with the film, half a roll on each spool and the CS-Lite as
grey reference solids. The sprockets, gears and spools are each printed twice (supply and take-up
side): each pair is one print, exported under both names.

## What the rig is

A light-tight path for scanning a whole uncut roll of 35mm B&W film with a camera:

    Sony A7 + Laowa 90mm f/2.8 2X ── 1 lens adapter ── 2 tube ── 3 film gate ── 4 light dock + CineStill CS-Lite
                                                                     ├ 5 film drive: sprockets, gears, knob
                                                                     └ 6 spools, either side of the gate

- Everything rests on one flat table. The camera sits on its own base. There's no cradle;
  the gate box carries the front end of the lens.
- The roll runs from the supply spool (−z) through the gate to the take-up spool (+z), flat, along z.
  The knob drives it a frame a turn; the spools are turned by hand to let it out and take it up.
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
| `GATE_D` | 39 | Gate depth: `GATE_FRONT + GAP`, so the body ends on the lit face (F10; was 30) |
| `GATE_FRONT` | 14 | Gate front's front face to film |
| Window | 38 × 26 | Frame window, in the gate front |
| `GAP` | 25 | Film to light face |
| `TUBE_RO` / `TUBE_RI` | 36 / 32 | Tube outer / inner radius |
| `FLANGE` | 3 | Adapter flange thickness |
| `THREAD_LEN` | 4.5 | Thread length |
| `channel` | 0.3 | Fixed film channel, 35.2 tall (D2) |
| `sprocket_teeth` | 8 | Sprocket pitch radius 6.048: one turn, one frame (D3) |
| `gear_teeth` | 30 | Every gear; module 1.029, 20°, 0.15 backlash (D4) |
| `spool_core_r` / `spool_flange_r` | 15 / 21 | Spools (D5) |
| `peg_d` / `peg_fit` | 4 / 0 | Friction pegs joining the gate front to the body (D2) |

**Derived values** at the defaults:

| Value | Formula | Result |
|---|---|---|
| Film plane | `xFilm = 125 + wd` | 255 |
| Gate box height | `GH = axis + 36` | 78.5 |
| Tube length | `wd − 13` | 117 |
| Dock width | `DOCK_W = 165 + 26` | 191 |
| Sprocket centres | `x_film + r_pitch`, z = ±(2.375 + 6 × 4.75) | x 261.05, z ±30.875 |
| Spool centres | `x_film − (15 + roll_r_full) / 2`, z = ±(46 + 3 + 21) | x 238.8, z ±70 |

The mockup's rail shows these live, and `updateText()` has the formulas.

## Parts

Each part gets `rig/parts/<part>/model.py`, which exposes `build(p, turn=0.0)`: a dict of the
part's solids, in mockup coordinates, with the knob `turn` turns from a frame centred (only the drive moves). `PRINT_UP` says which side of each faces up
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

Two printed pieces (D2): the gate front and the gate body, pressed together on four friction pegs.
Nothing clamps the film: it runs in a fixed channel between the two.

**Gate front** (solid block, prints with its rear face on the bed):
- x_gate .. `x_ref` (13.85 deep), 78.5 tall, 92 wide.
- Socket: Ø72.6, 4 deep, on the lens axis. The tube's end rests on its floor.
- Light passage: flares from the socket's floor (the frame window scaled until its corners reach
  the tube's Ø64 bore) down to the 38 × 26 frame window, which runs straight for 1.8 to the
  rear face. The passage only narrows toward the film, so it prints without support.
- Rear face: the film reference plane, `channel/2` (0.15) in front of the film plane. It's the
  first layer, so the film's front slides on bed-flat plastic.
- Four tooth grooves in the rear face, one per sprocket per perforation row: 2.8 wide, 1.2 deep
  (0.35 past the tooth tips), from the gate's side to 1 past where the tips cross the face, then a
  45° ramp up toward the window. They print as 2.8 bridges in the first layers.
- Four Ø4 holes right through, at y 10 and 70.5, z ±41, for the body's pegs. Same size as the pegs
  (`peg_fit` 0): FDM prints holes a little small, so they press.

**Gate body** (prints rear face down):
- A block from `x_ref` to the CS-Lite's lit face: 25.15 deep, 92 wide, 78.5 tall.
- Film channel across its whole front face: 0.3 deep, 35.2 tall (0.1 beyond each film edge),
  opening to 1.0 deep over the last 3 at each side so the film's end finds its way in.
- Light passage: 40 × 28 at the front face to 46 × 34 at the rear (the frame's chief rays and the
  lens cone, 25 behind the film). The panel closes it.
- Two sprocket pockets, vertical, r 7.45, at (x 261.05, z ±30.875), from y 21.67 up through the
  top, where the sprockets drop in. Each breaks through the front face, so the teeth reach the film.
  Below each, a Ø6.4 bearing hole down to y 4: the shaft's foot stands on its floor.
- The idler's axle hole: Ø6, 8 deep in the top, between the pockets (pressed).
- Four Ø4 pegs, 6 long, chamfered, on the front face outside the channel.
- The pockets and holes lie along the bed when it prints, so each is a teardrop pointing at the
  gate front (`cadutil.teardrop_y`). Nothing overhangs.

**Not designed yet:**
- **Gate position along the tube.** Nothing locates the gate along the tube. The socket is a
  slip fit, so the film plane sits wherever the gate is pushed. The floor's edge in front of the
  gate front, 0.2 clear, now stops it moving toward the camera.
- **Room light on the film's back.** The channel is open at both sides of the gate (the film runs
  through), and the film between the spools and the gate is in the open. Only the 25 between the
  film and the panel matters, and it's enclosed by the body.

### 4 · Light dock (`parts/light_dock/`)

Holds the CS-Lite standing on its long edge, lit face toward the film, `GAP` (25) behind
the film plane, with the gate standing in front of it and the spools beside the gate.

- **Floor:** 4 thick, 191 wide. It runs along x from 4 in front of the spools' flanges (x 213.8)
  to 6 past the slot's back edge (92.7 long).
- **No front wall** (D5): the spools stand where it was. The floor's edge in front of the gate
  front (0.2 clear) locates the gate toward the camera; the friction pegs hold the front on.
- **Lips:** front and back, 12 tall. Together they make a 20.5 wide slot for the light: its
  20 plus 0.5 clearance, all behind it, so the lit face stays at the front lip.
- **Side cheeks:** 62 tall, 12.5 wide.
- **Gate notch** (F10): 92.4 wide (the gate's 92 plus `dock_gate_clear` 0.2 each side), through the
  floor and the front lip, from 0.2 in front of the gate front to the lit face. The whole gate
  stands on the table in it, its rear face flush on the panel.
- **Spool stands** (D5): at (x 238.8, z ±70), a Ø16 pedestal up to y 22.5 and a Ø6 pin up to 1
  under the cap's spigot (y 56.5), chamfered. At axis 50 the pins stand 64 tall, past the cheeks.
- **Bed size:** at 191 wide the dock is the largest footprint (29 to spare on a 220 bed).
  **Confirm the printer's bed size.**

**Not designed yet:**
- Holding the CS-Lite against the front lip. The slot has 0.5 play behind it, so the gate's
  rear face can sit up to 0.5 off the lit face and leak light.
- Drag on the supply spool. It turns freely on its pin, 0.2 clear; hold it with a finger while
  winding on, or add a felt washer under it.

### 5 · Film drive (`parts/film_drive/`)

Two sprockets drive the film by its perforations; three gears turn them together; the knob on the
idler is turned by hand. One knob turn is one frame (D3, D4).

**Sprockets** (two, the same print; the take-up side's is turned half round):
- Upright in the gate body's pockets, on the light side of the film, at z ±30.875: each over a
  perforation's centre when a frame is centred in the window.
- Pitch radius 6.048, at the film's mid-plane: 8 teeth × 4.75 = 38, one frame a turn. The film is
  a rack and each sprocket a pinion on it.
- Two rings (r 5.933, 0.05 behind the film), one under each perforation row, from 12.6 off the
  axis to the film's edges, so they only touch the film outside the frame. A Ø9 hub between them.
- 8 teeth per ring, 1.0 past the pitch radius. Each tapers along the film (1.4 to 0.9; the
  perforation is 1.98) and comes to a 45° ridge across it (2.2–2.46 where it passes the film, in a
  2.79 perforation), so it finds the perforation's middle and prints without overhang. One or two
  teeth per row reach through the film at a time; the channel stops the film lifting off them.
- Ø6 shaft from its foot on the bearing hole's floor (y 4) to the gear's top (y 87.5), with a
  0.5 D-flat above the deck. 45° cones under each ring.
- Prints standing on its shaft's foot, at 0.12 layers.

**Gears:** 30 teeth, module 1.029 (so three in a row span the sprockets' 30.875 spacing), ISO 20°
involute, 0.15 backlash, 5 thick. One on each sprocket shaft's D-flat, standing on the deck; the
idler between them on its axle, with a Ø20 × 10 knob on top and a groove that counts turns.
Gear tips end 2.5 short of the CS-Lite.

**Mesh phase** (D4): each shaft's flat faces the idler and lies on a sprocket tooth and a gear tooth,
and the idler (an even tooth count) shows each gear a gap, so the same prints mesh on both sides with
a perforation centred on each sprocket.

**Deck:** 4 thick, on the gate body's top from the reference plane to 0.5 short of the CS-Lite:
the shafts' top bearings (Ø6.4) and the idler's axle (pressed). **Idler axle:** Ø6 × 26, through the
deck into the gate body's top.

**Assembly:** drop the sprockets into their pockets, lay the deck over the shafts, press the axle
through it into the body, put the gears on the D-flats with a tooth toward the idler and the idler
on its axle.

**Loading film:** wind the roll onto the supply spool, push its end into the channel at the −z
side, and turn the knob until the teeth catch the perforations; it comes out at +z. Tuck it in the
take-up spool's slit and wind on a turn or two by the cap.

### 6 · Spools (`parts/spools/`)

Two the same (D5), each two prints: the spool (bottom flange, r 21 × 2, and a Ø30 core with a Ø6.4
bore, a 1 × 6 slit for the film's end on the side away from the film, and a Ø16 × 3 socket in its
top) and the cap (flange r 21 × 2.5, scalloped round its rim, with a Ø16 × 3 spigot pressed into
the socket). The flanges are 0.5 beyond the film's edges. A whole roll is r 17.4.

They stand on the dock's pedestals and turn on its pins, beside the gate on the lens side, where a
half-wound roll is tangent to the film plane: the film leaves the roll within about 3° of the
channel's line, empty or full. The spool prints bottom flange down, the cap upside down.

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
├── viewer.py               writes exports/nlb-scan-rig.html (the assembly)
├── print_preview.py        writes exports/nlb-rig-print-preview.html (print direction per part)
├── mockup/
│   ├── nlb-scan-rig.html   copy of the published mockup (source of the numbers)
│   ├── viewer.html         template for viewer.py: the assembled CAD in three.js
│   └── print-preview.html  template for print_preview.py: each part on the bed, layer by layer
├── parts/
│   ├── lens_adapter/       model.py (+ thread_coupon in the same file)
│   ├── tube/               model.py
│   ├── film_gate/          model.py: gate_front, gate_body
│   ├── film_drive/         model.py: sprocket_*, gear_*, idler, idler_axle, deck
│   ├── spools/             model.py: spool_*, cap_*
│   └── light_dock/         model.py: light_dock
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
4. **Film gate.** (The clamp that was here first is superseded by D1.)
5. **Film drive and spools** (D1–D5).
6. **Light dock.** Settle the gate/dock joint with the user first.
7. **Assembly.** Write `assembly.py` and the assembly STEP, then an interference check
   across all parts.

## Checks before calling a part done

Write these as pytest checks against the built solids:

- Every solid is valid and closed (`shape.isValid()`) and its volume is greater than 0.
- Bounding boxes match the dimensions above at the default params, within 0.05.
- Mating fits:
  - tube OD vs adapter socket ID and gate hole: 0.3 radial clearance
  - the film channel (0.3) and the film's 0.085 either side; peg holes the pegs' size
  - the drive: rings 0.05 behind the film, tooth tips 0.35 short of the grooves' floors and 0.4
    from the pockets, shafts 0.2 in their bearings, the D-bores 0.1 off the flats
  - the spools: 0.2 on their pins, flanges 0.5 beyond the roll, caps pressed
  - CS-Lite slot 0.5 wider than the panel; the gate 0.2 in the dock's notch
- At the assembly level:
  - no two solids intersect, with a frame centred or half a sprocket tooth on; the teeth stay in
    the perforations at a quarter and a half turn too
- Every printed part fits the bed. 220 × 220 is assumed until the user confirms.
- STEP round-trip: re-import each exported STEP and check its volume matches.
- Every solid manifold: each edge between exactly two faces. OCC's `isValid()` misses a solid
  whose pieces meet only along an edge; Onshape marks it faulty (`cadutil.is_valid` checks both).
- Report the numbers (sizes, clearances, volumes) to the user. They check the look in
  Onshape.

## Decisions made while building

Each was a ruling made during the build (numbers at the defaults). The code cites them by
number.

- **Not modelled yet (R3):** leaf springs, pressure-plate guides, wedge-plate grooves,
  gate/dock joint, lid-slot detents. The surfaces where they'd attach are left plain.
- **Open-top box with a separate lid (R4).** The lid sits between the gate front and the rear
  wall, on the side walls. A closed box can't take the plates in or print without an 86 bridge.
- **Front plate is part of the box (R5).** Superseded by F5: the front plate is the rear end
  of the gate front.
- **Sloped pads (R6).** The pads' back faces slope like the ramps, `padT` thick at the
  centre. At SLIDE pads and ramps just touch; at LOCK they overlap by the 0.113 preload.
- **The clamp in a rigid model (R7).** At LOCK the only overlap allowed is the pads in the
  ramps, 0.113 deep. The film lies on the front plate and is only touched.
- **Gate height kept at `axis + 36` (R8).** The Ø72.6 socket then breaks 0.3 through the top
  of the gate front. `gate_above_axis` ≥ 39.3 closes it with 3 of wall over the hole.
- **Shroud 67.5 tall (R9).** Superseded by F10: there's no shroud.
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
  hit the table. Lower still,
  the tube (36) and the gate hole (36.3) reach the table too.
- **Film slots start at the front plate (F3).** Each side-wall slot runs from the front
  plate's rear face (`film_slot_x0`) to x 257.9, 3.2 along x. Centred on the film, as in the
  mockup, it opened a 0.4 × 37 slit into the lens-side chamber. Started at the plate's front
  face (5 along x), the side wall and the plate met only along an edge: a non-manifold solid
  that Onshape marked faulty. From the rear face the side wall covers the plate's end, and the
  film lies against the plane the slot starts from.
- **Clamp plates print on edge (F4).** Superseded by F7 (pressure plate) and F9 (wedge plate).
  On edge the ramp and pad slopes were smooth, but the windows were 38 and 52 wide bridges.
- **The gate in two pieces (F5).** The user asked for no large unsupported spans. In one
  piece the box needed support under the front-wall hole's upper arc and bridged 38 over the
  front plate's window and 46 over the rear window. Now the gate front is a solid block that
  prints film-face down: the socket and a flared light passage only widen going up. The gate
  body prints rear wall down, so its walls rise straight from the bed, and the film slots
  become notches open at the top of the print. Four M3 screws through pillars outside the
  side walls join the two. The pillars run the body's whole depth, so they stand on the bed.
  The block has no lens-side chamber, so the lid's front slit no longer opens on the lens
  side. The lettering moved from the lid to the gate front's top: the lid now starts at
  `x_ref`, behind where the lettering was.
- **The shroud is its own print (F6).** Superseded by F10. The user asked for it. Part of the dock, it was a 56
  wide bridge, 9 deep. On its own it prints on its end. A 1 deep pocket in the dock's floor
  and a notch over the front lip, each 0.2 clear (`shroud_clear`), locate it. `fits.py`
  measures both.
- **Film-contact faces on the bed (F7).** The user asked that every face touching the film be
  smooth. The film lies on the gate front's rear face and is pressed by the pressure plate's
  front face, and both print as the first layer. The film's edges pass the side walls' notch
  faces, which print upright. Cost: the pressure plate's sloped pads face up and print
  stepped (1:17, 0.23 rise across a pad). Use 0.12 or finer layers and ironing, and tune
  `ramp_rise` against the print.
- **Wedge plate prints flat (F9).** The user asked for it to print without supports. It lies
  on its back face (`PRINT_UP` -x), with the tab flush in the same first layer and the ramps on
  top. Nothing prints over air, but the ramps print stepped, like the pads (F7): stepped ramp
  against stepped pad. Use 0.12 or finer layers and ironing, and tune `ramp_rise` after a test
  print. If the lock action feels notchy, the next step is to design the slope out of one side,
  for example flat pads with a rounded leading edge riding the ramps.
- **Overhang check (F8).** `cadutil.overhangs` lists the faces that lean out more than 45°
  in print pose. The gate and the dock tests assert none.
- **No shroud: the gate body is inset in the dock (F10).** The user asked for it. `gate_d` is now
  derived, `gate_front + gap` (39, was 30), so the gate body's rear face is the CS-Lite's lit face
  and the panel closes the rear window directly. The film-to-light gap stays 25. The dock's floor
  starts at `x_ref`, and a notch through its floor and front lip, 0.2 clear each side of the gate's
  110 (`dock_gate_clear`), takes the body. `fits.py` measures the notch clearance and the gate's
  rear face against the panel. The body is 9 deeper (25.3), and the lid 9 longer (21.9).
- **The dock holds the gate together (F11).** The user asked for it. The dock's floor runs on
  under the gate front to a front wall, 4 thick and 62 tall, 0.2 (`dock_gate_clear`) in front of
  the gate front, with a U 1 (`dock_tube_clear`) around the tube, open at the top so it prints
  without overhangs. The gate front and body are trapped between that wall and the CS-Lite, and
  the dock is a closed frame instead of two cantilevered arms. The dock is 69.7 long. `fits.py`
  measures the wall's clearance to the gate front and to the tube. The M3 screws stay.
- **A backer behind the wedge plate (F12).** The user asked for it. The gate body's floor rises
  into a block that fills the 17 behind the wedge plate, from 0.05 behind it to the rear wall,
  wall to wall, up to the film's bottom edge (y 25, half a millimetre under the rear window), so
  no light is cut. At LOCK the pads push the plate back onto it, so the clamp holds instead of
  the plate bending away. The 0.05 play comes off the 0.113 preload: tune `wedge_back_clear`
  with `ramp_rise`. It prints standing on the rear wall, like the rest of the body. `fits.py`
  measures the 0.05.
- **The film rests on the film slots' floors (F13).** The user asked for it. The slots were 37
  tall, 1 clear of the 35 film each side, so the strip hung in the air between the two ledges. Each
  floor now starts at the film's lower edge (`film_slot_y0`, axis − 17.5), so the strip rests on
  it, and the roof is 0.2 (`film_slot_clear`) over the upper edge so the strip still slides. The
  film hasn't moved: it stays centred on the window. FDM tends to print a slot a little narrow, so
  check the strip slides freely and open `film_slot_clear` if it doesn't.
- **Lock icons on the knob, not lettering on the gate front (F14).** The user asked for it. With the
  gate front printing film face down, the SLIDE / LOCK engraving was in a face standing upright in
  the print, so it couldn't print cleanly. The gate front's top is now plain. The knob's three grip
  ridges are gone, and two padlock icons are raised 0.6 on its top instead (`icon_*`): open at
  the −z end, the way to SLIDE, and shut at the +z end, the way to LOCK. Each body is 4 × 3, the
  shackle stroke is 0.8 (two 0.4 lines), and the shackles point +x, so they read upright from the
  camera end. The knob prints top up, so the icons are its last layers and nothing overhangs.
  Superseded by F15: the knob, and its icons with it, are gone.
- **No knob: the tab is the grip (F15).** The user asked for it. The wedge plate's tab now runs
  12.7 (½ inch, `tab_reach`) above the lid top instead of ending flush with it, and you push it
  directly. The knob, its `knob_*` and `icon_*` params, and `x_knob` are gone, and there's no snap
  to design. The rig has 8 printed parts. The tab is still 2 × 4, so it fits the existing lid slot;
  the wedge plate prints flat as before, now 87.7 tall on the bed, with the tab in the first
  layers. Print the tab solid. Nothing marks SLIDE and LOCK any more.

- **The film transport is redesigned (D1).** The user asked for a full redesign: gears that drive the film
  by its perforations, left to right through the window, an uncut 36 exposure roll on spools either side,
  and no pressure plate or wedge, a friction fit between the gate body and front holding the film flat.
  This supersedes the clamp and everything that served it: R3, R4, R6, R7, F1 (the plate and lid fits),
  F3, F4, F7 (the pressure plate), F9, F11, F12, F13, F14 and F15. `build(p, lock)` became
  `build(p, turn)`, and the interference check runs at two knob positions instead of SLIDE and LOCK.
- **A fixed channel, a pegged gate (D2).** The film runs in a 0.3 channel (the film plus 0.17) recessed
  into the gate body's front face and closed by the gate front's bed-printed rear face; the channel's
  walls keep it straight in y. The front presses onto four Ø4 pegs, no screws, so the channel's depth is
  set by the body's recess however hard the front is pushed on. The film's front still slides on a
  first layer (F7's intent).
- **8 tooth sprockets on the light side (D3).** One turn, one frame. On the light side so the lens side
  stays a solid block with the tube socket; the 25 gap leaves room for the pocket (tips to x 268.1).
  Over the 7th perforation from the window's centre (z ±30.875), so a tooth stands in a perforation
  with a frame centred, and the pockets stay 2.7 clear of the light passage. The film runs flat past
  the sprockets, not wrapped: only the teeth near the tangent point engage, and the channel is the
  keeper. The model checks the rack and pinion by interference at four knob positions.
- **Three equal gears in a row (D4).** The idler reverses, so both sprockets turn the same way. Equal
  gears keep one knob turn one frame, which sets the module to 30.875 / 30. The gears sit on top of the
  gate, the only place clear of the light, the tube and the spools; the CS-Lite (112 tall, behind them)
  caps their size at about 16.5 radius. An even tooth count lets identical prints mesh on both sides.
- **Spools on pins beside the gate (D5).** On the lens side, where they can't block the light and the
  CS-Lite doesn't stand, at a spacing that keeps a half roll tangent to the film plane. The dock's front
  wall (F11) is gone to make room, and the dock grows to 191 wide and 92.7 long. The spools are turned by
  hand; nothing gears them to the drive, since the roll's radius changes as it winds.

## Mockup differences to republish

The CAD differs from the mockup on purpose here. The mockup hasn't been changed: republishing
it is the user's call.

| What | Mockup | CAD |
|---|---|---|
| Gate lid | full gate depth, over the front and rear walls (it overlaps the tube) | between the front and rear walls, 0.2 short of each |
| Gate floor | full gate depth, under the front and rear walls | between the front and rear walls |
| Pressure plate, wedge plate, lock switch, lid | present | none (D1): a fixed 0.3 channel, a sprocket drive and spools |
| Tube | plain ring | baffle ribs inside |
| Film slots | centred on the film plane, x 252.5–257.5 | a channel across the gate body's front face |
| Gate | one box with a thin front plate and a chamber in front of it | gate front (solid, flared light passage) + gate body (solid, sprocket pockets), pressed on four pegs, 92 wide |
| Film | a 228 strip | an uncut roll on two spools, driven by two sprockets, three gears and a knob |
| Lettering | on the lid | none |
| Knob | 10 × 12 on the tab, grip ridges | none: the tab sticks 12.7 out of the lid and is the grip |
| Shroud | part of the dock | none: the gate body (39 deep) stands in a notch in the dock, flush on the lit face |
| CS-Lite slot | 20, dock 35 long | 20.5; the dock runs forward past the spools, 92.7 long, 191 wide, no front wall |
| `axis` | slider 30–60 | 39 at least |

## Latest feedback

The design review of 2026-11-11 (at wd 111, axis 40.5, commit `0e836e1`) was of **main's clamp gate**, not of
this sprocket drive: every part and the assembly, measured on the built solids with scripts apart from the
repo's tests. No slicer was run, so print effects are inferred. It found sixteen things (FB1–FB16), none of
them certain to fail. Six concern parts this rig shares with main (the adapter, the tube, the gate front's
socket and window, the dock's notch) and are carried here under their original numbers, so the numbers have
gaps. The print preview's **Latest feedback** tab shows each with a drawing and its numbers
(`print_preview.feedback`, F19); this list is numbered the same. The drive itself (sprockets, gears, deck,
spools) has not been reviewed.

### Likely trouble

- **FB1 · The gate has no clearance at the dock floor's notch end.** The gate body's rear face and the
  floor's notch end are both at x 266; the gate front has 0.2 to the floor's edge in front of it (on main, to
  a front wall; here the stop is the 4 tall floor edge alone, D5). Both corners print on the bed, so
  first-layer flare lands on a zero gap. The pocket is 49.2 for the 49 deep gate (39.2 and 39 when reviewed).

### Minor

- **FB9 · The perforations show in the frame window.** Their inner edges are at 12.7, the window's at 13:
  0.3 of each row shows, 16 perforations, 9.5 mm² of bare light.
- **FB10 · The adapter's socket ledge prints as a ceiling, and the tube seats on it.** Thread up, the
  socket floor is a 3.3 wide ceiling 9 above the bed: it prints on supports, and it is the face the
  tube's end seats on.
- **FB14 · The thinnest section: over the tube's socket.** 1.7 of gate front over the Ø68.6 socket. The
  review's other two (1.25 round the screws' counterbores, and the strip under the dock's U) are not on this
  rig: the front is held by pegs, and the dock has no front wall.
- **FB15 · The tube's baffle flanks are exactly 45°.** They pass `cadutil.overhangs` only by its 1e-6
  tolerance.
- **FB16 · PLAN never names a filament.** Light-tightness through 2.25 and 1.7 walls needs an opaque, matte
  black one. About 56% of the panel's lit area shines past the gate and the deck (worked out for this gate;
  the review measured 57% on main's).

Not carried, because D1 removed the part: **FB2** (the clamp's margin), **FB3** (the lid as the lock's travel
stop), **FB5** (the strip on two 3 mm ledges), **FB6** (a strip going behind the pressure plate), **FB7** (the
lid's and the tab's openings), **FB8** (the wedge plate floating), **FB12** (notes written for the Ø72 tube:
fixed on main, and the same notes are fixed here), **FB13** (the film 0.3 in front of `x_film`: here it runs
in the middle of a 0.3 channel, 0.085 either side).

To measure again on this gate before they can be carried or dropped: **FB4** (plastic on the image area: here
every frame slides through the fixed 0.3 channel, on the gate front's bed-printed face and the channel's
floor, with no relief over the 24 image band) and **FB11** (nothing checks `wd`, or an axis that is too high:
the ranges that build, wd 40–233 and axis 39–62, were swept on main's dock, not this one; here `build.py`
has been run at the defaults, at axis 39, and at wd 150 / axis 50).

The review's design is `print_preview.reviewed()`: the review's wd and axis, and the defaults that have
changed since (`print_preview.CHANGED_SINCE`: F23, F24). The page's numbers that follow from the dimensions
are worked out at the build's wd and axis. Came out clean, on the shared parts: the lens side's
light-tightness, the optics on the lens side, and printability bar the adapter's ledge, the thread and the
tube's ribs. Not checked: the drive and the spools, slicing, the real hardware, the pages, and STEP import
into Onshape.

## Check before printing

**This sprocket design has not been printed.** (Main's clamp gate was, on 2026-11-14, and it worked; F23 and
F24 came from that print.) These are the sizes that come from outside the CAD (the camera and its base, the
lens, the CS-Lite, the film and the printer) and that the prints depend on. Each is a param in `params.py`;
the numbers below are at the defaults. "Changes" lists the printed solids whose shape changes with the
value. Most important first.

### Before printing anything

One session at the bench with the camera on its base, the lens, the CS-Lite and the printer's spec
sheet. These set most of the plastic, or decide whether it prints at all.

- **C1 · `axis` 40.5 (measured 2026-11-09; was the guess 42.5): table to lens centre.** With a ruler.
  - **Measure:** the camera and lens on the base they'll scan from, on the table. A steel rule
    standing on the table (or the calipers' depth rod) to the underside and to the top of the lens's
    front rim, averaged; or the underside plus 33.5. If the base adjusts (a rail, shims, a head),
    `axis` is a choice instead: anything from 39 up (F2), and set the base to it. The base and the
    body (A7 or A7 IV: see "Questions for the user") decide it.
  - **If it's off:** the tube joins the lens to the gate rigidly, so the camera tilts or the gate and
    dock lift off the table. The film isn't square to the sensor, and the gate's rear face leaves the
    CS-Lite and leaks.
  - **Changes:** gate front, gate body, both sprockets (their shafts), light dock (the spools' pedestals
    and pins). Fix: `build.py --axis A`, then `print_preview.py --axis A`.
- **C2 · `wd` 116 (measured 111 on 2026-11-09, was the guess 130; 5 more after main's first print, F24): lens
  front to film plane, at 1:1.** With a ruler.
  - **Measure:** from the lens's front rim (the filter-thread face, where the adapter's flange seats)
    to the film's surface. Focus ring at 1:1, the camera on its base, a negative or a ruler lying on
    the CS-Lite; move the camera until it's sharp and 36 mm of ruler fills the frame's width. Measure
    three times. Check whether the front of the lens moves when you focus; if it does, measure with
    the ring at 1:1.
  - **If it's off:** the tube is `wd − 18` (98) long and nothing else adjusts along the axis: its ends
    sit on the socket floors. A few mm off, the focus lands a little off 1:1, so the frame is cropped or
    shows its borders. Further off, the lens can't focus on the film.
  - **Changes:** the tube only, but it's the tallest print. Fix: `build.py --wd W`, then
    `print_preview.py --wd W`.
- **C3 · CS-Lite: `csl_l` × `csl_h` × `csl_t` 165 × 112 × 20, lit area `csl_lit_w` × `csl_lit_h`
  149 × 95 (datasheet).** With calipers and a straightedge.
  - **Measure:** length, height, and the thickness at its thickest point, feet and buttons included.
    A straightedge across the lit face: the gate body's rear face (92 wide, from the table to 76.5)
    lies on it from the panel's bottom edge, across the bezel, so the face must be flat edge to edge.
    Where the lit area sits: the build assumes it's centred, its bottom 12.5 above the table, and the
    gate's rear window is 23.5 to 57.5. Where the USB-C port and the button are: the cheeks cover the
    panel's ends up to 62. The gears and the knob stand in front of the panel's top (y 80.5 to 95.5), the
    gear tips 2.5 from its face.
  - **If it's off:** thicker than the 20.5 slot or longer than the 166 between the cheeks, it doesn't
    go in. Thinner, or a face that isn't flat, and the gate's rear face sits off it and leaks (see the
    light dock's "Not designed yet"). A port at an end is blocked by a cheek. A lit area that doesn't
    cover the rear window vignettes.
  - **Changes:** the light dock (`csl_l`, `csl_t`). The height and the lit area change nothing printed.
- **C4 · Printer: bed `bed_x` × `bed_y` 220 × 220 and build height (assumed).** From the spec sheet.
  - **Measure:** the usable print area and height, not the plate's size, less any brim or skirt. Load
    `light_dock.stl` in the slicer: it's the biggest footprint, 92.7 × 191. The tallest prints are the
    tube, 98 upright, and the sprockets, 81.5; with no height given, `tube_max_len` borrows the bed's 220.
  - **If it's off:** no shape changes, but a dock that doesn't fit doesn't print. `build.py` checks
    square-on only (29 margin at 220); turned 45° the dock fits a 201 square bed. Past `wd` ≈ 238 the
    tube wants a spigot split, which isn't built.
  - **Changes:** nothing; it decides whether the light dock and the tube print. Fix: `bed_x`, `bed_y`.
- **C5 · Filter thread M67 × 0.75, `thread_clear` 0.15: print the thread coupon.** A test print.
  - **Measure:** confirm the lens takes 67 mm filters. Print `thread_coupon.stl` first (thread up,
    0.12–0.16 layers) and screw it in by hand: it should turn smoothly, seat its ring flat on the
    rim, and not wobble. Never force it.
  - **If it's off:** too tight, it cross-threads or strips the lens's filter thread. Too loose, the
    adapter sits crooked, the tube points off-axis and the film tilts. Tight: raise `thread_clear`
    0.05; loose: lower it. It builds from 0.05 to 0.3 (R13).
  - **Changes:** adapter, thread coupon.

### Before a particular part

- **C6 · Filter thread depth and front element: `thread_len` 4.5, `adapter_bore_r` 31 (Ø62).
  Before the adapter.** With calipers. The depth rod from the rim to where the lens's thread stops;
  the inside jaws across the retaining ring or whatever stands proud inside the thread. The coupon
  tells too: its ring should seat on the rim. A thread shallower than 4.5 and the adapter bottoms out
  before its flange seats (crooked, or pressing on the glass's ring); a bore smaller than the glass's
  opening vignettes. **Changes:** adapter, thread coupon.
- **C7 · Tube in its sockets: `fit_clear` 0.05 (Ø68.5 tube, Ø68.6 sockets, F23). Before the tube.** Checked on
  main's first print: the Ø68 tube with a few layers of masking tape was a good friction fit, so the tube is now
  Ø68.5. Holes print small and outer walls a little big, so before printing the whole tube, cut it to a 10 mm ring
  in the slicer and try it in the printed adapter and gate front: it should push in firmly by hand and stay. Tight
  and it won't go in or cracks the socket; loose and the gate and lens aren't on one axis, and light gets in at the
  joint. On this gate it must also be looser than the pegs (C10). **Changes:** the tube (`tube_ro`); `fit_clear`
  follows it, so the sockets keep their Ø68.6.
- **C8 · The film channel: `film_w` 35, `channel_clear` 0.2 (35.2 tall), `channel` 0.3 deep, opening to
  `lead_in_depth` 1.0 over `lead_in` 3 at each side (D2). Before the gate body.** Calipers across your film. There's
  no channel coupon: model a 35.2 × 0.3 slot through a small block in the slicer, print it rear face down like the
  gate body, and push the film's end through. FDM prints slots narrow, so the film drags or won't start; too tall
  and it wanders in the window, and the teeth meet the perforations off centre (they have 0.17 to 0.3 each side).
  Open `channel_clear` or `channel` by 0.05 at a time. **Changes:** gate body.
- **C9 · Film thickness, the perforations and the first layer: `film_t` 0.13 in the 0.3 `channel`; `perf_pitch`
  4.75, perforations `perf_l` × `perf_w` 1.98 × 2.79 (ISO 1007, KS). Before the gate front and the sprockets.**
  Calipers or a micrometer on the film, in a few places: 0.085 is left either side of it, and thicker film (or a
  splice) takes it up. Eight perforations should measure 38.0: the sprockets' pitch radius comes from it, one turn a
  frame. The gate front's rear face is a first layer: level the bed, keep it clean, and turn off or compensate
  elephant's foot, which puts a lip round the frame window and the tooth grooves. Print one sprocket and try it in a
  strip of film before the rest (see "Tuning and print notes"). **Changes:** nothing from `film_t`; the sprockets
  and the gate front's grooves from the perforation sizes.
- **C10 · The friction pegs: four Ø4 × 6 (`peg_d`, `peg_len`), in holes of the same size right through the gate
  front (`peg_fit` 0, D2). Before the gate front and body.** A test print: one peg on a small plate and one Ø4 hole
  through a 6 thick block, both in the parts' print poses (the peg along the bed, the hole upright). It should
  press on by hand and take a firm pull to come off. The pegs are all that holds the gate front on, and since F23
  the tube grips the front's socket: the pegs must hold harder than the tube, or pulling the tube out opens the film
  channel (see the film gate's "Not designed yet"). Too tight: `peg_fit` up 0.05. Too loose: a drop of glue, or
  screws would have to come back. **Changes:** gate front (`peg_fit`), gate body (`peg_d`, `peg_len`).
- **C11 · Bearing, press and standing fits: `bearing_clear` 0.2 (the Ø6 sprocket shafts in the body and the deck, the
  idler on its axle, the spools on their pins), `flat_clear` 0.1 (the gears' D-bores), `pocket_clear` 0.4,
  `gear_backlash` 0.15, the pressed fits at 0 (the idler's axle in the deck and the body, the caps' spigots),
  `dock_gate_clear` 0.2, `csl_clear` 0.5. Before the drive, the spools and the dock.** A test print: a calibration
  cube and a Ø6 pin in a Ø6.4 hole, measured with calipers. If the printer prints outer sizes big or holes small by
  more than about 0.1, the shafts bind and the pressed fits won't go together. After the gate body prints, stand
  both sprockets in it, lay the deck on and check they spin before printing the gears. **Changes:** gate body,
  deck, gears, idler, spools, caps, light dock.

### Worth measuring, but no print depends on it

- **C12 · Lens barrel: `lens_len` 125, `lens_r` 37 (guesses).** Calipers: mount flange to front rim,
  and the barrel's diameter. Nothing printed changes: the lens is reference geometry (R14), and x is
  measured from its front. **Changes:** nothing.

After printing, tune `channel`, `peg_fit`, the tooth sizes and `gear_backlash` against the parts ("Tuning and
print notes").

## Tuning and print notes

- **`thread_clear`** builds valid solids from 0.05 to 0.3. Print the coupon to choose.
- **Supports:** only the adapter's socket ledge (a 5.3 wide annular overhang in the thread-up
  pose). The gate front's four tooth grooves are 2.8 wide bridges.
- **First layer:** the gate front's first layer is the film's front surface. Level the bed, keep the
  plate clean, and turn off or compensate elephant's foot, which would put a lip on the frame
  window's edge and the grooves.
- **The channel's floor** is the gate body's last layers: use ironing.
- **`channel`** (0.3): if the film drags, open it to 0.35; if it bows, close it. **`channel_clear`**
  (0.2): FDM prints slots narrow; open it if the film's edges bind.
- **`peg_fit`** (0): open it 0.05 at a time if the gate front won't press on.
- **Sprockets:** print at 0.12 layers so the 1.0 teeth keep their shape; two at once, or a brim,
  since each is Ø6 × 83.5. Print one first with a short test strip of film: if the teeth don't
  enter the perforations cleanly, tune `tooth_tip`, `tooth_w` and `tooth_h`.
- **Gears:** if they bind, open `gear_backlash`; if the knob feels loose, close it.
- **Stale exports:** an invalid solid isn't exported, so the previous STEP/STL stays in
  `exports/`.

## Questions for the user## Questions for the user

- **Printer:** bed size and build height. 220 × 220 is assumed. `tube_max_len` borrows the
  220 footprint as the height. The plan wants a spigot split past `wd` ≈ 200; that isn't built.
- **`wd` and `axis`:** were they measured? The mockup still tags them "guess".
- **Camera:** A7 or A7 IV? Nothing depends on it yet.
- **Gate height (R8):** keep `gate_above_axis` at 36, or raise it to 39.3 to close the hole?
- **Mockup:** republish it with the differences above?
- **Film direction:** the roll runs from −z to +z (left to right from the camera's side, looking at the
  gate). Should either end be the supply side for how the roll comes off the developing reel?
- **Roll length:** `film_roll_len` is 1600 (36 frames plus leader and trailer). A 37 or 38 frame roll fits.
- **Print preview:** republish it from this branch, or wait until the branch merges? The page's URL
  shows main's design now.

## Conventions from this session

- **Temp files:** put scratch work in the session scratchpad, not `~` or `/tmp`.
- **Confirmation:** don't commit or push unless the user asks.
- **Memory:** no MEMORY files. Durable context goes in `CLAUDE.md` or here.
- **Mockup previews:** headless Chrome via `uvx --with playwright python -I <script>`
  (`channel="chrome"`, swiftshader args) works for screenshots. Use a mobile context, since
  plain `--window-size` can't go narrower than about 500px.

## Suggested skills

- `superpowers:brainstorming`: before designing the open mechanisms (holding the CS-Lite, spool drag,
  locating the gate on the tube). These are design decisions for the user.
- `superpowers:test-driven-development`: write the geometry checks before each `model.py`.
- `superpowers:verification-before-completion`: run `build.py` and the tests and quote the
  output before saying a part is done.
- `jta`: republish the mockup to the same URL whenever a dimension or mechanism changes.
