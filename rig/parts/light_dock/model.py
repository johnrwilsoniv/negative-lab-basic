"""6 · Light dock: the printed holder for the CS-Lite panel, with the film gate inset in it.

Mockup `rebuild()` lines 473-494. The panel (bought, 165 x 112 x 20) stands on its long edge in a
slot between two lips, its lit face toward the film, against the front lip. The gate body's rear face
lies flush on that lit face (ruling F10): the gate is `gate_front + gap` deep, so its rear wall ends at
x_light, and the panel closes the rear window. There is no shroud.

One solid, the union of:
  - the floor, from the front wall's front face (dock_x0) to `dock_tail` past the slot's back edge;
  - the front wall (F11), `dock_front_t` thick, `dock_gate_clear` in front of the gate front, full width and up
    to `cheek_top`, with a U for the tube: a half circle `dock_tube_clear` around it below the axis, straight
    up from there, so it prints with no overhang. The gate front and the gate body are held between it and
    the panel, so they can't come apart by more than dock_gate_clear;
  - a front and a back lip, full width, `lip_t` thick, with the panel's slot (`csl_slot`) between them;
  - a side cheek at each end of the slot, from `cheek_clear` outside the panel's end to the floor's
    edge, up to `cheek_top`;
less the gate notch: through the floor and the front lip, from the front wall to x_light, as wide as the
gate front (the body and its screw pillars) plus `dock_gate_clear` each side. The whole gate stands on the
table in it, between two floor arms that locate it in z, its rear wall in the lip's gap.
What is left of the front lip holds the panel's ends; the gate's rear wall holds its middle.

The slot is the panel's thickness plus `csl_clear` (ruling F1, which reverses R16's zero clearance): the
front lip stays at x_light, so the lit face does not move, and the back lip moves back.

The front wall covers the gate front's two lower screw heads: lift the gate out to reach them.
"""

import cadquery as cq

from params import DEFAULT, Params

# The dock prints floor down: lips and cheeks stand up from it.
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


def _front_wall(p: Params) -> cq.Workplane:
    """In front of the gate front, full width, up to cheek_top, less the U the tube passes through."""
    x0, x1 = p.dock_x0, p.x_gate - p.dock_gate_clear
    wall = _box(x0, x1, 0, p.cheek_top, -p.dock_w / 2, p.dock_w / 2)
    r = p.tube_ro + p.dock_tube_clear
    round_ = cq.Workplane("YZ", origin=(x0 - 1, 0, 0)).center(p.axis, 0).circle(r).extrude(x1 - x0 + 2)
    straight = _box(x0 - 1, x1 + 1, p.axis, p.cheek_top + 1, -r, r)
    return wall.cut(round_).cut(straight)


def _gate_notch(p: Params) -> cq.Workplane:
    """Where the gate stands: the front wall to x_light, the gate front's width plus dock_gate_clear each side,
    through the floor and the front lip."""
    hw = p.gate_front_w / 2 + p.dock_gate_clear
    return _box(p.x_gate - p.dock_gate_clear, p.x_light, -1, p.floor_t + p.lip_h + 1, -hw, hw)


def light_dock(p: Params = DEFAULT) -> cq.Workplane:
    dock = _floor(p)
    for part in (*_lips(p), *_cheeks(p)):
        dock = dock.union(part)
    return dock.cut(_gate_notch(p)).union(_front_wall(p))


def build(p: Params = DEFAULT, lock: bool = False) -> dict[str, cq.Workplane]:
    """The light dock in mockup coordinates. It does not move with the lock switch."""
    return {"light_dock": light_dock(p)}
