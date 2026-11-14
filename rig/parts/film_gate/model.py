"""2 · Film gate: the gate front, the gate body, the lid, and the floating pressure plate.

Mockup `rebuild()` lines 415-465, split for printing (ruling F5). The gate front is a solid block from
the gate's front face to the film reference plane (`x_ref`): the tube socket, then a light passage
that narrows to the frame window, which runs straight for `plate_t` to the reference plane. It prints
with that plane on the bed, so the face the film lies on is the smoothest one there is. The gate body
is the floor, the side walls and the rear wall, from the reference plane back; it prints rear wall
down. The film slots in its side walls are notches open toward the gate front, which closes them, so
neither part has a bridge. Four M3 screws join the two through pillars outside the side walls. Each notch is only as
deep as the channel at the wall's inner face and widens to `film_slot_mouth` at its outer face (ruling F21), so a strip
fed in can only reach the channel, not the pressure plate's edge or the space behind it.

Below the film the gate body is filled with the sill (ruling F20): from the reference plane to the rear wall, wall to
wall, up to the film's lower edge, level with the slots' floors, so the strip lies on it across the whole gate and an
end frame held by one slot cannot droop. The pressure plate and the wedge plate stand on it. Behind the wedge plate's
lower ramps the sill carries the backer (ruling F12), a step `backer_step_d` deep with a 45 degree slope under it, up
to the plate's settled window edge, so it stays out of the light path. At LOCK the pads push the plate back onto it,
so the plate is wedged between the pressure plate and the body rather than bending away into free space.

The lid is its own solid resting on the side walls, `lid_clear` short of the gate front and of the
rear wall. A rail on each upper screw pillar, the body's whole depth and up to the lid's top, stands `lid_side_clear`
beside each of its sides (ruling F22), so the switch's tab can't drag it along z; it still lifts straight off. The pressure plate is `plate_clear` inside the sill, the lid and the side walls all round,
so it drops in and floats; it prints with the face that meets the film on the bed (F7). Each end of that face has a
45 degree lead-in (F21): a plate lying forward on the gate front is pushed back by the strip's tip, not struck by it.

The walls are slabs with rectangular windows extruded in one go, so the booleans are the tube socket
(1.7 under the top edge, ruling R8), the light passage, the screw holes, the pads joined to the
pressure plate, and the unions that make the body. The gate front's top is plain (F14).

Assembly marks (F18), each `mark_depth` deep and only where they print without a ceiling: a ▲ on the gate front's
socket floor, pointing up; an open padlock on the lid's top at the SLIDE end of the slot and a shut one at the LOCK
end; and a ▲ on the pressure plate's back, pointing up and facing the light (the wedge plate's faces it from the
lens side).

Not modelled (ruling R3): leaf springs, pressure plate guides, wedge plate z-grooves, the
lid-slot detent bumps, and anything holding the lid down.
"""

import cadquery as cq

import cadutil
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
    """x_gate .. x_ref, gh tall, gate_front_w wide: the tube socket (front_wall deep, 9 since F24, where the tube is a
    friction fit, F23), the light passage and the screw holes, counterbored cbore_depth so an M3 x 20 reaches the
    pillar."""
    block = _box(p.x_gate, p.x_ref, 0, p.gh, -p.gate_front_w / 2, p.gate_front_w / 2)
    socket = cq.Workplane("YZ", origin=(p.x_gate - 1, 0, 0)).center(p.axis, 0).circle(p.fit_r).extrude(p.front_wall + 1)
    block = block.cut(socket).cut(_light_passage(p))
    block = block.cut(_bores(p, p.x_gate - 1, p.x_ref + 1, p.joint_hole_d))
    block = block.cut(_bores(p, p.x_gate - 1, p.x_gate + p.cbore_depth, p.cbore_d))
    return cadutil.cut_marks(block, [_front_triangle(p)] if p.mark_depth else [])


def _front_triangle(p: Params) -> cq.Workplane:
    """The gate front's ▲ (F18), pointing up on the socket floor, where the tube's end goes: centred between the
    light passage's top and the tube's bore, so it shows down the tube. The front prints -x up, so the floor is a
    top layer."""
    floor = cadutil.face_plane((p.x_gate + p.front_wall, 0, 0), (-1, 0, 0), (0, 1, 0))
    v = p.axis + (p.flare_scale * p.win_h / 2 + p.tube_ri) / 2
    return cadutil.mark_triangle(floor, 0, v, p.mark_tri, p.mark_depth)


def _rear_wall(p: Params) -> cq.Workplane:
    x1 = p.x_gate + p.gate_d
    return _wall_x(p, x1 - p.wall, x1, 0, p.gh, p.gw / 2, (p.rear_win_w, p.rear_win_h))


def _floor(p: Params) -> cq.Workplane:
    """From the reference plane to the rear wall."""
    return _slab("XZ", (0, p.wall, 0), (p.x_ref, p.x_gate + p.gate_d - p.wall, -p.gw / 2, p.gw / 2), None, p.wall)


def _side_wall(p: Params, sign: int) -> cq.Workplane:
    """From the reference plane to the rear wall, from the floor up to the lid, with the film slot: a notch from
    film_slot_x0 (the reference plane, so the notch is open toward the gate front, which closes it), film_slot_h along y
    from film_slot_y0, the film's lower edge, so the film rests on the notch's floor (F13). Along x it is `channel` deep
    at the wall's inner face and `film_slot_mouth` at the outer face, a funnel whose lens side is the reference plane
    (F21)."""
    z0 = p.gw / 2 - p.wall if sign > 0 else -p.gw / 2
    wall = _slab("XY", (0, 0, z0), (p.x_ref, p.x_gate + p.gate_d - p.wall, p.wall, p.gh - p.wall), None, p.wall)
    x0, z_in, z_out, e = p.film_slot_x0, sign * (p.gw / 2 - p.wall), sign * p.gw / 2, sign
    outline = [(x0 - 1, z_in - e), (x0 + p.channel, z_in - e), (x0 + p.channel, z_in), (x0 + p.film_slot_mouth, z_out),
               (x0 + p.film_slot_mouth, z_out + e), (x0 - 1, z_out + e)]
    top = p.film_slot_y0 + p.film_slot_h
    notch = cq.Workplane("XZ", origin=(0, top, 0)).polyline(outline).close().extrude(p.film_slot_h)    # XZ extrudes -y
    return wall.cut(notch)


def _pillars(p: Params) -> list[cq.Workplane]:
    """One per joint screw, outside the side walls, the body's whole depth so each stands on the bed."""
    x1 = p.x_gate + p.gate_d
    out = []
    for y, z in p.screw_points:
        out.append(_box(p.x_ref, x1, y - p.ear_h / 2, y + p.ear_h / 2, z - p.ear_w / 2, z + p.ear_w / 2))
    return out


def _lid_rails(p: Params) -> list[cq.Workplane]:
    """One on each upper pillar beside the lid (F22): from the side wall's outer face, lid_rail_w wide, up to the lid's
    top, the body's whole depth so it stands on the bed. The lid is lid_side_clear inside each."""
    x1, z0, z1 = p.x_gate + p.gate_d, p.gw / 2, p.gw / 2 + p.lid_rail_w
    return [_box(p.x_ref, x1, p.gh - p.wall, p.gh, *sorted((k * z0, k * z1))) for k in (-1, 1)]


def _sill(p: Params) -> cq.Workplane:
    """The reference plane to the rear wall, side wall to side wall, from the floor up to the film's lower edge (F20)."""
    return _box(p.x_ref, p.x_gate + p.gate_d - p.wall, p.wall, p.sill_y, -(p.gw / 2 - p.wall), p.gw / 2 - p.wall)


def _backer(p: Params) -> cq.Workplane:
    """The step on the sill behind the wedge plate's lower ramps (F12, F20), side wall to side wall: its face
    wedge_back_clear behind the plate's back face, up to backer_step_top, its top backer_step_d deep, then a 45 degree
    slope down to the sill. The body prints -x up, so the slope is the step's underside."""
    x0, x1 = p.x_wedge + p.wedge_t + p.wedge_back_clear, p.x_wedge + p.wedge_t + p.wedge_back_clear + p.backer_step_d
    rise = p.backer_step_top - p.sill_y
    outline = [(x0, p.sill_y), (x0, p.backer_step_top), (x1, p.backer_step_top), (x1 + rise, p.sill_y)]
    half = p.gw / 2 - p.wall
    return cq.Workplane("XY", origin=(0, 0, -half)).polyline(outline).close().extrude(2 * half)


def gate_body(p: Params = DEFAULT) -> cq.Workplane:
    body = _rear_wall(p)
    for part in (_floor(p), _side_wall(p, -1), _side_wall(p, 1), _sill(p), _backer(p), *_pillars(p), *_lid_rails(p)):
        body = body.union(part)
    return body.cut(_bores(p, p.x_ref - 1, p.x_ref + p.pilot_depth, p.pilot_d))


def gate_lid(p: Params = DEFAULT) -> cq.Workplane:
    """Between the gate front and the rear wall, lid_clear short of each, and between the rails, lid_side_clear inside
    each (F22), on the side walls, with the switch slot (placed absolutely, not from the lid's ends): tab_clear each
    side of the tab, none since F25, so the tab holds the lid along x."""
    slot_x0 = p.x_wedge - p.tab_clear
    slot_w = p.tab_t + 2 * p.tab_clear
    slot_z = p.sw_travel / 2 + p.slot_end
    lid = _slab(
        "XZ", (0, p.gh, 0),
        (p.x_ref + p.lid_clear, p.x_gate + p.gate_d - p.wall - p.lid_clear, -p.gw / 2 + p.lid_side_clear,
         p.gw / 2 - p.lid_side_clear),
        (slot_x0, slot_x0 + slot_w, -slot_z, slot_z),
        p.wall,
    )
    if not p.mark_depth:
        return lid
    # padlocks either side of the slot (F18), shackles toward +x: open toward SLIDE (-z), shut toward LOCK (+z)
    top = cadutil.face_plane((0, p.gh, 0), (0, 1, 0), (1, 0, 0))                  # u = +z, v = +x
    u, v = slot_z + p.mark_lock_off, slot_x0 + slot_w / 2
    return cadutil.cut_marks(lid, [cadutil.mark_padlock(top, -u, v, p.mark_depth, shut=False),
                                   cadutil.mark_padlock(top, u, v, p.mark_depth, shut=True)])


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


def _lead_ins(p: Params, x0: float, y0: float, y1: float, z_end: float) -> cq.Workplane:
    """What comes off the pressure plate's front edge at each end (F21): plate_lead_in by 45 degrees, y0 to y1."""
    lead = p.plate_lead_in
    out = None
    for k in (-1, 1):
        ze = k * z_end
        tri = [(x0 - 1, ze - k * (lead + 1)), (x0 + lead + 1, ze + k), (x0 - 1, ze + k)]
        cut = cq.Workplane("XZ", origin=(0, y1 + 1, 0)).polyline(tri).close().extrude(y1 - y0 + 2)
        out = cut if out is None else out.union(cut)
    return out


def pressure_plate(p: Params = DEFAULT, lock: bool = False) -> cq.Workplane:
    """Floats along x: half the channel behind the film at SLIDE, `lock_shift` toward it at LOCK.

    plate_clear inside the sill, the lid and the side walls; its x, window and pads are as the mockup's, its front
    edge led in at each end.
    """
    x0, c = p.x_film + p.channel / 2, p.plate_clear
    y0, y1, z_end = p.sill_y + c, p.gh - p.wall - c, p.gw / 2 - p.wall - c
    plate = _wall_x(p, x0, p.x_pp, y0, y1, z_end, (p.win_w, p.win_h))
    if p.plate_lead_in:
        plate = plate.cut(_lead_ins(p, x0, y0, y1, z_end))
    for zc in (-p.pad_z, p.pad_z):
        for yc in (p.axis - p.pad_dy, p.axis + p.pad_dy):
            plate = plate.union(_pad(p, zc, yc))
    if p.mark_depth:        # ▲ on the back (F18), pointing up, toward the light
        back = cadutil.face_plane((p.x_pp, 0, 0), (1, 0, 0), (0, 1, 0))
        plate = cadutil.cut_marks(plate, [cadutil.mark_triangle(back, 0, p.gh - p.wall - p.mark_drop, p.mark_tri, p.mark_depth)])
    return plate.translate((-p.lock_shift, 0, 0)) if lock else plate


def build(p: Params = DEFAULT, lock: bool = False) -> dict[str, cq.Workplane]:
    """The gate's printed solids in mockup coordinates. Only the pressure plate moves with `lock`."""
    return {
        "gate_front": gate_front(p), "gate_body": gate_body(p), "gate_lid": gate_lid(p),
        "pressure_plate": pressure_plate(p, lock),
    }
