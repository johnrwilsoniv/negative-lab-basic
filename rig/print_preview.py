"""Write the print-direction preview: each printed solid on the bed, with a layer slider, and the whole assembly.

    uv run python build.py          # first: writes exports/stl/ in print pose
    uv run python print_preview.py

Writes exports/nlb-rig-print-preview.html, one self-contained page with the print-pose STLs from
exports/stl/ embedded, and the assembly: every printed solid in place at SLIDE (built here, meshed
more coarsely to keep the page small) with the film and the CS-Lite as boxes. The page template is
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
        "reference plane. SLIDE / LOCK engraved on top.",
        [
            "<b>Film face on the bed.</b> The rear face, which the film lies on, is the first layer: as flat and "
            "smooth as the bed. Keep the first layer clean (no elephant's foot) around the window.",
            "No supports. The passage and the socket only widen going up.",
            "Four M3 × 20 screws, heads in the counterbores, self-tap into the body's pillars (or use heat-set inserts: "
            "set <code>pilot_d</code> 4.0).",
            "The lettering is engraved in a face that stands upright here; its 0.4 deep walls are the only overhang.",
        ],
    ),
    "gate_body": (
        "3b", "Gate body", "3 · Film gate", 0.2,
        "Floor, side walls and rear wall, with four screw pillars outside the walls. Joins to the gate front's rear face.",
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
        "5a", "Wedge plate", "5 · Lock switch", 0.12,
        "Slides ±5 along z; four ramps push the pressure plate onto the film at LOCK.",
        [
            "Flat, back face on the bed, ramps up (F9). No bridges, no supports, no brim needed.",
            "The ramps' 1:17 slopes are now the top layers, so they print stepped, like the pressure plate's pads. "
            "Use 0.12 or finer layers and ironing; tune <code>ramp_rise</code> against the print.",
        ],
    ),
    "knob": (
        "5b", "Knob", "5 · Lock switch", 0.2,
        "Sits on the tab above the lid, three grip ridges on top. Printed separately.",
        [
            "Ridges up.",
            "The snap onto the tab isn't designed yet.",
        ],
    ),
    "light_dock": (
        "4", "Light dock", "4 · Light dock", 0.2,
        "Holds the CS-Lite on its long edge, 25 behind the film. A 1 deep pocket in the floor seats the shroud.",
        [
            "Floor down. No bridges now that the shroud is its own print.",
            "At 181 wide it's the largest part: confirm the bed size.",
        ],
    ),
    "shroud": (
        "4b", "Shroud", "4 · Light dock", 0.2,
        "Light tunnel from the gate's rear window to the CS-Lite's lit face. Straddles the dock's front lip.",
        [
            "On its end, the face that seals against the gate on the bed. The old 56 bridge is now a wall.",
            "Sits in the dock's pocket and over the front lip with 0.2 all round.",
        ],
    ),
}
ORDER = [
    "thread_coupon", "adapter", "tube", "gate_front", "gate_body", "gate_lid", "pressure_plate", "light_dock", "shroud",
    "wedge_plate", "knob",
]


def _commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "?"


def assembled(p: Params) -> dict:
    """The printed solids in place at SLIDE (mockup coordinates: y up, the table at y = 0), as STLs, in assembly order;
    the film and the CS-Lite as boxes."""
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
    refs = [
        {"name": name, "label": label, "box": [round(v, 4) for v in cadutil.bounds(placed[name])]}
        for name, label in (("film", "Film strip"), ("cs_lite", "CS-Lite"))
    ]
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
