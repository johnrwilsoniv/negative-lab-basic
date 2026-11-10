"""The mating fits, measured on the assembled solids (not read from params.py).

`report(p, solids)` takes `assembly.placed(p)` (a frame centred), measures each
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
TOP = "+y"      # the side the gate front's tube socket breaks through (ruling R8)


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


def _outer_radii(wp: cq.Workplane, p: Params) -> dict[str, float]:
    """How far `wp` reaches from the lens axis along +y, -y, +z, -z."""
    _, _, ya, yb, za, zb = cadutil.bounds(wp)
    return {"+y": yb - p.axis, "-y": p.axis - ya, "+z": zb, "-z": -za}


def _radial_clearance(
    tube: cq.Workplane, bore: cq.Workplane, p: Params, x0: float, top: str = "the hole breaks through the top edge, R8"
) -> tuple[float, str]:
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
            f" ({top})" if TOP in open_sides else ""
        )
    return min(gaps.values()), note




def _x_face(wp: cq.Workplane, p: Params, near: bool) -> float:
    """x of the near (lens side, near=True: its least x) or far face of `wp` in the channel's height, beside the window,
    between the sprocket pocket and the lead-in (z 38 .. 42): where the gate front and the gate body face each other."""
    hit = _slice_bounds(wp, p.x_film - 6, p.x_film + 6, p.axis - 5, p.axis + 5, 38, 42)
    return hit[0] if near else hit[1]


def _channel_height(body: cq.Workplane, p: Params) -> float:
    """The channel's walls in y, probed in its depth at z 38 .. 42."""
    x = (p.x_ref + 0.01, p.x_ref + p.channel / 2)
    top = _slice_bounds(body, *x, p.axis, p.axis + REACH, 38, 42)[2]
    bottom = _slice_bounds(body, *x, p.axis - REACH, p.axis, 38, 42)[3]
    return top - bottom


def _on_line(wp: cq.Workplane, x0: float, x1: float, y0: float, y1: float, z: float) -> cadutil.Bounds:
    """What `wp` has in x0 .. x1, y0 .. y1, on the plane z (a SLICE either side)."""
    return _slice_bounds(wp, x0, x1, y0, y1, z - SLICE, z + SLICE)


def _drive(solids: Solids, p: Params) -> dict[str, float]:
    """The supply side's sprocket against the film, the gate front's groove, its pocket, its two bearings and its gear's
    D-bore; the idler on its axle; the axle in the deck. A frame is centred, so tooth 0 points at the film."""
    sp, front, body, deck = solids["sprocket_supply"], solids["gate_front"], solids["gate_body"], solids["deck"]
    xs, zs = p.x_sprocket, -p.sprocket_z
    row = p.axis - p.perf_dy
    film_back = cadutil.bounds(solids["film"])[1]
    y_deck = p.y_deck + p.deck_t / 2
    y_gear = p.y_gear + p.gear_t / 2
    shaft = _on_line(sp, xs, xs + REACH, y_deck - 1, y_deck + 1, zs)[1]
    return {
        "ring": _on_line(sp, xs - REACH, xs, p.y_ring_lo[0] + 0.2, p.y_ring_lo[0] + 1.5, zs)[0] - film_back,
        "groove": (_on_line(sp, xs - REACH, p.x_ref, row - 0.1, row + 0.1, zs)[0]
                   - _on_line(front, p.x_ref - 3, p.x_ref, row - 0.1, row + 0.1, zs)[1]),
        "pocket": (_on_line(body, xs + 1, xs + REACH, row - 0.1, row + 0.1, zs)[0]
                   - _on_line(sp, xs, xs + REACH, row - 0.1, row + 0.1, zs)[1]),
        "deck": _on_line(deck, xs, xs + REACH, y_deck - 1, y_deck + 1, zs)[0] - shaft,
        "floor": (_on_line(body, xs, xs + REACH, p.shaft_floor + 2, p.shaft_floor + 6, zs)[0]
                  - _on_line(sp, xs, xs + REACH, p.shaft_floor + 2, p.shaft_floor + 6, zs)[1]),
        "flat": (_slice_bounds(solids["gear_supply"], xs - SLICE, xs + SLICE, y_gear - 1, y_gear + 1, zs, zs + 5)[4]
                 - _slice_bounds(sp, xs - SLICE, xs + SLICE, y_gear - 1, y_gear + 1, zs, zs + 5)[5]),
        "idler": (_on_line(solids["idler"], xs, xs + REACH, y_gear - 1, y_gear + 1, 0)[0]
                  - _on_line(solids["idler_axle"], xs, xs + REACH, y_gear - 1, y_gear + 1, 0)[1]),
        "axle": (_on_line(deck, xs, xs + REACH, y_deck - 1, y_deck + 1, 0)[0]
                 - _on_line(solids["idler_axle"], xs, xs + REACH, y_deck - 1, y_deck + 1, 0)[1]),
    }


def _peg(solids: Solids, p: Params) -> float:
    """The lower +z peg in its hole, radially toward +z."""
    y, z = p.peg_points[1]
    x = (p.x_ref - p.peg_len + 1, p.x_ref - 1)
    peg = _slice_bounds(solids["gate_body"], *x, y - SLICE, y + SLICE, z, z + REACH)[5]
    hole = _slice_bounds(solids["gate_front"], *x, y - SLICE, y + SLICE, z, z + REACH)[4]
    return hole - peg


def _spool(solids: Solids, p: Params) -> dict[str, float]:
    """The supply spool: its flanges to the roll's edges, its bore on the dock's pin, the cap's spigot in its socket."""
    sp, cap, roll, dock = solids["spool_supply"], solids["cap_supply"], solids["roll_supply"], solids["light_dock"]
    xs, zs = p.x_spool, -p.spool_z
    r = (p.spool_core_r + p.roll_r_half) / 2        # in the roll, between the core and its outside
    _, _, ry0, ry1, _, _ = cadutil.bounds(roll)
    y_socket = p.y_spool + p.spool_core_h - p.cap_spigot_h / 2
    return {
        "lower": ry0 - _on_line(sp, xs + r - 0.5, xs + r + 0.5, ry0 - REACH, ry0, zs)[3],
        "upper": _on_line(cap, xs + r - 0.5, xs + r + 0.5, ry1, ry1 + REACH, zs)[2] - ry1,
        "pin": (_on_line(sp, xs, xs + REACH, p.y_spool + 5, p.y_spool + 10, zs)[0]
                - _on_line(dock, xs, xs + REACH, p.y_spool + 5, p.y_spool + 10, zs)[1]),
        "cap": (_on_line(sp, xs + 1, xs + REACH, y_socket - 0.5, y_socket + 0.5, zs)[0]
                - _on_line(cap, xs, xs + REACH, y_socket - 0.5, y_socket + 0.5, zs)[1]),
    }


def _gate_seat(solids: Solids, p: Params) -> dict[str, float]:
    """The gate body's clearance to the dock's notch in z (the smaller), probed in the floor's thickness over the
    floor arms; how far the body's rear face is in front of the CS-Lite's lit face, probed beside its light passage;
    and the floor's edge in front of the gate front, in x."""
    dock, body, front = solids["light_dock"], solids["gate_body"], solids["gate_front"]
    x0, x1 = cadutil.bounds(body)[0] + p.peg_len, cadutil.bounds(solids["cs_lite"])[0]
    floor = (0.5, p.floor_t - 0.5)
    beside = (p.axis - 1, p.axis + 1, p.rear_win_w / 2 + 1, p.gw / 2 - 1)
    return {
        "z": min(
            _gap(body, dock, 2, x0, x1, *floor, 0, REACH),
            _gap(dock, body, 2, x0, x1, *floor, -REACH, 0),
        ),
        "light": x1 - _slice_bounds(body, x1 - REACH, x1 + REACH, *beside)[1],
        "front": _gap(dock, front, 0, p.x_gate - REACH, p.x_gate + 1, *floor, -10, 10),
    }


# ---- the report -------------------------------------------------------------------


def _fit(label: str, expected: float, measure: Callable[[], float | tuple[float, str]]) -> Fit:
    try:
        got = measure()
    except (LookupError, ValueError, KeyError) as err:      # a solid missing, or nothing where the probe looks
        return Fit(label, None, expected, note=f"not measured ({type(err).__name__}: {err})")
    measured, note = got if isinstance(got, tuple) else (got, "")
    return Fit(label, measured, expected, note=note)


def report(p: Params, solids: Solids) -> list[Fit]:
    """Every fit, each measured on the solids (a frame centred) and compared with what params.py intends."""
    s = solids
    drive = functools.cache(lambda: _drive(s, p))
    spool = functools.cache(lambda: _spool(s, p))
    seat = functools.cache(lambda: _gate_seat(s, p))
    return [
        _fit("tube / adapter socket, radial clearance", p.fit_clear, lambda: _radial_clearance(
            s["tube"], s["adapter"], p, cadutil.bounds(s["tube"])[0])),
        _fit("tube / gate front socket, radial clearance", p.fit_clear, lambda: _radial_clearance(
            s["tube"], s["gate_front"], p, cadutil.bounds(s["gate_front"])[0])),
        _fit("film channel, gate front to gate body", p.channel,
             lambda: _x_face(s["gate_body"], p, near=True) - _x_face(s["gate_front"], p, near=False)),
        _fit("film / gate front (reference plane)", (p.channel - p.film_t) / 2,
             lambda: cadutil.bounds(s["film"])[0] - _x_face(s["gate_front"], p, near=False)),
        _fit("film channel height less the film", p.channel_clear, lambda: _channel_height(s["gate_body"], p) - p.film_w),
        _fit("peg / hole in the gate front, radial", p.peg_fit / 2, lambda: _peg(s, p)),
        _fit("film / sprocket rings", p.ring_clear, lambda: drive()["ring"]),
        _fit("tooth tip / groove in the gate front", p.relief_clear, lambda: drive()["groove"]),
        _fit("tooth tip / sprocket pocket, radial", p.pocket_clear, lambda: drive()["pocket"]),
        _fit("sprocket shaft / deck bearing, radial", p.bearing_clear, lambda: drive()["deck"]),
        _fit("sprocket shaft / gate body bearing, radial", p.bearing_clear, lambda: drive()["floor"]),
        _fit("gear's D-bore / shaft's flat", p.flat_clear, lambda: drive()["flat"]),
        _fit("idler / its axle, radial", p.bearing_clear, lambda: drive()["idler"]),
        _fit("idler axle / deck (pressed)", 0.0, lambda: drive()["axle"]),
        _fit("spool's lower flange / roll", p.spool_clear, lambda: spool()["lower"]),
        _fit("cap / roll", p.spool_clear, lambda: spool()["upper"]),
        _fit("spool / dock pin, radial", p.bearing_clear, lambda: spool()["pin"]),
        _fit("cap spigot / spool socket (pressed)", 0.0, lambda: spool()["cap"]),
        _fit("CS-Lite slot, width less the panel", p.csl_clear, lambda: _csl_slot(s)),
        _fit("gate body / dock notch, z clearance (the smaller)", p.dock_gate_clear, lambda: seat()["z"]),
        _fit("gate body rear face / CS-Lite lit face", 0.0, lambda: seat()["light"]),
        _fit("gate front / dock floor's edge, x clearance", p.dock_gate_clear, lambda: seat()["front"]),
    ]


def _gap(lower: cq.Workplane, upper: cq.Workplane, axis: int, *ranges: float) -> float:
    """How far `upper` starts beyond where `lower` ends along x (axis 0), y (1) or z (2), both measured on what
    the probe over `ranges` (x0 x1 y0 y1 z0 z1) takes from them."""
    return _slice_bounds(upper, *ranges)[2 * axis] - _slice_bounds(lower, *ranges)[2 * axis + 1]


def _csl_slot(solids: Solids) -> float:
    """The dock's slot between the lips, less the CS-Lite panel's thickness, probed over the panel's own span in y
    and z (inside the cheeks, above the floor)."""
    dock = solids["light_dock"]
    x0, x1, y0, y1, z0, z1 = cadutil.bounds(solids["cs_lite"])
    mid, y = (x0 + x1) / 2, (y0 + 0.5, y1)
    front = _slice_bounds(dock, x0 - REACH, mid, *y, z0, z1)[1]
    back = _slice_bounds(dock, mid, x1 + REACH, *y, z0, z1)[0]
    return (back - front) - (x1 - x0)


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
