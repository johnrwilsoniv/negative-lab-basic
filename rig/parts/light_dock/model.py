"""3 · Light dock: the printed holder for the CS-Lite panel, with the film gate inset in it and the spools beside it.

Mockup `rebuild()` lines 473-494, then the film transport (ruling D5). The panel (bought, 165 x 112 x 20) stands on its
long edge in a slot between two lips, its lit face toward the film, against the front lip. The gate body's rear face
lies flush on that lit face (ruling F10): the gate is `gate_front + gap` deep, so its body ends at x_light, and the
panel closes the light passage's rear end.

One solid, the union of:
  - the floor, from `dock_margin` in front of the spools' flanges (dock_x0) to `dock_tail` past the slot's back
    edge, dock_w wide, so the spools stand on it;
  - a front and a back lip, full width, `lip_t` thick, with the panel's slot (`csl_slot`) between them;
  - a side cheek at each end of the slot, from `cheek_clear` outside the panel's end to the floor's
    edge, up to `cheek_top`;
  - a pedestal and a pin for each spool, at (x_spool, +-spool_z): the spool stands on the pedestal and turns on the pin,
    which stops short of the cap's socket;
less the gate notch: through the floor and the front lip, from the gate's front face to x_light, as wide as the gate
plus `dock_gate_clear` each side. The whole gate stands on the table in it, between two floor arms that locate it in
z, and the floor's edge in front of it locates it in x. The front wall the gate used to be held in by (F11) is gone:
the spools stand where it was, and the friction pegs hold the gate front on (D2).

The floor still runs under the tube, from dock_x0 to the gate's front face. A trough along x, `dock_tube_clear` around
the tube, is cut from it (F17, which was the round of the front wall's U): at a low axis it reaches below the floor's
top, so the floor can never come within dock_tube_clear of the tube. With the Ø68.5 tube (F23) its bottom is
axis - 35.25: at axis 39, the lowest allowed, it cuts 0.25 into the floor's top, and from 39.25 up nothing. It is cut
before the spool stands go on, so it never touches them.

The slot is the panel's thickness plus `csl_clear` (ruling F1): the front lip stays at x_light, so the lit face does not
move, and the back lip moves back.
"""

import cadquery as cq

import cadutil
from cadutil import box
from params import DEFAULT, Params

# The dock prints floor down: lips, cheeks, pedestals and pins stand up from it.
PRINT_UP = {"light_dock": "+y"}
PIN_CHAMFER = 0.5


def _floor(p: Params) -> cq.Workplane:
    return box(p.dock_x0, p.dock_x1, 0, p.floor_t, -p.dock_w / 2, p.dock_w / 2)


def _lips(p: Params) -> list[cq.Workplane]:
    """The front lip (toward the film) and the back lip, full width, with the panel's slot between."""
    y0, y1, hw = p.floor_t, p.floor_t + p.lip_h, p.dock_w / 2
    return [
        box(p.x_light - p.lip_t, p.x_light, y0, y1, -hw, hw),
        box(p.x_light + p.csl_slot, p.x_light + p.csl_slot + p.lip_t, y0, y1, -hw, hw),
    ]


def _cheeks(p: Params) -> list[cq.Workplane]:
    """Both ends of the slot, spanning the lips and the slot in x."""
    x0, x1 = p.x_light - p.lip_t, p.x_light + p.csl_slot + p.lip_t
    inner, outer = p.csl_l / 2 + p.cheek_clear, p.dock_w / 2
    return [box(x0, x1, p.floor_t, p.cheek_top, inner, outer), box(x0, x1, p.floor_t, p.cheek_top, -outer, -inner)]


def pin_top(p: Params) -> float:
    """The spools' pins end 1 under the floor of the cap's socket."""
    return p.y_spool + p.spool_core_h - p.cap_spigot_h - 1


def _spool_stands(p: Params) -> list[cq.Workplane]:
    out = []
    for z in (-p.spool_z, p.spool_z):
        pedestal = cadutil.cylinder_y(p.x_spool, z, p.pedestal_r, p.floor_t - 0.01, p.y_pedestal)
        pin = cadutil.cylinder_y(p.x_spool, z, p.spool_pin_d / 2, p.y_pedestal - 0.01, pin_top(p))
        out.append(pedestal.union(pin.faces(">Y").edges().chamfer(PIN_CHAMFER)))
    return out


def _gate_notch(p: Params) -> cq.Workplane:
    """Where the gate stands: its front face to x_light, its width plus dock_gate_clear each side, through the floor and
    the front lip."""
    hw = p.gw / 2 + p.dock_gate_clear
    return box(p.x_gate - p.dock_gate_clear, p.x_light, -1, p.floor_t + p.lip_h + 1, -hw, hw)


def _tube_trough(p: Params) -> cq.Workplane:
    """The air kept around the tube where it passes over the floor (F17): dock_tube_clear around it, from in front of
    the floor to the gate notch."""
    x0, x1 = p.dock_x0 - 1, p.x_gate - p.dock_gate_clear + 1
    r = p.tube_ro + p.dock_tube_clear
    return cq.Workplane("YZ", origin=(x0, 0, 0)).center(p.axis, 0).circle(r).extrude(x1 - x0)


def light_dock(p: Params = DEFAULT) -> cq.Workplane:
    dock = _floor(p)
    for part in (*_lips(p), *_cheeks(p)):
        dock = dock.union(part)
    dock = dock.cut(_gate_notch(p)).cut(_tube_trough(p))
    for stand in _spool_stands(p):
        dock = dock.union(stand)
    return dock


def build(p: Params = DEFAULT, turn: float = 0.0) -> dict[str, cq.Workplane]:
    """The light dock in mockup coordinates. It does not move when the knob turns."""
    return {"light_dock": light_dock(p)}
