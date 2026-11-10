"""Write the print-direction preview: each printed solid on the bed, with a layer slider, and the whole assembly.

    uv run python build.py          # first: writes exports/stl/ in print pose
    uv run python print_preview.py

Writes exports/nlb-rig-print-preview.html, one self-contained page with the print-pose STLs from
exports/stl/ embedded, and the assembly: every printed solid in place with a frame in the window (built
here, meshed more coarsely to keep the page small) with the references: the film through the gate with its
perforations and its exposures, and half the roll on each spool, as meshes; the CS-Lite as a box. The page template is
mockup/print-preview.html. The notes per solid come from PLAN.md ("Tuning and print notes" and each
part's "Printing" line).
"""

import base64
import datetime
import json
import subprocess
import sys
import tempfile
from pathlib import Path

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
FILM_GROUP, DOCK_GROUP, SPOOL_GROUP = "3 · Film gate", "4 · Light dock", "6 · Spools"   # the picker's groups for the refs
REF_MESHES = (                  # name, label, group, colour, opacity: the film's base is clear orange, its exposures dark
    ("film", "Film through the gate (perforated)", FILM_GROUP, "#b39466", 0.55),
    ("film_frames", "Exposures, 36 × 24", FILM_GROUP, "#2b2622", 0.85),
    ("rolls", "Half the roll on each spool", SPOOL_GROUP, "#6b5a45", 0.7),
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
        "reference plane, with a groove under each sprocket's tooth rows. Presses onto the gate body's four pegs.",
        [
            "<b>Film face on the bed.</b> The rear face, which the film slides on, is the first layer: as flat and "
            "smooth as the bed. Keep the first layer clean (no elephant's foot) around the window.",
            "No supports. The passage and the socket only widen going up; the four tooth grooves are 2.8 wide bridges, "
            "1.2 deep, in the first layers.",
            "The peg holes run through. They're the pegs' own size, so the front presses on (FDM prints holes a little "
            "small); open <code>peg_fit</code> if it won't go.",
        ],
    ),
    "gate_body": (
        "3b", "Gate body", "3 · Film gate", 0.2,
        "The film channel across its front face (0.3 deep, 35.2 tall, with a lead-in at each side), the light passage "
        "to the lit face, the two sprocket pockets and their bearing holes, the idler's axle hole, and the four pegs.",
        [
            "Rear face on the bed. The channel's floor is the last layers: use ironing, since the film slides on it.",
            "The pockets and holes run along the bed, so each is a teardrop pointing up: no supports.",
        ],
    ),
    "sprocket_supply": (
        "5", "Sprocket (×2)", "5 · Film drive", 0.12,
        "Eight teeth on each of two rings come up through the perforations: one turn is one frame. The shaft stands "
        "in a bearing hole in the gate body and runs up through the deck to its gear, keyed by a D-flat.",
        [
            "Standing on its shaft's foot, at 0.12 layers. The rings sit on 45° cones and the teeth come to 45° ridges, "
            "so nothing hangs over air.",
            "Tall and thin (Ø6 × 83.5): print two at once, or with a brim, so each layer has time to cool.",
            "The take-up side is the same print: <code>sprocket_takeup</code>.",
        ],
    ),
    "sprocket_takeup": (
        "5", "Sprocket, take-up side", "5 · Film drive", 0.12,
        "The same as the supply side's, turned half round in the rig.", [],
    ),
    "gear_supply": (
        "5", "Gear (×2)", "5 · Film drive", 0.12,
        "30 teeth, module 1.03, 20°: on each sprocket shaft's D-flat, standing on the deck.",
        ["Flat. The take-up side is the same print: <code>gear_takeup</code>."],
    ),
    "gear_takeup": (
        "5", "Gear, take-up side", "5 · Film drive", 0.12, "The same as the supply side's.", [],
    ),
    "idler": (
        "5", "Idler and knob", "5 · Film drive", 0.12,
        "30 teeth, between the two gears, so both sprockets turn the same way. One knob turn is one frame; the groove "
        "on top counts turns.",
        ["Gear face down, knob up."],
    ),
    "idler_axle": (
        "5", "Idler axle", "5 · Film drive", 0.2,
        "Ø6 × 26: presses through the deck into the gate body's top.", ["Upright."],
    ),
    "deck": (
        "5", "Deck", "5 · Film drive", 0.2,
        "Lies on the gate body's top: the sprocket shafts' top bearings, and the idler's axle pressed in.",
        ["Flat."],
    ),
    "spool_supply": (
        "6", "Spool (×2)", "6 · Spools", 0.2,
        "The bottom flange and a Ø30 core, with a slit for the film's end and a socket for the cap. Turns on a pin on "
        "the dock.",
        ["Bottom flange on the bed. The take-up spool is the same print: <code>spool_takeup</code>."],
    ),
    "spool_takeup": (
        "6", "Take-up spool", "6 · Spools", 0.2, "The same as the supply spool.", [],
    ),
    "cap_supply": (
        "6", "Spool cap (×2)", "6 · Spools", 0.2,
        "The top flange, scalloped for a grip, with a spigot that presses into the core's socket. Turn the spools by "
        "their caps.",
        ["Upside down: its top on the bed, the spigot up. The other cap is the same print: <code>cap_takeup</code>."],
    ),
    "cap_takeup": (
        "6", "Take-up spool cap", "6 · Spools", 0.2, "The same as the supply spool's cap.", [],
    ),
    "light_dock": (
        "4", "Light dock", "4 · Light dock", 0.2,
        "Holds the CS-Lite on its long edge, 25 behind the film. The gate stands in a notch against the lit face; the "
        "spools stand on pedestals and pins beside it.",
        [
            "Floor down. No bridges. The pins print upright.",
            "At 191 wide it's the largest part: confirm the bed size.",
        ],
    ),
}
ORDER = [
    "thread_coupon", "adapter", "tube", "gate_front", "gate_body", "sprocket_supply", "sprocket_takeup", "gear_supply",
    "gear_takeup", "idler", "idler_axle", "deck", "spool_supply", "spool_takeup", "cap_supply", "cap_takeup",
    "light_dock",
]



def _commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
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


def data(p: Params, stl_dir: Path = STL_DIR) -> dict:
    ups = {name: up for model in build.discover().values() for name, up in model.PRINT_UP.items()}
    missing = set(ups) ^ set(ORDER)
    if missing:
        raise ValueError(f"print_preview.py and the models disagree on the solids: {sorted(missing)}")
    parts = []
    for name in ORDER:
        num, label, group, layer, desc, notes = SOLIDS[name]
        up = ups[name]
        path = stl_dir / f"{name}.stl"
        if not path.exists():
            raise FileNotFoundError(f"{path} is missing: run build.py first")
        parts.append({
            "name": name, "num": num, "label": label, "group": group, "up": up, "layer": layer,
            "desc": desc, "notes": notes, "stl": base64.b64encode(path.read_bytes()).decode(),
        })
    stamp = datetime.date.today().isoformat()
    return {
        "bed": [p.bed_x, p.bed_y],
        "parts": parts,
        "assembly": assembled(p),
        "built": f"wd {p.wd:g} · axis {p.axis:g} · {_commit()} · {stamp}",
        "foot": (
            f"Print-pose STLs from <code>rig/exports/stl/</code>, built by <code>build.py</code> at "
            f"wd {p.wd:g}, axis {p.axis:g}. The {p.bed_x:g} × {p.bed_y:g} bed is assumed until the printer "
            "is confirmed. Overhangs are faces pointing down more steeply than 45°, off the bed."
        ),
    }


def main() -> int:
    page = TEMPLATE.read_text()
    if MARK not in page:
        print(f"{TEMPLATE} has no {MARK} to fill in", file=sys.stderr)
        return 1
    p = Params()
    d = data(p)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(page.replace(MARK, json.dumps(d, separators=(",", ":"))))
    print(f"{len(d['parts'])} solids  {OUT.stat().st_size / 1e6:.1f} MB  -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
