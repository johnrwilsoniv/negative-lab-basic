"""7 · Assembly: every printed part in place at SLIDE or LOCK, the proof they do not intersect, the STEP.

Parts return their solids in mockup coordinates already, so assembling is collecting them. Only the STEP
file is turned into Onshape's frame (`to_onshape`): Z up, the origin on the table under the film. Two
reference solids stand in for what is bought (ruling R14): the film strip, lying against the front
plate's rear face, and the CS-Lite panel in the dock. There is no camera or lens.

At LOCK the pressure plate's pads press `preload` into the wedge plate's ramps; the rigid model has no
other way to show the clamp, so that is the one overlap allowed (ruling R7). The film does not move: the
pressure plate only comes to touch it.
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

REFERENCE_NAMES = ("film", "cs_lite")
CONTACT_VOLUME = 1e-3       # mm3: a common smaller than this is two solids touching
PREFILTER_GAP = 1e-6        # mm: boxes further apart than this cannot intersect (bounds are exact to ~1e-9)
PRELOAD_TOL = 0.005         # mm: how far the pads' overlap may be from the designed preload

# STEP colours: printed parts opaque and distinct, references grey-ish and translucent.
COLORS = {
    "adapter": (1.0, 0.65, 0.0), "tube": (0.27, 0.51, 0.71), "gate_box": (0.13, 0.55, 0.13),
    "gate_lid": (0.56, 0.93, 0.56), "pressure_plate": (0.58, 0.44, 0.86), "wedge_plate": (0.85, 0.2, 0.2),
    "knob": (1.0, 0.84, 0.0), "light_dock": (0.63, 0.32, 0.18),
}
REFERENCE_COLORS = {"film": (0.45, 0.45, 0.45, 0.45), "cs_lite": (0.75, 0.75, 0.8, 0.35)}
UNKNOWN_COLOR = (0.8, 0.8, 0.8)         # a printed solid that has no colour of its own yet
PRINTED = tuple(COLORS)                 # the solids a complete rig has

Found = tuple[str, str, float, float]       # a, b, common volume, x-thickness of the common


def _modules(modules: Mapping[str, ModuleType] | None) -> Mapping[str, ModuleType]:
    if modules is None:
        import build        # build.py imports this module, so it cannot be imported at the top
        return build.discover()
    return modules


def parts(
    p: Params = DEFAULT, lock: bool = False, modules: Mapping[str, ModuleType] | None = None
) -> dict[str, cq.Workplane]:
    """Every printed solid of every part (not the print-only extras), in mockup coordinates."""
    solids: dict[str, cq.Workplane] = {}
    for part, model in _modules(modules).items():
        for name, wp in model.build(p, lock).items():
            if name in solids:
                raise ValueError(f"solid name {name!r} (part {part}) is built by more than one part")
            solids[name] = wp
    return solids


def references(p: Params = DEFAULT, lock: bool = False) -> dict[str, cq.Workplane]:
    """The film strip and the CS-Lite panel. Neither moves with `lock`."""
    x0 = p.x_film - p.channel / 2            # against the front plate's rear face
    film = cadutil.probe(
        x0, x0 + p.film_t,
        p.axis - p.film_w / 2, p.axis + p.film_w / 2,
        p.film_strip_z - p.film_strip_len / 2, p.film_strip_z + p.film_strip_len / 2,
    )
    cs_lite = cadutil.probe(
        p.x_light, p.x_light + p.csl_t, p.floor_t, p.floor_t + p.csl_h, -p.csl_l / 2, p.csl_l / 2
    )
    return {"film": film, "cs_lite": cs_lite}


def placed(
    p: Params = DEFAULT, lock: bool = False, modules: Mapping[str, ModuleType] | None = None
) -> dict[str, cq.Workplane]:
    """The printed solids, then the references."""
    return {**parts(p, lock, modules), **references(p, lock)}


def pairs(solids: Mapping[str, cq.Workplane]) -> list[tuple[str, str]]:
    """Every two printed solids, and every printed solid with each reference; references not with each other."""
    return [
        (a, b) for a, b in itertools.combinations(solids, 2)
        if not (a in REFERENCE_NAMES and b in REFERENCE_NAMES)
    ]


def _apart(a: cadutil.Bounds, b: cadutil.Bounds) -> bool:
    """Whether the boxes are separated by a gap on some axis, so the solids cannot intersect."""
    return any(
        max(a[i], b[i]) - min(a[i + 1], b[i + 1]) > PREFILTER_GAP for i in (0, 2, 4)
    )


def interference(
    p: Params = DEFAULT, lock: bool = False, solids: Mapping[str, cq.Workplane] | None = None
) -> list[Found]:
    """(a, b, common volume, x-thickness) for every pair whose common volume exceeds CONTACT_VOLUME.

    `solids` is `placed(p, lock)` when not given. Touching solids (zero volume) are not interference.
    The x-thickness is the common's volume over its footprint (the bounding rectangle in y and z of each
    solid in it): how deep the one goes into the other, however its faces slope. That is exact for a
    prism between two parallel planes, which is what a pad pressed into a ramp is. The common's own
    x-extent would add the rise of the slope across it (0.29 for the pads, not the 0.11 preload).
    """
    solids = placed(p, lock) if solids is None else solids
    boxes = {name: cadutil.bounds(wp) for name, wp in solids.items()}
    found: list[Found] = []
    for a, b in pairs(solids):
        if _apart(boxes[a], boxes[b]):
            continue
        pieces = cadutil.common_pieces(solids[a], solids[b])
        volume = sum(v for v, _ in pieces)
        if volume > CONTACT_VOLUME:
            footprint = sum((box[3] - box[2]) * (box[5] - box[4]) for _, box in pieces)
            found.append((a, b, volume, volume / footprint))
    return found


def allowed(p: Params = DEFAULT, lock: bool = False) -> list[tuple[str, str, float]]:
    """The overlaps the design wants, as (a, b, x-thickness): at LOCK the pads in the ramps (ruling R7)."""
    return [("pressure_plate", "wedge_plate", p.preload)] if lock else []


def problems(p: Params, lock: bool, found: list[Found]) -> list[str]:
    """What is wrong with the interference result `found`: any overlap that is not allowed, any allowed one missing."""
    wanted = {frozenset((a, b)): thickness for a, b, thickness in allowed(p, lock)}
    messages = []
    seen = set()
    for a, b, volume, thickness in found:
        key = frozenset((a, b))
        if key not in wanted:
            messages.append(f"{a} and {b} intersect by {volume:.4g} mm3 (x-thickness {thickness:.4g})")
        elif abs(thickness - wanted[key]) > PRELOAD_TOL:
            messages.append(f"{a} and {b} overlap {thickness:.4g} thick, not the {wanted[key]:.4g} designed")
        seen.add(key)
    for key, thickness in wanted.items():
        if key not in seen:
            a, b = sorted(key)
            messages.append(f"{a} and {b} should overlap {thickness:.4g} thick and do not touch")
    return messages


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
    return f"ref_{name}" if name in REFERENCE_NAMES else name


def write_step(
    p: Params = DEFAULT, path: Path | str = STEP_PATH, solids: Mapping[str, cq.Workplane] | None = None
) -> None:
    """The assembly at SLIDE, in the Onshape frame (`to_onshape`), one named and coloured solid per part.

    The references are named ref_film and ref_cs_lite, grey and translucent.
    """
    solids = placed(p, False) if solids is None else solids
    asm = cq.Assembly(name="nlb-scan-rig")
    for name, wp in solids.items():
        wp = to_onshape(p, wp)
        if name in REFERENCE_NAMES:
            asm.add(wp, name=_step_name(name), color=cq.Color(*REFERENCE_COLORS[name]))
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
