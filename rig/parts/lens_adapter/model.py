"""1 · Lens adapter: screws into the Laowa's M67 x 0.75 filter thread; the tube slides into its socket.

Mockup `rebuild()` lines 396-408. Each solid is built about the local +Z axis (local z = mockup x,
radius along local X), then turned onto the lens axis.
"""

import math

import cadquery as cq

from params import DEFAULT, Params

# How far the thread's hidden parts reach into the body: its root sinks this deep into the core,
# and the lead-in cone starts this much deeper still at the free end. The booleans then cut
# through faces instead of running along an edge of the other solid.
OVERLAP = 0.05

PRINT_UP = {"adapter": "-x", "thread_coupon": "-x"}


def _revolve(rz: list[tuple[float, float]]) -> cq.Solid:
    """The closed (r, z) polygon turned a full circle about the local z axis."""
    wire = cq.Wire.makePolygon([cq.Vector(r, 0, z) for r, z in rz], close=True)
    return cq.Solid.revolve(cq.Face.makeFromWires(wire), 360, cq.Vector(0, 0, 0), cq.Vector(0, 0, 1))


def _on_lens_axis(shape: cq.Shape, p: Params) -> cq.Workplane:
    # A rotation, not a mirror, so the thread keeps its hand: local +z -> mockup +x.
    placed = shape.rotate(cq.Vector(0, 0, 0), cq.Vector(0, 1, 0), 90).translate(cq.Vector(0, p.axis, 0))
    return cq.Workplane("XY").add(placed)


def _thread(p: Params) -> cq.Solid:
    """The right-hand helical thread for x_front - thread_len .. x_front, in local coordinates.

    Its root is buried OVERLAP inside the core and its far end inside whatever follows the
    flange face (flange or grip ring), so it only shows once fused to a body. The free end is
    cut back by the lead-in cone.
    """
    pitch, crest, x0, x1 = p.thread_pitch, p.thread_crest_r, p.x_front - p.thread_len, p.x_front
    bottom = p.thread_root_r - OVERLAP
    flank = (pitch / 2) / p.thread_h                      # axial run per unit depth: tan 30°

    def half_width(r: float) -> float:
        return p.thread_crest_flat / 2 + (crest - r) * flank

    # Ends one turn past the flange face, about 1.1 deep including the profile's half width, so
    # the flange (3) and grip ring (2) cover it; starts at least one turn before the free end.
    turns = math.ceil(p.thread_len / pitch) + 2
    z_start = x1 + pitch - turns * pitch
    # One helix edge per turn: a sweep face that wraps several turns makes the booleans miss
    # their intersections (common volume 0, wrong fuse) without raising.
    helix = cq.Wire.assembleEdges([
        cq.Wire.makeHelix(pitch, pitch, crest, center=cq.Vector(0, 0, z_start + i * pitch)).Edges()[0]
        for i in range(turns)
    ])
    profile = cq.Wire.makePolygon(
        [
            cq.Vector(r, 0, z_start + dz)
            for r, dz in [
                (bottom, -half_width(bottom)),
                (crest, -half_width(crest)),
                (crest, half_width(crest)),
                (bottom, half_width(bottom)),
            ]
        ],
        close=True,
    )
    sweep = cq.Solid.sweep(profile, [], helix, makeSolid=True, isFrenet=True)

    rise = 1 / math.tan(math.radians(p.thread_lead_in))   # axial run per unit radius
    cone_r, outside = bottom - OVERLAP, crest + 1
    lead_in = _revolve(
        [(cone_r, z_start - 1), (cone_r, x0), (outside, x0 + (outside - cone_r) * rise), (outside, z_start - 1)]
    )
    return sweep.cut(lead_in)


def _threaded(p: Params, beyond: list[tuple[float, float]]) -> cq.Workplane:
    """The threaded core, carried on past the flange face by the (r, local z) outline `beyond`,
    which runs from the outer corner at x_front round to the bore."""
    x0 = p.x_front - p.thread_len
    core = [(p.adapter_bore_r, x0), (p.thread_root_r, x0), (p.thread_root_r, p.x_front)]
    return _on_lens_axis(_revolve(core + beyond).fuse(_thread(p)), p)


def build(p: Params = DEFAULT, lock: bool = False) -> dict[str, cq.Workplane]:
    """The adapter: threaded core, then the flange, then the tube socket."""
    floor = p.x_front + p.flange            # the tube end sits here
    rim = floor + p.socket_depth
    od = p.adapter_r
    beyond = [(od, p.x_front), (od, rim), (p.fit_r, rim), (p.fit_r, floor), (p.adapter_bore_r, floor)]
    return {"adapter": _threaded(p, beyond)}


def extras(p: Params = DEFAULT) -> dict[str, cq.Workplane]:
    """Print-only: the adapter's thread on a grip ring, to check the fit before the full print."""
    top = p.x_front + p.coupon_grip
    beyond = [(p.adapter_r, p.x_front), (p.adapter_r, top), (p.adapter_bore_r, top)]
    return {"thread_coupon": _threaded(p, beyond)}
