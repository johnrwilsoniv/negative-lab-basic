"""5 · Lock switch: the wedge plate (with its tab and four ramps) and the knob.

Mockup `rebuild()` lines 422-442 (the `sl` group) and the lock animation at 686-690. The switch
slides along z inside the gate. Its wedge plate sits behind the pressure plate; the plate's four
ramps run under the pressure plate's four sloped pads (film_gate `_pad`) and push it forward to
clamp the film at LOCK. The tab rises through the lid's slot to the knob, a separate print that
sits on the lid top.

Everything is drawn at s = 0 (switch centred) and then moved along z, as the mockup's `sl` group
is: SLIDE is s = -sw_travel/2, LOCK s = +sw_travel/2.

The ramps are extruded from a profile in (x, z), so each face is a plane; it's the same profile
film_gate's pads use, mirrored across the gap, so at SLIDE the two faces coincide and at LOCK
they overlap by `preload` (rulings R6, R7).

Not modelled (ruling R3, R15): the knob's snap onto the tab, the lid-slot detent bumps, and the
grooves that guide the wedge plate along z. The surfaces where they would attach (the tab's top,
the lid slot's ends, the plate's z edges) are left plain.
"""

import cadquery as cq

from params import DEFAULT, Params

# Wedge plate on its bottom edge: the ramp slopes are traced in XY, not stepped by layers as thick as the preload.
# The knob prints flat with the grip ridges up.
PRINT_UP = {"wedge_plate": "+y", "knob": "+y"}


def _shift(p: Params, lock: bool) -> float:
    """Where the switch is along z: -sw_travel/2 at SLIDE (the knob toward -z), +sw_travel/2 at LOCK."""
    return p.sw_travel / 2 if lock else -p.sw_travel / 2


def _plate(p: Params) -> cq.Workplane:
    """x_wedge .. +wedge_t, z +-wedge_w/2, between the floor and the lid, with the window on the axis."""
    y0, y1 = p.wall + p.wedge_clear, p.gh - p.wall - p.wedge_clear
    return (
        cq.Workplane("YZ", origin=(p.x_wedge, 0, 0))
        .moveTo((y0 + y1) / 2, 0).rect(y1 - y0, p.wedge_w)
        .moveTo(p.axis, 0).rect(p.win_h, p.wedge_win_w)
        .extrude(p.wedge_t)
    )


def _tab(p: Params) -> cq.Workplane:
    """From the plate's top to the lid's top face, tab_t (x) by tab_w (z)."""
    y0 = p.gh - p.wall - p.wedge_clear
    return (
        cq.Workplane("YZ", origin=(p.x_wedge, 0, 0))
        .moveTo((y0 + p.gh) / 2, 0).rect(p.gh - y0, p.tab_w)
        .extrude(p.tab_t)
    )


def _ramp(p: Params, zc: float, yc: float) -> cq.Workplane:
    """One ramp on the plate's front face, footprint pad (y) by ramp_len (z) centred on (zc, yc).

    Its face is ramp_t(u) in front of the plate, u = z - zc: thick toward -z, thin toward +z.
    """
    h = p.ramp_len / 2
    outline = [
        (p.x_wedge, zc - h),
        (p.x_wedge - p.ramp_t(-h), zc - h),
        (p.x_wedge - p.ramp_t(h), zc + h),
        (p.x_wedge, zc + h),
    ]
    return cq.Workplane("XZ", origin=(0, yc + p.pad / 2, 0)).polyline(outline).close().extrude(p.pad)


def wedge_plate(p: Params = DEFAULT, lock: bool = False) -> cq.Workplane:
    """The plate, its tab and its four ramps, moved to SLIDE or LOCK."""
    wedge = _plate(p).union(_tab(p))
    for zc in (-p.pad_z, p.pad_z):
        for yc in (p.axis - p.pad_dy, p.axis + p.pad_dy):
            wedge = wedge.union(_ramp(p, zc, yc))
    return wedge.translate((0, 0, _shift(p, lock)))


def knob(p: Params = DEFAULT, lock: bool = False) -> cq.Workplane:
    """knob_w by knob_h by knob_l on the lid top and the tab's top, with the grip ridges above it.

    One profile in (x, y), ridges as teeth along its top edge, extruded along z.
    """
    x0, x1 = p.x_knob - p.knob_w / 2, p.x_knob + p.knob_w / 2
    top = p.gh + p.knob_h
    centres = [p.x_knob + (i - (p.ridges - 1) / 2) * p.ridge_pitch for i in range(p.ridges)]
    if p.ridges > 0 and (
        min(centres) - p.ridge_w / 2 < x0
        or max(centres) + p.ridge_w / 2 > x1
        or (p.ridges > 1 and p.ridge_pitch <= p.ridge_w)
    ):
        raise ValueError("the grip ridges must fit on the knob's top without touching each other")

    outline = [(x0, p.gh), (x1, p.gh), (x1, top)]
    for c in reversed(centres):                        # along the top, from +x to -x
        outline += [(c + p.ridge_w / 2, top), (c + p.ridge_w / 2, top + p.ridge_h),
                    (c - p.ridge_w / 2, top + p.ridge_h), (c - p.ridge_w / 2, top)]
    outline.append((x0, top))
    body = cq.Workplane("XY", origin=(0, 0, -p.knob_l / 2)).polyline(outline).close().extrude(p.knob_l)
    return body.translate((0, 0, _shift(p, lock)))


def build(p: Params = DEFAULT, lock: bool = False) -> dict[str, cq.Workplane]:
    """The lock switch's printed solids in mockup coordinates, both moved together by `lock`."""
    return {"wedge_plate": wedge_plate(p, lock), "knob": knob(p, lock)}
