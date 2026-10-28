"""6 · Light dock: the printed holder for the CS-Lite panel, and the shroud from the gate to its face.

Mockup `rebuild()` lines 473-494. The panel (bought, 165 x 112 x 20) stands on its long edge in a
slot between two lips, its lit face toward the film, against the front lip. A short tunnel, the
shroud, runs from the gate's rear face to that lit face so no stray light reaches the film; it is
the largest printed part.

One solid, the union of:
  - the floor, from the gate's rear face (dock_x0) to `dock_tail` past the slot's back edge;
  - a front and a back lip, full width, `lip_t` thick, with the panel's slot (`csl_slot`) between them;
  - a side cheek at each end of the slot, from `cheek_clear` outside the panel's end to the floor's
    edge, up to `cheek_top`;
  - the shroud: x dock_x0 .. x_light, `shroud_w` wide outside, with a `shroud_h` tall opening
    centred on the axis and `shroud_t` walls around it, a solid block below.

The slot is the panel's thickness plus `csl_clear` (ruling F1, which reverses R16's zero clearance): the
front lip stays at x_light, so the lit face does not move, and the back lip moves back. The shroud top,
axis + shroud_h/2 + shroud_t, stands above the cheeks (ruling R9). At the lowest axis Params allows
(adapter_r, 39; ruling F2) the opening's bottom is level with the lips' top.

Not modelled (ruling R3): how the dock locates against the gate, and keeping light from leaking at
the gate/shroud joint. The shroud's front face is the gate's rear face, touching, and nothing more.
"""

import cadquery as cq

from params import DEFAULT, Params

# Prints floor down: lips, cheeks and shroud all stand up from it. The shroud's top plate bridges its
# opening (shroud_w - 2 * shroud_t wide) from wall to wall.
PRINT_UP = {"light_dock": "+y"}


def _box(x0: float, x1: float, y0: float, y1: float, z0: float, z1: float) -> cq.Workplane:
    return cq.Workplane("XY").box(x1 - x0, y1 - y0, z1 - z0, centered=False).translate((x0, y0, z0))


def _floor(p: Params) -> cq.Workplane:
    return _box(p.dock_x0, p.dock_x1, 0, p.floor_t, -p.dock_w / 2, p.dock_w / 2)


def _lips(p: Params) -> list[cq.Workplane]:
    """The front lip (toward the film) and the back lip, full width, with the panel's slot between."""
    y0, y1, hw = p.floor_t, p.floor_t + p.lip_h, p.dock_w / 2
    return [
        _box(p.x_light - p.lip_t, p.x_light, y0, y1, -hw, hw),
        _box(p.x_light + p.csl_slot, p.x_light + p.csl_slot + p.lip_t, y0, y1, -hw, hw),
    ]


def _cheeks(p: Params) -> list[cq.Workplane]:
    """Both ends of the slot, spanning the lips and the slot in x."""
    x0, x1 = p.x_light - p.lip_t, p.x_light + p.csl_slot + p.lip_t
    inner, outer = p.csl_l / 2 + p.cheek_clear, p.dock_w / 2
    return [_box(x0, x1, p.floor_t, p.cheek_top, inner, outer), _box(x0, x1, p.floor_t, p.cheek_top, -outer, -inner)]


def _shroud(p: Params) -> cq.Workplane:
    """dock_x0 .. x_light. One (z, y) profile extruded along x: the outside rectangle from the floor's
    top to the top plate, less the opening, so the block under the opening is solid."""
    top = p.axis + p.shroud_h / 2 + p.shroud_t
    open_w = p.shroud_w - 2 * p.shroud_t
    return (
        cq.Workplane("YZ", origin=(p.dock_x0, 0, 0))
        .moveTo((p.floor_t + top) / 2, 0).rect(top - p.floor_t, p.shroud_w)
        .moveTo(p.axis, 0).rect(p.shroud_h, open_w)
        .extrude(p.x_light - p.dock_x0)
    )


def light_dock(p: Params = DEFAULT) -> cq.Workplane:
    dock = _floor(p)
    for part in (*_lips(p), *_cheeks(p), _shroud(p)):
        dock = dock.union(part)
    return dock


def build(p: Params = DEFAULT, lock: bool = False) -> dict[str, cq.Workplane]:
    """The light dock in mockup coordinates. It does not move with the lock switch."""
    return {"light_dock": light_dock(p)}
