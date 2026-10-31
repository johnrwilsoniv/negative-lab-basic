"""3 · Film gate: the box with its integral front plate, the lid, and the floating pressure plate.

Mockup `rebuild()` lines 415-465. The box is open-topped (rulings R4, R5): front and rear walls run
the full height, the side walls stop `wall` short of the top, and the lid is its own solid resting
on them, `lid_clear` short of the front and rear walls at each end. The front plate is part of the
box, standing between the side walls. The pressure plate is `plate_clear` inside the floor, the lid
and the side walls all round, so it drops in and floats. Each side wall's film slot starts at the
front plate's rear face: the side wall covers the plate's end, and none of the slot opens into the
chamber on the lens side of the front plate.

The walls are slabs with rectangular windows extruded in one go, so the only booleans are the
tube hole (it breaks through the top edge of the front wall, ruling R8), the pads joined to the
pressure plate, the unions that make the box, and the lettering cut into the lid.

Not modelled (ruling R3): leaf springs, pressure plate guides, wedge plate z-grooves, the
lid-slot detent bumps, and how the lid is fastened.
"""

import cadquery as cq

import cadutil
from params import DEFAULT, Params

# Box and lid print with the floor down.
# Pressure plate on its bottom edge: the pad slopes are traced in XY, not stepped by layers as thick as the preload.
PRINT_UP = {"gate_box": "+y", "gate_lid": "+y", "pressure_plate": "+y"}

LETTER_FONT = "Arial"        # a system font; CadQuery finds it by name on macOS
LETTER_STYLE = "bold"        # a 0.4 deep engraving needs strokes wider than a regular weight gives
OVERCUT = 0.1                # the lettering tool pokes this far above the lid so its top face isn't coplanar


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


def _front_wall(p: Params) -> cq.Workplane:
    """x_gate .. +front_wall, full height, with the tube's hole on the axis."""
    wall = _wall_x(p, p.x_gate, p.x_gate + p.front_wall, 0, p.gh, p.gw / 2, None)
    hole = cq.Workplane("YZ", origin=(p.x_gate - 1, 0, 0)).center(p.axis, 0).circle(p.fit_r).extrude(p.front_wall + 2)
    return wall.cut(hole)


def front_plate(p: Params = DEFAULT) -> cq.Workplane:
    """Fixed; sets the focus plane. Its rear face is half the channel in front of the film."""
    x0 = p.x_front_plate
    return _wall_x(p, x0, x0 + p.plate_t, p.wall, p.gh - p.wall, p.gw / 2 - p.wall, (p.win_w, p.win_h))


def _rear_wall(p: Params) -> cq.Workplane:
    x1 = p.x_gate + p.gate_d
    return _wall_x(p, x1 - p.wall, x1, 0, p.gh, p.gw / 2, (p.rear_win_w, p.rear_win_h))


def _floor(p: Params) -> cq.Workplane:
    """Between the front and rear walls."""
    return _slab(
        "XZ", (0, p.wall, 0),
        (p.x_gate + p.front_wall, p.x_gate + p.gate_d - p.wall, -p.gw / 2, p.gw / 2),
        None, p.wall,
    )


def _side_wall(p: Params, sign: int) -> cq.Workplane:
    """Between the front and rear walls, from the floor up to the lid, with the film slot: film_slot_w along x from
    film_slot_x0 (the front plate's rear face), film_slot_h along y centred on the axis."""
    z0 = p.gw / 2 - p.wall if sign > 0 else -p.gw / 2
    slot = _centred((p.film_slot_x0 + p.film_slot_w / 2, p.axis), p.film_slot_w, p.film_slot_h)
    return _slab(
        "XY", (0, 0, z0),
        (p.x_gate + p.front_wall, p.x_gate + p.gate_d - p.wall, p.wall, p.gh - p.wall),
        slot, p.wall,
    )


def gate_box(p: Params = DEFAULT) -> cq.Workplane:
    box = _front_wall(p)
    for part in (_floor(p), _side_wall(p, -1), _side_wall(p, 1), front_plate(p), _rear_wall(p)):
        box = box.union(part)
    return box


def gate_lid(p: Params = DEFAULT) -> cq.Workplane:
    """Between the front and rear walls, lid_clear short of each, on the side walls, with the switch slot and the
    lettering (both placed absolutely, not from the lid's ends)."""
    slot_x0 = p.x_wedge - p.tab_clear
    slot_z = p.sw_travel / 2 + p.slot_end
    lid = _slab(
        "XZ", (0, p.gh, 0),
        (p.x_gate + p.front_wall + p.lid_clear, p.x_gate + p.gate_d - p.wall - p.lid_clear, -p.gw / 2, p.gw / 2),
        (slot_x0, slot_x0 + p.tab_t + 2 * p.tab_clear, -slot_z, slot_z),
        p.wall,
    )
    for word, z in (("SLIDE", -p.lid_text_z), ("LOCK", p.lid_text_z)):
        lid = lid.cut(_lettering(p, word, p.x_knob - p.lid_text_back, z))
    return lid


def _lettering(p: Params, word: str, x: float, z: float) -> cq.Workplane:
    """The engraving tool for `word`, its glyphs centred on (x, z) in the lid's top face.

    Reads along +z with the letter tops toward +x, so it is upright to someone at the camera end
    looking down on the lid.
    """
    if p.lid_text_depth <= 0:
        raise ValueError(f"lid_text_depth must be positive, got {p.lid_text_depth:g}")
    plane = cq.Plane(origin=(0, p.gh + OVERCUT, 0), xDir=(0, 0, 1), normal=(0, 1, 0))
    text = cq.Workplane(plane).text(
        word, p.lid_text_size, -(p.lid_text_depth + OVERCUT),
        combine=False, halign="center", valign="center", font=LETTER_FONT, kind=LETTER_STYLE,
    )
    if not text.val().Solids():
        raise RuntimeError(f"no glyphs were made for {word!r}; font {LETTER_FONT!r} not found?")
    xmin, xmax, _, _, zmin, zmax = cadutil.shape_bounds(text.val())
    return text.translate((x - (xmin + xmax) / 2, 0, z - (zmin + zmax) / 2))


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
    return {"gate_box": gate_box(p), "gate_lid": gate_lid(p), "pressure_plate": pressure_plate(p, lock)}
