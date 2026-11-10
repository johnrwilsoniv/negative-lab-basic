"""Film gate: the gate front (tube socket, light passage, frame window, peg holes, the teeth's grooves, and the
film reference plane) and the gate body (the film channel, the light passage, the sprocket pockets and bearings,
the idler's axle hole, the pegs).

Openings are measured by probing the solids with thin boxes, not recomputed from the shapes the model cuts.
"""

import math

import pytest

import cadutil
from cadutil import probe
from params import DEFAULT, Params
from parts.film_gate import model

p = DEFAULT
Q = Params(wd=150, axis=50)
EPS = 1e-6
T = 0.02                  # how far an opening's edge is probed


@pytest.fixture(scope="module")
def built():
    return model.build(p)


@pytest.fixture(scope="module")
def front(built):
    return built["gate_front"]


@pytest.fixture(scope="module")
def body(built):
    return built["gate_body"]


def filled(wp, *ranges):
    """Fraction of the probe box (x0, x1, y0, y1, z0, z1) that is material."""
    pr = probe(*ranges)
    return cadutil.common_volume(wp, pr) / cadutil.volume(pr)


def assert_void(wp, *ranges):
    assert filled(wp, *ranges) < EPS, ranges


def assert_full(wp, *ranges):
    assert filled(wp, *ranges) > 1 - EPS, ranges


# ---- the two solids ------------------------------------------------------------------------


def test_two_solids_and_their_print_directions(built):
    assert list(built) == ["gate_front", "gate_body"]
    assert model.PRINT_UP == {"gate_front": "-x", "gate_body": "-x"}


@pytest.mark.parametrize("q", [p, Q], ids=["defaults", "other"])
def test_each_is_one_valid_solid(q):
    for name, wp in model.build(q).items():
        assert cadutil.is_valid(wp), name
        assert cadutil.volume(wp) > 0, name


def test_the_knob_does_not_move_the_gate(built):
    turned = model.build(p, 0.3)
    for name, wp in built.items():
        assert cadutil.bounds(turned[name]) == pytest.approx(cadutil.bounds(wp)), name


def test_sizes(front, body):
    assert cadutil.bounds(front) == pytest.approx((241, 254.85, 0, 78.5, -46, 46), abs=EPS)
    # the body from the reference plane to the lit face, and its pegs peg_len in front of it
    assert cadutil.bounds(body) == pytest.approx((254.85 - 6, 280, 0, 78.5, -46, 46), abs=EPS)


def test_front_and_body_meet_on_the_reference_plane_and_do_not_intersect(front, body):
    assert cadutil.common_volume(front, body) < 1e-6
    # beside the channel, the two faces touch across the whole plane
    assert_full(front, p.x_ref - T, p.x_ref, 2, 8, -40, 40)
    assert_full(body, p.x_ref, p.x_ref + T, 2, 8, -30, 30)


# ---- the gate front --------------------------------------------------------------------------


def test_the_frame_window_is_38_by_26_at_the_reference_plane(front):
    x = (p.x_ref - p.win_depth + 0.1, p.x_ref)
    assert_void(front, *x, p.axis - 13 + T, p.axis + 13 - T, -19 + T, 19 - T)
    assert_full(front, *x, p.axis + 13, p.axis + 13 + T, -10, 10)
    assert_full(front, *x, p.axis - 13 - T, p.axis - 13, -10, 10)
    assert_full(front, *x, p.axis - 5, p.axis + 5, 19, 19 + T)
    assert_full(front, *x, p.axis - 5, p.axis + 5, -19 - T, -19)


def test_the_tube_socket_is_4_deep(front):
    r = p.fit_r - T
    assert_void(front, p.x_gate, p.x_gate + 4 - T, p.axis - r / 2, p.axis + r / 2, -r / 2, r / 2)
    # just outside the socket's radius there is wall
    assert_full(front, p.x_gate, p.x_gate + 4, p.axis - 0.1, p.axis + 0.1, p.fit_r + T, p.fit_r + 0.5)


def test_the_peg_holes_run_right_through(front):
    for y, z in p.peg_points:
        h = (p.peg_d + p.peg_fit) / 2 / math.sqrt(2) - T          # a square inside the hole
        assert_void(front, p.x_gate, p.x_ref, y - h, y + h, z - h, z + h)
        assert_full(front, p.x_gate, p.x_ref, y - 0.1, y + 0.1, z + p.peg_d / 2 + T, z + p.peg_d / 2 + 0.5)


@pytest.mark.parametrize("sign", [-1, 1])
@pytest.mark.parametrize("row", [-1, 1])
def test_each_tooth_row_has_a_groove_from_the_side_to_beyond_the_sprocket(front, sign, row):
    y = p.axis + row * p.perf_dy
    d, w = p.relief_depth, p.tooth_w / 2
    z0, z1 = sorted((sign * (p.relief_z + T), sign * p.gw / 2))
    assert_void(front, p.x_ref - d + T, p.x_ref, y - w + T, y + w - T, z0, z1)
    # its floor, its sides, and the face beyond its 45 degree ramp
    assert_full(front, p.x_ref - d - T, p.x_ref - d, y - w + T, y + w - T, z0, z1)
    assert_full(front, p.x_ref - d, p.x_ref, y + w, y + w + T, z0, z1)
    zr, zw = sign * (p.relief_z - d - T), sign * (p.win_w / 2 + 0.5)       # from the ramp's foot to the window
    assert_full(front, p.x_ref - d, p.x_ref, y - w + T, y + w - T, min(zr, zw), max(zr, zw))


def test_the_grooves_clear_the_frame_window(front):
    # beside the window, between it and the grooves' ramps, the reference plane is whole
    for row in (-1, 1):
        y = p.axis + row * p.perf_dy
        assert_full(front, p.x_ref - T, p.x_ref, y - 1, y + 1, 19 + 0.5, p.relief_z - p.relief_depth - 0.1)


def test_the_gate_front_prints_with_only_the_grooves_bridged(front):
    posed = cadutil.print_pose(front, model.PRINT_UP["gate_front"])
    faces = cadutil.overhangs(posed)
    assert len(faces) == 4
    for face in faces:
        x0, x1, y0, y1, _, _ = cadutil.shape_bounds(face)
        assert min(x1 - x0, y1 - y0) == pytest.approx(p.tooth_w, abs=1e-6)      # a 2.8 bridge each


# ---- the gate body ----------------------------------------------------------------------------


def test_the_channel_runs_across_the_whole_body(body):
    y0, y1 = p.axis - p.channel_h / 2, p.axis + p.channel_h / 2
    for z in (-44, -40, 0, 40, 44):         # the lead-ins, beside the pockets, and through the window
        assert_void(body, p.x_ref, p.x_ref + p.channel - T, y0 + T, y1 - T, z - 0.5, z + 0.5)
    # its floor, beside the pockets and the window
    assert_full(body, p.x_ref + p.channel, p.x_ref + p.channel + T, y0 + T, y1 - T, 38, 42)
    # and its walls, 0.1 beyond the film's edges
    assert_full(body, p.x_ref, p.x_ref + p.channel, y1, y1 + T, 38, 42)
    assert_full(body, p.x_ref, p.x_ref + p.channel, y0 - T, y0, 38, 42)
    assert p.channel_h - p.film_w == pytest.approx(0.2)


@pytest.mark.parametrize("sign", [-1, 1])
def test_the_channel_opens_up_at_each_side(body, sign):
    y = (p.axis - 5, p.axis + 5)
    z = sign * (p.gw / 2 - T)
    assert_void(body, p.x_ref, p.x_ref + p.lead_in_depth - T, *y, min(z, sign * p.gw / 2), max(z, sign * p.gw / 2))
    assert_full(body, p.x_ref + p.lead_in_depth, p.x_ref + p.lead_in_depth + T, *y, min(z, sign * p.gw / 2),
                max(z, sign * p.gw / 2))


def test_the_light_passage_runs_through_from_the_lit_face(body):
    assert_void(body, p.x_ref, p.x_ref + 0.1, p.axis - 14 + T, p.axis + 14 - T, -20 + T, 20 - T)
    assert_full(body, p.x_ref + p.channel, p.x_ref + 0.4, p.axis - 5, p.axis + 5, 20.1, 20.1 + T)    # it widens back
    assert_void(body, p.x_light - 0.1, p.x_light, p.axis - 17 + T, p.axis + 17 - T, -23 + T, 23 - T)
    assert_full(body, p.x_light - 0.1, p.x_light, p.axis - 5, p.axis + 5, 23, 23 + T)


@pytest.mark.parametrize("sign", [-1, 1])
def test_each_sprocket_pocket_is_open_at_the_top_and_breaks_through_to_the_film(body, sign):
    xs, zs = p.x_sprocket, sign * p.sprocket_z
    h = p.r_pocket / math.sqrt(2) - T
    assert_void(body, xs - h, xs + h, p.y_pocket + T, p.gh, zs - h, zs + h)
    # it opens through the front face, where the teeth reach the film
    assert_void(body, p.x_ref, p.x_ref + 0.5, p.axis - 5, p.axis + 5, zs - 3, zs + 3)
    # its floor, and the wall behind it
    assert_full(body, xs + 1, xs + 2, p.y_pocket - 1, p.y_pocket, zs + 4, zs + 5)      # beside the bearing hole
    assert_full(body, xs + p.r_pocket, xs + p.r_pocket + T, p.axis - 1, p.axis + 1, zs - 0.5, zs + 0.5)


@pytest.mark.parametrize("sign", [-1, 1])
def test_each_bearing_hole_takes_the_shaft_down_to_the_floor(body, sign):
    xs, zs, r = p.x_sprocket, sign * p.sprocket_z, p.shaft_d / 2 + p.bearing_clear
    h = r / math.sqrt(2) - T
    assert_void(body, xs - h, xs + h, p.shaft_floor + T, p.y_pocket, zs - h, zs + h)
    assert_full(body, xs - 1, xs + 1, p.shaft_floor - 1, p.shaft_floor, zs - 1, zs + 1)
    assert_full(body, xs + r, xs + r + T, p.shaft_floor + 2, p.shaft_floor + 6, zs - 0.1, zs + 0.1)


def test_the_idler_axle_hole_is_in_the_top(body):
    xs, r = p.x_sprocket, p.shaft_d / 2
    h = r / math.sqrt(2) - T
    assert_void(body, xs - h, xs + h, p.gh - p.axle_hole_depth + T, p.gh, -h, h)
    assert_full(body, xs - 1, xs + 1, p.gh - p.axle_hole_depth - 1, p.gh - p.axle_hole_depth, -1, 1)
    assert_full(body, xs + r, xs + r + T, p.gh - 4, p.gh - 2, -0.1, 0.1)


def test_four_pegs_stand_on_the_body_and_fill_the_holes(front, body):
    for y, z in p.peg_points:
        h = p.peg_d / 2 / math.sqrt(2) - T
        assert_full(body, p.x_ref - p.peg_len + p.peg_chamfer, p.x_ref, y - h, y + h, z - h, z + h)
        assert_void(body, p.x_ref - p.peg_len + p.peg_chamfer, p.x_ref, y - 0.1, y + 0.1, z + p.peg_d / 2 + T, z + 3)
    assert p.peg_len < p.x_ref - p.x_gate                 # they never come out of the front's face


def test_the_gate_body_prints_with_no_overhangs(body):
    posed = cadutil.print_pose(body, model.PRINT_UP["gate_body"])
    assert cadutil.overhangs(posed) == []
