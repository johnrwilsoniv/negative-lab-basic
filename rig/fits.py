"""The mating fits, measured on the assembled solids (not read from params.py).

`report(p, slide, lock)` takes `assembly.placed(p, False)` and `assembly.placed(p, True)`, measures each
fit with thin probes and the exact bounds of what they take from a solid (cadutil), and sets it
against what the design intends, which params.py gives. A fit that cannot be measured, say because a
solid is missing, is a failed fit, not an exception.
"""

import functools
from dataclasses import dataclass
from typing import Callable, Mapping, Sequence

import cadquery as cq

import cadutil
from params import Params

Solids = Mapping[str, cq.Workplane]

TOL = 1e-5      # mm: measured against intended. The thin probes cost ~1e-8 on a curved face.
SLICE = 0.001   # half the thickness of the probes that find an edge along a ray
REACH = 100     # how far a ray looks
TOP = "+y"      # the side the gate's front-wall hole breaks through (ruling R8)


@dataclass(frozen=True)
class Fit:
    label: str
    measured: float | None      # None: could not be measured
    expected: float
    tol: float = TOL
    note: str = ""

    @property
    def ok(self) -> bool:
        return self.measured is not None and abs(self.measured - self.expected) <= self.tol


# ---- measuring ----------------------------------------------------------------------


def _slice_bounds(wp: cq.Workplane, *ranges: float) -> cadutil.Bounds:
    """The bounds of what the probe over `ranges` (x0 x1 y0 y1 z0 z1) takes from `wp`; LookupError if nothing."""
    hit = cadutil.common_bounds(wp, cadutil.probe(*ranges))
    if hit is None:
        raise LookupError(f"nothing in the probe {ranges}")
    return hit


def _rays(wp: cq.Workplane, p: Params, x0: float, x1: float) -> dict[str, float | None]:
    """Distance from the lens axis to the nearest material of `wp` between x0 and x1, along each of
    +y, -y, +z, -z; None where there is none."""
    t = SLICE
    aim = {      # y0, y1, z0, z1
        "+y": (p.axis, p.axis + REACH, -t, t),
        "-y": (p.axis - REACH, p.axis, -t, t),
        "+z": (p.axis - t, p.axis + t, 0, REACH),
        "-z": (p.axis - t, p.axis + t, -REACH, 0),
    }
    out: dict[str, float | None] = {}
    for side, (y0, y1, z0, z1) in aim.items():
        hit = cadutil.common_bounds(wp, cadutil.probe(x0, x1, y0, y1, z0, z1))
        if hit is None:
            out[side] = None
        else:
            _, _, ya, yb, za, zb = hit
            out[side] = {"+y": ya - p.axis, "-y": p.axis - yb, "+z": za, "-z": -zb}[side]
    return out


def _walled(rays: dict[str, float | None], what: str) -> dict[str, float]:
    """`rays` with a distance on every side; LookupError if `what` has no wall toward one."""
    gone = [side for side, distance in rays.items() if distance is None]
    if gone:
        raise LookupError(f"{what} has no wall toward {', '.join(gone)}")
    return {side: distance for side, distance in rays.items() if distance is not None}


def _outer_radii(wp: cq.Workplane, p: Params) -> dict[str, float]:
    """How far `wp` reaches from the lens axis along +y, -y, +z, -z."""
    _, _, ya, yb, za, zb = cadutil.bounds(wp)
    return {"+y": yb - p.axis, "-y": p.axis - ya, "+z": zb, "-z": -za}


def _radial_clearance(tube: cq.Workplane, bore: cq.Workplane, p: Params, x0: float) -> tuple[float, str]:
    """Smallest gap between the tube's outside and the bore of `bore` around it (looked at from x0 + 1 to x0 + 2),
    and a note on any side where `bore` has no wall."""
    reach = _outer_radii(tube, p)
    walls = _rays(bore, p, x0 + 1, x0 + 2)
    gaps = {side: walls[side] - reach[side] for side in reach if walls[side] is not None}
    if not gaps:
        raise LookupError("nothing around the tube")
    open_sides = [side for side in reach if walls[side] is None]
    note = ""
    if open_sides:
        note = f"no wall toward {', '.join(open_sides)}" + (
            " (the hole breaks through the top edge, R8)" if TOP in open_sides else ""
        )
    return min(gaps.values()), note


def _face(wp: cq.Workplane, p: Params, back: bool) -> float:
    """x of a plate's front (back=False) or back face, probed below the window where there is only plate."""
    hit = _slice_bounds(wp, p.x_film - 6, p.x_film + 6, p.wall + 1, p.wall + 5, -10, 10)
    return hit[1] if back else hit[0]


def _window_z_edges(wp: cq.Workplane, p: Params, x0: float, x1: float) -> tuple[float, float]:
    """z of the window's two edges on the lens axis, in the plate between x0 and x1."""
    t = SLICE
    left = _slice_bounds(wp, x0, x1, p.axis - t, p.axis + t, -REACH, 0)[5]
    right = _slice_bounds(wp, x0, x1, p.axis - t, p.axis + t, 0, REACH)[4]
    return left, right


def _wedge_window_clearance(solids: Solids, p: Params) -> float:
    """How far, in z, the frame window (in the front plate) is inside the wedge plate's window."""
    wedge = cadutil.bounds(solids["wedge_plate"])
    rear = _face(solids["gate_box"], p, back=True)
    frame_l, frame_r = _window_z_edges(solids["gate_box"], p, rear - 1.0, rear - 0.1)
    wedge_l, wedge_r = _window_z_edges(solids["wedge_plate"], p, wedge[0], wedge[1])
    return min(frame_l - wedge_l, wedge_r - frame_r)


def _tab_slot(solids: Solids, p: Params) -> dict[str, float]:
    """x clearance each side of the tab in the lid's slot, and z clearance from the tab to each end of the slot."""
    lid, wedge = solids["gate_lid"], solids["wedge_plate"]
    top = cadutil.bounds(lid)[3]
    y0, y1 = top - p.wall + 0.5, top - 0.5      # within the lid's thickness, above the wedge plate: only the tab
    wx0, wx1 = cadutil.bounds(wedge)[:2]
    tx0, tx1, _, _, tz0, tz1 = _slice_bounds(wedge, wx0 - 1, wx1 + 1, y0, y1, -REACH, REACH)
    return {
        "front": tx0 - _slice_bounds(lid, tx0 - 3, tx0, y0, y1, tz0, tz1)[1],
        "rear": _slice_bounds(lid, tx1, tx1 + 3, y0, y1, tz0, tz1)[0] - tx1,
        "z": min(
            tz0 - _slice_bounds(lid, tx0, tx1, y0, y1, -REACH, tz0)[5],
            _slice_bounds(lid, tx0, tx1, y0, y1, tz1, REACH)[4] - tz1,
        ),
    }


def _gap(lower: cq.Workplane, upper: cq.Workplane, axis: int, *ranges: float) -> float:
    """How far `upper` starts beyond where `lower` ends along x (axis 0), y (1) or z (2), both measured on what
    the probe over `ranges` (x0 x1 y0 y1 z0 z1) takes from them."""
    return _slice_bounds(upper, *ranges)[2 * axis] - _slice_bounds(lower, *ranges)[2 * axis + 1]


def _plate_clearances(solids: Solids, p: Params) -> dict[str, float]:
    """The pressure plate's clearance to the floor, to the lid, and to the nearer side wall, each probed in the
    plate's own shadow: its x and z span for the floor and lid; its x span, below the film slots, for the walls."""
    plate, box, lid = solids["pressure_plate"], solids["gate_box"], solids["gate_lid"]
    x0, x1, y0, y1, z0, z1 = cadutil.bounds(plate)
    low = (p.wall + 1, p.wall + 5)              # under the film slots (and the window), as `_face` probes
    return {
        "floor": _gap(box, plate, 1, x0, x1, y0 - REACH, y1, z0, z1),
        "lid": _gap(plate, lid, 1, x0, x1, y0, y1 + REACH, z0, z1),
        "side": min(
            _gap(plate, box, 2, x0, x1, *low, 0, z1 + REACH),
            _gap(box, plate, 2, x0, x1, *low, z0 - REACH, 0),
        ),
    }


def _lid_ends(solids: Solids) -> dict[str, float]:
    """x clearance from the gate's front wall to the lid's front end, and from the lid's rear end to the rear wall,
    probed within the lid's thickness (where the box has only those two walls) and below its lettering."""
    lid, box = solids["gate_lid"], solids["gate_box"]
    x0, x1, y0, y1, _, _ = cadutil.bounds(lid)
    mid, y = (x0 + x1) / 2, (y0 + 0.5, y1 - 0.5)
    return {
        "front": _gap(box, lid, 0, x0 - REACH, mid, *y, -REACH, REACH),
        "rear": _gap(lid, box, 0, mid, x1 + REACH, *y, -REACH, REACH),
    }


def _csl_slot(solids: Solids) -> float:
    """The dock's slot between the lips, less the CS-Lite panel's thickness, probed over the panel's own span in y
    and z (inside the cheeks, above the floor)."""
    dock = solids["light_dock"]
    x0, x1, y0, y1, z0, z1 = cadutil.bounds(solids["cs_lite"])
    mid, y = (x0 + x1) / 2, (y0 + 0.5, y1)
    front = _slice_bounds(dock, x0 - REACH, mid, *y, z0, z1)[1]
    back = _slice_bounds(dock, mid, x1 + REACH, *y, z0, z1)[0]
    return (back - front) - (x1 - x0)


def _shroud_margins(solids: Solids, p: Params) -> dict[str, float]:
    """Per side, how far the shroud's opening is outside the rear wall's window: z and y."""
    box, dock = solids["gate_box"], solids["light_dock"]
    rear = cadutil.bounds(box)[1]
    window = _walled(_rays(box, p, rear - 2, rear - 1), "the rear wall")
    opening = _walled(_rays(dock, p, cadutil.bounds(dock)[0] + 1, cadutil.bounds(dock)[0] + 2), "the shroud")
    margin = {side: opening[side] - window[side] for side in window}
    return {"z": min(margin["+z"], margin["-z"]), "y": min(margin["+y"], margin["-y"])}


# ---- the report -------------------------------------------------------------------


def _fit(label: str, expected: float, measure: Callable[[], float | tuple[float, str]]) -> Fit:
    try:
        got = measure()
    except (LookupError, ValueError) as err:       # a solid missing, or nothing where the probe looks
        return Fit(label, None, expected, note=f"not measured ({type(err).__name__}: {err})")
    measured, note = got if isinstance(got, tuple) else (got, "")
    return Fit(label, measured, expected, note=note)


def report(p: Params, slide: Solids, lock: Solids) -> list[Fit]:
    """Every fit, each measured on the solids and compared with what params.py intends."""
    both = {"SLIDE": slide, "LOCK": lock}
    out = [
        _fit("tube / adapter socket, radial clearance", p.fit_clear, lambda: _radial_clearance(
            slide["tube"], slide["adapter"], p, cadutil.bounds(slide["tube"])[0])),
        _fit("tube / gate hole, radial clearance", p.fit_clear, lambda: _radial_clearance(
            slide["tube"], slide["gate_box"], p, cadutil.bounds(slide["gate_box"])[0])),
        _fit("film / front plate", 0.0,
             lambda: cadutil.bounds(slide["film"])[0] - _face(slide["gate_box"], p, back=True)),
    ]
    intended_channel = {"SLIDE": p.channel, "LOCK": p.channel - p.lock_shift}
    intended_gap = {"SLIDE": p.channel - p.film_t, "LOCK": 0.0}
    for name, solids in both.items():
        out.append(_fit(f"film channel, {name}", intended_channel[name], lambda s=solids: (
            _face(s["pressure_plate"], p, back=False) - _face(s["gate_box"], p, back=True)
        )))
        out.append(_fit(f"film / pressure plate, {name}", intended_gap[name], lambda s=solids: (
            _face(s["pressure_plate"], p, back=False) - cadutil.bounds(s["film"])[1]
        )))
    plate = functools.cache(lambda: _plate_clearances(slide, p))      # measured once for its three rows
    out += [
        _fit("pressure plate / floor, clearance", p.plate_clear, lambda: plate()["floor"]),
        _fit("pressure plate / lid, clearance", p.plate_clear, lambda: plate()["lid"]),
        _fit("pressure plate / side walls, clearance (the smaller)", p.plate_clear, lambda: plate()["side"]),
    ]
    wedge_clear = (p.wedge_win_w - p.win_w) / 2 - p.sw_travel / 2
    for name, solids in both.items():
        out.append(_fit(f"wedge window / frame window, z clearance, {name}", wedge_clear,
                        lambda s=solids: _wedge_window_clearance(s, p)))
    lid = functools.cache(lambda: _lid_ends(slide))
    out += [
        _fit("tab / lid slot, x clearance, front", p.tab_clear, lambda: _tab_slot(slide, p)["front"]),
        _fit("tab / lid slot, x clearance, rear", p.tab_clear, lambda: _tab_slot(slide, p)["rear"]),
        _fit("lid / front wall, x clearance", p.lid_clear, lambda: lid()["front"]),
        _fit("lid / rear wall, x clearance", p.lid_clear, lambda: lid()["rear"]),
    ]
    for name, solids in both.items():
        out.append(_fit(f"tab / lid slot, z clearance to the end, {name}", p.slot_end - p.tab_w / 2,
                        lambda s=solids: _tab_slot(s, p)["z"]))
    out += [
        _fit("shroud opening / rear window, z margin per side",
             (p.shroud_w - 2 * p.shroud_t - p.rear_win_w) / 2, lambda: _shroud_margins(slide, p)["z"]),
        _fit("shroud opening / rear window, y margin per side",
             (p.shroud_h - p.rear_win_h) / 2, lambda: _shroud_margins(slide, p)["y"]),
        _fit("CS-Lite slot, width less the panel", p.csl_clear, lambda: _csl_slot(slide)),
    ]
    return out


def format_report(report: Sequence[Fit]) -> str:
    header = ("fit", "measured", "intended", "result")
    cells = [
        (
            f.label,
            "-" if f.measured is None else f"{round(f.measured, 4) + 0.0:.4f}",     # + 0.0: no "-0.0000"
            f"{f.expected:.4f}",
            ("ok" if f.ok else "FAIL") + (f"  {f.note}" if f.note else ""),
        )
        for f in report
    ]
    return cadutil.format_table([header, *cells])
