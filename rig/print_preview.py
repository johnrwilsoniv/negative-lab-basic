"""Write the print-direction preview: each printed solid on the bed, with a layer slider, and the whole assembly.

    uv run python build.py [--wd W] [--axis A]           # first: writes exports/stl/ in print pose
    uv run python print_preview.py [--wd W] [--axis A]   # the same values: it refuses STLs built at others

Writes exports/nlb-rig-print-preview.html, one self-contained page with the print-pose STLs from
exports/stl/ embedded, and the assembly: every printed solid in place with a frame in the window (built
here, meshed more coarsely to keep the page small) with the references: the film through the gate with its
perforations and its exposures, and half the roll on each spool, as meshes; the CS-Lite as a box; and the
"Latest feedback" tab: the findings of the last design review that still concern a part of this rig
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
# The picker's groups. 1-3 are main's (the tube under the adapter); the film transport (D1) adds 4 and 5.
ADAPTER_GROUP, FILM_GROUP, DOCK_GROUP = "1 · Lens adapter", "2 · Film gate", "3 · Light dock"
DRIVE_GROUP, SPOOL_GROUP = "4 · Film drive", "5 · Spools"
REF_MESHES = (                  # name, label, group, colour, opacity: the film's base is clear orange, its exposures dark
    ("film", "Film through the gate (perforated)", FILM_GROUP, "#b39466", 0.55),
    ("film_frames", "Exposures, 36 × 24", FILM_GROUP, "#2b2622", 0.85),
    ("rolls", "Half the roll on each spool", SPOOL_GROUP, "#6b5a45", 0.7),
)

# name: (number, label, group, default layer, description, notes); which way up comes from the models' PRINT_UP
SOLIDS = {
    "thread_coupon": (
        "1a", "Thread coupon", ADAPTER_GROUP, 0.12,
        "The adapter's M67 × 0.75 thread on a 2 thick Ø78/Ø62 ring. Print it before the adapter.",
        [
            "Print first: the thread is the riskiest geometry in the rig. At 0.75 pitch, FDM is marginal.",
            "Thread up, axis vertical, at 0.12–0.16 layers.",
            "<code>thread_clear</code> builds from 0.05 to 0.3 (0.15 now). Print the coupon to choose it.",
        ],
    ),
    "adapter": (
        "1", "Lens adapter", ADAPTER_GROUP, 0.12,
        "Screws into the Laowa's 67 mm filter thread; the tube slides into its socket.",
        [
            "Flat, thread axis vertical, thread up, at 0.12–0.16 layers.",
            "Support the socket ledge: a 3.3 wide annular overhang in this pose.",
            "Check the coupon's fit first.",
        ],
    ),
    "tube": (
        "1b", "Tube", ADAPTER_GROUP, 0.2,
        "Ø68.5 / Ø64, <code>wd − 18</code> long, with sawtooth baffle ribs inside. A friction fit in the Ø68.6 sockets "
        "(F23), 9 deep at each end.",
        [
            "Upright. The baffles' lower flanks are 45°, so no supports.",
            "Ø68.5 in a Ø68.6 socket is 0.05 a side: tested with masking tape on the first print (of main's clamp "
            "gate, which has the same sockets). If it won't go in, sand the tube's ends rather than the sockets.",
        ],
    ),
    "gate_front": (
        "2", "Gate front", FILM_GROUP, 0.2,
        "Solid block: a 9 deep tube socket (F24), a light passage flaring down to the 38 × 26 frame window, and the "
        "film reference plane, with a groove under each sprocket's tooth rows. Presses onto the gate body's four pegs.",
        [
            "<b>Film face on the bed.</b> The rear face, which the film slides on, is the first layer: as flat and "
            "smooth as the bed. Keep the first layer clean (no elephant's foot) around the window.",
            "No supports. The passage and the socket only widen going up; the four tooth grooves are 2.8 wide bridges, "
            "1.2 deep, in the first layers.",
            "The peg holes run through. They're the pegs' own size, so the front presses on (FDM prints holes a little "
            "small); open <code>peg_fit</code> if it won't go.",
            "The ▲ on the socket's floor (F18) is 0.36 deep in a top layer; it points up.",
            "The tube is a friction fit in the socket (F23), and only the pegs hold this front on: hold the gate front, "
            "not the dock, when you pull the tube out.",
        ],
    ),
    "gate_body": (
        "2b", "Gate body", FILM_GROUP, 0.2,
        "The film channel across its front face (0.3 deep, 35.2 tall, with a lead-in at each side), the light passage "
        "to the lit face, the two sprocket pockets and their bearing holes, the idler's axle hole, and the four pegs.",
        [
            "Rear face on the bed. The channel's floor is the last layers: use ironing, since the film slides on it.",
            "The pockets and holes run along the bed, so each is a teardrop pointing up: no supports.",
        ],
    ),
    "sprocket_supply": (
        "4", "Sprocket (×2)", DRIVE_GROUP, 0.12,
        "Eight teeth on each of two rings come up through the perforations: one turn is one frame. The shaft stands "
        "in a bearing hole in the gate body and runs up through the deck to its gear, keyed by a D-flat.",
        [
            "Standing on its shaft's foot, at 0.12 layers. The rings sit on 45° cones and the teeth come to 45° ridges, "
            "so nothing hangs over air.",
            "Tall and thin (Ø6 × 81.5): print two at once, or with a brim, so each layer has time to cool.",
            "The take-up side is the same print: <code>sprocket_takeup</code>.",
        ],
    ),
    "sprocket_takeup": (
        "4", "Sprocket, take-up side", DRIVE_GROUP, 0.12,
        "The same as the supply side's, turned half round in the rig.", [],
    ),
    "gear_supply": (
        "4", "Gear (×2)", DRIVE_GROUP, 0.12,
        "30 teeth, module 1.03, 20°: on each sprocket shaft's D-flat, standing on the deck.",
        ["Flat. The take-up side is the same print: <code>gear_takeup</code>."],
    ),
    "gear_takeup": (
        "4", "Gear, take-up side", DRIVE_GROUP, 0.12, "The same as the supply side's.", [],
    ),
    "idler": (
        "4", "Idler and knob", DRIVE_GROUP, 0.12,
        "30 teeth, between the two gears, so both sprockets turn the same way. One knob turn is one frame; the groove "
        "on top counts turns.",
        ["Gear face down, knob up."],
    ),
    "idler_axle": (
        "4", "Idler axle", DRIVE_GROUP, 0.2,
        "Ø6 × 26: presses through the deck into the gate body's top.", ["Upright."],
    ),
    "deck": (
        "4", "Deck", DRIVE_GROUP, 0.2,
        "Lies on the gate body's top: the sprocket shafts' top bearings, and the idler's axle pressed in.",
        ["Flat."],
    ),
    "spool_supply": (
        "5", "Spool (×2)", SPOOL_GROUP, 0.2,
        "The bottom flange and a Ø30 core, with a slit for the film's end and a socket for the cap. Turns on a pin on "
        "the dock.",
        ["Bottom flange on the bed. The take-up spool is the same print: <code>spool_takeup</code>."],
    ),
    "spool_takeup": (
        "5", "Take-up spool", SPOOL_GROUP, 0.2, "The same as the supply spool.", [],
    ),
    "cap_supply": (
        "5", "Spool cap (×2)", SPOOL_GROUP, 0.2,
        "The top flange, scalloped for a grip, with a spigot that presses into the core's socket. Turn the spools by "
        "their caps.",
        ["Upside down: its top on the bed, the spigot up. The other cap is the same print: <code>cap_takeup</code>."],
    ),
    "cap_takeup": (
        "5", "Take-up spool cap", SPOOL_GROUP, 0.2, "The same as the supply spool's cap.", [],
    ),
    "light_dock": (
        "3", "Light dock", DOCK_GROUP, 0.2,
        "Holds the CS-Lite on its long edge, 25 behind the film. The gate stands in a notch against the lit face; the "
        "spools stand on pedestals and pins beside it.",
        [
            "Floor down. No bridges. The pins print upright.",
            "At 191 wide it's the largest part: confirm the bed size.",
        ],
    ),
}
ORDER = [                 # the picker's order: by subassembly number
    "thread_coupon", "adapter", "tube", "gate_front", "gate_body", "light_dock", "sprocket_supply", "sprocket_takeup",
    "gear_supply", "gear_takeup", "idler", "idler_axle", "deck", "spool_supply", "spool_takeup", "cap_supply",
    "cap_takeup",
]

# ---- "Latest feedback": the design review of REVIEW["date"], each finding that still has a part here, with a drawing ----
# The review was of main's clamp gate (cut strips, a lid, a pressure plate, a lock switch). This rig has the same
# adapter, tube, gate front socket and dock, so six of its sixteen findings carry over, under main's numbers; the rest
# concern parts D1 removed (DROPPED) or need measuring again on this gate (REMEASURE).
REVIEW = {
    "date": "2026-11-11", "wd": 111, "axis": 40.5, "commit": "0e836e1",
    "verdict": "The review was of the clamp gate on main, not of this sprocket drive. Six of its sixteen findings "
               "concern parts this rig shares with it (the adapter, the tube, the gate front's socket and window, the "
               "dock's notch) and are shown here under their original numbers. Nothing it found will certainly fail. "
               "The drive itself (sprockets, gears, deck, spools) has not been reviewed or printed.",
    "ran": "On main: 437 tests passed; build.py: 9 solids ok, no interference, 24 fits ok.",
    "how": "Measured on main's built solids with scripts independent of the repo's own tests. No slicer was used, so "
           "every print effect is inferred from the measured geometry.",
}
SEVERITIES = (
    ("fail", "Will fail", "A print or the assembly won't work."),
    ("trouble", "Likely trouble", "It may work as drawn; each is a real risk once it's plastic."),
    ("minor", "Minor", "Worth knowing. None of them stops a print."),
)
# Defaults that were at the review's values and have changed since, after the first print (F23, F24): with these and the
# review's wd and axis, `reviewed()` rebuilds the shared parts as the review measured them.
CHANGED_SINCE = {"gate_front": 14, "front_wall": 4, "tube_ro": 34, "fit_clear": 0.3}
DROPPED = {         # findings about parts this rig does not have (D1, D2): main's number and what it was about
    "FB2": "the clamp's margin", "FB3": "the lid as the lock's travel stop", "FB5": "the strip on two 3 mm ledges",
    "FB6": "a strip going behind the pressure plate", "FB7": "the lid's and the tab's openings",
    "FB8": "the wedge plate floating", "FB12": "notes written for the Ø72 tube (fixed on main)",
    "FB13": "the film 0.3 in front of x_film",
}
REMEASURE = {       # findings that need measuring again on this gate before they can be carried or dropped
    "FB4": "plastic on the image area: here every frame slides through a fixed 0.3 channel, on the gate front's "
           "bed-printed face and the body's channel floor, with no relief over the 24 image band",
    "FB11": "nothing checks wd, or an axis that is too high: the wd and axis ranges that build were swept on main's "
            "dock (40-233, 39-62), not on this one",
}
CLEAN = (                       # checked in the review, on parts this rig shares, and fine
    "Lens side: 0 of 1.92 M rays escaped with the tube seated and the lens closing the adapter. The adapter, the "
    "tube and the gate front's socket are the same here.",
    "Optics: the film's centre and the tube's axis are both at the lens axis, and the frame window is 38 × 26 and "
    "centred. The cone behind the film was checked against main's gate body, not this one.",
    "Printability of the adapter, the tube and the dock's floor, lips and cheeks: apart from the adapter's ledge, the "
    "thread's flanks and the tube's ribs, every layer stands wholly on the one below.",
)
KNOWN = (                       # already in PLAN.md as unfinished, or not carried from the review: not new findings
    "Not carried, the part is gone (D1): " + "; ".join(f"{k}, {v}" for k, v in DROPPED.items()) + ".",
    "To measure again on this gate: " + "; ".join(f"{k}, {v}" for k, v in REMEASURE.items()) + ".",
    "The tube is a friction fit in the gate front's socket (F23), but only four Ø4 × 6 friction pegs hold the gate "
    "front on the body, and only the dock floor's edge stops it toward the camera: pulling the tube out can pull the "
    "front off and open the film channel.",
    "Nothing winds the take-up spool: turn its cap by hand as the knob feeds film. No detent marks a frame.",
    "The CS-Lite is not held forward (0.5 + 0.2 of play).",
    "No tube split past wd ≈ 200.",
    "C1–C12 in PLAN.md \"Check before printing\": bed, CS-Lite, thread depth, the channel, the pegs, the bearing fits.",
)
UNCHECKED = (
    "The film drive and the spools: no review has measured them. The repo's own tests and build.py do (no "
    "interference at a frame centred or half a tooth on; the teeth stay in the perforations), and nothing is printed.",
    "Slicing: no slicer was run, so supports, bridging and thin walls are judged from geometry alone.",
    "Real hardware: the lens's thread depth, the CS-Lite's shape, the film's thickness, the printer's tolerances.",
    "The viewer and print-preview pages, the website, and STEP import into Onshape.",
)


def reviewed() -> Params:
    """The shared parts as the review measured them: today's defaults at the review's wd and axis, less what has changed
    since."""
    return Params(wd=REVIEW["wd"], axis=REVIEW["axis"], **CHANGED_SINCE)


def _n(v: float) -> str:
    return f"{round(v, 3):g}"


def fig_params(p: Params) -> dict:
    """Every field and derived property of `p`, for the page's drawings."""
    names = [f.name for f in dataclasses.fields(p)] + [k for k, v in vars(Params).items() if isinstance(v, property)]
    return {name: (round(v, 4) if isinstance(v := getattr(p, name), float) else v) for name in names}


def measures(p: Params) -> dict:
    """The numbers the findings turn on, from `p`. At the review's wd and axis the ones that do not depend on the gate
    body are the review's own (tests/test_print_preview.py checks each against what the review measured)."""
    lit = p.csl_lit_w * p.csl_lit_h
    lit_y0 = p.floor_t + (p.csl_h - p.csl_lit_h) / 2
    lit_y1 = lit_y0 + p.csl_lit_h
    # what stands in front of the lit area: the gate body, and the deck on its top (the gears and the knob above it
    # are left out: they cover a little more)
    behind_gate = min(p.gw, p.csl_lit_w) * max(0.0, min(p.y_deck + p.deck_t, lit_y1) - lit_y0)
    past = lit - behind_gate
    shown = [z for z in p.perf_zs if abs(z) + p.perf_l / 2 <= p.win_w / 2]
    show = p.win_h / 2 - p.perf_inner
    return {
        "notch_gap": p.x_light - (p.x_gate + p.gate_d), "pocket": p.gate_d + p.dock_gate_clear,
        "lit": lit, "past": past, "past_pct": 100 * past / lit,
        "perf_show": show, "perf_count": 2 * len(shown), "perf_area": 2 * len(shown) * p.perf_l * show,
        "ledge": p.fit_r - p.adapter_bore_r, "ledge_area": math.pi * (p.fit_r ** 2 - p.adapter_bore_r ** 2),
        "over_socket": p.gh - p.axis - p.fit_r, "tube_wall": p.tube_ro - p.tube_ri,
    }


def feedback(p: Params) -> dict:
    """The page's "Latest feedback" tab: the review's findings that still concern a part of this rig, worded and
    dimensioned at `p`, most serious first.

    Each item has an `id` the template has a drawing for, main's number for it (`num`, set here, not counted: the
    numbers have gaps where a finding was not carried), the solids it concerns (`parts`), what was found, why it matters,
    how it is known (`basis`) and where in the code it comes from. Numbers that follow from the dimensions are worked
    out from `p` (`measures`); the rest are the review's, measured at its wd and axis.
    """
    n, m = _n, measures(p)

    def num(label: str, value: str | float, tag: str = "") -> dict:
        return {"label": label, "value": value if isinstance(value, str) else n(value), "tag": tag}

    items = [
        {
            "id": "notch", "num": "FB1", "sev": "trouble",
            "title": "The gate has no clearance at the dock floor's notch end",
            "parts": ["gate_body", "light_dock"],
            "nums": [num("notch end", m["notch_gap"], "bad"), num("floor's edge", p.dock_gate_clear),
                     num("gate / pocket", f"{n(p.gate_d)} / {n(m['pocket'])}"), num("each side", p.dock_gate_clear)],
            "what": f"The gate body's rear face and the end of the notch in the dock's floor are both at x {n(p.x_light)}: "
                    f"{n(m['notch_gap'])} between them. The gate front has {n(p.dock_gate_clear)} to the floor's edge in "
                    f"front of it, so the {n(p.gate_d)} gate stands in a {n(m['pocket'])} pocket between two hard faces. "
                    f"On main the stop in front is a wall; here it is the {n(p.floor_t)} tall floor edge alone (D5).",
            "risk": "Both parts print with that corner on the bed, so first-layer flare on each lands on a zero gap: the "
                    "gate rides up on the floor's edge, or is held off the lit face and leaks. Sideways it has "
                    f"{n(p.dock_gate_clear)} per side on a {n(p.gw)} wide part.",
            "basis": "Clearances measured (on main, where the notch is the same); the print effect is inferred.",
            "where": ["parts/light_dock/model.py · _gate_notch", "params.py · dock_gate_clear"],
            "status": f"As found. Since F24 the gate is {n(p.gate_d)} deep (39 when reviewed) in a {n(m['pocket'])} "
                      "pocket. The floor's edge is also all that keeps the gate front on its pegs when the tube, now a "
                      "friction fit (F23), is pulled out.",
        },
        {
            "id": "perfs", "num": "FB9", "sev": "minor", "title": "The perforations show in the frame window",
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
            "id": "ledge", "num": "FB10", "sev": "minor",
            "title": "The adapter's socket ledge prints as a ceiling, and the tube seats on it",
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
            "id": "thin", "num": "FB14", "sev": "minor", "title": "The thinnest section: over the tube's socket",
            "parts": ["gate_front"],
            "nums": [num("over the socket", m["over_socket"], "bad"), num("socket", f"Ø{n(2 * p.fit_r)}"),
                     num("gate front", f"{n(p.gw)} × {n(p.gh)}")],
            "what": f"The gate front is {n(m['over_socket'])} thick over the tube's socket. The review's other two thin "
                    "sections, the walls round the screws' counterbores and the strip under the dock's U, are not on this "
                    "rig: the front is held by pegs, and the dock has no front wall.",
            "risk": "It prints. It is where the gate front is weakest in the hand, and since F23 the tube grips the "
                    "socket under it.",
            "basis": "Measured.",
            "where": ["params.py · tube_ro, fit_clear, gate_above_axis"],
        },
        {
            "id": "baffle", "num": "FB15", "sev": "minor", "title": "The tube's baffle flanks are exactly 45°",
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
            "id": "filament", "num": "FB16", "sev": "minor", "title": "PLAN never names a filament",
            "parts": ["tube", "gate_front"],
            "nums": [num("tube wall", m["tube_wall"]), num("over the socket", m["over_socket"]),
                     num("past the gate", f"{m['past_pct']:.0f}%", "bad")],
            "what": f"Nothing says what to print in. The light path is closed by walls {n(m['tube_wall'])} (the tube) and "
                    f"{n(m['over_socket'])} (over the socket) thick; the gate body is solid round the light passage. Of "
                    f"the CS-Lite's {n(m['lit'])} mm² lit area about {round(m['past'], -2):.0f} "
                    f"({m['past_pct']:.0f}%) shines past the gate and the deck on it.",
            "risk": "Light-tightness through walls that thin needs an opaque, matte black filament.",
            "basis": "Inferred. The share of the lit area is worked out for this gate, not measured by the review.",
            "where": ["PLAN.md · \"Tuning and print notes\""],
        },
    ]
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
    """The printed solids in place with a frame in the window (mockup coordinates: y up, the table at y = 0), as STLs, in
    assembly order; then the references: the perforated film, its exposures (all frames in one mesh) and the two rolls
    as STLs, the CS-Lite as a box."""
    placed = assembly.placed(p)
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
            "rolls": cq.Compound.makeCompound([cadutil.solid(placed[n]) for n in ("roll_supply", "roll_takeup")]),
        }
        refs = []
        for name, label, group, colour, opacity in REF_MESHES:
            path = Path(tmp) / f"{name}.stl"
            if not meshes[name].exportStl(
                str(path), tolerance=ASM_LINEAR_TOL, angularTolerance=ASM_ANGULAR_TOL, relative=False
            ):
                raise RuntimeError(f"STL export of {name} failed")
            refs.append({"name": name, "label": label, "group": group, "colour": colour, "opacity": opacity,
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
