"""3 · Film gate: the gate front and the gate body, pressed together on four friction pegs (ruling D2).

The film runs along z, flat, in a channel `channel` deep recessed into the gate body's front face, across
the whole width of the body, so it enters at one side and leaves at the other. The gate front's rear face
closes the channel: it is the film reference plane (`x_ref`), and it prints on the bed, so the face the
film's front slides on is the smoothest there is. Nothing clamps: the channel is the film's thickness plus
0.17, which holds it flat. The channel is `channel_clear` taller than the film, so its walls keep the strip
straight in y, and it opens up over `lead_in` at each side so the film's end finds its way in.

The gate front is a solid block from the gate's front face to the reference plane: the tube socket, then a
light passage that narrows to the frame window, which runs straight for `win_depth` to the reference plane.
Behind the channel the gate body is solid too, apart from:
  - the light passage, from `body_win` at its front face to `rear_win` on the CS-Lite's lit face;
  - the two sprocket pockets (D3), vertical, at z = +-sprocket_z, `r_pocket` round, from `y_pocket` up
    through the body's top, where the sprockets drop in; each breaks through the front face, so the teeth reach
    the film. A bearing hole under each pocket takes the shaft's lower end, which stands on its floor;
  - the idler's axle hole, in the top, between the pockets (the deck and the gears: film_drive).
Pockets and holes run along y, which lies on the bed when the body prints, so each is a teardrop pointing at
the gate front (the top of the print).

The teeth reach `tooth_h` past the film, into the gate front: two grooves in its rear face per sprocket, one
per perforation row, from the side of the gate to `relief_z`, ramping up to the face at 45 degrees on the
window's side.

The pegs stand on the body's front face, outside the channel, and press into holes through the gate front
(`peg_fit` 0: FDM prints holes a little small).
"""

import cadquery as cq

import cadutil
from cadutil import box
from params import DEFAULT, Params

# Both print with their reference-plane faces on the bed (-x up for the gate front, whose rear face it is) or up
# (the body, rear face on the bed, -x up too): every opening then runs straight up, or leans no more than 45 degrees.
PRINT_UP = {"gate_front": "-x", "gate_body": "-x"}


def _rect_x(p: Params, x: float, w: float, h: float) -> cq.Workplane:
    """A w (z) by h (y) rectangle on the lens axis, in the plane at x (the workplane's normal is +x)."""
    return cq.Workplane("YZ", origin=(x, 0, 0)).center(p.axis, 0).rect(h, w)


def _light_passage(p: Params) -> cq.Workplane:
    """The air the lens looks through: the frame window straight for win_depth from the reference plane, then flaring
    to `flare_scale` times its size at the socket's floor, so its corners reach the tube's bore."""
    x_win = p.x_ref - p.win_depth
    x_socket = p.x_gate + p.front_wall
    k = p.flare_scale
    window = box(x_win - 0.01, p.x_ref + 1, p.axis - p.win_h / 2, p.axis + p.win_h / 2, -p.win_w / 2, p.win_w / 2)
    flare = (
        _rect_x(p, x_socket, k * p.win_w, k * p.win_h)
        .workplane(offset=x_win - x_socket).rect(p.win_h, p.win_w)
        .loft(combine=True, ruled=True)
    )
    return window.union(flare)


def _rods_x(p: Params, x0: float, x1: float, d: float) -> cq.Workplane:
    """A d diameter rod along x from x0 to x1 at each of the four pegs."""
    return cq.Workplane("YZ", origin=(x0, 0, 0)).pushPoints(p.peg_points).circle(d / 2).extrude(x1 - x0)


def _relief(p: Params, sign: int, y_row: float) -> cq.Workplane:
    """One tooth groove: relief_depth forward of the reference plane, tooth_w wide about the row at y_row, from past the
    gate's side to relief_z, then up to the face at 45 degrees."""
    d, edge, z_in = p.relief_depth, p.gw / 2 + 1, p.relief_z
    outline = [(p.x_ref + 1, edge), (p.x_ref - d, edge), (p.x_ref - d, z_in), (p.x_ref, z_in - d),
               (p.x_ref + 1, z_in - d - 1)]
    outline = [(x, sign * z) for x, z in outline]
    y1 = y_row + p.tooth_w / 2
    return cq.Workplane("XZ", origin=(0, y1, 0)).polyline(outline).close().extrude(p.tooth_w)


def gate_front(p: Params = DEFAULT) -> cq.Workplane:
    """x_gate .. x_ref, gh tall, gw wide: the tube socket, the light passage, the peg holes, the tooth grooves."""
    block = box(p.x_gate, p.x_ref, 0, p.gh, -p.gw / 2, p.gw / 2)
    socket = cq.Workplane("YZ", origin=(p.x_gate - 1, 0, 0)).center(p.axis, 0).circle(p.fit_r).extrude(p.front_wall + 1)
    block = block.cut(socket).cut(_light_passage(p))
    block = block.cut(_rods_x(p, p.x_gate - 1, p.x_ref + 1, p.peg_d + p.peg_fit))
    for sign in (-1, 1):
        for y_row in (p.axis - p.perf_dy, p.axis + p.perf_dy):
            block = block.cut(_relief(p, sign, y_row))
    return block


def _channel(p: Params) -> cq.Workplane:
    """The film's channel, across the body's whole width, with a lead-in at each side."""
    y0, y1 = p.axis - p.channel_h / 2, p.axis + p.channel_h / 2
    cut = box(p.x_ref - 1, p.x_ref + p.channel, y0, y1, -p.gw / 2 - 1, p.gw / 2 + 1)
    for sign in (-1, 1):
        z_in, z_out = p.gw / 2 - p.lead_in, p.gw / 2 + 1
        outline = [(p.x_ref - 1, z_in), (p.x_ref + p.channel, z_in), (p.x_ref + p.lead_in_depth, p.gw / 2),
                   (p.x_ref + p.lead_in_depth, z_out), (p.x_ref - 1, z_out)]
        wedge = cq.Workplane("XZ", origin=(0, y1, 0)).polyline([(x, sign * z) for x, z in outline]).close()
        cut = cut.union(wedge.extrude(y1 - y0))
    return cut


def _body_passage(p: Params) -> cq.Workplane:
    """The light's way from the lit face to the film: rear_win at the rear face, body_win at the front."""
    return (
        _rect_x(p, p.x_ref - 0.01, p.body_win_w, p.body_win_h)
        .workplane(offset=p.x_light - p.x_ref + 0.02).rect(p.rear_win_h, p.rear_win_w)
        .loft(combine=True, ruled=True)
    )


def _pegs(p: Params) -> cq.Workplane:
    """Standing peg_len forward of the body's front face, chamfered at the tip."""
    pegs = _rods_x(p, p.x_ref - p.peg_len, p.x_ref + 0.01, p.peg_d)
    return pegs.faces("<X").edges().chamfer(p.peg_chamfer)


def gate_body(p: Params = DEFAULT) -> cq.Workplane:
    """x_ref .. x_light, gh tall, gw wide: the channel, the light passage, the sprocket pockets and bearings, the idler's
    axle hole, and the pegs."""
    body = box(p.x_ref, p.x_light, 0, p.gh, -p.gw / 2, p.gw / 2)
    body = body.cut(_channel(p)).cut(_body_passage(p))
    xs = p.x_sprocket
    for z in (-p.sprocket_z, p.sprocket_z):
        body = body.cut(cadutil.teardrop_y(xs, z, p.r_pocket, p.y_pocket, p.gh + 1))
        body = body.cut(cadutil.teardrop_y(xs, z, p.shaft_d / 2 + p.bearing_clear, p.shaft_floor, p.y_pocket + 0.01))
    body = body.cut(cadutil.teardrop_y(xs, 0, p.shaft_d / 2, p.gh - p.axle_hole_depth, p.gh + 1))
    return body.union(_pegs(p))


def build(p: Params = DEFAULT, turn: float = 0.0) -> dict[str, cq.Workplane]:
    """The gate's printed solids in mockup coordinates. Neither moves when the knob turns."""
    return {"gate_front": gate_front(p), "gate_body": gate_body(p)}
