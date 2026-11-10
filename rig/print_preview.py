"""Write the print-direction preview: each printed solid on the bed, with a layer slider, and the whole assembly.

    uv run python build.py [--wd W] [--axis A]           # first: writes exports/stl/ in print pose
    uv run python print_preview.py [--wd W] [--axis A]   # the same values: it refuses STLs built at others

Writes exports/nlb-rig-print-preview.html, one self-contained page with the print-pose STLs from
exports/stl/ embedded, and the assembly: every printed solid in place at SLIDE (built here, meshed
more coarsely to keep the page small) with the references: the film strip with its perforations and its
exposures as meshes, the CS-Lite as a box; and the "Dimensions to confirm" tab: the values its drawings are
dimensioned from and the checklist (`checks`), both from the same Params. The page template is
mockup/print-preview.html. The notes per solid come from PLAN.md ("Tuning and print notes" and each
part's "Printing" line); the checklist from PLAN.md "Check before printing".
"""

import argparse
import base64
import datetime
import json
import math
import struct
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Sequence

import cadquery as cq

import assembly
import build
import cadutil
from params import Params

ROOT = Path(__file__).parent
TEMPLATE = ROOT / "mockup" / "print-preview.html"
OUT = build.EXPORTS / "nlb-rig-print-preview.html"
STL_DIR = build.EXPORTS / "stl"
MARK = "/*__PRINT_DATA__*/null"
ASM_LINEAR_TOL = 0.05         # coarser than the print STLs (0.01): the assembly is for looking at, and it halves the page
ASM_ANGULAR_TOL = 0.2
REF_GREY = "#9aa3a0"
FILM_GROUP, DOCK_GROUP = "3 · Film gate", "4 · Light dock"     # the picker lists each reference under these
REF_MESHES = (                  # name, label, colour, opacity: the film's base is clear orange, its exposures dark
    ("film", "Film strip (perforated)", "#b39466", 0.55),
    ("film_frames", "Exposures, 36 × 24", "#2b2622", 0.85),
)

# name: (number, label, group, default layer, description, notes); which way up comes from the models' PRINT_UP
SOLIDS = {
    "thread_coupon": (
        "1a", "Thread coupon", "1 · Lens adapter", 0.12,
        "The adapter's M67 × 0.75 thread on a 2 thick Ø78/Ø62 ring. Print it before the adapter.",
        [
            "Print first: the thread is the riskiest geometry in the rig. At 0.75 pitch, FDM is marginal.",
            "Thread up, axis vertical, at 0.12–0.16 layers.",
            "<code>thread_clear</code> builds from 0.05 to 0.3 (0.15 now). Print the coupon to choose it.",
        ],
    ),
    "adapter": (
        "1", "Lens adapter", "1 · Lens adapter", 0.12,
        "Screws into the Laowa's 67 mm filter thread; the tube slides into its socket.",
        [
            "Flat, thread axis vertical, thread up, at 0.12–0.16 layers.",
            "Support the socket ledge: a 5.3 wide annular overhang in this pose.",
            "Check the coupon's fit first.",
        ],
    ),
    "tube": (
        "2", "Tube", "2 · Tube", 0.2,
        "Ø72 / Ø64, <code>wd − 13</code> long, with sawtooth baffle ribs inside.",
        [
            "Upright. The baffles' lower flanks are 45°, so no supports.",
        ],
    ),
    "gate_front": (
        "3", "Gate front", "3 · Film gate", 0.2,
        "Solid block: tube socket, a light passage flaring down to the 38 × 26 frame window, and the film "
        "reference plane.",
        [
            "<b>Film face on the bed.</b> The rear face, which the film lies on, is the first layer: as flat and "
            "smooth as the bed. Keep the first layer clean (no elephant's foot) around the window.",
            "No supports. The passage and the socket only widen going up.",
            "Four M3 × 20 screws, heads in the counterbores, self-tap into the body's pillars (or use heat-set inserts: "
            "set <code>pilot_d</code> 4.0).",
        ],
    ),
    "gate_body": (
        "3b", "Gate body", "3 · Film gate", 0.2,
        "Floor, side walls and rear wall, with four screw pillars outside the walls, and a backer below the film that "
        "the wedge plate is wedged against at LOCK. Joins to the gate front's rear face.",
        [
            "Rear wall on the bed. Walls, pillars and the film notches all rise straight up: no bridges, no supports.",
            "The film slots are notches open at the top of the print; the gate front closes them, so the film's "
            "front face only ever touches the bed-printed reference plane.",
        ],
    ),
    "gate_lid": (
        "3c", "Gate lid", "3 · Film gate", 0.2,
        "Drops in between the gate front and the rear wall, on the side walls, with the switch tab's slot.",
        [
            "Flat, top up.",
        ],
    ),
    "pressure_plate": (
        "3d", "Pressure plate", "3 · Film gate", 0.12,
        "Floats along the optical axis; its four sloped pads ride the wedge plate's ramps.",
        [
            "<b>Film face on the bed.</b> The face that presses the film is the first layer. No bridge over the window.",
            "The pads' 1:17 slopes are now the top layers, so they print stepped. Use 0.12 or finer layers and ironing "
            "on top surfaces; tune <code>ramp_rise</code> if the clamp is off.",
        ],
    ),
    "wedge_plate": (
        "5", "Wedge plate", "5 · Lock switch", 0.12,
        "Slides ±5 along z; four ramps push the pressure plate onto the film at LOCK. Its tab sticks 12.7 (½ in) "
        "out of the lid: push it toward LOCK or SLIDE (no knob).",
        [
            "Flat, back face on the bed, ramps up (F9). No bridges, no supports, no brim needed.",
            "The tab is 2 × 4: print it solid (100% infill there) so it doesn't snap when you push it.",
            "The ramps' 1:17 slopes are now the top layers, so they print stepped, like the pressure plate's pads. "
            "Use 0.12 or finer layers and ironing; tune <code>ramp_rise</code> against the print.",
        ],
    ),
    "light_dock": (
        "4", "Light dock", "4 · Light dock", 0.2,
        "Holds the CS-Lite on its long edge, 25 behind the film. The gate stands in a notch between a front wall "
        "(a U around the tube) and the lit face, which hold the gate front and body together.",
        [
            "Floor down. No bridges.",
            "At 181 wide it's the largest part: confirm the bed size.",
        ],
    ),
}
ORDER = [
    "thread_coupon", "adapter", "tube", "gate_front", "gate_body", "gate_lid", "pressure_plate", "light_dock",
    "wedge_plate",
]

# ---- "Dimensions to confirm": the page's checklist, PLAN.md "Check before printing" item for item ----
SCREW_LEN = 20                  # the gate joint's four M3 x 20 (PLAN.md "Gate screws"); not a Params field: no part uses it
FIG_PARAMS = (                  # the values the page's drawings are dimensioned from
    "wd", "axis", "axis_min", "lens_len", "lens_r", "thread_major", "thread_pitch", "thread_len", "thread_clear",
    "thread_crest_r", "thread_root_r", "adapter_r", "adapter_bore_r", "flange", "socket_depth", "tube_ro", "tube_ri",
    "tube_len", "tube_max_len", "tube_x0", "tube_x1", "fit_r", "fit_clear", "x_front", "x_film", "x_gate", "x_ref",
    "x_light", "gap", "gh", "gw", "gate_front_w", "gate_d", "wall", "front_wall", "csl_l", "csl_h", "csl_t",
    "csl_lit_w", "csl_lit_h", "csl_slot", "csl_clear", "floor_t", "lip_h", "lip_t", "cheek_top", "cheek_clear",
    "dock_w", "dock_x0", "dock_x1", "dock_gate_clear", "rear_win_w", "rear_win_h", "film_w", "film_t", "film_slot_h",
    "film_slot_y0", "film_slot_clear", "film_slot_w", "channel", "plate_t", "joint_hole_d", "cbore_d", "cbore_depth",
    "pilot_d", "pilot_depth", "ear_w", "ear_h", "bed_x", "bed_y", "preload", "lock_shift",
)
CHECK_GROUPS = (
    ("first", "Before printing anything",
     "One session at the bench with the camera on its base, the lens, the CS-Lite and the printer's spec sheet. "
     "These set most of the plastic, or decide whether it prints at all."),
    ("part", "Before a particular part",
     "Each matters to one or two parts. Check it before slicing those."),
    ("ref", "Worth measuring, but no print depends on it",
     "Only the drawings use these."),
)


def _n(v: float) -> str:
    return f"{round(v, 3):g}"


def _code(*names: str) -> str:
    return " ".join(f"<code>{name}</code>" for name in names)


def checks(p: Params, sizes: dict[str, list[float]]) -> dict:
    """The page's "Dimensions to confirm" tab: the values its drawings use, and the checklist, worded at `p`.

    `sizes` is each printed solid's print-pose size (x, y, z on the bed). Each item's `parts` are the solids whose
    geometry changes with the params to measure (tests/test_print_preview.py rebuilds to prove it), not counting those
    tagged "derived" or "fixed" (shown for context); `watch` the ones it matters to without changing their shape.
    """
    n = _n
    dock_x, dock_y, _ = sizes["light_dock"]
    tall = max(sizes, key=lambda name: sizes[name][2])
    diag = (dock_x + dock_y) / 2 ** 0.5             # the square bed the dock fits on turned 45°
    lens_off = p.wd - p.tube_len                    # tube length is wd less this
    through = p.x_ref - p.x_gate - p.cbore_depth    # screw shank in the gate front, under the head
    lit_y0 = p.floor_t + (p.csl_h - p.csl_lit_h) / 2
    win_y0, win_y1 = p.axis - p.rear_win_h / 2, p.axis + p.rear_win_h / 2

    def param(name: str, tag: str = "", note: str = "") -> dict:
        return {"name": name, "value": round(getattr(p, name), 4), "tag": tag, "note": note}

    items = [
        {
            "id": "axis", "group": "first", "title": "Lens axis height", "method": "ruler",
            "params": [param("axis", "measured")],
            "what": "Table to the centre of the lens, with the camera on the base it will scan from.",
            "how": "Camera and lens on their base on the table. Measure from the table to the underside and to the top of "
                   "the lens's front rim (a steel rule standing on the table, or the calipers' depth rod), and average. "
                   f"Or table to the rim's underside plus {n(p.thread_major / 2)}. If the base adjusts (rail, shims, a head), "
                   f"this is a choice instead: any axis from {n(p.axis_min)} up, and set the base to it. The base and the body "
                   "(A7 or A7 IV) are what decide it.",
            "wrong": "The tube joins the lens to the gate rigidly, so a wrong axis tilts the camera or lifts the gate and dock "
                     "off the table: the film isn't square to the sensor, and the gate's rear face lifts off the CS-Lite and "
                     f"leaks. Below {n(p.axis_min)} the Ø{n(2 * p.adapter_r)} adapter hits the table (build.py refuses it).",
            "parts": ["gate_front", "gate_body", "pressure_plate", "wedge_plate", "light_dock"],
            "fix": "uv run python build.py --axis A, then print_preview.py --axis A",
            "figs": ["side", "cslite"],
        },
        {
            "id": "wd", "group": "first", "title": "Working distance at 1:1", "method": "ruler",
            "params": [param("wd", "measured"), param("tube_len", "derived", f"wd − {n(p.wd - p.tube_len)}")],
            "what": "The lens's front rim (the filter-thread face, where the adapter's flange seats) to the film's surface, "
                    "focused at the magnification you'll scan at (1:1).",
            "how": "Set the focus ring to 1:1, camera on its base. Lay a negative (or a ruler) flat on the CS-Lite and move "
                   "the camera until it's sharp and 36 mm of ruler fills the frame's width. Measure rim to film with a ruler "
                   "or the calipers' depth rod; do it three times. Also check whether the front of the lens moves when you "
                   "focus: if it does, measure with the ring at 1:1.",
            "wrong": f"The tube is wd − {n(lens_off)} = {n(p.tube_len)} long and nothing else adjusts along the axis (the "
                     "tube's ends sit on the socket floors). A few mm off and you focus at a little more or less than 1:1, "
                     "so the frame is cropped or shows its borders; further off, the lens can't focus on the film at all.",
            "parts": ["tube"],
            "fix": "uv run python build.py --wd W, then print_preview.py --wd W",
            "figs": ["side", "lens"],
        },
        {
            "id": "cslite", "group": "first", "title": "CS-Lite body, face and lit area", "method": "calipers",
            "params": [param("csl_l"), param("csl_h"), param("csl_t"), param("csl_lit_w"), param("csl_lit_h")],
            "what": f"The panel stands on a long edge in the dock, between cheeks {n(p.csl_l + 2 * p.cheek_clear)} apart, in a "
                    f"{n(p.csl_slot)} slot, its lit face flat on the gate body's rear face, which covers it from the table up "
                    f"to {n(p.gh)} and {n(p.gate_front_w)} across.",
            "how": f"Calipers: length and height, and the thickness at the thickest point, feet and buttons included. With a "
                   "straightedge across the lit face, check it's flat edge to edge: a raised rim or a recessed diffuser leaves "
                   f"a gap at the gate. Measure the lit area and how far it sits from each edge (the page assumes it's centred: "
                   f"its bottom at {n(lit_y0)} above the table, the gate's rear window {n(win_y0)} to {n(win_y1)}). Note where "
                   f"the USB-C port and the button are: the cheeks cover the ends up to {n(p.cheek_top)}.",
            "wrong": f"Thicker than {n(p.csl_slot)} or longer than {n(p.csl_l + 2 * p.cheek_clear)} and it won't go in. Thinner, "
                     "or a face that isn't flat, and the gate's rear face sits off the light and leaks. A port at an end is "
                     "blocked by a cheek. A lit area that doesn't cover the rear window vignettes the frame.",
            "parts": ["light_dock"],
            "fix": f"edit {_code('csl_l', 'csl_t')} (and the lit area) in params.py",
            "figs": ["cslite", "slot"],
        },
        {
            "id": "bed", "group": "first", "title": "Printer bed and build height", "method": "spec",
            "params": [
                param("bed_x", "assumed"), param("bed_y", "assumed"),
                param("tube_max_len", "derived", "build height: assumed the bed's smaller side"),
            ],
            "what": "The printer's usable print area and height: not the plate's size, and less any brim or skirt.",
            "how": f"From the printer's spec sheet, then load light_dock.stl in the slicer: it's the biggest footprint at "
                   f"{n(dock_x)} × {n(dock_y)}. The tallest is the {SOLIDS[tall][1].lower()}, "
                   f"{n(sizes[tall][2])} high on the bed.",
            "wrong": f"No geometry changes, but a dock that doesn't fit doesn't print: build.py checks it square-on (margin "
                     f"{n(p.bed_y - dock_y)} at {n(p.bed_x)} × {n(p.bed_y)}). Turned 45° it fits a {diag:.0f} square bed. "
                     f"No height is given, so the tube's limit borrows the bed's {n(p.tube_max_len)}.",
            "parts": [], "watch": ["light_dock", "tube"],
            "fix": f"edit {_code('bed_x', 'bed_y')} in params.py",
            "figs": ["bed"],
        },
        {
            "id": "thread", "group": "first", "title": "Filter thread fit: print the coupon", "method": "coupon",
            "params": [param("thread_major"), param("thread_pitch"), param("thread_clear")],
            "what": f"The adapter's male M{n(p.thread_major)} × {n(p.thread_pitch)} thread, moved in {n(p.thread_clear)} "
                    "radially for FDM, against the lens's filter thread.",
            "how": "Confirm the lens takes 67 mm filters. Print thread_coupon.stl first (thread up, 0.12–0.16 layers) and "
                   "screw it in by hand: it should turn smoothly and seat its ring flat on the lens's rim, without wobble. "
                   "Never force it.",
            "wrong": "Too tight and it cross-threads or strips the lens's filter thread. Too loose and the adapter sits "
                     "crooked, so the tube points off-axis and the film tilts. Tight: raise thread_clear by 0.05; loose: "
                     "lower it. It builds from 0.05 to 0.3.",
            "parts": ["adapter", "thread_coupon"],
            "fix": f"edit {_code('thread_clear')} in params.py",
            "figs": ["lens"],
        },
        {
            "id": "thread_depth", "group": "part", "when": "adapter", "title": "Filter thread depth and front element",
            "method": "calipers",
            "params": [param("thread_len"), param("adapter_bore_r", note=f"Ø{n(2 * p.adapter_bore_r)} bore")],
            "what": f"How deep the lens's filter thread runs before a step or the glass, against the adapter's {n(p.thread_len)} "
                    f"of thread; and what's inside it, against the adapter's Ø{n(2 * p.adapter_bore_r)} bore.",
            "how": "Calipers' depth rod from the rim to where the thread stops; inside jaws across the retaining ring or "
                   "whatever stands proud inside the thread. The coupon tells too: its ring should seat on the rim.",
            "wrong": f"A thread shallower than {n(p.thread_len)} and the adapter bottoms out before its flange seats: crooked, "
                     "or pressing on the front element's ring. A bore smaller than the glass's opening vignettes.",
            "parts": ["adapter", "thread_coupon"],
            "fix": f"edit {_code('thread_len', 'adapter_bore_r')} in params.py",
            "figs": ["lens"],
        },
        {
            "id": "tube_fit", "group": "part", "when": "tube", "title": "Tube in its sockets", "method": "test print",
            "params": [param("fit_clear"), param("fit_r", "derived", f"Ø{n(2 * p.fit_r)} socket")],
            "what": f"The Ø{n(2 * p.tube_ro)} tube slides into Ø{n(2 * p.fit_r)} sockets in the adapter and the gate front: "
                    f"{n(p.fit_clear)} radial. The printer decides the real fit: holes print small, outer walls a little big.",
            "how": f"Print the adapter, then cut the tube to a 10 mm ring in the slicer and try it in the socket. It should "
                   f"slide in by hand with no rattle. Or calipers on the printed socket: Ø{n(2 * p.fit_r)} wanted.",
            "wrong": "Tight and the tube won't go in or cracks the socket. Loose and the gate and the lens aren't on one "
                     "axis, and room light gets in at the joint.",
            "parts": ["adapter", "gate_front"],
            "fix": f"edit {_code('fit_clear')} in params.py, or the slicer's hole compensation",
            "figs": ["lens"],
        },
        {
            "id": "film_slot", "group": "part", "when": "gate body", "title": "Film slots in the gate body",
            "method": "test print",
            "params": [
                param("film_w"), param("film_slot_clear"), param("film_slot_h", "derived", "film_w + film_slot_clear"),
            ],
            "what": f"The strip runs through a {n(p.film_slot_h)} slot in each side wall: it rests on the slot's floor, "
                    f"with {n(p.film_slot_clear)} over its top edge.",
            "how": f"Calipers across a strip of your film ({n(p.film_w)} nominal). There's no slot coupon: model a "
                   f"{n(p.film_slot_h)} × {n(p.film_slot_w)} slot in a small block in the slicer, print it on its end like "
                   "the gate body, and slide the strip through.",
            "wrong": "FDM prints slots narrow: the strip drags or jams. Too wide and it wanders up and down in the window.",
            "parts": ["gate_body"],
            "fix": f"edit {_code('film_slot_clear')} in params.py",
            "figs": ["film"],
        },
        {
            "id": "channel", "group": "part", "when": "gate front, pressure plate", "title": "Film thickness and the first layer",
            "method": "calipers",
            "params": [
                param("film_t"), param("channel", "fixed", "don't change it"),
                param("preload", "derived", "the clamp, at LOCK"),
            ],
            "what": f"The film slides in a {n(p.channel)} channel between the gate front's rear face and the pressure plate, "
                    f"{n(p.channel - p.film_t)} free at SLIDE. Both faces are first layers.",
            "how": "Calipers or a micrometer on a strip, in a few places. In the slicer, turn off or compensate elephant's "
                   "foot, level the bed, and keep the plate clean: those faces are the film's surfaces.",
            "wrong": f"Film thicker or thinner changes the clamp's preload ({n(p.preload)} at {n(p.film_t)}) by as much, not "
                     "the plastic: tune ramp_rise after a print. Elephant's foot puts a lip round the frame window that "
                     "scratches the film or closes the channel.",
            "parts": [], "watch": ["gate_front", "pressure_plate", "wedge_plate"],
            "fix": f"tune {_code('ramp_rise')} after a print; don't change {_code('channel')}",
            "figs": ["film"],
        },
        {
            "id": "screws", "group": "part", "when": "gate front, gate body", "title": "Gate joint screws",
            "method": "calipers",
            "params": [
                param("pilot_d"), param("pilot_depth"), param("cbore_d"), param("cbore_depth"), param("joint_hole_d"),
            ],
            "what": f"Four M3 × {SCREW_LEN} through the gate front into the body's pillars: heads in Ø{n(p.cbore_d)} × "
                    f"{n(p.cbore_depth)} counterbores, {n(through)} of shank in the gate front, then a Ø{n(p.pilot_d)} pilot "
                    f"{n(p.pilot_depth)} deep.",
            "how": f"Calipers on the screws you have: head no wider than Ø{n(p.cbore_d)} and no taller than "
                   f"{n(p.cbore_depth)} (socket and button heads fit), length {n(through + 6)} to "
                   f"{n(through + p.pilot_depth)}. Decide: self-tap into the Ø{n(p.pilot_d)} pilot, or heat-set inserts "
                   f"(pilot_d 4.0; check the insert's hole size and that it's under {n(p.pilot_depth)} long).",
            "wrong": f"M3 × {SCREW_LEN} bites {n(SCREW_LEN - through)}. Longer than {n(through + p.pilot_depth)} bottoms out "
                     "in the pilot and won't pull the halves together; much shorter strips out. A big head stands proud and "
                     "hits the dock's front wall.",
            "parts": ["gate_front", "gate_body"],
            "fix": f"edit {_code('pilot_d')} in params.py (4.0 for inserts)",
            "figs": ["screw"],
        },
        {
            "id": "fits", "group": "part", "when": "gate body, lid, plates, dock", "title": "Drop-in and sliding fits",
            "method": "test print",
            "params": [param("plate_clear"), param("lid_clear"), param("tab_clear"), param("wedge_clear"),
                       param("dock_gate_clear"), param("csl_clear")],
            "what": "The clearances that let parts drop in and slide: the pressure plate in the gate, the lid between its "
                    "walls, the tab in the lid slot, the wedge plate, the gate in the dock's notch, the CS-Lite in its slot.",
            "how": "Print a calibration cube and measure it with calipers: if the printer prints outer sizes big or holes "
                   "small by more than about 0.1, these will bind. After the gate body prints, drop the plates in before "
                   "printing the dock.",
            "wrong": "Tight and the plate binds instead of floating, the lid won't drop in, or the gate won't stand in the "
                     "dock. Loose and the plates rattle and light gets round the lid.",
            "parts": ["pressure_plate", "gate_lid", "wedge_plate", "light_dock"],
            "fix": "edit the clearance in params.py",
            "figs": [],
        },
        {
            "id": "lens", "group": "ref", "title": "Lens barrel", "method": "calipers",
            "params": [param("lens_len", "guess"), param("lens_r", "guess")],
            "what": "The Laowa's length, mount to front rim, and its barrel radius.",
            "how": "Calipers: the barrel's diameter, and mount flange to front rim.",
            "wrong": f"Nothing printed changes: the lens is reference geometry, and x is measured from its front. A barrel "
                     f"wider than Ø{n(2 * p.axis)} would reach the table.",
            "parts": [],
            "fix": f"edit {_code('lens_len', 'lens_r')} in params.py",
            "figs": ["side"],
        },
    ]
    for i, it in enumerate(items, 1):
        it["num"] = f"C{i}"                         # PLAN.md "Check before printing" numbers them the same
    return {
        "p": {name: (round(v, 4) if isinstance(v := getattr(p, name), float) else v) for name in FIG_PARAMS},
        "sizes": {name: [round(v, 2) for v in size] for name, size in sizes.items()},
        "screw_len": SCREW_LEN,
        "groups": [{"id": gid, "title": title, "blurb": blurb} for gid, title, blurb in CHECK_GROUPS],
        "items": items,
    }


def _commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "?"


def assembled(p: Params) -> dict:
    """The printed solids in place at SLIDE (mockup coordinates: y up, the table at y = 0), as STLs, in assembly order;
    then the references: the perforated film strip and its exposures (all frames in one mesh) as STLs, the CS-Lite
    as a box."""
    placed = assembly.placed(p, False)
    solids = []
    with tempfile.TemporaryDirectory() as tmp:
        for name in assembly.PRINTED:
            path = Path(tmp) / f"{name}.stl"
            if not cadutil.solid(placed[name]).exportStl(
                str(path), tolerance=ASM_LINEAR_TOL, angularTolerance=ASM_ANGULAR_TOL, relative=False
            ):
                raise RuntimeError(f"STL export of {name} failed")
            solids.append({"name": name, "stl": base64.b64encode(path.read_bytes()).decode()})
        frames = [wp for name, wp in placed.items() if name.startswith("film_frame_")]
        meshes = {
            "film": cadutil.solid(placed["film"]),
            "film_frames": cq.Compound.makeCompound([cadutil.solid(wp) for wp in frames]),
        }
        refs = []
        for name, label, colour, opacity in REF_MESHES:
            path = Path(tmp) / f"{name}.stl"
            if not meshes[name].exportStl(
                str(path), tolerance=ASM_LINEAR_TOL, angularTolerance=ASM_ANGULAR_TOL, relative=False
            ):
                raise RuntimeError(f"STL export of {name} failed")
            refs.append({"name": name, "label": label, "group": FILM_GROUP, "colour": colour, "opacity": opacity,
                         "stl": base64.b64encode(path.read_bytes()).decode()})
    refs.append({"name": "cs_lite", "label": "CS-Lite", "group": DOCK_GROUP, "colour": REF_GREY, "opacity": 0.35,
                 "box": [round(v, 4) for v in cadutil.bounds(placed["cs_lite"])]})
    return {"solids": solids, "refs": refs}


def stl_size(path: Path) -> list[float]:
    """The bounding box size (x, y, z) of a binary STL, as cadutil.export writes them."""
    raw = path.read_bytes()
    (count,) = struct.unpack_from("<I", raw, 80)
    lo, hi = [math.inf] * 3, [-math.inf] * 3
    for i in range(count):
        tri = struct.unpack_from("<12f", raw, 84 + 50 * i)
        for k in range(3):
            for j in range(3):
                v = tri[3 + 3 * k + j]
                lo[j], hi[j] = min(lo[j], v), max(hi[j], v)
    return [b - a for a, b in zip(lo, hi)]


def _check_built_at(p: Params, sizes: dict[str, list[float]]) -> None:
    """The STLs were built at p's wd and axis: the tube prints wd - 13 tall, the gate front stands axis + 36 on the bed."""
    for name, axis, want, what in (("tube", 2, p.tube_len, "wd"), ("gate_front", 1, p.gh, "axis")):
        got = sizes[name][axis]
        if abs(got - want) > 0.05:
            raise ValueError(
                f"exports/stl/{name}.stl is {got:.2f} where wd {p.wd:g}, axis {p.axis:g} make it {want:.2f}: "
                f"exports/stl was built with another {what}. Run build.py with the same --wd and --axis first."
            )


def data(p: Params, stl_dir: Path = STL_DIR) -> dict:
    ups = {name: up for model in build.discover().values() for name, up in model.PRINT_UP.items()}
    missing = set(ups) ^ set(ORDER)
    if missing:
        raise ValueError(f"print_preview.py and the models disagree on the solids: {sorted(missing)}")
    parts, sizes = [], {}
    for name in ORDER:
        num, label, group, layer, desc, notes = SOLIDS[name]
        up = ups[name]
        path = stl_dir / f"{name}.stl"
        if not path.exists():
            raise FileNotFoundError(f"{path} is missing: run build.py first")
        sizes[name] = stl_size(path)
        parts.append({
            "name": name, "num": num, "label": label, "group": group, "up": up, "layer": layer,
            "desc": desc, "notes": notes, "stl": base64.b64encode(path.read_bytes()).decode(),
        })
    _check_built_at(p, sizes)
    stamp = datetime.date.today().isoformat()
    return {
        "bed": [p.bed_x, p.bed_y],
        "parts": parts,
        "assembly": assembled(p),
        "check": checks(p, sizes),
        "built": f"wd {p.wd:g} · axis {p.axis:g} · {_commit()} · {stamp}",
        "foot": (
            f"Print-pose STLs from <code>rig/exports/stl/</code>, built by <code>build.py</code> at "
            f"wd {p.wd:g}, axis {p.axis:g}. The {p.bed_x:g} × {p.bed_y:g} bed is assumed until the printer "
            "is confirmed. Overhangs are faces pointing down more steeply than 45°, off the bed."
        ),
    }


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--wd", type=float, help="lens front to film, mm (default: params.py); as given to build.py")
    ap.add_argument("--axis", type=float, help="table to lens centre, mm (default: params.py); as given to build.py")
    args = ap.parse_args(argv)
    page = TEMPLATE.read_text()
    if MARK not in page:
        print(f"{TEMPLATE} has no {MARK} to fill in", file=sys.stderr)
        return 1
    try:
        p = Params(**{k: v for k, v in (("wd", args.wd), ("axis", args.axis)) if v is not None})
        d = data(p)
    except (ValueError, FileNotFoundError) as err:
        print(f"{ap.prog}: {err}", file=sys.stderr)
        return 2
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(page.replace(MARK, json.dumps(d, separators=(",", ":"))))
    print(f"wd={p.wd:g}  axis={p.axis:g}  {len(d['parts'])} solids  {len(d['check']['items'])} checks  "
          f"{OUT.stat().st_size / 1e6:.1f} MB  -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
