"""Write the print-direction preview: each printed solid on the bed, with a layer slider, and the whole assembly.

    uv run python build.py [--wd W] [--axis A]           # first: writes exports/stl/ in print pose
    uv run python print_preview.py [--wd W] [--axis A]   # the same values: it refuses STLs built at others

Writes exports/nlb-rig-print-preview.html, one self-contained page with the print-pose STLs from
exports/stl/ embedded, and the assembly: every printed solid in place at SLIDE (built here, meshed
more coarsely to keep the page small) with the references: the film strip with its perforations and its
exposures as meshes, the CS-Lite as a box; and the "Latest feedback" tab: the last design review's findings
(`feedback`), each with a drawing the template makes from the same Params. The page template is
mockup/print-preview.html. The notes per solid come from PLAN.md ("Tuning and print notes" and each
part's "Printing" line); the findings are PLAN.md "Latest feedback".
"""

import argparse
import base64
import dataclasses
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
FILM_GROUP, DOCK_GROUP = "2 · Film gate", "3 · Light dock"     # the picker lists each reference under these
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
            "Support the socket ledge: a 3.3 wide annular overhang in this pose.",
            "Check the coupon's fit first.",
        ],
    ),
    "tube": (
        "1b", "Tube", "1 · Lens adapter", 0.2,
        "Ø68.5 / Ø64, <code>wd − 18</code> long, with sawtooth baffle ribs inside. A friction fit in the Ø68.6 sockets "
        "(F23), 9 deep at each end.",
        [
            "Upright. The baffles' lower flanks are 45°, so no supports.",
            "Ø68.5 in a Ø68.6 socket is 0.05 a side: tested with masking tape on the first print. If it won't go in, "
            "sand the tube's ends rather than the sockets.",
        ],
    ),
    "gate_front": (
        "2", "Gate front", FILM_GROUP, 0.2,
        "Solid block: a 9 deep tube socket (F24), a light passage flaring down to the 38 × 26 frame window, and the film "
        "reference plane.",
        [
            "<b>Film face on the bed.</b> The rear face, which the film lies on, is the first layer: as flat and "
            "smooth as the bed. Keep the first layer clean (no elephant's foot) around the window.",
            "No supports. The passage and the socket only widen going up.",
            "Four M3 × 20 screws, heads in the 13.5 deep counterbores, self-tap into the body's pillars (or use heat-set "
            "inserts: set <code>pilot_d</code> 4.0). The hex key goes down the counterbore to the head.",
        ],
    ),
    "gate_body": (
        "2b", "Gate body", FILM_GROUP, 0.2,
        "Floor, side walls and rear wall, with four screw pillars outside the walls; a sill up to the film's lower edge "
        "that the strip lies on and both plates stand on (F20), and a step on it, the backer, that the wedge plate is "
        "wedged against at LOCK; a rail on each upper pillar beside the lid, so the lid can't slide along z (F22). Joins "
        "to the gate front's rear face.",
        [
            "Rear wall on the bed. Walls, pillars and the film notches all rise straight up: no bridges, no supports.",
            "The film slots are notches open at the top of the print; the gate front closes them, so the film's "
            "front face only ever touches the bed-printed reference plane.",
            "Each slot is only 0.6 deep where it meets the inside of the gate (F21), the top 0.6 of the print. At "
            "0.12 layers that is 5 layers; at 0.2 the body's top and the slot's floor are each half a layer off, so it "
            "can print 0.4–0.8. Check a strip goes in edgewise.",
            "The backer's step has a 45° slope under it, so it prints without support.",
            "The lid's rails stand on the upper pillars the body's whole depth, so they rise straight from the bed too.",
        ],
    ),
    "gate_lid": (
        "2c", "Gate lid", FILM_GROUP, 0.2,
        "Drops in between the gate front and the rear wall and between the body's two rails, on the side walls, with "
        "the switch tab's slot. 0.2 to the rails each side: pushing the tab can't drag it along z (F22). The slot is the "
        "tab's own 2 thick, so the tab holds the lid along x (F25).",
        [
            "Flat, top up.",
            "The slot has no clearance round the tab (F25). Holes print small: if the tab binds, file the slot's long "
            "sides, or set <code>tab_clear</code> 0.05.",
        ],
    ),
    "pressure_plate": (
        "2d", "Pressure plate", FILM_GROUP, 0.12,
        "Floats along the optical axis; its four sloped pads ride the wedge plate's ramps.",
        [
            "<b>Film face on the bed.</b> The face that presses the film is the first layer. No bridge over the window.",
            "The 0.6 lead-ins at the ends of that face (F21) rise from the bed at 45°: no supports.",
            "The pads' 1:17 slopes are now the top layers, so they print stepped. Use 0.12 or finer layers and ironing "
            "on top surfaces; tune <code>ramp_rise</code> if the clamp is off.",
        ],
    ),
    "wedge_plate": (
        "2e", "Wedge plate", FILM_GROUP, 0.12,
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
        "3", "Light dock", DOCK_GROUP, 0.2,
        "Holds the CS-Lite on its long edge, 25 behind the film. The gate stands in a notch between a front wall "
        "(a U around the tube) and the lit face, which hold the gate front and body together.",
        [
            "Floor down. No bridges.",
            "At 181 wide it's the largest part: confirm the bed size.",
        ],
    ),
}
ORDER = [
    "thread_coupon", "adapter", "tube", "gate_front", "gate_body", "gate_lid", "pressure_plate", "wedge_plate",
    "light_dock",
]

# ---- "Latest feedback": the design review of REVIEW["date"], finding for finding, each with a drawing on the page ----
REVIEW = {
    "date": "2026-11-11", "wd": 111, "axis": 40.5, "commit": "0e836e1",
    "verdict": "The CAD is geometrically sound: all nine solids are valid, single-body and watertight, and nothing found "
               "will certainly fail. The risks are in how it prints and handles.",
    "ran": "437 tests passed. build.py: 9 solids ok, no interference at SLIDE, only the designed pad / ramp overlap "
           "at LOCK, 24 fits ok.",
    "how": "Measured on the built solids with scripts independent of the repo's own tests. No slicer was used, so "
           "every print effect is inferred from the measured geometry.",
}
SEVERITIES = (
    ("fail", "Will fail", "A print or the assembly won't work."),
    ("trouble", "Likely trouble", "It may work as drawn; each is a real risk once it's plastic."),
    ("minor", "Minor", "Worth knowing. None of them stops a print."),
)
# Dimensions the review measured that have changed since (F20, F21): the findings and their drawings describe the design
# as it was reviewed, and each one that has changed says so in its status.
AS_REVIEWED = {"film_slot_w": 3.2}
# Defaults that were otherwise at the review's values and have changed since, after the first print (F23-F25): with
# these and the review's wd and axis, `reviewed()` rebuilds the design the review measured.
CHANGED_SINCE = {"gate_front": 14, "front_wall": 4, "tube_ro": 34, "fit_clear": 0.3, "tab_clear": 0.5, "cbore_depth": 3.5}
LAYERS = (0.12, 0.16, 0.2)      # the layer heights the page offers for the gate body
CLEAN = (                       # checked in the review, and fine
    "Printability: apart from the adapter's ledge, the thread's flanks and the tube's ribs, every layer of every "
    "part stands wholly on the one below. All parts fit a 220 bed; the dock has 39 of margin.",
    "Lens side: 0 of 1.92 M rays escape at SLIDE or LOCK with the tube seated and the lens closing the adapter.",
    "Optics: the film's centre and the tube's axis are both at the lens axis, the frame window is 38 × 26 and "
    "centred, and nothing stands in the cone from the 36 × 24 frame to a pupil as large as the Ø62 bore.",
    "Lock travel: no collision anywhere from s = −6 to +6. The pressure plate drops in with 0.60 to spare at SLIDE "
    "but only 0.017 at LOCK, so assemble at SLIDE.",
    "Assembly order: screw the gate front to the body, drop in the plates at SLIDE, the lid over the tab, the gate "
    "into the dock. The upper screw heads clear the dock's 62 wall.",
    "Parameters: wd 40–233 and axis 39–62 all build valid, with no interference.",
)
KNOWN = (                       # already in PLAN.md as unfinished: not new findings
    "LOCK can't clamp flat: the upper ramps' only backing is the tab in the lid's slot (no play there since F25), and "
    "the lid has 0.2 to the gate front and to the rear wall, against the 0.47 stroke.",
    "No leaf springs, pressure-plate guides, wedge z-grooves or detents.",
    "Nothing holds the lid down (since F22 its rails stop it along z). Since F23 the tube is a friction fit, so the gate "
    "stays where it is pushed, but nothing but its socket's floor locates it along the tube: push it home.",
    "The lid's front slit (0.2 × 86).",
    "The CS-Lite is not held forward (0.5 + 0.2 of play).",
    "The lower gate screws are hidden by the dock's front wall.",
    "Pads and ramps print stepped; elephant's foot on the film faces.",
    "No tube split past wd ≈ 200.",
    "C1–C12 in PLAN.md \"Check before printing\": bed, CS-Lite, thread depth, slot and sliding fits, A7 or A7 IV.",
)
UNCHECKED = (
    "Slicing: no slicer was run, so supports, bridging and thin walls are judged from geometry alone.",
    "Real hardware: the lens's thread depth, the CS-Lite's shape, the film's thickness, the printer's tolerances.",
    "Illumination clipping, which depends on an assumed lens pupil.",
    "Flex and tilt: the travel sweep was rigid-body, in 1 mm steps along z.",
    "The viewer and print-preview pages, the website, and STEP import into Onshape.",
)


def reviewed() -> Params:
    """The design as the review measured it: today's defaults at the review's wd and axis, less what has changed since."""
    return Params(wd=REVIEW["wd"], axis=REVIEW["axis"], **CHANGED_SINCE)


def _n(v: float) -> str:
    return f"{round(v, 3):g}"


def _code(*names: str) -> str:
    return " ".join(f"<code>{name}</code>" for name in names)


def fig_params(p: Params) -> dict:
    """Every field and derived property of `p`, for the page's drawings."""
    names = [f.name for f in dataclasses.fields(p)] + [k for k, v in vars(Params).items() if isinstance(v, property)]
    return {**AS_REVIEWED, **{name: (round(v, 4) if isinstance(v := getattr(p, name), float) else v) for name in names}}


def _to_layers(height: float, layer: float) -> list[float]:
    """`height` as it prints at `layer`: the nearest whole number of layers, or both when it is exactly half way."""
    k = round(height / layer, 6)
    whole = [math.floor(k), math.ceil(k)] if abs(k - math.floor(k) - 0.5) < 1e-6 else [math.floor(k + 0.5)]
    return [round(i * layer, 4) for i in whole]


def measures(p: Params) -> dict:
    """The numbers the findings turn on, from `p`. At the review's wd and axis they are the review's own
    (tests/test_print_preview.py checks each against what the review measured)."""
    half = p.sw_travel / 2
    backer_x0 = p.x_wedge + p.wedge_t + p.wedge_back_clear
    room = backer_x0 - p.x_ref
    stack = p.film_t + p.plate_t + p.pad_t + p.ramp_t(-half) + p.wedge_t
    stroke = p.channel - p.film_t
    body_h, backer_h = p.x_light - p.x_ref, p.x_light - backer_x0       # heights above the bed: the body prints -x up
    layers = []
    for layer in LAYERS:
        rooms = sorted({round(a - b, 4) for a in _to_layers(body_h, layer) for b in _to_layers(backer_h, layer)})
        layers.append({"layer": layer, "rooms": rooms, "squeeze": [round(stack - r, 4) for r in rooms]})
    tab_stop = half + p.slot_end - p.tab_w / 2
    wall_stop = p.gw / 2 - p.wall - p.wedge_w / 2

    def on_ramp(s: float) -> float:         # how much of a pad (along z) is still on its ramp with the switch at s
        return max(0.0, min(p.pad / 2, s + p.ramp_len / 2) - max(-p.pad / 2, s - p.ramp_len / 2))

    near = p.frame_pitch - p.frame_w / 2                                # a neighbouring frame's near edge, from the axis
    covered = min(p.frame_pitch + p.frame_w / 2, p.gate_front_w / 2) - near
    lit = p.csl_lit_w * p.csl_lit_h
    lit_y0 = p.floor_t + (p.csl_h - p.csl_lit_h) / 2
    lit_y1 = lit_y0 + p.csl_lit_h
    behind_gate = min(p.gw, p.csl_lit_w) * max(0.0, min(p.gh, lit_y1) - lit_y0)
    pillars = sum(                                                       # the screw pillars stand outside the body's walls
        p.ear_w * max(0.0, min(y + p.ear_h / 2, lit_y1) - max(y - p.ear_h / 2, lit_y0)) for y, _ in p.screw_points
    )
    past = lit - behind_gate - pillars
    shown = [z for z in p.perf_zs if abs(z) + p.perf_l / 2 <= p.win_w / 2]
    show = p.win_h / 2 - p.perf_inner
    slot_l, slot_w = 2 * (half + p.slot_end), p.tab_t + 2 * p.tab_clear
    film_slot_w = AS_REVIEWED["film_slot_w"]
    return {
        "notch_gap": p.x_light - (p.x_gate + p.gate_d), "pocket": p.gate_d + p.dock_gate_clear,
        "room": room, "stack": stack, "squeeze": stack - room, "body_h": body_h, "backer_h": backer_h,
        "squeeze_over": stack - room + p.ramp_t(-tab_stop) - p.ramp_t(-half),
        "reach": stroke * p.ramp_len / p.ramp_rise, "reach_play": (stroke + p.wedge_back_clear) * p.ramp_len / p.ramp_rise,
        "layers": layers,
        "tab_stop": tab_stop, "wall_stop": wall_stop,
        "on_ramp": {"lock": on_ramp(half), "tab": on_ramp(tab_stop), "wall": on_ramp(wall_stop),
                    "lid": on_ramp(tab_stop + p.lid_side_clear)},
        "covered": covered, "contact": covered * p.frame_h, "frame_area": p.frame_w * p.frame_h,
        "tilt": math.degrees(math.atan(p.film_slot_clear / p.wall)),
        "drop": (p.gw / 2 - p.wall + p.win_w / 2) * p.film_slot_clear / p.wall, "margin": (p.win_h - p.frame_h) / 2,
        "behind": film_slot_w - p.channel - p.plate_t, "plate_edge": p.gw / 2 - p.wall - p.plate_clear,
        "lit": lit, "past": past, "past_pct": 100 * past / lit, "side": (p.csl_lit_w - p.gw) / 2, "above": lit_y1 - p.gh,
        "tab_slot": slot_l * slot_w, "tab_open": slot_l * slot_w - p.tab_t * p.tab_w,
        "lid_slit_l": p.gw - 2 * p.wall, "lid_slit": p.lid_clear * (p.gw - 2 * p.wall),
        "settled": p.win_h / 2 - p.wedge_clear, "tab_proud": p.tab_reach - p.wedge_clear,
        "perf_show": show, "perf_count": 2 * len(shown), "perf_area": 2 * len(shown) * p.perf_l * show,
        "ledge": p.fit_r - p.adapter_bore_r, "ledge_area": math.pi * (p.fit_r ** 2 - p.adapter_bore_r ** 2),
        "u_bottom": p.axis - p.tube_ro - p.dock_tube_clear, "u_lowest": p.axis_min - p.tube_ro - p.dock_tube_clear,
        "film_face": p.x_ref, "film_off": p.x_film - p.x_ref, "rim_to_film": p.x_ref - p.x_front,
        "over_socket": p.gh - p.axis - p.fit_r, "cbore_wall": (p.ear_w - p.cbore_d) / 2,
        "tube_wall": p.tube_ro - p.tube_ri,
    }


def feedback(p: Params) -> dict:
    """The page's "Latest feedback" tab: the review's findings, worded and dimensioned at `p`, most serious first.

    Each item has an `id` the template has a drawing for, the solids it concerns (`parts`), what was found, why it
    matters, how it is known (`basis`) and where in the code it comes from. Numbers that follow from the dimensions
    are worked out from `p` (`measures`); the rest are the review's, measured at its wd and axis.
    """
    n, m = _n, measures(p)
    half = p.sw_travel / 2
    film_slot_w = AS_REVIEWED["film_slot_w"]
    since_f23 = "" if p.tube_ro == CHANGED_SINCE["tube_ro"] else f"; {_n(p.tube_ro)} since F23"
    squeezes = "; ".join(
        f"{n(row['layer'])} layers: " + " or ".join(f"{v:+.3f}" for v in row["squeeze"]) for row in m["layers"]
    )

    def num(label: str, value: str | float, tag: str = "") -> dict:
        return {"label": label, "value": value if isinstance(value, str) else n(value), "tag": tag}

    items = [
        {
            "id": "notch", "sev": "trouble", "title": "The gate has no clearance at the dock floor's notch end",
            "parts": ["gate_body", "light_dock"],
            "nums": [num("notch end", m["notch_gap"], "bad"), num("front wall", p.dock_gate_clear),
                     num("gate / pocket", f"{n(p.gate_d)} / {n(m['pocket'])}"), num("each side", p.dock_gate_clear)],
            "what": f"The gate body's rear face and the end of the notch in the dock's floor are both at x {n(p.x_light)}: "
                    f"{n(m['notch_gap'])} between them. The gate front has {n(p.dock_gate_clear)} to the front wall, so the "
                    f"{n(p.gate_d)} gate stands in a {n(m['pocket'])} pocket between two hard faces. PLAN says the gate is "
                    f"held between the front wall and the CS-Lite; in the model the stop is the {n(p.floor_t)} tall floor edge.",
            "risk": "Both parts print with that corner on the bed, so first-layer flare on each lands on a zero gap: the "
                    "gate rides up on the floor's edge, or is held off the lit face and leaks. Sideways it has "
                    f"{n(p.dock_gate_clear)} per side on a {n(p.gate_front_w)} wide part.",
            "basis": "Clearances measured; the print effect is inferred.",
            "where": ["parts/light_dock/model.py · _gate_notch", "params.py · dock_gate_clear"],
        },
        {
            "id": "clamp", "sev": "trouble", "title": "The clamp's margin is smaller than one layer",
            "parts": ["gate_body", "pressure_plate", "wedge_plate"],
            "nums": [num("room", m["room"]), num("stack at LOCK", m["stack"]), num("squeeze", m["squeeze"], "bad"),
                     num("reaches the film at", f"{m['reach']:.2f} of {n(p.sw_travel)}")],
            "what": f"From the reference plane to the backer's face there is {n(m['room'])}. At LOCK the stack between them "
                    f"(film, pressure plate, pad, ramp, wedge plate) is {n(m['stack'])}: a squeeze of {m['squeeze']:.3f} once "
                    f"the wedge plate has taken up its {n(p.wedge_back_clear)} to the backer, {m['squeeze_over']:.3f} if the tab "
                    f"runs on to the slot's end. The plate reaches the film at {m['reach']:.2f} of the {n(p.sw_travel)} travel "
                    f"({m['reach_play']:.2f} with the backer's play).",
            "risk": f"The {n(m['room'])} is the difference of two heights in the gate body's print, {n(m['body_h'])} and "
                    f"{n(m['backer_h'])}, and neither is a whole number of layers. Printed, the squeeze becomes: {squeezes}. "
                    "A stack that prints thick only locks earlier; about 0.1 thin and it never clamps. The ramps' thin end "
                    f"({n(p.ramp_min)}) is less than one layer. PLAN covers tuning {_code('ramp_rise')}, but not that the "
                    "datum spans two parts and sits off the layer grid.",
            "basis": "Stack measured; the layer effect is inferred.",
            "where": ["params.py · ramp_rise, ramp_min, wedge_gap, wedge_back_clear", "parts/film_gate/model.py · _backer"],
        },
        {
            "id": "lidstop", "sev": "trouble", "title": "The loose lid is the lock's only travel stop",
            "parts": ["gate_lid", "wedge_plate"],
            "nums": [num("LOCK / SLIDE", f"±{n(half)}"), num("tab on the slot's end", f"±{n(m['tab_stop'])}", "bad"),
                     num("plate on the side wall", f"±{n(m['wall_stop'])}"), num("lid rests on", "131 mm²"),
                     num("lid", "≈ 7 g")],
            "what": f"The tab meets the end of the lid's slot at s = ±{n(m['tab_stop'])}. Nothing locates the lid along z: "
                    "moved ±20 it interferes with neither the gate front nor the body. Past the slot's end the tab drags "
                    "the lid with it.",
            "risk": f"The next stop is the wedge plate on the side wall at s = ±{n(m['wall_stop'])}, where "
                    f"{n(m['on_ramp']['wall'])} of each {n(p.pad)} pad is left on its ramp ({n(m['on_ramp']['lock'])} at LOCK, "
                    f"{n(m['on_ramp']['tab'])} at ±{n(m['tab_stop'])}). PLAN lists lid retention as unfinished, but not that "
                    "the lid is the stop.",
            "basis": "Measured.",
            "where": ["parts/film_gate/model.py · gate_lid, _lid_rails (F22)", "params.py · slot_end, lid_side_clear"],
            "status": f"Changed in CAD 2026-11-12 (F22), not yet printed: a rail on each of the gate body's upper pillars, "
                      f"{n(p.lid_rail_w)} wide and up to the lid's top, stands {n(p.lid_side_clear)} beside each side of "
                      f"the lid, so the lid moves at most {n(p.lid_side_clear)} along z and the slot's end stops the tab at "
                      f"s = ±{n(m['tab_stop'] + p.lid_side_clear)}, with {n(m['on_ramp']['lid'])} of each pad still on its "
                      "ramp. The lid still lifts straight off: nothing holds it down.",
        },
        {
            "id": "contact", "sev": "trouble", "title": "Plastic touches the image area of the neighbouring frames",
            "parts": ["gate_front", "pressure_plate"],
            "nums": [num("frame in the window", "0 mm²"),
                     num("each neighbour", f"{n(m['contact'])} of {n(m['frame_area'])} mm²", "bad"),
                     num("gap at SLIDE", p.channel - p.film_t), num("at LOCK", 0.0)],
            "what": f"The frame in the window touches nothing. Each neighbouring frame lies on the gate front's rear face over "
                    f"{n(m['covered'])} of its {n(p.frame_w)} width: {n(m['contact'])} of {n(m['frame_area'])} mm². At LOCK "
                    f"the pressure plate is on it from behind; at SLIDE the film is dragged between the two faces through "
                    f"{n(p.channel - p.film_t)}.",
            "risk": f"Neither face has a relief over the {n(p.frame_h)} image band, so every frame slides across printed "
                    "plastic on its way to the window and away from it. F7 asks for smooth faces; nothing in PLAN covers "
                    "image-area contact or scratching.",
            "basis": "Measured.",
            "where": ["parts/film_gate/model.py · gate_front, pressure_plate"],
        },
        {
            "id": "guide", "sev": "trouble", "title": f"The strip is guided only by two {n(p.wall)} mm ledges",
            "parts": ["gate_body"],
            "nums": [num("ledge", p.wall), num("over the strip", p.film_slot_clear), num("tilt", f"{m['tilt']:.1f}°", "bad"),
                     num("at the window's far edge", f"{m['drop']:.1f}", "bad"), num("window margin", m["margin"])],
            "what": f"The strip rests on the floor of a slot in each side wall, {n(p.wall)} long. Between the walls nothing "
                    "lies under its lower edge in the film's plane (0 mm³ within 5 below it). With the first or last frame of "
                    f"a strip in the window only one slot holds it, and {n(p.film_slot_clear)} over a {n(p.wall)} wall allows "
                    f"{m['tilt']:.1f}° of tilt: about {m['drop']:.1f} at the window's far edge.",
            "risk": f"The window has {n(m['margin'])} of margin round the frame, so an end frame can hang out of it.",
            "basis": "Clearances measured; the behaviour is inferred.",
            "where": ["params.py · film_slot_clear", "parts/film_gate/model.py · _side_wall, _sill (F20)"],
            "status": f"Changed in CAD 2026-11-11 (F20), not yet printed: the gate body is filled up to the film's lower "
                      f"edge (y {n(p.sill_y)}, the slots' floors), so the strip lies on the sill from wall to wall and an "
                      f"end frame cannot droop. The pressure plate and the wedge plate stand on it, the pads moved to "
                      f"pad_dy {n(p.pad_dy)}, and a step on the sill backs the wedge plate's lower ramps. "
                      "Fixed once a strip has been fed through the printed gate.",
        },
        {
            "id": "misfeed", "sev": "trouble", "title": "A strip can go the wrong side of the pressure plate",
            "parts": ["gate_body", "pressure_plate"],
            "nums": [num("slot", film_slot_w), num("channel", p.channel), num("plate's edge", p.plate_t, "bad"),
                     num("behind the plate", m["behind"], "bad")],
            "what": f"Each slot is {n(film_slot_w)} wide along the axis (x {n(p.film_slot_x0)}–"
                    f"{n(p.film_slot_x0 + film_slot_w)}), but the channel is only {n(p.channel)} of it. The pressure "
                    f"plate's square edge (at z {n(m['plate_edge'])}, no lead-in) blocks {n(p.plate_t)}, and the last "
                    f"{n(m['behind'])} leads behind the plate, into the pads and ramps.",
            "risk": "With no springs the plate can also lie on the gate front and close the entry altogether.",
            "basis": "Geometry measured; the behaviour is inferred.",
            "where": ["params.py · film_slot_mouth, plate_lead_in (F21)", "parts/film_gate/model.py · _side_wall, pressure_plate"],
            "status": f"Changed in CAD 2026-11-11 (F21), not yet printed: each slot is {n(p.channel)} deep at the wall's "
                      f"inner face, the channel and no more, widening to {n(p.film_slot_mouth)} (film_slot_mouth) at the "
                      f"outer face, so nothing leads to the plate's edge or behind it. Each end of the plate's front edge "
                      f"has a {n(p.plate_lead_in)} × 45° lead-in, so a plate lying forward is pushed back by the strip's "
                      "tip. Fixed once a strip has been fed through the printed gate.",
        },
        {
            "id": "light", "sev": "minor", "title": "Openings on the light side that PLAN doesn't list",
            "parts": ["gate_lid", "gate_body", "light_dock"],
            "nums": [num("lit area", f"{n(m['lit'])} mm²"), num("past the gate", f"{m['past_pct']:.0f}%", "bad"),
                     num("each side", m["side"]), num("above the lid", m["above"]),
                     num("tab slot", f"{n(m['tab_slot'])} mm²"), num("lid slits", f"{n(m['lid_slit'])} mm² each")],
            "what": f"The tab's slot is {n(m['tab_slot'])} mm², {n(m['tab_open'])} of it open round the tab. The slit behind the "
                    f"lid is {n(p.lid_clear)} × {n(m['lid_slit_l'])} = {m['lid_slit']:.0f} mm², the same as the documented one "
                    f"in front. The film slots are {n(film_slot_w)} × {n(p.film_slot_h)} each. And of the CS-Lite's "
                    f"{n(m['lit'])} mm² lit area about {round(m['past'], -2):.0f} ({m['past_pct']:.0f}%) shines past the gate: "
                    f"{n(m['side'])} each side, {n(m['above'])} above the lid.",
            "risk": "Rays cast from the frame's light-side face (1.92 M per case) escape at SLIDE only within 1.1° of the "
                    "film plane, out through the film slots and the lid's front slit; at LOCK none do. So this is stray "
                    "light in the room, not on the frame.",
            "basis": "Measured.",
            "where": ["parts/film_gate/model.py · gate_lid, _side_wall", "params.py · gw, csl_lit_w, csl_lit_h"],
        },
        {
            "id": "wedge", "sev": "minor", "title": f"The wedge plate is modelled floating {n(p.wedge_clear)} above the floor",
            "parts": ["wedge_plate"],
            "nums": [num("modelled edge", p.win_h / 2), num("settled edge", m["settled"], "bad"),
                     num("frame edge", p.frame_h / 2), num("tab proud", f"{n(m['tab_proud'])}, not {n(p.tab_reach)}")],
            "what": f"The model gives it {n(p.wedge_clear)} under it and over it; in the gate it settles onto the floor. "
                    f"Settled, its window's top edge is {n(m['settled'])} above the axis, the frame's edge {n(p.frame_h / 2)}, "
                    f"and the tab stands {n(m['tab_proud'])} out of the lid.",
            "risk": "With the lens's pupil assumed 140–170 from the film, the settled edge cuts 0.03–0.41 into the imaging "
                    "bundle, so the top 0.1–0.4 of the frame may get less backlight. The rear window (±23) is 0.55 short at "
                    "f/2.8 with the pupil at 140, and clear from f/5.6.",
            "basis": "Edges measured; the lens's pupil is assumed.",
            "where": ["parts/lock_switch/model.py · _plate", "params.py · win_h, wedge_clear"],
        },
        {
            "id": "perfs", "sev": "minor", "title": "The perforations show in the frame window",
            "parts": ["gate_front"],
            "nums": [num("perforations from", p.perf_inner), num("window edge", p.win_h / 2),
                     num("showing", m["perf_show"], "bad"), num("perforations", f"{m['perf_count']}"),
                     num("bare light", f"{m['perf_area']:.1f} mm²")],
            "what": f"The perforations' inner edges are {n(p.perf_inner)} from the axis and the window's half height is "
                    f"{n(p.win_h / 2)}, so {n(m['perf_show'])} of each row shows: {m['perf_count']} perforations, about "
                    f"{m['perf_area']:.1f} mm² of bare panel light along the frame's long edges.",
            "risk": "Bare light beside the image, to be cropped off every scan.",
            "basis": "Measured.",
            "where": ["params.py · win_h"],
        },
        {
            "id": "ledge", "sev": "minor", "title": "The adapter's socket ledge prints as a ceiling, and the tube seats on it",
            "parts": ["adapter"],
            "nums": [num("ledge", m["ledge"], "bad"), num("area", f"{m['ledge_area']:.0f} mm²"),
                     num("above the bed", p.socket_depth), num("thread", "pitch 0.750, r 32.890–33.350")],
            "what": f"Thread up, the socket's floor is a flat ceiling {n(m['ledge'])} wide, {n(p.socket_depth)} above the bed, "
                    "and it is the face the tube's end seats on.",
            "risk": "It prints on supports and will carry their scars, on a locating face. The thread's flanks are 60° from "
                    "vertical (614 mm² of facets), normal for a printed thread: right-hand, 1.89 of wall under the root, and "
                    "0.256 of 0.406 flank overlap with a nominal internal thread.",
            "basis": "Measured.",
            "where": ["parts/lens_adapter/model.py · build"],
        },
        {
            "id": "ranges", "sev": "minor", "title": "Nothing checks wd, or an axis that is too high",
            "parts": [],
            "nums": [num("wd builds", "40–233"), num("axis builds", f"{n(p.axis_min)}–62"),
                     num("now", f"wd {n(p.wd)}, axis {n(p.axis)}")],
            "what": f"An axis under {n(p.axis_min)} is refused with one line. Nothing else is checked: an axis of 63 or more "
                    "ends in a bare OCC <code>Standard_Failure</code> from the dock; a wd of 30 or less builds an adapter "
                    "that hits the dock's front wall (111 mm³ at 30; build.py exits 1), and at 13 the tube fails; a wd of 234 "
                    "or more is an uncaught <code>ValueError</code> traceback.",
            "risk": "In range everything holds. Out of range the failure is a traceback, not a message.",
            "basis": "Measured: a sweep of builds.",
            "where": ["params.py · __post_init__", "build.py · main", "parts/light_dock/model.py · _front_wall"],
        },
        {
            "id": "docs", "sev": "minor", "title": "Notes still written for the Ø72 tube",
            "parts": ["light_dock", "adapter"],
            "nums": [num("U's bottom", m["u_bottom"]), num("floor's top", p.floor_t), num("ledge", f"{n(m['ledge'])}, not 5.3")],
            "what": f"Since {_code('tube_ro')} went 36 → 34 (R8{since_f23}) the round of the dock's U stops "
                    f"{n(m['u_bottom'])} above the table, clear of the floor's top ({n(p.floor_t)})"
                    + (": the F17 cut takes nothing at any allowed axis. " if m["u_lowest"] >= p.floor_t else
                       f"; only at axis {n(p.axis_min)}, the lowest allowed, does the F17 cut take "
                       f"{n(p.floor_t - m['u_lowest'])} off it. ")
                    + "PLAN still described a trough 3.5 above the table and a 16 mm³ sliver, a 5.3 wide ledge, and tube 36 / hole "
                    "36.3; the mockup still has TUBE_RO 36.",
            "risk": "Nothing printed changes. The notes disagreed with the build.",
            "basis": "Measured.",
            "where": ["PLAN.md · F17, \"Tuning and print notes\"", "parts/light_dock/model.py · light_dock"],
            "status": "Fixed 2026-11-11: PLAN (F17, the ledge, the radii, the mockup table), the dock's comment, and the "
                      "adapter's print note on this page.",
        },
        {
            "id": "xfilm", "sev": "minor", "title": f"The film sits {n(m['film_off'])} in front of x_film",
            "parts": ["gate_front"],
            "nums": [num("x_film", p.x_film), num("film's face", m["film_face"]),
                     num("rim to film", f"{n(m['rim_to_film'])}, not {n(p.wd)}", "bad")],
            "what": f"{_code('x_film')} ({n(p.x_film)}) is the middle of the {n(p.channel)} channel. The film lies on the "
                    f"reference plane, so its lens-side face is at x {n(m['film_face'])}: {n(m['rim_to_film'])} from the lens's "
                    f"rim, not {n(p.wd)}.",
            "risk": "Well inside what focusing takes up.",
            "basis": "Measured.",
            "where": ["assembly.py · references", "params.py · x_ref"],
        },
        {
            "id": "thin", "sev": "minor", "title": "The thinnest sections",
            "parts": ["gate_front", "light_dock"],
            "nums": [num("over the socket", m["over_socket"]), num("counterbore walls", m["cbore_wall"]),
                     num("strip under the U", f"{n(p.dock_front_t)} × {n(m['u_bottom'])}")],
            "what": f"The gate front is {n(m['over_socket'])} thick over the tube's socket, and {n(m['cbore_wall'])} round each "
                    f"counterbore. The two halves of the dock's front wall are joined across the gate's notch by a strip under "
                    f"the U, {n(p.dock_front_t)} × {n(m['u_bottom'])}.",
            "risk": "All of them print. They are where the parts are weakest in the hand.",
            "basis": "Measured.",
            "where": ["params.py · tube_ro, ear_w, cbore_d, dock_front_t"],
        },
        {
            "id": "baffle", "sev": "minor", "title": "The tube's baffle flanks are exactly 45°",
            "parts": ["tube"],
            "nums": [num("flank", "45°", "bad"), num("rib", f"{n(p.baffle_h)} high, every {n(p.baffle_pitch)}"),
                     num("ribs", f"{p.baffle_count}")],
            "what": f"Each rib's lower flank climbs {n(p.baffle_h)} over {n(p.baffle_h)}: a 45° overhang (facet normal z "
                    "−0.7071).",
            "risk": "It passes <code>cadutil.overhangs</code> only by the check's 1e-6 tolerance: nothing in hand.",
            "basis": "Measured.",
            "where": ["parts/tube/model.py · _bore"],
        },
        {
            "id": "filament", "sev": "minor", "title": "PLAN never names a filament",
            "parts": ["tube", "gate_front"],
            "nums": [num("tube wall", m["tube_wall"]), num("over the socket", m["over_socket"]), num("plates", p.plate_t),
                     num("gate walls", p.wall)],
            "what": f"Nothing says what to print in. The light path is closed by walls {n(m['tube_wall'])} (the tube), "
                    f"{n(m['over_socket'])} (over the socket) and {n(p.wall)} (the gate) thick.",
            "risk": "Light-tightness through walls that thin needs an opaque, matte black filament.",
            "basis": "Inferred.",
            "where": ["PLAN.md · \"Tuning and print notes\""],
        },
    ]
    for i, it in enumerate(items, 1):
        it["num"] = f"FB{i}"                        # PLAN.md "Latest feedback" numbers them the same
    return {
        "review": REVIEW,
        "same": abs(p.wd - REVIEW["wd"]) < 1e-9 and abs(p.axis - REVIEW["axis"]) < 1e-9,
        "p": fig_params(p),
        "m": m,
        "severities": [{"id": sid, "title": title, "blurb": blurb} for sid, title, blurb in SEVERITIES],
        "items": items,
        "clean": list(CLEAN), "known": list(KNOWN), "unchecked": list(UNCHECKED),
    }


def _commit() -> str:
    try:
        return subprocess.run(
            ["git", "describe", "--always", "--dirty", "--abbrev=7"], cwd=ROOT, capture_output=True, text=True, check=True
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
    """The STLs were built at p's wd and axis: the tube prints tube_len (wd - 18) tall, the gate front stands axis + 36
    on the bed."""
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
        "feedback": feedback(p),
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
    print(f"wd={p.wd:g}  axis={p.axis:g}  {len(d['parts'])} solids  {len(d['feedback']['items'])} findings  "
          f"{OUT.stat().st_size / 1e6:.1f} MB  -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
