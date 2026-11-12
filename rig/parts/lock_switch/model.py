"""2e · Lock switch: the wedge plate, with its tab and four ramps.

Mockup `rebuild()` lines 422-442 (the `sl` group) and the lock animation at 686-690. The switch
slides along z inside the gate. Its wedge plate sits behind the pressure plate; the plate's four
ramps run under the pressure plate's four sloped pads (film_gate `_pad`) and push it forward to
clamp the film at LOCK. The tab rises through the lid's slot and sticks `tab_reach` (1/2 inch) out of
the lid top, so it is the grip that slides the switch: there is no knob (F15). The lid goes on after
the wedge plate, over the tab.

A ▲ on the plate's front face (F18), pointing up, faces the pressure plate's, so the ramps go toward the lens.

Everything is drawn at s = 0 (switch centred) and then moved along z, as the mockup's `sl` group
is: SLIDE is s = -sw_travel/2, LOCK s = +sw_travel/2.

The ramps are extruded from a profile in (x, z), so each face is a plane; it's the same profile
film_gate's pads use, mirrored across the gap, so at SLIDE the two faces coincide and at LOCK
they overlap by `preload` (rulings R6, R7).

Not modelled (ruling R3, R15): the lid-slot detent bumps and the grooves that guide the wedge plate
along z. The surfaces where they would attach (the lid slot's ends, the plate's z edges) are left plain.
"""

import cadquery as cq

import cadutil
from params import DEFAULT, Params

# Wedge plate flat, back face on the bed, ramps up (F9): on its bottom edge it bridged 52 over its window. The ramps'
# slopes then print stepped by the layers, as the pressure plate's pads do (F7). The tab lies flat with it.
PRINT_UP = {"wedge_plate": "-x"}


def _shift(p: Params, lock: bool) -> float:
    """Where the switch is along z: -sw_travel/2 at SLIDE (the tab toward -z), +sw_travel/2 at LOCK."""
    return p.sw_travel / 2 if lock else -p.sw_travel / 2


def _plate(p: Params) -> cq.Workplane:
    """x_wedge .. +wedge_t, z +-wedge_w/2, between the gate body's sill (F20) and the lid, with the window on the axis."""
    y0, y1 = p.sill_y + p.wedge_clear, p.gh - p.wall - p.wedge_clear
    return (
        cq.Workplane("YZ", origin=(p.x_wedge, 0, 0))
        .moveTo((y0 + y1) / 2, 0).rect(y1 - y0, p.wedge_w)
        .moveTo(p.axis, 0).rect(p.win_h, p.wedge_win_w)
        .extrude(p.wedge_t)
    )


def _tab(p: Params) -> cq.Workplane:
    """From the plate's top up through the lid slot to tab_reach above the lid's top face, tab_t (x) by tab_w (z)."""
    y0, y1 = p.gh - p.wall - p.wedge_clear, p.gh + p.tab_reach
    return (
        cq.Workplane("YZ", origin=(p.x_wedge, 0, 0))
        .moveTo((y0 + y1) / 2, 0).rect(y1 - y0, p.tab_w)
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
    if p.mark_depth:
        front = cadutil.face_plane((p.x_wedge, 0, 0), (-1, 0, 0), (0, 1, 0))
        wedge = cadutil.cut_marks(wedge, [cadutil.mark_triangle(front, 0, p.gh - p.wall - p.mark_drop, p.mark_tri, p.mark_depth)])
    return wedge.translate((0, 0, _shift(p, lock)))


def build(p: Params = DEFAULT, lock: bool = False) -> dict[str, cq.Workplane]:
    """The lock switch's printed solid in mockup coordinates, moved by `lock`."""
    return {"wedge_plate": wedge_plate(p, lock)}
