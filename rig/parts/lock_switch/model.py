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

import cadutil
from params import DEFAULT, Params

# Wedge plate flat, back face on the bed, ramps up (F9): on its bottom edge it bridged 52 over its window. The ramps'
# slopes then print stepped by the layers, as the pressure plate's pads do (F7). The knob prints flat, icons up.
PRINT_UP = {"wedge_plate": "-x", "knob": "+y"}


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


def _icon(p: Params, shut: bool, zc: float) -> cq.Workplane:
    """A padlock icon_h tall on the knob's top, its body centred on zc along z, the shackle toward +x.

    Drawn in (u, v) on the top face, u along +z and v along +x from the body's -x edge, so it is upright to someone
    at the camera end looking down, as the lettering on the gate front was. Shut, both legs run into the body. Open,
    the shackle is lifted icon_lift and only its -z leg reaches the body, so a gap shows on the +z side.
    """
    ro = p.icon_w / 2 - p.icon_stroke / 2
    ri = ro - p.icon_stroke
    if ri <= 0 or p.icon_leg <= 0 or p.icon_lift <= 0 or p.icon_h <= 0:
        raise ValueError("the lock icons need a positive height, legs, lift and a shackle with a hole in it")
    lift = 0 if shut else p.icon_lift
    cy = p.icon_body_h + p.icon_leg + lift                     # the shackle's arc centre
    v0 = p.x_knob - (p.icon_body_h + p.icon_leg + p.icon_lift + ro) / 2   # both icons' bodies on one line, the open
    top = cq.Plane(origin=(v0, p.gh + p.knob_h, zc), xDir=(0, 0, 1), normal=(0, 1, 0))  # one centred on the knob

    def box(u0, u1, a, b):
        return cq.Workplane(top).center((u0 + u1) / 2, (a + b) / 2).rect(u1 - u0, b - a).extrude(p.icon_h)

    arc = cq.Workplane(top).center(0, cy).circle(ro).circle(ri).extrude(p.icon_h).intersect(box(-ro, ro, cy, cy + ro))
    icon = box(-p.icon_w / 2, p.icon_w / 2, 0, p.icon_body_h).union(arc)
    icon = icon.union(box(-ro, -ri, p.icon_body_h / 2, cy))                   # the -z leg, always in the body
    icon = icon.union(box(ri, ro, p.icon_body_h / 2 if shut else cy - p.icon_leg, cy))
    return icon


def knob(p: Params = DEFAULT, lock: bool = False) -> cq.Workplane:
    """knob_w by knob_h by knob_l on the lid top and the tab's top, with the two lock icons raised on its top: open
    toward -z, the way it slides to SLIDE, shut toward +z, the way to LOCK."""
    x0 = p.x_knob - p.knob_w / 2
    body = cq.Workplane("XY").box(p.knob_w, p.knob_h, p.knob_l, centered=False).translate((x0, p.gh, -p.knob_l / 2))
    icons = [_icon(p, False, -p.icon_z), _icon(p, True, p.icon_z)]
    for icon in icons:
        b = cadutil.bounds(icon)
        if b[0] < x0 or b[1] > x0 + p.knob_w or b[4] < -p.knob_l / 2 or b[5] > p.knob_l / 2:
            raise ValueError("the lock icons must fit on the knob's top")
    if cadutil.bounds(icons[0])[5] >= cadutil.bounds(icons[1])[4]:
        raise ValueError("the lock icons must not touch each other")
    for icon in icons:
        body = body.union(icon)
    return body.translate((0, 0, _shift(p, lock)))


def build(p: Params = DEFAULT, lock: bool = False) -> dict[str, cq.Workplane]:
    """The lock switch's printed solids in mockup coordinates, both moved together by `lock`."""
    return {"wedge_plate": wedge_plate(p, lock), "knob": knob(p, lock)}
