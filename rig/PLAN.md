# NLB Scan Rig: CAD plan

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

2026-11-09: `wd` and `axis` are measured: 111 and 40.5 (were the guesses 130 and 42.5). The tube is
19 shorter, and the gate front, gate body, pressure plate and wedge plate 2 shorter; the adapter, the
thread coupon and the lid keep their shape. At the lower axis the dock's floor came within 0.5 of the
tube under its front wall, so the U's round now goes through the floor too (F17). Numbers in the
rulings below are as they were when each was made, at the old defaults.

**Before printing anything, go through "Check before printing" below** (also the print preview's
"Dimensions to confirm" tab): the sizes that come from the camera, lens, CS-Lite, film, screws and
printer, most of them still guesses or assumptions.

Run it from `rig/`:
- `uv run pytest`: the checks on the built solids (about a minute).
- `uv run python build.py [--wd W] [--axis A]`: builds every part, writes `exports/`, and prints
  the sizes and volumes, the interference check at SLIDE and LOCK, the fit numbers and the bed
  margins. It exits non-zero if a check fails. An axis below 39 is refused with a one-line message.
- `uv run python viewer.py` and `uv run python print_preview.py [--wd W] [--axis A]`: write the two pages
  as standalone files, `exports/nlb-scan-rig.html` and `exports/nlb-rig-print-preview.html`, every STL
  embedded. Give them the same `--wd` and `--axis` as `build.py`: the print preview refuses STLs built at
  other values.
- `./publish.sh [slot] [--wd W] [--axis A]`: runs `build.py`, then `website.py`, and puts the pages on
  **https://nlb.jrwiv.com**: the viewer as the home page, the print preview at `/main/print-preview/`, and
  every STL and STEP under `/main/files/`. `main` is published only from a clean `main` branch; any other
  slot (by default the current branch) is a preview at `nlb.jrwiv.com/<slot>/`. **Whenever a page changes**
  (a template, `viewer.py`, `print_preview.py`, or the parts they show), publish again. The site is nginx
  in `~/dev/docker/nlb-site` on bunbun (`deploy/`), proxied by NPM on eggo; `publish.sh` syncs its config
  too. The pages used to live on tmp.jrwiv.com (`nlb-scan-rig-zh2mb48s`, `nlb-rig-print-preview-a5yj677u`);
  don't push them there any more.
- `uv run make_icons.py`: scales `icon-source.png` (the film canister) to every icon format (`icons/`:
  favicon.ico, favicon-96x96.png, the iPhone's apple-touch-icon, the PWA icons and `site.webmanifest`), the
  repo's `favicon.ico`, and the pages' inline icon. `website.py` serves `icons/` from the site root with `main`.

`exports/step/` and `exports/stl/` hold one STEP and one STL per printed solid, plus the thread
coupon, in print pose. `exports/step/nlb-scan-rig-assembly.step` has every part in place at
SLIDE, in the Onshape frame (R10), with the film and the CS-Lite as grey reference solids.

## What the rig is

A light-tight path for scanning 35mm film strips with a camera:

    Sony A7 + Laowa 90mm f/2.8 2X ── 1 lens adapter ── 2 tube ── 3 film gate ── 4 light dock + CineStill CS-Lite
                                                                     └ 5 lock switch on the gate lid

- Everything rests on one flat table. The camera sits on its own base. There's no cradle;
  the gate box carries the front end of the lens.
- Strips lie flat and slide sideways through the gate.
- The README in this repo says the camera is an **A7 IV**, but the mockup says "A7". Confirm
  with the user before any part depends on body dimensions. Currently none do: the camera
  and lens are reference geometry only.

## Source of truth

`rig/mockup/nlb-scan-rig.html` is a copy of the three.js mockup that was published at
https://tmp.jrwiv.com/a/nlb-scan-rig-zh2mb48s; that URL has since held the CAD viewer, so this copy
is the only one. Every dimension below comes from its script.

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

**Republishing:** the mockup isn't published anywhere now. To show it again, add it to `website.py` as
another page on nlb.jrwiv.com; don't push it to tmp.jrwiv.com.

**Mockup coordinates:**
- `x`: the optical axis, running from the camera (−) to the light (+). `x = 0` is the
  lens mount, and `x = 125` is the lens front.
- `y`: up from the table.
- `z`: across the gate. This is the direction the film travels.

All units are mm.

## Parameters

Put these in `rig/params.py`. Every part reads from there, so nothing hard-codes a derived
size.

**User inputs.** Measured by the user on 2026-11-09, with the dimensions and the framing checked
(C1 and C2 in "Check before printing"). They were the guesses 130 and 42.5.

| Parameter | Default |
|---|---|
| `wd`: lens front to film | 111 |
| `axis`: table to lens centre | 40.5 |

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
| Film plane | `xFilm = 125 + wd` | 236 |
| Gate box height | `GH = axis + 36` | 76.5 |
| Tube length | `wd − 13` | 98 |
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

- **Size:** Ø72 OD / Ø64 ID. Length is `wd − 13` (98 at the default), with 12 baffle ribs.
- **Ends:** one end slides into the adapter socket and the other into the gate's front-wall
  hole (Ø72.6, 4 deep).
- **Inside:** blocks room light and should cut flare. Consider internal baffle ribs or a
  matte texture.
- **Printing:** upright.
- **Bed size:** 98 tall is fine. If `wd` grows past roughly 200, split the tube with a
  spigot joint.

### 3 · Film gate (`parts/film_gate/`)

Four printed pieces (F5): the gate front, the gate body, the lid and the pressure plate.

**Gate front** (solid block, prints with its rear face on the bed):
- x_gate .. `x_ref` (13.7 deep), 76.5 tall, 110 wide (`gw` plus a screw pillar's width each side).
- Socket: Ø72.6, 4 deep, on the lens axis. The tube's end rests on its floor.
- Light passage: flares from the socket's floor (the frame window scaled until its corners reach
  the tube's Ø64 bore) down to the 38 × 26 frame window, which runs straight for 1.8 to the
  rear face. The passage only narrows toward the film, so it prints without support.
- Rear face: the film reference plane, `CHANNEL/2` (0.3) in front of the film plane. It's the
  first layer, so the film lies on bed-flat plastic, across the whole width, including where the
  film leaves through the side walls.
- Four Ø3.4 holes for M3 × 20 screws, counterbored Ø6.5 × 3.5 from the front.
- Its top is plain (F14).

**Gate body** (prints rear wall down):
- Floor (3), side walls (3) and the rear wall (3, with a 46 × 34 window toward the light),
  from `x_ref` back to the CS-Lite's lit face (F10): 25.3 deep, 92 wide, 76.5 tall. Open at the top for the lid and open at the
  front, where the gate front closes it.
- Film slots: 3.2 (along x) × 35.2 (along y) notches in the side walls, open toward the gate front.
  Each floor is flush under the film's lower edge, so the strip rests on it; the roof is 0.2
  (`film_slot_clear`) over its upper edge (F13).
- Four 9 × 9 screw pillars outside the side walls, the body's whole depth so they stand on the
  bed: two at the floor, two just under the lid. Ø2.5 pilots, 12 deep, for the M3 screws to
  self-tap (`pilot_d` 4.0 for heat-set inserts).
- **Backer** (F12): a block on the floor behind the wedge plate, from 0.05 (`wedge_back_clear`)
  behind its back face to the rear wall, side wall to side wall, up to the film's bottom edge
  (y 23), so it stays out of the light path. At LOCK the plate is wedged between the pressure
  plate's pads and the backer.

**Lid:** 3 thick, on the side walls, 0.2 short of the gate front and of the rear wall. Slot
3 × 16 for the lock switch's tab.

**Pressure plate:**
- 1.8 thick, with a 38 × 26 window. Floats along x only. 0.25 clearance to the floor, the
  lid and the side walls (F1).
- Prints flat with the face that presses the film on the bed (F7).
- Sits `CHANNEL/2` behind the film plane.
- Four pads on its back face, 4 × 4, at z = ±22 and y = axis ± 15.5. Pad thickness is
  computed in the mockup (`padT`).

**Not designed yet. Brainstorm these with the user before modelling:**
- Two **leaf springs** that pull the pressure plate back toward the light in slide mode.
  They should be printed flexures, probably in PETG. They are what returns the plate to
  SLIDE: nothing else pulls it off the film.
- **Guides** that let the pressure plate move along x but stop it moving along y or z.
- **Grooves** that guide the wedge plate along z. Below the film the backer (F12) now carries the
  clamp's reaction in x with 0.05 play. Above the film nothing does: the upper ramps (y 56) push
  on a 2 thick plate held only by its tab, which has 0.5 play each side in the lid slot, more
  than the 0.47 stroke. The upper ramps need backing too, outside the light path: at the sides
  (|z| > 26, beside the wedge window) or a lid-side rail.
- **Lid retention.** Nothing holds the lid on yet.
- **Gate position along the tube.** Nothing locates the gate along the tube. The socket is a
  slip fit, so the film plane sits wherever the gate is pushed.
- **Light seal at the lid's front end.** The lid's 0.2 end clearance leaves a 0.2 × 86 slit
  from the top into the film chamber, on the light side of the film. Since F5 there is no
  lens-side chamber for it to open into, but it still lets room light onto the film's back.
  Tape, or a lip on the lid.

### 4 · Light dock (`parts/light_dock/`)

Holds the CS-Lite standing on its long edge, lit face toward the film, `GAP` (25) behind
the film plane.

- **Floor:** 4 thick, 181 wide. It runs along x from the front wall to 6 past the slot's back
  edge (69.7 at the default).
- **Front wall** (F11): 4 thick, full width, 62 tall, 0.2 in front of the gate front. A U 1 clear
  of the tube (a half circle below the axis, straight up above it) lets the tube through. The half
  circle goes on down through the floor under the wall (F17): at axis 40.5 it leaves a trough 3.5
  above the table, 1 under the tube. The gate
  front and the gate body are held between it and the CS-Lite, with 0.2 play. It covers the gate
  front's two lower screw heads: lift the gate out to reach them.
- **Lips:** front and back, 12 tall. Together they make a 20.5 wide slot for the light: its
  20 plus 0.5 clearance, all behind it, so the lit face stays at the front lip.
- **Side cheeks:** 62 tall.
- **Gate notch** (F10): 110.4 wide (the gate front's 110 plus `dock_gate_clear` 0.2 each side),
  through the floor and the front lip, from the front wall to the lit face. The whole gate
  stands on the table in it, between two floor arms that locate it in z, its rear face flush on
  the panel, which closes the rear window. What's left of the front lip holds the panel's ends.
  There's no shroud.
- **Bed size:** at 181 wide the dock is the largest footprint. The mockup says it fits a 220
  bed, but the 220 bed was my assumption. **Confirm the printer's bed size** (C4 in "Check before
  printing").

**Not designed yet:**
- Holding the CS-Lite against the front lip. The slot has 0.5 play behind it. With the front
  wall's 0.2, the gate's rear face can sit up to 0.2 off the lit face and leak light.

### 5 · Lock switch (`parts/lock_switch/`)

**Tab:** 2 (x) × 4 (z), up from the plate's top through the lid slot and 12.7 (½ inch,
`tab_reach`) out of the lid top. It is the grip: push it toward +z for LOCK, −z for SLIDE.
There's no knob (F15).

**Wedge plate:**
- 2 thick, 70 wide (z), and as tall as the gate interior (about 70).
- Window 52 × 26. Shifted ±5, it still clears the 38 wide frame window.
- Four ramps on its front face, one under each pressure-plate pad. Each is 12 long and goes
  from 0.8 thick at the −z end to 0.1 at the +z end.

**How it works:**
- Travel is ±5 along z. At SLIDE (tab at −z) each pad sits on the thin end of its ramp.
- At LOCK, the pressure plate moves forward by
  `min(rampT(−s) − rampT(SW_TRAVEL/2), CHANNEL − FILM_T)`.
- The ramp slope (about 1:17) should be self-locking. Still add a detent bump at each end
  of the slot. Not designed yet: a working detent needs a compliant member, and the tab is
  rigid with 0.5 play. The detents are what hold LOCK; the
  leaf springs are what return the plate to SLIDE.

**Assembly:** drop the wedge plate in, then lower the lid over it so the tab comes up through
the slot. Nothing to snap on.

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
├── viewer.py               writes exports/nlb-scan-rig.html (the assembly)
├── print_preview.py        writes exports/nlb-rig-print-preview.html (print direction per part, and the
│                           "Dimensions to confirm" checklist)
├── website.py              writes site-out/<slot>/: both pages for nlb.jrwiv.com, the STLs as files
├── publish.sh              build.py + website.py, then rsync to bunbun (nlb.jrwiv.com)
├── deploy/                 the site's compose.yaml and nginx.conf, as they run on bunbun
├── mockup/
│   ├── nlb-scan-rig.html   copy of the published mockup (source of the numbers)
│   ├── viewer.html         template for viewer.py: the assembled CAD in three.js
│   └── print-preview.html  template for print_preview.py: each part on the bed, layer by layer
├── parts/
│   ├── lens_adapter/       model.py (+ thread_coupon in the same file)
│   ├── tube/               model.py
│   ├── film_gate/          model.py: gate_front, gate_body, gate_lid, pressure_plate
│   ├── light_dock/         model.py: light_dock
│   └── lock_switch/        model.py: wedge_plate
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
- Every printed part fits the bed. 220 × 220 is assumed until the user confirms (C4).
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

- **"Dimensions to confirm" on the print preview (F16).** The user asked for it. The print preview has
  a second tab: seven drawings (side view, lens front, CS-Lite, its slot, bed, film path, gate screw),
  each measurement a dimension line labelled with its param and value, and the checklist from "Check
  before printing", C1–C12, ticked in the browser's localStorage. Each tick belongs to the values it
  confirmed: rebuild with another value and it clears. The values and the wording come from the built
  `Params` (`print_preview.checks`), so `print_preview.py` now takes `--wd` and `--axis` like
  `build.py`, and refuses STLs built at others (it reads the tube's height and the gate front's from
  the STLs). Each item's "Changes" list is checked by rebuilding with its params nudged
  (`tests/test_print_preview.py`). Keep this section and `print_preview.checks` in step.

- **The U goes through the dock's floor too (F17).** The user asked for it. At the measured axis
  40.5 the bottom of the front wall's U (axis − 37, so 3.5) was below the floor's top (4): the floor
  filled the U's bottom and came 0.5 under the tube, against the 1 intended. Below axis 40 the tube
  ran into it (at 39, 45 mm³; `build.py` failed), though `Params` allows 39, and the tests only
  checked the solid there. The U's round is now cut from the whole dock across the front wall's
  depth, so the tube is 1 clear at every axis; above 41 the cut takes nothing. At 40.5 it removes a
  16 mm³ sliver and leaves 3.5 of floor under the tube; the trough opens upward, so it prints
  without support. `tests/test_light_dock.py` checks the clearance at axis 39, 40.5, 42.5 and 50.

## Mockup differences to republish

The CAD differs from the mockup on purpose here. The mockup's shapes haven't been changed (the local
copy's `wd` and `axis` sliders now start at the measured 111 and 40.5; the copy once published started
at 130 and 42.5): republishing it is the user's call.

| What | Mockup | CAD |
|---|---|---|
| Gate lid | full gate depth, over the front and rear walls (it overlaps the tube) | between the front and rear walls, 0.2 short of each |
| Gate floor | full gate depth, under the front and rear walls | between the front and rear walls |
| Pressure plate | 86 × 72.5, flat pads `padT` thick | 85.5 × 70 (0.25 clearance), pads sloped like the ramps |
| Tube | plain ring | baffle ribs inside |
| Film slots | centred on the film plane, x 252.5–257.5 | notches from the reference plane, x 235.7–238.9 |
| Gate | one box with a thin front plate and a chamber in front of it | gate front (solid, flared light passage) + gate body, M3 screws through side pillars, 110 wide |
| Lettering | on the lid | none |
| Knob | 10 × 12 on the tab, grip ridges | none: the tab sticks 12.7 out of the lid and is the grip |
| Shroud | part of the dock | none: the gate body (39 deep) stands in a notch in the dock, flush on the lit face |
| CS-Lite slot | 20, dock 35 long | 20.5; the dock runs forward under the gate to a front wall, 69.7 long |
| `axis` | slider 30–60 | 39 at least |

## Check before printing

Nothing has been printed yet. These are the sizes that come from outside the CAD (the camera and its
base, the lens, the CS-Lite, the film, the screws and the printer) and that the prints depend on.
Each is a param in `params.py`; the numbers below are at the defaults. The print preview's
**Dimensions to confirm** tab draws them, dimensioned from the build, with this list as a checklist,
numbered the same (F16). "Changes" lists the printed solids whose shape changes with the value;
`tests/test_print_preview.py` rebuilds to prove each list. Most important first.

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
  - **Changes:** gate front, gate body, pressure plate, wedge plate, light dock.
    Fix: `build.py --axis A`, then `print_preview.py --axis A`.
- **C2 · `wd` 111 (measured 2026-11-09; was the guess 130): lens front to film plane, at 1:1.** With a ruler.
  - **Measure:** from the lens's front rim (the filter-thread face, where the adapter's flange seats)
    to the film's surface. Focus ring at 1:1, the camera on its base, a negative or a ruler lying on
    the CS-Lite; move the camera until it's sharp and 36 mm of ruler fills the frame's width. Measure
    three times. Check whether the front of the lens moves when you focus; if it does, measure with
    the ring at 1:1.
  - **If it's off:** the tube is `wd − 13` (98) long and nothing else adjusts along the axis: its ends
    sit on the socket floors. A few mm off, the focus lands a little off 1:1, so the frame is cropped or
    shows its borders. Further off, the lens can't focus on the film.
  - **Changes:** the tube only, but it's the tallest print. Fix: `build.py --wd W`, then
    `print_preview.py --wd W`.
- **C3 · CS-Lite: `csl_l` × `csl_h` × `csl_t` 165 × 112 × 20, lit area `csl_lit_w` × `csl_lit_h`
  149 × 95 (datasheet).** With calipers and a straightedge.
  - **Measure:** length, height, and the thickness at its thickest point, feet and buttons included.
    A straightedge across the lit face: the gate body's rear face (110 wide, from the table to 76.5)
    lies on it from the panel's bottom edge, across the bezel, so the face must be flat edge to edge.
    Where the lit area sits: the build assumes it's centred, its bottom 12.5 above the table, and the
    gate's rear window is 23.5 to 57.5. Where the USB-C port and the button are: the cheeks cover the
    panel's ends up to 62.
  - **If it's off:** thicker than the 20.5 slot or longer than the 166 between the cheeks, it doesn't
    go in. Thinner, or a face that isn't flat, and the gate's rear face sits off it and leaks (see the
    light dock's "Not designed yet"). A port at an end is blocked by a cheek. A lit area that doesn't
    cover the rear window vignettes.
  - **Changes:** the light dock (`csl_l`, `csl_t`). The height and the lit area change nothing printed.
- **C4 · Printer: bed `bed_x` × `bed_y` 220 × 220 and build height (assumed).** From the spec sheet.
  - **Measure:** the usable print area and height, not the plate's size, less any brim or skirt. Load
    `light_dock.stl` in the slicer: it's the biggest footprint, 69.7 × 181. The tallest print is the
    tube, 98 upright; with no height given, `tube_max_len` borrows the bed's 220.
  - **If it's off:** no shape changes, but a dock that doesn't fit doesn't print. `build.py` checks
    square-on only (39 margin at 220); turned 45° the dock fits a 177 square bed. Past `wd` ≈ 200 the
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
- **C7 · Tube in its sockets: `fit_clear` 0.3 (Ø72 tube, Ø72.6 sockets). Before the tube.** A test
  print. Holes print small and outer walls a little big. Print the adapter, cut the tube to a 10 mm
  ring in the slicer and try it in the socket: it should slide in by hand without rattling. Tight and
  it won't go in or cracks the socket; loose and the gate and lens aren't on one axis, and light gets
  in at the joint. **Changes:** adapter, gate front.
- **C8 · Film slots: `film_w` 35, `film_slot_clear` 0.2 (slot 35.2, F13). Before the gate body.**
  Calipers across a strip of your film. There's no slot coupon: model a 35.2 × 3.2 slot in a small
  block in the slicer, print it on its end like the gate body, and slide the strip through. FDM prints
  slots narrow, so the strip drags; too wide and it wanders in the window. **Changes:** gate body.
- **C9 · Film thickness and the first layer: `film_t` 0.13 in the 0.6 `channel`. Before the gate front
  and the pressure plate.** Calipers or a micrometer on a strip, in a few places. Film thicker or
  thinner moves the clamp's preload (0.113) by as much, not the plastic: tune `ramp_rise` after a
  print, and don't change `channel`. Both faces of the channel are first layers: level the bed, keep
  it clean, and turn off or compensate elephant's foot, which puts a lip round the frame window.
  **Changes:** nothing; it matters to the gate front, the pressure plate and the wedge plate.
- **C10 · Gate joint screws: four M3 × 20, `pilot_d` 2.5, `pilot_depth` 12, counterbores `cbore_d` 6.5
  × `cbore_depth` 3.5, `joint_hole_d` 3.4. Before the gate front and body.** Calipers on the screws you
  have: a head no wider than 6.5 and no taller than 3.5 (socket and button heads fit). The shank runs
  10.2 through the gate front, so M3 × 20 bites 9.8; anything longer than 22.2 bottoms out in the
  pilot and won't pull the halves together. Decide: self-tap into Ø2.5, or heat-set inserts (`pilot_d`
  4.0: check the insert's hole size, and that it's under 12 long). **Changes:** gate front, gate body.
- **C11 · Drop-in and sliding fits: `plate_clear` 0.25, `lid_clear` 0.2, `tab_clear` 0.5,
  `wedge_clear` 0.5, `dock_gate_clear` 0.2, `csl_clear` 0.5 (F1). Before the gate body, lid, plates
  and dock.** A test print: a calibration cube, measured with calipers. If the printer prints outer
  sizes big or holes small by more than about 0.1, these bind. After the gate body prints, drop the
  plates in before printing the dock. **Changes:** pressure plate, gate lid, wedge plate, light dock.

### Worth measuring, but no print depends on it

- **C12 · Lens barrel: `lens_len` 125, `lens_r` 37 (guesses).** Calipers: mount flange to front rim,
  and the barrel's diameter. Nothing printed changes: the lens is reference geometry (R14), and x is
  measured from its front. **Changes:** nothing.

After printing, tune `ramp_rise` and `wedge_back_clear` against the parts ("Tuning and print notes").

## Tuning and print notes

- **`ramp_rise`** works only from about 0.6 to 0.8 (0.7 gives the 0.113 preload). Below about
  0.56 the ramps run out before the plate reaches the film. `build.py` then fails with
  "pressure_plate and wedge_plate should overlap … and do not touch" at LOCK, and FAIL on
  "film / pressure plate, LOCK". Above 0.8 the ramps' thick ends are thicker than `wedge_gap`
  (0.9) and hit the pressure plate's body: "pressure_plate and wedge_plate intersect" at
  SLIDE. At 0.57 the preload is only 0.005.
- **`thread_clear`** builds valid solids from 0.05 to 0.3. Print the coupon to choose.
- **Supports:** only the adapter's socket ledge (a 5.3 wide annular overhang in the thread-up
  pose).
- **First layer:** the gate front's and the pressure plate's first layers are the film's
  surfaces. Level the bed, keep the plate clean, and turn off or compensate elephant's foot,
  which would put a lip on the frame window's edge.
- **Pads and ramps:** both print as top layers, stepped (F7, F9). Use 0.12 layers or finer,
  and ironing.
- **Gate screws:** four M3 × 20, socket or button head, from the front. They self-tap into the
  Ø2.5 pilots, so don't overtighten. For repeated assembly, use M3 heat-set inserts and
  `pilot_d` 4.0.
- **Wedge window:** 26 tall, the same as the frame window, so there's no y margin. The ramps
  cap it at ±13.5 from the axis.
- **Lettering font:** if Arial is missing, CadQuery silently uses another font. It's fine on
  this Mac.
- **Stale exports:** an invalid solid isn't exported, so the previous STEP/STL stays in
  `exports/`.

## Questions for the user

- **Measurements:** `wd` and `axis` are measured (C1, C2). The CS-Lite, the printer's bed and height,
  the thread and the rest: see "Check before printing" (C3–C12).
- **Camera:** A7 or A7 IV? No part depends on it; with its base, it decides `axis` (C1).
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
  gate/dock joint). These are design decisions for the user.
- `superpowers:test-driven-development`: write the geometry checks before each `model.py`.
- `superpowers:verification-before-completion`: run `build.py` and the tests and quote the
  output before saying a part is done.
- `jta`: republish the mockup to the same URL whenever a dimension or mechanism changes.
