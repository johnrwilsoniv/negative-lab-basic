"""2 · Tube: slides into the adapter socket at the camera end and the gate's front-wall hole at the other.

Mockup `rebuild()` lines 410-413 draw a plain ring; the sawtooth baffle ribs inside are ruling R12.
The tube is one revolved (x, r) profile, so there are no booleans to go wrong.
"""

import cadquery as cq

from params import DEFAULT, Params

# Printed upright with the camera end (-x) on the bed: print-up is +x.
# Each rib's lower flank is a 45 degree cone, as steep as an overhang can be without supports: it
# climbs from the bore (x = a) to the tip (x = a + h) with an axial run equal to its height. The
# rib's other face, square to the axis, faces up and needs no support. Light from the film runs
# toward -x, so it meets those square faces head on and is sent back.
PRINT_UP = {"tube": "+x"}


def _bore(p: Params) -> list[tuple[float, float]]:
    """The inner (x, r) outline, camera end to light end: the bore with a rib every baffle_pitch,
    centred between the end margins."""
    h = p.baffle_h
    n = p.baffle_count
    span = (n - 1) * p.baffle_pitch + h
    first = p.tube_x0 + p.baffle_margin + (p.tube_len - 2 * p.baffle_margin - span) / 2
    outline = [(p.tube_x0, p.tube_ri)]
    for k in range(n):
        a = first + k * p.baffle_pitch
        outline += [(a, p.tube_ri), (a + h, p.tube_ri - h), (a + h, p.tube_ri)]
    return outline + [(p.tube_x1, p.tube_ri)]


def build(p: Params = DEFAULT, lock: bool = False) -> dict[str, cq.Workplane]:
    """The tube, along x at y = axis, from tube_x0 to tube_x1."""
    if p.tube_len > p.tube_max_len:
        raise ValueError(
            f"the tube is {p.tube_len:g} mm long but prints upright, so at most {p.tube_max_len:g} mm; "
            "the spigot split for long tubes isn't built yet"
        )
    if not 0 <= p.baffle_h < p.baffle_pitch:
        raise ValueError(f"baffle_h must be from 0 up to baffle_pitch ({p.baffle_pitch:g}), got {p.baffle_h:g}")

    outline = [(p.tube_x0, p.tube_ro), (p.tube_x1, p.tube_ro)] + _bore(p)[::-1]
    tube = (
        cq.Workplane("XY")
        .polyline(outline)
        .close()
        .revolve(360, (0, 0, 0), (1, 0, 0))
        .translate((0, p.axis, 0))
    )
    return {"tube": tube}
