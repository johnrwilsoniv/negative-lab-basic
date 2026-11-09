"""3 · Film gate: the gate front, the gate body, the lid, and the floating pressure plate.

Mockup `rebuild()` lines 415-465, split for printing (ruling F5). The gate front is a solid block from
the gate's front face to the film reference plane (`x_ref`): the tube socket, then a light passage
that narrows to the frame window, which runs straight for `plate_t` to the reference plane. It prints
with that plane on the bed, so the face the film lies on is the smoothest one there is. The gate body
is the floor, the side walls and the rear wall, from the reference plane back; it prints rear wall
down. The film slots in its side walls are notches open toward the gate front, which closes them, so
neither part has a bridge. Four M3 screws join the two through pillars outside the side walls.

Below the film the gate body fills the space behind the wedge plate with the backer (ruling F12): a block on
the floor from `wedge_back_clear` behind the plate to the rear wall, wall to wall, up to the film's bottom
edge, so it stays out of the light path. At LOCK the pads push the plate back onto it, so the plate is
wedged between the pressure plate and the body rather than bending away into free space.

The lid is its own solid resting on the side walls, `lid_clear` short of the gate front and of the
rear wall. The pressure plate is `plate_clear` inside the floor, the lid and the side walls all round,
so it drops in and floats; it prints with the face that meets the film on the bed (F7).

The walls are slabs with rectangular windows extruded in one go, so the booleans are the tube socket
(it breaks through the top edge, ruling R8), the light passage, the screw holes, the pads joined to the
pressure plate, and the unions that make the body. The gate front's top is plain (F14).

Not modelled (ruling R3): leaf springs, pressure plate guides, wedge plate z-grooves, the
lid-slot detent bumps, and how the lid is fastened.
"""

import cadquery as cq

from params import DEFAULT, Params

# The gate front and the pressure plate print with their film faces on the bed (F5, F7): -x up for the gate front,
# whose rear face is the reference plane, +x up for the pressure plate, whose front face meets the film. The body
# prints rear wall down (-x up), so its walls, pillars and film notches all stand straight up from the bed.
PRINT_UP = {"gate_front": "-x", "gate_body": "-x", "gate_lid": "+y", "pressure_plate": "+x"}

def _slab(plane, origin, outer, hole, depth):
    """Extrude the rectangle `outer` = (u0, u1, v0, v1), with `hole` (same form, or None) cut through,
    `depth` along the plane's normal. u and v are the plane's own x and y axes."""

    def rect(wp, r):
        u0, u1, v0, v1 = r
        return wp.moveTo((u0 + u1) / 2, (v0 + v1) / 2).rect(u1 - u0, v1 - v0)

    wp = rect(cq.Workplane(plane, origin=origin), outer)
    if hole is not None:
        wp = rect(wp, hole)
    return wp.extrude(depth)


def _centred(c, w, h):
    """(u0, u1, v0, v1) of a w by h rectangle centred on c."""
    return c[0] - w / 2, c[0] + w / 2, c[1] - h / 2, c[1] + h / 2


def _wall_x(p: Params, x0: float, x1: float, y0: float, y1: float, z_half: float, window: tuple[float, float] | None):
    """A wall across the gate from x0 to x1, y0..y1, z +-z_half, with a window (along z, along y) on the axis."""
    hole = None if window is None else _centred((p.axis, 0), window[1], window[0])
    return _slab("YZ", (x0, 0, 0), (y0, y1, -z_half, z_half), hole, x1 - x0)


def _box(x0: float, x1: float, y0: float, y1: float, z0: float, z1: float) -> cq.Workplane:
    return cq.Workplane("XY").box(x1 - x0, y1 - y0, z1 - z0, centered=False).translate((x0, y0, z0))


def _bores(p: Params, x0: float, x1: float, d: float) -> cq.Workplane:
    """A d diameter rod along x from x0 to x1 at each of the four joint screws."""
    rods = cq.Workplane("YZ", origin=(x0, 0, 0)).pushPoints(p.screw_points).circle(d / 2)
    return rods.extrude(x1 - x0)


def _light_passage(p: Params) -> cq.Workplane:
    """The air the lens looks through: the frame window straight for plate_t from the reference plane, then flaring
    to `flare_scale` times its size at the socket's floor, so its corners reach the tube's bore and the tube's end
    rests on the ledge all round."""
    x_win = p.x_ref - p.plate_t
    x_socket = p.x_gate + p.front_wall
    k = p.flare_scale
    window = _box(x_win - 0.01, p.x_ref + 1, p.axis - p.win_h / 2, p.axis + p.win_h / 2, -p.win_w / 2, p.win_w / 2)
    flare = (
        cq.Workplane("YZ", origin=(x_socket, 0, 0)).center(p.axis, 0).rect(k * p.win_h, k * p.win_w)
        .workplane(offset=x_win - x_socket).rect(p.win_h, p.win_w)
        .loft(combine=True, ruled=True)
    )
    return window.union(flare)


def gate_front(p: Params = DEFAULT) -> cq.Workplane:
    """x_gate .. x_ref, gh tall, gate_front_w wide: the tube socket, the light passage and the screw holes."""
    block = _box(p.x_gate, p.x_ref, 0, p.gh, -p.gate_front_w / 2, p.gate_front_w / 2)
    socket = cq.Workplane("YZ", origin=(p.x_gate - 1, 0, 0)).center(p.axis, 0).circle(p.fit_r).extrude(p.front_wall + 1)
    block = block.cut(socket).cut(_light_passage(p))
    block = block.cut(_bores(p, p.x_gate - 1, p.x_ref + 1, p.joint_hole_d))
    return block.cut(_bores(p, p.x_gate - 1, p.x_gate + p.cbore_depth, p.cbore_d))


def _rear_wall(p: Params) -> cq.Workplane:
    x1 = p.x_gate + p.gate_d
    return _wall_x(p, x1 - p.wall, x1, 0, p.gh, p.gw / 2, (p.rear_win_w, p.rear_win_h))


def _floor(p: Params) -> cq.Workplane:
    """From the reference plane to the rear wall."""
    return _slab("XZ", (0, p.wall, 0), (p.x_ref, p.x_gate + p.gate_d - p.wall, -p.gw / 2, p.gw / 2), None, p.wall)


def _side_wall(p: Params, sign: int) -> cq.Workplane:
    """From the reference plane to the rear wall, from the floor up to the lid, with the film slot: a notch film_slot_w
    along x from film_slot_x0 (the reference plane, so the notch is open toward the gate front, which closes it),
    film_slot_h along y from film_slot_y0, the film's lower edge, so the film rests on the notch's floor (F13)."""
    z0 = p.gw / 2 - p.wall if sign > 0 else -p.gw / 2
    wall = _slab("XY", (0, 0, z0), (p.x_ref, p.x_gate + p.gate_d - p.wall, p.wall, p.gh - p.wall), None, p.wall)
    notch = _box(p.film_slot_x0 - 1, p.film_slot_x0 + p.film_slot_w, p.film_slot_y0,
                 p.film_slot_y0 + p.film_slot_h, z0 - 1, z0 + p.wall + 1)
    return wall.cut(notch)


def _pillars(p: Params) -> list[cq.Workplane]:
    """One per joint screw, outside the side walls, the body's whole depth so each stands on the bed."""
    x1 = p.x_gate + p.gate_d
    out = []
    for y, z in p.screw_points:
        out.append(_box(p.x_ref, x1, y - p.ear_h / 2, y + p.ear_h / 2, z - p.ear_w / 2, z + p.ear_w / 2))
    return out


def _backer(p: Params) -> cq.Workplane:
    """wedge_back_clear behind the wedge plate's back face to the rear wall, side wall to side wall, from the floor up to
    the film's bottom edge."""
    x0 = p.x_wedge + p.wedge_t + p.wedge_back_clear
    return _box(x0, p.x_gate + p.gate_d - p.wall, p.wall, p.axis - p.film_w / 2, -(p.gw / 2 - p.wall), p.gw / 2 - p.wall)


def gate_body(p: Params = DEFAULT) -> cq.Workplane:
    body = _rear_wall(p)
    for part in (_floor(p), _side_wall(p, -1), _side_wall(p, 1), _backer(p), *_pillars(p)):
        body = body.union(part)
    return body.cut(_bores(p, p.x_ref - 1, p.x_ref + p.pilot_depth, p.pilot_d))


def gate_lid(p: Params = DEFAULT) -> cq.Workplane:
    """Between the gate front and the rear wall, lid_clear short of each, on the side walls, with the switch slot
    (placed absolutely, not from the lid's ends)."""
    slot_x0 = p.x_wedge - p.tab_clear
    slot_z = p.sw_travel / 2 + p.slot_end
    return _slab(
        "XZ", (0, p.gh, 0),
        (p.x_ref + p.lid_clear, p.x_gate + p.gate_d - p.wall - p.lid_clear, -p.gw / 2, p.gw / 2),
        (slot_x0, slot_x0 + p.tab_t + 2 * p.tab_clear, -slot_z, slot_z),
        p.wall,
    )


def _pad(p: Params, zc: float, yc: float) -> cq.Workplane:
    """One pad on the pressure plate's back face, footprint pad x pad centred on (zc, yc).

    Its back face is parallel to the face of the ramp that presses on it (ruling R6). A ramp's face recedes
    from the wedge plate (toward -x) by ramp_t, thick toward -z, so that face climbs toward +x as
    z grows; the pad, on the other side of the gap, therefore grows thicker toward +z.
    """
    h = p.pad / 2
    slope = p.ramp_rise / p.ramp_len

    def thickness(z):
        return p.pad_t + slope * (z - zc)

    outline = [(p.x_pp, zc - h), (p.x_pp + thickness(zc - h), zc - h), (p.x_pp + thickness(zc + h), zc + h), (p.x_pp, zc + h)]
    return cq.Workplane("XZ", origin=(0, yc + h, 0)).polyline(outline).close().extrude(p.pad)


def pressure_plate(p: Params = DEFAULT, lock: bool = False) -> cq.Workplane:
    """Floats along x: half the channel behind the film at SLIDE, `lock_shift` toward it at LOCK.

    plate_clear inside the floor, the lid and the side walls; its x, window and pads are as the mockup's.
    """
    x0, c = p.x_film + p.channel / 2, p.plate_clear
    plate = _wall_x(p, x0, p.x_pp, p.wall + c, p.gh - p.wall - c, p.gw / 2 - p.wall - c, (p.win_w, p.win_h))
    for zc in (-p.pad_z, p.pad_z):
        for yc in (p.axis - p.pad_dy, p.axis + p.pad_dy):
            plate = plate.union(_pad(p, zc, yc))
    return plate.translate((-p.lock_shift, 0, 0)) if lock else plate


def build(p: Params = DEFAULT, lock: bool = False) -> dict[str, cq.Workplane]:
    """The gate's printed solids in mockup coordinates. Only the pressure plate moves with `lock`."""
    return {
        "gate_front": gate_front(p), "gate_body": gate_body(p), "gate_lid": gate_lid(p),
        "pressure_plate": pressure_plate(p, lock),
    }
