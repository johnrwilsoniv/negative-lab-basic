"""5 · Film drive: two sprockets that drive the film by its perforations, three gears that turn them together,
the deck the gears stand on, and the axle the knobbed idler turns on (rulings D3, D4).

The sprockets stand upright in pockets in the gate body (film_gate), one each side of the window, on the light side
of the film, at z = +-sprocket_z: each over a perforation's centre when a frame is centred in the window. Each has
two rings, one under each perforation row, `ring_clear` behind the film, and between them a hub well clear of the
image. `sprocket_teeth` teeth on each ring come up through the perforations; the film is a rack and each sprocket a
pinion on it, with its pitch radius at the film's mid-plane, so one turn is `sprocket_teeth` perforations: a frame.
Only the teeth near the tangent point reach through the film (one or two per row at a time); the channel keeps the
film from lifting off them. Each tooth tapers along the film and comes to a ridge across it, at 45 degrees, so it
finds the perforation's middle, and so it prints without hanging over air when the sprocket stands on its shaft.

Each sprocket's shaft stands on the floor of a bearing hole under its pocket and runs up through the deck to its gear,
keyed by a D-flat. The idler sits between the two gears on an axle pressed through the deck into the gate body's top,
with the knob on top. Every gear has `gear_teeth`, so the knob, the gears and the sprockets all turn once per frame.
The knob turns against the sprockets (an idler reverses), and both sprockets the same way, so the film runs through.

Mesh phase: for the same printed parts to work at both ends, the D-flat of each shaft faces the idler and lies on a
sprocket tooth (90 degrees from the one at the film) and on a gear tooth, and the idler, with an even number of teeth,
shows a gap to each gear. `turn` is knob turns from a frame centred in the window, positive moving the film toward +z:
the sprockets and their gears turn `turn` whole turns about +y, the idler the other way.
"""

import math

import cadquery as cq

import cadutil
from cadutil import box
from params import DEFAULT, Params

# Everything prints standing as it stands in the rig: the sprockets on their shaft's foot, the gears and the idler
# face down (the idler's knob up), the deck flat, the axle upright.
PRINT_UP = {
    "sprocket_supply": "+y", "sprocket_takeup": "+y", "gear_supply": "+y", "gear_takeup": "+y",
    "idler": "+y", "idler_axle": "+y", "deck": "+y",
}
SIDES = {"supply": -1, "takeup": 1}     # the supply spool and sprocket are at -z: the film runs toward +z
FLANK_POINTS = 8                        # points along each involute flank


def _inv(a: float) -> float:
    return math.tan(a) - a


def gear_outline(p: Params) -> list[tuple[float, float]]:
    """The gear's outline in its own plane, (u, v), one tooth centred on +v.

    ISO 20 degree involute, `gear_backlash` taken half off each gear's teeth at the pitch circle. Below the base circle
    the flanks run radially to the root circle (at 30 teeth the root is under the base circle).
    """
    n, r, ra, rf = p.gear_teeth, p.gear_r, p.gear_tip_r, p.gear_root_r
    alpha = math.radians(p.gear_pressure)
    rb = r * math.cos(alpha)
    half_pitch = (math.pi * r / n - p.gear_backlash / 2) / (2 * r)    # half the tooth's angle at the pitch circle

    def half(rr: float) -> float:       # half the tooth's angle at radius rr
        rr = max(rr, rb)
        return half_pitch + _inv(alpha) - _inv(math.acos(rb / rr))

    radii = [max(rf, rb) + (ra - max(rf, rb)) * i / FLANK_POINTS for i in range(FLANK_POINTS + 1)]
    flank = ([(rf, half(rb))] if rf < rb else []) + [(rr, half(rr)) for rr in radii]
    pts = []
    for k in range(n):
        c = math.pi / 2 + 2 * math.pi * k / n
        tooth = [(rr, c - h) for rr, h in flank] + [(rr, c + h) for rr, h in reversed(flank)]
        pts += [(rr * math.cos(a), rr * math.sin(a)) for rr, a in tooth]
    return pts


def _gear_blank(p: Params, x: float, z: float) -> cq.Workplane:
    """A gear on the line (x, z), tooth 0 toward +z, standing on the deck. The outline's (u, v) is the plane's (x, z)."""
    outline = [(x + u, z + v) for u, v in gear_outline(p)]
    return cq.Workplane("XZ", origin=(0, p.y_gear + p.gear_t, 0)).polyline(outline).close().extrude(p.gear_t)


def _flat_cut(p: Params, x: float, z: float, r_flat: float, y0: float, y1: float) -> cq.Workplane:
    """Everything beyond r_flat toward +z from the line (x, z), from y0 to y1: what makes a shaft a D (r_flat, the
    flat) or what a D-bore leaves in (r_flat plus the clearance)."""
    return box(x - 10, x + 10, y0, y1, z + r_flat, z + 10)


def _tooth(p: Params, y_row: float) -> cq.Workplane:
    """One sprocket tooth pointing -x from the shaft at the origin, on the row at y_row: the intersection of a taper
    along the film (tooth_base at the ring to tooth_tip at r_tip) and a ridge across it (tooth_w tooth_seat inside the
    ring, narrowing at 45 degrees), both from 1 inside the ring."""
    r0, r1 = p.r_ring - 1, p.r_tip
    span = r1 - p.r_ring
    hw = lambda r: p.tooth_base / 2 + (p.tooth_tip - p.tooth_base) / 2 * (r - p.r_ring) / span   # noqa: E731
    taper = [(-r0, -hw(r0)), (-r1, -hw(r1)), (-r1, hw(r1)), (-r0, hw(r0))]
    y_top = y_row + p.tooth_w / 2
    along = cq.Workplane("XZ", origin=(0, y_top, 0)).polyline(taper).close().extrude(p.tooth_w)
    w, rk = p.tooth_w / 2, p.r_ring - p.tooth_seat
    ridge = [(-r0, y_row - w), (-rk, y_row - w), (-r1, y_row - w + r1 - rk), (-r1, y_row + w - r1 + rk),
             (-rk, y_row + w), (-r0, y_row + w)]
    z = p.tooth_base
    across = cq.Workplane("XY", origin=(0, 0, -z)).polyline(ridge).close().extrude(2 * z)
    return along.intersect(across)


def sprocket_at_origin(p: Params) -> cq.Workplane:
    """A sprocket on the y axis, tooth 0 toward -x, its D-flat toward +z (two teeth on): the shaft from shaft_floor to
    y_shaft_top, a cone up to the lower ring, the hub, a cone up to the upper ring, the shaft on up."""
    rs = p.shaft_d / 2
    (lo0, lo1), (hi0, hi1) = p.y_ring_lo, p.y_ring_hi
    profile = [
        (0, p.shaft_floor), (rs, p.shaft_floor), (rs, lo0 - (p.r_ring - rs)), (p.r_ring, lo0), (p.r_ring, lo1),
        (p.hub_r, lo1), (p.hub_r, hi0 - (p.r_ring - p.hub_r)), (p.r_ring, hi0), (p.r_ring, hi1), (rs, hi1),
        (rs, p.y_shaft_top), (0, p.y_shaft_top),
    ]
    body = cq.Workplane("XY").polyline(profile).close().revolve(360, (0, 0, 0), (0, 1, 0))
    for y_row in (p.axis - p.perf_dy, p.axis + p.perf_dy):
        tooth = _tooth(p, y_row)
        for k in range(p.sprocket_teeth):
            body = body.union(tooth.rotate((0, 0, 0), (0, 1, 0), 360 * k / p.sprocket_teeth))
    return body.cut(_flat_cut(p, 0, 0, rs - p.shaft_flat, p.y_gear - 1, p.y_shaft_top + 1))


def _side_angle(sign: int) -> float:
    """The -z (supply) parts as built; the +z ones turned half round, so their D-flats face the idler too."""
    return 0.0 if sign < 0 else 180.0


def sprocket(p: Params, side: str, turn: float = 0.0) -> cq.Workplane:
    sign = SIDES[side]
    wp = sprocket_at_origin(p).rotate((0, 0, 0), (0, 1, 0), _side_angle(sign) + 360 * turn)
    return wp.translate((p.x_sprocket, 0, sign * p.sprocket_z))


def gear(p: Params, side: str, turn: float = 0.0) -> cq.Workplane:
    """On its sprocket's shaft, tooth 0 and the bore's flat toward the idler."""
    sign = SIDES[side]
    rb = p.shaft_d / 2 + p.flat_clear
    blank = _gear_blank(p, 0, 0)
    bore = cadutil.cylinder_y(0, 0, rb, p.y_gear - 1, p.y_gear + p.gear_t + 1)
    bore = bore.cut(_flat_cut(p, 0, 0, p.shaft_d / 2 - p.shaft_flat + p.flat_clear, p.y_gear - 2, p.y_gear + p.gear_t + 2))
    wp = blank.cut(bore).rotate((0, 0, 0), (0, 1, 0), _side_angle(sign) + 360 * turn)
    return wp.translate((p.x_sprocket, 0, sign * p.sprocket_z))


def idler(p: Params, turn: float = 0.0) -> cq.Workplane:
    """Between the gears, gaps toward them (tooth 0 toward +x), the knob on top with a groove from its centre toward +x
    to count turns; it turns the other way from the sprockets."""
    x = p.x_sprocket
    blank = _gear_blank(p, 0, 0).rotate((0, 0, 0), (0, 1, 0), 90)     # tooth 0 from +z to +x
    y_knob = p.y_gear + p.gear_t
    knob = cadutil.cylinder_y(0, 0, p.knob_r, y_knob - 0.01, y_knob + p.knob_h)
    wp = blank.union(knob)
    wp = wp.cut(cadutil.cylinder_y(0, 0, p.shaft_d / 2 + p.bearing_clear, p.y_gear - 1, y_knob + p.knob_h + 1))
    wp = wp.cut(box(0, p.knob_r + 1, y_knob + p.knob_h - p.mark_depth, y_knob + p.knob_h + 1, -p.mark_w / 2, p.mark_w / 2))
    return wp.rotate((0, 0, 0), (0, 1, 0), -360 * turn).translate((x, 0, 0))


def idler_axle(p: Params) -> cq.Workplane:
    """Pressed through the deck into the gate body's top; the idler turns on it."""
    y0, y1 = p.gh - p.axle_hole_depth, p.y_gear + p.gear_t + p.knob_h - p.axle_top_clear
    return cadutil.cylinder_y(p.x_sprocket, 0, p.shaft_d / 2, y0, y1)


def deck(p: Params) -> cq.Workplane:
    """On the gate body's top, from the reference plane to deck_clear short of the CS-Lite: a bearing for each sprocket
    shaft and the idler's axle (pressed)."""
    slab = box(p.x_ref, p.x_light - p.deck_clear, p.y_deck, p.y_deck + p.deck_t, -p.gw / 2, p.gw / 2)
    y0, y1 = p.y_deck - 1, p.y_deck + p.deck_t + 1
    for z in (-p.sprocket_z, p.sprocket_z):
        slab = slab.cut(cadutil.cylinder_y(p.x_sprocket, z, p.shaft_d / 2 + p.bearing_clear, y0, y1))
    return slab.cut(cadutil.cylinder_y(p.x_sprocket, 0, p.shaft_d / 2, y0, y1))


def build(p: Params = DEFAULT, turn: float = 0.0) -> dict[str, cq.Workplane]:
    """The drive's printed solids in mockup coordinates, the knob `turn` turns from a frame centred in the window."""
    out = {}
    for side in SIDES:
        out[f"sprocket_{side}"] = sprocket(p, side, turn)
        out[f"gear_{side}"] = gear(p, side, turn)
    out["idler"] = idler(p, turn)
    out["idler_axle"] = idler_axle(p)
    out["deck"] = deck(p)
    return out
