"""7 · Assembly: every printed part in place with the knob at two positions, the proof they do not intersect, the STEP.

Parts return their solids in mockup coordinates already, so assembling is collecting them. Only the STEP
file is turned into Onshape's frame (`to_onshape`): Z up, the origin on the table under the film. Reference
solids stand in for what is bought (ruling R14): the straight run of film through the gate, a half-wound roll
on each spool, and the CS-Lite panel in the dock. There is no camera or lens. The film has its perforations cut
through it, and each exposed frame is its own solid filling a hole in it (film_frame_1 from -z), so the STEP can
colour the frames apart from the base.

The knob's positions (`TURNS`): a frame centred in the window, and half a sprocket tooth on, where each row has two
teeth part-way into their perforations and every gear mesh is between teeth. The sprockets, their gears and the idler
turn; the film runs with them. Nothing may intersect at either position: the teeth sit in the perforations, the
pegs, the axle and the spools' caps press into holes their own size, all only touching.
"""

import itertools
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Mapping

import cadquery as cq

import cadutil
from params import DEFAULT, Params

STEP_PATH = Path(__file__).parent / "exports" / "step" / "nlb-scan-rig-assembly.step"

TURNS = {"FRAME": 0.0, "HALF TOOTH": 1 / 16}    # knob turns from a frame centred: 1/16 is half of an 8 tooth sprocket's pitch
REFERENCE_NAMES = ("film", "roll_supply", "roll_takeup", "cs_lite")     # plus a film_frame_<n> per frame, see is_reference
CONTACT_VOLUME = 1e-3       # mm3: a common smaller than this is two solids touching
PREFILTER_GAP = 1e-6        # mm: boxes further apart than this cannot intersect (bounds are exact to ~1e-9)

# STEP colours: printed parts opaque and distinct, references grey-ish and translucent.
COLORS = {      # the twin prints (each side's sprocket, gear, spool and cap) in two shades of one hue
    "adapter": (1.0, 0.65, 0.0), "tube": (0.27, 0.51, 0.71), "gate_front": (0.1, 0.42, 0.1),
    "gate_body": (0.13, 0.55, 0.13), "sprocket_supply": (0.85, 0.2, 0.2), "gear_supply": (0.93, 0.5, 0.2),
    "sprocket_takeup": (0.7, 0.12, 0.15), "gear_takeup": (0.8, 0.4, 0.12), "idler": (0.58, 0.44, 0.86),
    "idler_axle": (0.4, 0.4, 0.45), "deck": (0.56, 0.93, 0.56), "spool_supply": (0.2, 0.6, 0.75),
    "cap_supply": (0.35, 0.75, 0.9), "spool_takeup": (0.12, 0.45, 0.6), "cap_takeup": (0.5, 0.82, 0.95),
    "light_dock": (0.63, 0.32, 0.18),
}
REFERENCE_COLORS = {
    "film": (0.66, 0.6, 0.5, 0.45), "roll_supply": (0.45, 0.38, 0.3, 0.6), "roll_takeup": (0.45, 0.38, 0.3, 0.6),
    "cs_lite": (0.75, 0.75, 0.8, 0.35),
}
FRAME_COLOR = (0.17, 0.15, 0.13, 0.75)  # the exposures: dark, as on a negative
UNKNOWN_COLOR = (0.8, 0.8, 0.8)         # a printed solid that has no colour of its own yet
PRINTED = tuple(COLORS)                 # the solids a complete rig has

Found = tuple[str, str, float]          # a, b, common volume


def _modules(modules: Mapping[str, ModuleType] | None) -> Mapping[str, ModuleType]:
    if modules is None:
        import build        # build.py imports this module, so it cannot be imported at the top
        return build.discover()
    return modules


def parts(
    p: Params = DEFAULT, turn: float = 0.0, modules: Mapping[str, ModuleType] | None = None
) -> dict[str, cq.Workplane]:
    """Every printed solid of every part (not the print-only extras), in mockup coordinates, the knob at `turn`."""
    solids: dict[str, cq.Workplane] = {}
    for part, model in _modules(modules).items():
        for name, wp in model.build(p, turn).items():
            if name in solids:
                raise ValueError(f"solid name {name!r} (part {part}) is built by more than one part")
            solids[name] = wp
    return solids


def is_reference(name: str) -> bool:
    return name in REFERENCE_NAMES or name.startswith("film_frame_")


def _frames(p: Params, x0: float, dz: float) -> list[cq.Workplane]:
    """The exposed frames, frame_w along z by frame_h across, centred on the axis, each one solid."""
    return [cadutil.probe(
        x0, x0 + p.film_t, p.axis - p.frame_h / 2, p.axis + p.frame_h / 2, dz + z - p.frame_w / 2, dz + z + p.frame_w / 2
    ) for z in p.frame_zs]


def _perforations(p: Params, x0: float, dz: float) -> cq.Workplane:
    """Both rows of perforations, as one cutter: rounded rectangles through the film's thickness."""
    ys = (p.axis - p.perf_dy, p.axis + p.perf_dy)
    return (
        cq.Workplane("YZ", origin=(x0, 0, 0))           # local x is y, local y is z, extruded along +x
        .pushPoints([(y, dz + z) for y in ys for z in p.perf_zs])
        .rect(p.perf_w, p.perf_l)
        .extrude(p.film_t)
        .edges("|X").fillet(p.perf_r)
    )


def _roll(p: Params, sign: int) -> cq.Workplane:
    """Half the roll, wound on the spool at sign * spool_z: from the core to roll_r_half, the film's width."""
    y0, y1 = p.axis - p.film_w / 2, p.axis + p.film_w / 2
    z = sign * p.spool_z
    outer = cadutil.cylinder_y(p.x_spool, z, p.roll_r_half, y0, y1)
    return outer.cut(cadutil.cylinder_y(p.x_spool, z, p.spool_core_r, y0 - 1, y1 + 1))


def references(p: Params = DEFAULT, turn: float = 0.0) -> dict[str, cq.Workplane]:
    """The film through the gate, its frames, the two rolls and the CS-Lite panel. The film runs turn frames toward +z,
    the rolls and the panel stay."""
    x0, dz = p.x_film - p.film_t / 2, turn * p.frame_pitch       # the film's mid-plane is the film plane
    strip = cadutil.probe(
        x0, x0 + p.film_t, p.axis - p.film_w / 2, p.axis + p.film_w / 2,
        dz - p.film_strip_len / 2, dz + p.film_strip_len / 2,
    )
    frames = _frames(p, x0, dz)
    film = strip.cut(_perforations(p, x0, dz))
    for frame in frames:
        film = film.cut(frame)
    cs_lite = cadutil.probe(
        p.x_light, p.x_light + p.csl_t, p.floor_t, p.floor_t + p.csl_h, -p.csl_l / 2, p.csl_l / 2
    )
    return {
        "film": film, **{f"film_frame_{i}": f for i, f in enumerate(frames, 1)},
        "roll_supply": _roll(p, -1), "roll_takeup": _roll(p, 1), "cs_lite": cs_lite,
    }


def placed(
    p: Params = DEFAULT, turn: float = 0.0, modules: Mapping[str, ModuleType] | None = None
) -> dict[str, cq.Workplane]:
    """The printed solids, then the references."""
    return {**parts(p, turn, modules), **references(p, turn)}


def pairs(solids: Mapping[str, cq.Workplane]) -> list[tuple[str, str]]:
    """Every two printed solids, and every printed solid with each reference; references not with each other."""
    return [
        (a, b) for a, b in itertools.combinations(solids, 2)
        if not (is_reference(a) and is_reference(b))
    ]


def _apart(a: cadutil.Bounds, b: cadutil.Bounds) -> bool:
    """Whether the boxes are separated by a gap on some axis, so the solids cannot intersect."""
    return any(
        max(a[i], b[i]) - min(a[i + 1], b[i + 1]) > PREFILTER_GAP for i in (0, 2, 4)
    )


def interference(p: Params = DEFAULT, turn: float = 0.0, solids: Mapping[str, cq.Workplane] | None = None) -> list[Found]:
    """(a, b, common volume) for every pair whose common volume exceeds CONTACT_VOLUME.

    `solids` is `placed(p, turn)` when not given. Touching solids (zero volume) are not interference.
    """
    solids = placed(p, turn) if solids is None else solids
    boxes = {name: cadutil.bounds(wp) for name, wp in solids.items()}
    found: list[Found] = []
    for a, b in pairs(solids):
        if _apart(boxes[a], boxes[b]):
            continue
        volume = cadutil.common_volume(solids[a], solids[b])
        if volume > CONTACT_VOLUME:
            found.append((a, b, volume))
    return found


def problems(found: list[Found]) -> list[str]:
    """What is wrong with the interference result `found`: nothing may intersect."""
    return [f"{a} and {b} intersect by {volume:.4g} mm3" for a, b, volume in found]


def to_onshape(p: Params, wp: cq.Workplane) -> cq.Workplane:
    """`wp` in the assembly STEP's frame, which fits Onshape's default planes.

    Z is up (mockup y), so the Top plane is the table. Y runs along the optical axis from the camera to the light
    (mockup x - x_film), so the Front plane is the film plane, the Front view looks into the adapter, and so does
    the default isometric (from +X, -Y, +Z). X = mockup z, so the Right plane is the vertical plane through the
    axis and the Right view shows the rig's side. The origin is on the table under the film's centre.
    """
    z_up = wp.translate((-p.x_film, 0, 0)).rotate((0, 0, 0), (1, 0, 0), 90)
    return z_up.rotate((0, 0, 0), (0, 0, 1), 90)


def _step_name(name: str) -> str:
    return f"ref_{name}" if is_reference(name) else name


def write_step(
    p: Params = DEFAULT, path: Path | str = STEP_PATH, solids: Mapping[str, cq.Workplane] | None = None
) -> None:
    """The assembly with a frame centred, in the Onshape frame (`to_onshape`), one named and coloured solid per part.

    The references are named ref_film, ref_film_frame_<n>, ref_roll_supply, ref_roll_takeup and ref_cs_lite,
    translucent; the frames darker.
    """
    solids = placed(p) if solids is None else solids
    asm = cq.Assembly(name="nlb-scan-rig")
    for name, wp in solids.items():
        wp = to_onshape(p, wp)
        if is_reference(name):
            asm.add(wp, name=_step_name(name), color=cq.Color(*REFERENCE_COLORS.get(name, FRAME_COLOR)))
        else:
            asm.add(wp, name=name, color=cq.Color(*COLORS.get(name, UNKNOWN_COLOR), 1.0))
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    asm.export(str(path))


@dataclass(frozen=True)
class StepCheck:
    count: int              # solids in the file
    volume: float           # their total volume
    expected: float         # total volume of the solids written
    problems: list[str]

    @property
    def error(self) -> float:
        """Relative difference of the total volume."""
        return abs(self.volume - self.expected) / self.expected


def check_step(path: Path | str, solids: Mapping[str, cq.Workplane]) -> StepCheck:
    """Re-import the assembly STEP and compare it with the `solids` written: the names, each volume, the total."""
    read = cadutil.step_assembly(path)
    wrote = {_step_name(name): wp for name, wp in solids.items()}
    messages = [f"{name} is not in the STEP file" for name in wrote if name not in read]
    messages += [f"{name} is in the STEP file but was not written" for name in read if name not in wrote]
    volumes = {name: cadutil.volume(part.solid) for name, part in read.items()}
    for name in wrote.keys() & read.keys():
        was = cadutil.volume(wrote[name])
        if abs(volumes[name] - was) > cadutil.STEP_VOLUME_RTOL * was:
            messages.append(f"{name} changes volume in the STEP file: {was:.6g} -> {volumes[name]:.6g} mm3")
    total = sum(volumes.values())
    expected = sum(cadutil.volume(wp) for wp in wrote.values())
    if abs(total - expected) > cadutil.STEP_VOLUME_RTOL * expected:
        messages.append(f"the STEP file's total volume is {total:.6g} mm3, not the {expected:.6g} written")
    return StepCheck(len(read), total, expected, messages)
