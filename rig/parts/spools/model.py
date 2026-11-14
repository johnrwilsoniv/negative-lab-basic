"""5 · Spools: the supply spool the uncut roll is wound on, and the take-up spool it winds onto (ruling D5).

Each spool stands upright on a pin on the light dock's floor, beside the gate, on the lens side of the film, at
x_spool: there a half-wound roll is tangent to the film plane, so the film runs straight from the roll into the
channel, off by no more than a degree or two as the roll grows or shrinks. A Ø30 core (`spool_core_r` 15) keeps processed
film from curling hard; the flanges are `spool_clear` beyond the film's edges.

Each spool is two prints: the spool (the bottom flange and the core, with a slit for the film's end and a socket
in its top) and the cap (the top flange, scalloped round its rim for a grip, with a spigot that presses into the
socket). In one piece the top flange would hang over air. Turn the spools by their caps: the knob drives the film,
the spools only take it up or let it out, by hand.
"""

import math

import cadquery as cq

import cadutil
from cadutil import box
from params import DEFAULT, Params

# The spool prints bottom flange down; the cap upside down, its top on the bed and the spigot up.
PRINT_UP = {"spool_supply": "+y", "spool_takeup": "+y", "cap_supply": "-y", "cap_takeup": "-y"}
SIDES = {"supply": -1, "takeup": 1}


def spool(p: Params, side: str) -> cq.Workplane:
    """The bottom flange (standing on its pedestal) and the core, bored for the pin, with the cap's socket in its top and
    a slit spool_slit_depth into the core, on the side away from the film, for the film's end."""
    x, z = p.x_spool, SIDES[side] * p.spool_z
    y_top = p.y_spool + p.spool_core_h
    wp = cadutil.cylinder_y(x, z, p.spool_flange_r, p.y_pedestal, p.y_spool)
    wp = wp.union(cadutil.cylinder_y(x, z, p.spool_core_r, p.y_spool - 0.01, y_top))
    wp = wp.cut(cadutil.cylinder_y(x, z, p.spool_pin_d / 2 + p.bearing_clear, p.y_pedestal - 1, y_top + 1))
    wp = wp.cut(cadutil.cylinder_y(x, z, p.cap_spigot_r, y_top - p.cap_spigot_h, y_top + 1))
    slit = box(x - p.spool_core_r - 1, x - p.spool_core_r + p.spool_slit_depth, p.y_spool, y_top + 1,
               z - p.spool_slit_w / 2, z + p.spool_slit_w / 2)
    return wp.cut(slit)


def cap(p: Params, side: str) -> cq.Workplane:
    """The top flange on the core's top, cap_t thick, scalloped, with its spigot pressed into the core's socket."""
    x, z = p.x_spool, SIDES[side] * p.spool_z
    y0 = p.y_spool + p.spool_core_h
    wp = cadutil.cylinder_y(x, z, p.spool_flange_r, y0, y0 + p.cap_t)
    wp = wp.union(cadutil.cylinder_y(x, z, p.cap_spigot_r, y0 - p.cap_spigot_h, y0 + 0.01))
    for k in range(p.grip_n):
        a = 2 * math.pi * k / p.grip_n
        wp = wp.cut(cadutil.cylinder_y(x + p.spool_flange_r * math.cos(a), z + p.spool_flange_r * math.sin(a),
                                       p.grip_r, y0 - 1, y0 + p.cap_t + 1))
    return wp


def build(p: Params = DEFAULT, turn: float = 0.0) -> dict[str, cq.Workplane]:
    """The spools and caps in mockup coordinates. They are turned by hand, so `turn` does not move them."""
    out: dict[str, cq.Workplane] = {}
    for side in SIDES:
        out[f"spool_{side}"] = spool(p, side)
        out[f"cap_{side}"] = cap(p, side)
    return out
