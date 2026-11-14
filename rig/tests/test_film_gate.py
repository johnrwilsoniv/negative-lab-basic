"""Film gate: the gate front (tube socket, light passage, frame window, and the film reference plane),
the gate body (floor, side walls, rear wall, screw pillars), the lid, and the floating
pressure plate.

Windows, slots and pads are measured by probing the solids with thin boxes, and faces by the
bounds of what a probe finds, not recomputed from the params. The pads are also mated against
ramps drawn the way the mockup draws them, because that is the interface the lock switch has to
meet.
"""

import math

import cadquery as cq
import pytest

import cadutil
from cadutil import probe
from params import DEFAULT, Params
from parts.film_gate import model
from parts.lock_switch import model as switch_model
from parts.tube import model as tube_model

p = DEFAULT
EPS = 1e-6
T = 0.02                  # how far an opening's edge is probed
FACE_TOL = 1e-3
SLOPE = p.ramp_rise / p.ramp_len


@pytest.fixture(scope="module")
def built():
    return model.build(p)


@pytest.fixture(scope="module")
def built_lock():
    return model.build(p, lock=True)


@pytest.fixture(scope="module")
def front(built):
    return built["gate_front"]


@pytest.fixture(scope="module")
def body(built):
    return built["gate_body"]


@pytest.fixture(scope="module")
def lid(built):
    return built["gate_lid"]


@pytest.fixture(scope="module")
def plate(built):
    return built["pressure_plate"]


@pytest.fixture(scope="module")
def plate_lock(built_lock):
    return built_lock["pressure_plate"]


def filled(wp, *ranges):
    """Fraction of the probe box (x0, x1, y0, y1, z0, z1) that is material."""
    pr = probe(*ranges)
    return cadutil.common_volume(wp, pr) / cadutil.volume(pr)


def assert_void(wp, *ranges):
    assert filled(wp, *ranges) < EPS, ranges


def assert_full(wp, *ranges):
    assert filled(wp, *ranges) > 1 - EPS, ranges


def assert_opening(wp, place, a, b, ca=0.0, cb=p.axis):
    """An opening a wide by b tall, centred on (ca, cb), through the wall.

    `place(a0, a1, b0, b1)` gives the probe's six ranges: those two ranges across the opening and
    the wall's whole thickness. The opening is clear T inside every edge and solid T outside it.
    """
    assert_void(wp, *place(ca - a / 2 + T, ca + a / 2 - T, cb - b / 2 + T, cb + b / 2 - T))
    inside_a, inside_b = (ca - a / 2 + T, ca + a / 2 - T), (cb - b / 2 + T, cb + b / 2 - T)
    for edge in (-1, 1):
        a_out = sorted((ca + edge * (a / 2 + 0.001), ca + edge * (a / 2 + T)))
        b_out = sorted((cb + edge * (b / 2 + 0.001), cb + edge * (b / 2 + T)))
        assert_full(wp, *place(*a_out, *inside_b))
        assert_full(wp, *place(*inside_a, *b_out))


def across_x(x0, x1):
    """Probe placer for a wall in x, opening across (z, y)."""
    return lambda z0, z1, y0, y1: (x0, x1, y0, y1, z0, z1)


def across_z(z0, z1):
    """Probe placer for a wall in z, opening across (x, y)."""
    return lambda x0, x1, y0, y1: (x0, x1, y0, y1, z0, z1)


def across_y(y0, y1):
    """Probe placer for a wall in y, opening across (x, z)."""
    return lambda x0, x1, z0, z1: (x0, x1, y0, y1, z0, z1)


def face_x(wp, lo_or_hi):
    """x of the plate's front (0) or back (1) face, probed where there is only plate: below the window, above the sill
    the pressure plate stands on (F20). On the gate front, 1 is the reference plane."""
    bounds = cadutil.common_bounds(wp, probe(p.x_film - 6, p.x_film + 6, BELOW_WINDOW[0], BELOW_WINDOW[1], -10, 10))
    return bounds[lo_or_hi]


def rod(x, length, r):
    """A cylinder of radius r along the lens axis from x."""
    return cq.Workplane("YZ", origin=(x, p.axis, 0)).circle(r).extrude(length)


def ramp(zr, y0):
    """A wedge plate ramp as the mockup draws it: 4 high from y0, spanning ramp_len about zr, its
    face ramp_t(u) in front of the wedge plate, thick toward -z."""
    h = p.ramp_len / 2
    pts = [
        (p.x_wedge, zr - h),
        (p.x_wedge - p.ramp_t(-h), zr - h),
        (p.x_wedge - p.ramp_t(h), zr + h),
        (p.x_wedge, zr + h),
    ]
    return cq.Workplane("XZ", origin=(0, y0 + p.pad, 0)).polyline(pts).close().extrude(p.pad)


PADS = [(zc, p.axis + dy) for zc in (-p.pad_z, p.pad_z) for dy in (-p.pad_dy, p.pad_dy)]


def ramps(shift):
    """The four ramps with the lock switch `shift` along z from where a pad's own centre is."""
    return [ramp(zc + shift, yc - p.pad / 2) for zc, yc in PADS]


# ---- solids and parameters -----------------------------------------------------------

NAMES = ["gate_front", "gate_body", "gate_lid", "pressure_plate"]
SILL = 23                       # the sill's top (F20): the film's lower edge, axis - 17.5
STEP = (246.05, 248.05, 27)     # the backer's step on it (F12, F20): its face, the end of its top, and its top
BELOW_WINDOW = (SILL + 1, 27)   # where the plates are plate only: above the sill, under the window (axis - 13)
REF = 240.7                     # x_ref: the film reference plane, the gate front's rear face
REAR = 266                      # the body's rear face: the CS-Lite's lit face (F10)
PILLARS = [(0, 9, -55, -46), (0, 9, 46, 55), (64.5, 73.5, -55, -46), (64.5, 73.5, 46, 55)]     # y0 y1 z0 z1
RAILS = [(-49, -46), (46, 49)]  # the lid's rails (F22), z0 z1: on the upper pillars, up to the lid's top


def test_solid_names_and_print_directions(built):
    assert list(built) == NAMES
    assert model.PRINT_UP == {"gate_front": "-x", "gate_body": "-x", "gate_lid": "+y", "pressure_plate": "+x"}


@pytest.mark.parametrize("name", NAMES)
@pytest.mark.parametrize("lock", [False, True])
def test_each_solid_is_one_valid_closed_solid(name, lock):
    solid = cadutil.solid(model.build(p, lock)[name])      # raises unless exactly one
    assert solid.isValid()
    assert all(shell.Closed() for shell in solid.Shells())
    assert solid.Volume() > 0
    assert cadutil.non_manifold_edges(model.build(p, lock)[name]) == []     # Onshape rejects any


def test_new_params_defaults():
    assert (p.film_slot_mouth, p.film_slot_h, p.film_slot_y0) == (2.0, 35.2, p.axis - 17.5)
    assert (p.sill_y, p.backer_step_d, p.backer_step_top, p.plate_lead_in) == (SILL, 2, STEP[2], 0.6)
    assert (p.rear_win_w, p.rear_win_h) == (46, 34)
    assert (p.tab_t, p.tab_clear, p.slot_end) == (2, 0, 3)                  # the slot as wide as the tab (F25)
    assert (p.pad, p.pad_z, p.pad_dy) == (4, 22, 15)
    assert (p.ear_w, p.ear_h, p.joint_hole_d, p.cbore_d, p.cbore_depth, p.pilot_d, p.pilot_depth) == (9, 9, 3.4, 6.5, 13.5, 2.5, 12)
    assert (p.x_ref, p.gate_front_w) == (REF, 110)
    assert p.screw_points == [(4.5, -50.5), (4.5, 50.5), (69, -50.5), (69, 50.5)]
    assert (p.lid_side_clear, p.lid_rail_w) == (0.2, 3)


# ---- gate front ----------------------------------------------------------------------


def test_front_bounds_at_default(front):
    assert cadutil.bounds(front) == pytest.approx((217, REF, 0, 76.5, -55, 55), abs=EPS)
    assert (p.x_gate, p.gh) == (217, 76.5)


def test_socket_is_the_tube_friction_fit_and_on_the_axis(front):
    tube = tube_model.build(p)["tube"]
    tube_r = cadutil.size(tube)[1] / 2
    arcs = [e for e in cadutil.solid(front).Edges() if e.geomType() == "CIRCLE" and e.radius() > 30]
    assert len(arcs) == 2                                        # the socket's two rims
    for arc in arcs:
        assert arc.radius() - tube_r == pytest.approx(0.05, abs=EPS)          # Ø68.5 in Ø68.6 (F23)
        centre = arc.arcCenter()
        assert (centre.y, centre.z) == pytest.approx((p.axis, 0), abs=EPS)
    assert sorted(arc.arcCenter().x for arc in arcs) == pytest.approx([217, 226], abs=EPS)     # 9 deep (F24)


def test_socket_is_clear_to_r34_3_and_solid_beyond(front):
    assert cadutil.common_volume(front, rod(217, 9, 34.3 - T)) < 1e-3
    assert cadutil.common_volume(front, rod(217, 9, 34.3 + T)) > 1.0


def test_socket_stays_under_the_top_edge(front):
    # R8 closed: the r34.3 socket tops out at 74.8, leaving 1.7 of the gate front over it, no notch in the top
    assert p.axis + p.fit_r == pytest.approx(74.8)
    assert_void(front, 217, 226, 74.7, 74.79, -0.5, 0.5)
    assert_full(front, 217, 226, 74.81, 76.5, -8, 8)


def test_tube_light_end_rests_on_the_socket_floor_all_round(front):
    tube = tube_model.build(p)["tube"]
    assert cadutil.bounds(tube)[1] == pytest.approx(226, abs=EPS)       # ends on the socket's floor
    assert cadutil.common_volume(front, tube) < 1e-3
    # the floor is solid under the whole tube wall (r 32 .. 34.25): the light passage's corners reach r 32, no further
    ring = rod(226, 0.5, 34.25).cut(rod(226, 0.5, 32 + 1e-4))
    assert cadutil.common_volume(front, ring) == pytest.approx(cadutil.volume(ring), rel=1e-6)
    assert p.flare_scale * math.hypot(38, 26) / 2 == pytest.approx(32, abs=EPS)


def test_frame_window_is_38_by_26_straight_for_1_8_from_the_reference_plane(front):
    assert_opening(front, across_x(REF - 1.8, REF), 38, 26)
    assert face_x(front, 1) == pytest.approx(REF, abs=EPS)
    assert face_x(front, 1) == pytest.approx(p.x_film - p.channel / 2, abs=EPS)


def test_light_passage_flares_from_the_window_to_the_socket(front):
    # halfway along the flare (x 232.45) the opening is the window scaled by (1 + k) / 2
    k = (1 + p.flare_scale) / 2
    x = (226 + REF - 1.8) / 2
    assert_opening(front, across_x(x - 0.0001, x + 0.0001), 38 * k, 26 * k)     # thin: the walls lean ~0.58 in x
    # and it only widens toward the camera: at every x the opening holds the window's own outline
    assert_void(front, 226, REF, p.axis - 13 + T, p.axis + 13 - T, -19 + T, 19 - T)


def test_the_reference_plane_is_whole_but_for_the_window(front):
    # the film lies on it across the whole width, beyond the side walls where it leaves through the notches
    thin = (REF - 0.01, REF)
    assert cadutil.common_volume(front, probe(*thin, 0, 76.5, -55, 55)) == pytest.approx(
        0.01 * (76.5 * 110 - 38 * 26 - 4 * math.pi * 1.7**2), rel=1e-6)


def test_four_screw_holes_counterbored_from_the_front(front):
    for y, z in p.screw_points:
        # thin probes along y through the screw's centre line (z +-0.05): the hole r 1.7, the counterbore r 3.25
        assert_void(front, 217, REF, y - 1.65, y + 1.65, z - 0.05, z + 0.05)
        assert_full(front, 230.51, REF, y + 1.71, y + 1.71 + T, z - 0.05, z + 0.05)
        assert_void(front, 217, 230.49, y - 3.2, y + 3.2, z - 0.05, z + 0.05)          # 13.5 deep (F24)
        assert_full(front, 217, 230.5, y + 3.26, y + 3.26 + T, z - 0.05, z + 0.05)


def segment_area(r, d):
    """Area of the circle of radius r on the far side of a chord d from its centre."""
    return r * r * math.acos(d / r) - d * math.sqrt(r * r - d * d)


def test_front_volume(front):
    a1, k = 38 * 26, p.flare_scale
    a2 = k * k * a1
    flare = 12.9 / 3 * (a1 + a2 + math.sqrt(a1 * a2))
    socket = 9 * math.pi * 34.3**2                                      # whole: 1.7 under the top
    holes = 4 * (23.7 * math.pi * 1.7**2 + 13.5 * math.pi * (3.25**2 - 1.7**2))
    mark = 3 * 3 / 2 * 0.36                                             # the ▲ (F18)
    assert cadutil.volume(front) == pytest.approx(23.7 * 76.5 * 110 - socket - 1.8 * a1 - flare - holes - mark, rel=1e-6)


def test_front_top_is_plain_behind_the_socket(front):
    # F14: no lettering; the top is solid from the front face to x_ref.
    assert_full(front, 217, REF, 76, 76.5, -55, 55)


# ---- gate body -----------------------------------------------------------------------


def test_body_bounds_at_default(body):
    assert cadutil.bounds(body) == pytest.approx((REF, REAR, 0, 76.5, -55, 55), abs=EPS)


def test_front_and_body_meet_on_the_reference_plane_and_only_touch(front, body):
    assert cadutil.common_volume(front, body) < 1e-3
    # touching over the walls' ends, not apart: 0.01 closer and they overlap
    assert cadutil.common_volume(front, body.translate((-0.01, 0, 0))) > 1e-3


def test_body_is_open_topped_and_open_toward_the_gate_front(body):
    # side walls stop 3 below the top and the floor is 3 thick: the lid and the floor close the rest
    assert_void(body, REF, 263, 73.5 + EPS, 76.5, -46, 46)
    assert_full(body, REF, 263, 0, 3, -46, 46)
    for sign in (-1, 1):
        z = sorted((sign * 43, sign * 46))
        assert_full(body, 244, 263, 3, 73.5, *z)
    assert_void(body, REF, STEP[0], SILL, 73.5, -42.99, 42.99)            # hollow between the walls above the sill,
    assert_void(body, STEP[0], 263, STEP[2], 73.5, -42.99, 42.99)         # over the step,
    assert_void(body, STEP[1] + STEP[2] - SILL, 263, SILL, 73.5, -42.99, 42.99)    # and behind its slope; no front wall


def test_rear_wall_is_full_height_and_full_width_with_its_window(body):
    assert_full(body, 263, REAR, 0, 76.5, -46, -37)
    assert_full(body, 263, REAR, 0, 76.5, 37, 46)
    assert_full(body, 263, REAR, 0, 20, -10, 10)                          # below the window
    assert_opening(body, across_x(263, REAR), 46, 34)


@pytest.mark.parametrize("sign", [-1, 1])
def test_film_slots_are_35_2_tall_notches_open_toward_the_gate_front_and_the_channel_deep_inside(body, front, sign):
    z = sorted((sign * 43, sign * 46))
    lo, hi = p.axis - 17.5, p.axis + 17.7        # floor flush under the film's lower edge, roof 0.2 over its upper (F13)
    # along x: the channel, 0.6, at the wall's inner face, widening to 2.0 at its outer face (F21)
    for depth_at, depth in ((43, 0.6), (44.5, 1.3), (46, 2.0)):
        za = sign * (depth_at - 0.0005 if depth_at == 46 else depth_at + 0.0005)
        slab = sorted((za - 0.0005, za + 0.0005))
        assert_void(body, REF, REF + depth - T, lo + T, hi - T, *slab)
        assert_full(body, REF + depth + 0.002, REF + depth + T, lo + T, hi - T, *slab)
    assert_full(body, REF, REF + 2.0, hi + 0.001, hi + T, *z)
    assert_full(body, REF, REF + 2.0, lo - T, lo - 0.001, *z)
    assert_full(body, REF + 2.0 + 0.001, 263, lo, hi, *z)                    # and nothing deeper
    # so the slot opens into the gate only between the reference plane and the pressure plate's front face
    assert cadutil.common_volume(body, probe(REF, REF + 0.6, lo, hi, *sorted((sign * 42.99, sign * 43.001)))) < EPS
    assert_full(body, REF + 0.6 + 0.001, REF + 3.2, lo, hi, *sorted((sign * 43, sign * 43.001)))
    # the gate front closes the notch: the film (x 240.7 .. 240.83) lies on the reference plane through the wall
    assert_full(front, REF - T, REF, lo, hi, *z)
    assert p.film_slot_x0 == pytest.approx(REF, abs=EPS)


@pytest.mark.parametrize("sign", [-1, 1])
def test_side_walls_are_3_thick_and_solid_elsewhere(body, sign):
    z = sorted((sign * 43, sign * 46))
    assert_full(body, 243.9, 263, 3, 73.5, *z)
    assert_full(body, REF, 243.9, 3, 21.9, *z)
    assert_full(body, REF, 243.9, 59.1, 73.5, *z)


def test_four_screw_pillars_stand_the_bodys_whole_depth_outside_the_side_walls(body):
    for y0, y1, z0, z1 in PILLARS:
        yc, zc = (y0 + y1) / 2, (z0 + z1) / 2
        solid = probe(REF, REAR, y0, y1, z0, z1).cut(
            cq.Workplane("YZ", origin=(REF, 0, 0)).center(yc, zc).circle(1.25).extrude(12))
        assert cadutil.common_volume(body, solid) == pytest.approx(cadutil.volume(solid), rel=1e-6)
        assert_void(body, REF, REF + 12 - 0.01, yc - 1.2, yc + 1.2, zc - 0.05, zc + 0.05)     # the pilot ...
        assert_full(body, REF + 12 + 0.01, REAR, yc - 1.2, yc + 1.2, zc - 0.05, zc + 0.05)    # ... is blind
    assert sorted(((y0 + y1) / 2, (z0 + z1) / 2) for y0, y1, z0, z1 in PILLARS) == sorted(p.screw_points)
    assert_void(body, REF, REAR, 9.001, 64.499, 46.001, 55)                # nothing else outside the walls
    assert_void(body, REF, REAR, 73.501, 76.5, 49.001, 55)                 # nor beside the lid but its rails (F22)


@pytest.mark.parametrize("z", RAILS)
def test_a_rail_on_each_upper_pillar_beside_the_lid_the_bodys_whole_depth_up_to_the_lids_top(body, z):
    assert_full(body, REF, REAR, 73.5, 76.5, *z)
    assert_void(body, REF - 1, REAR + 1, 76.501, 80, -56, 56)              # nothing above the lid's top
    assert cadutil.bounds(body)[3] == pytest.approx(76.5, abs=EPS)


def test_body_volume_is_the_sum_of_its_walls_and_pillars(body):
    t = 3
    floor = 22.3 * 3 * 92
    sides = 2 * (22.3 * 70.5 * t - (0.6 + 2.0) / 2 * t * 35.2)           # less the tapered notch (F21)
    rear = 3 * 76.5 * 92 - 3 * 46 * 34
    pillars = 4 * (25.3 * 9 * 9 - 12 * math.pi * 1.25**2)
    rails = 2 * 25.3 * 3 * 3                                              # F22: on the upper pillars, beside the lid
    sill = 22.3 * 20 * 86                                                 # the reference plane to the rear wall (F20)
    step = (2 * 4 + 4 * 4 / 2) * 86                                       # its top 2 deep, then the 45 degree slope
    assert cadutil.volume(body) == pytest.approx(floor + sides + rear + pillars + rails + sill + step, rel=1e-6)


# ---- the sill under the film (F20) and the backer behind the wedge plate (F12) --------


def test_the_sill_fills_the_gate_up_to_the_films_lower_edge_from_wall_to_wall(body):
    # x: the reference plane to the rear wall; y: the floor to the film's lower edge, level with the slots' floors
    assert p.sill_y == pytest.approx(p.film_slot_y0) == pytest.approx(p.axis - p.film_w / 2) == pytest.approx(SILL)
    assert_full(body, REF, 263, 3, SILL, -43, 43)
    assert cadutil.common_volume(body, probe(REF, STEP[0], SILL, SILL + 0.01, -43, 43)) < EPS
    # so the strip's lower edge lies on plastic across the whole gate, the slots' floors and the sill one plane
    edge = cadutil.common_bounds(body, probe(REF, REF + p.film_t, 0, SILL + 1, -46, 46))
    assert edge[3] == pytest.approx(SILL, abs=EPS) and (edge[4], edge[5]) == pytest.approx((-46, 46), abs=EPS)
    assert_full(body, REF, REF + p.film_t, SILL - 0.01, SILL, -46, 46)


def test_the_backer_is_a_step_on_the_sill_behind_the_wedge_plates_lower_ramps(body):
    # x: 0.05 behind the wedge plate's back face (246), 2 deep; y: the sill to 27, the wedge window's settled edge
    assert (p.x_wedge + p.wedge_t, p.wedge_back_clear) == pytest.approx((246, 0.05))
    assert STEP[2] == pytest.approx(p.axis - p.win_h / 2 - p.wedge_clear)
    assert_full(body, STEP[0], STEP[1], SILL, STEP[2], -43, 43)
    assert_void(body, 244, STEP[0], SILL, 73.5, -42.99, 42.99)              # the wedge plate's room
    assert cadutil.common_volume(body, probe(STEP[0] - 0.01, STEP[0], SILL, STEP[2], -43, 43)) < EPS
    # then a 45 degree slope down to the sill: the step's underside as the body prints, -x up
    for dx in (1, 2, 3):
        top = cadutil.common_bounds(body, probe(STEP[1] + dx - 0.001, STEP[1] + dx + 0.001, SILL, 73.5, -1, 1))[3]
        assert top == pytest.approx(STEP[2] - dx, abs=0.002)
    # it backs the lower ramps where the wedge plate stands on the sill, over 3.5 of their 4 and all their length
    lower = p.axis - p.pad_dy - p.pad / 2, p.axis - p.pad_dy + p.pad / 2
    assert (lower[0] - p.wedge_clear, lower[1]) == pytest.approx((SILL, STEP[2] + 0.5))


def test_backer_stays_out_of_the_wedge_window_and_the_light(body):
    top = cadutil.common_bounds(body, probe(247, 262, 3, 73.5, -42, 42))[3]
    assert top == pytest.approx(STEP[2], abs=EPS)
    assert top <= p.axis - p.win_h / 2 - p.wedge_clear        # under the wedge window's edge, even with the plate settled
    # its top corner is under the line from the frame's lower edge (on the film's light side) to the rear window's
    # lower edge at the lit face: it takes no ray the rear window lets through, whatever the lens's pupil
    (fx, fy), (rx, ry) = (REF + p.film_t, p.axis - p.frame_h / 2), (REAR, p.axis - p.rear_win_h / 2)
    line = fy + (ry - fy) * (STEP[1] - fx) / (rx - fx)
    assert line - top == pytest.approx(0.066, abs=0.001)
    # and the lowest ray to a pupil 140 in front of the film (assumed, as FB8) passes 0.87 over it
    ray = p.axis - p.frame_h / 2 - (STEP[1] - REF) * (p.frame_h / 2) / 140
    assert ray - top == pytest.approx(0.87, abs=0.005)


@pytest.mark.parametrize("q", [Params(wd=150), Params(axis=40), Params(wd=100, axis=50), Params(backer_step_d=6)])
def test_the_step_never_rises_into_the_rear_windows_light(q):
    corner = q.x_wedge + q.wedge_t + q.wedge_back_clear + q.backer_step_d
    (fx, fy), (rx, ry) = (q.x_ref + q.film_t, q.axis - q.frame_h / 2), (q.x_light, q.axis - q.rear_win_h / 2)
    assert q.backer_step_top <= fy + (ry - fy) * (corner - fx) / (rx - fx) + 1e-9
    assert q.backer_step_top <= q.axis - q.win_h / 2 - q.wedge_clear
    top = cadutil.common_bounds(model.gate_body(q), probe(corner - 0.5, corner, q.sill_y, q.gh - 4, -10, 10))[3]
    assert top == pytest.approx(q.backer_step_top, abs=EPS)


@pytest.mark.parametrize("lock", [False, True])
def test_the_wedge_plate_slides_0_05_in_front_of_the_backer(body, lock):
    wedge = switch_model.build(p, lock)["wedge_plate"]
    assert cadutil.common_volume(wedge, body) < 1e-3
    assert cadutil.common_volume(wedge.translate((0.049, 0, 0)), body) < 1e-3
    assert cadutil.common_volume(wedge.translate((0.051, 0, 0)), body) > 1e-4     # pushed back, it bears on the backer


# ---- pressure plate and the channel --------------------------------------------------


def test_pressure_plate_bounds_at_slide(plate):
    # 0.25 inside the interior (sill 23, lid 73.5, side walls +-43) all round
    xmin, xmax, ymin, ymax, zmin, zmax = cadutil.bounds(plate)
    assert (xmin, ymin, ymax, zmin, zmax) == pytest.approx((241.3, SILL + 0.25, 73.25, -42.75, 42.75), abs=EPS)
    assert xmax == pytest.approx(243.1 + 0.7417 + 2 * SLOPE, abs=FACE_TOL)     # the pads' thick edge


def test_pressure_plate_front_face_is_a_half_channel_behind_the_film(plate):
    assert face_x(plate, 0) == pytest.approx(p.x_film + 0.3, abs=EPS)
    assert face_x(plate, 1) == pytest.approx(243.1, abs=EPS)


def test_channel_between_the_plates_at_slide_and_lock(front, plate, plate_lock):
    gap = face_x(plate, 0) - face_x(front, 1)
    assert gap == pytest.approx(0.6, abs=EPS)
    assert gap == pytest.approx(p.channel, abs=EPS)
    lock_gap = face_x(plate_lock, 0) - face_x(front, 1)
    assert lock_gap == pytest.approx(0.13, abs=EPS)
    assert lock_gap == pytest.approx(p.film_t, abs=EPS)


def test_lock_moves_the_pressure_plate_toward_the_film_and_nothing_else(built, built_lock, plate, plate_lock):
    shift = face_x(plate, 0) - face_x(plate_lock, 0)
    assert shift == pytest.approx(0.47, abs=EPS)
    assert shift == pytest.approx(p.lock_shift, abs=EPS)
    assert cadutil.bounds(plate_lock) == pytest.approx(
        tuple(b - (shift if i < 2 else 0) for i, b in enumerate(cadutil.bounds(plate))), abs=EPS
    )
    assert cadutil.volume(plate_lock) == pytest.approx(cadutil.volume(plate), rel=1e-12)
    for name in ("gate_front", "gate_body", "gate_lid"):
        assert cadutil.bounds(built_lock[name]) == pytest.approx(cadutil.bounds(built[name]), abs=EPS)
        assert cadutil.volume(built_lock[name]) == pytest.approx(cadutil.volume(built[name]), rel=1e-12)


def test_pressure_plate_window(plate):
    assert_opening(plate, across_x(241.3, 243.1), 38, 26)
    assert_full(plate, 241.3, 243.1, SILL + 0.25, 73.25, -42.15, -20)       # to the lead-ins
    assert_full(plate, 241.3, 243.1, SILL + 0.25, 73.25, 20, 42.15)


@pytest.mark.parametrize("sign", [-1, 1])
def test_the_pressure_plate_front_edge_is_led_in_0_6_by_45_degrees_at_each_end(plate, sign):
    # F21: a strip's tip, coming in along the reference plane, meets the slope, not a square edge
    for dz, front in ((0.001, 241.3 + 0.599), (0.3, 241.3 + 0.3), (0.599, 241.3 + 0.001)):
        za = sign * (42.75 - dz)
        b = cadutil.common_bounds(plate, probe(241, 243, 40, 40.1, *sorted((za - 0.0005, za + 0.0005))))
        assert b[0] == pytest.approx(front, abs=0.002)
    za = sign * (42.75 - 0.61)
    assert cadutil.common_bounds(plate, probe(241, 243, 40, 40.1, *sorted((za - 0.0005, za + 0.0005))))[0] == pytest.approx(241.3, abs=EPS)
    # lying forward on the gate front, the plate's slope still spans the whole channel for the strip's tip to push on
    assert p.plate_lead_in >= p.channel


def test_the_pressure_plate_drops_in_with_a_quarter_millimetre_to_the_sill_the_lid_and_each_side_wall(plate, body, lid):
    # moved 0.249 toward any of them it is still clear; 0.251 and it runs into it
    for direction, other in (((0, -1, 0), body), ((0, 1, 0), lid), ((0, 0, -1), body), ((0, 0, 1), body)):
        clear = plate.translate(tuple(0.249 * d for d in direction))
        hit = plate.translate(tuple(0.251 * d for d in direction))
        assert cadutil.common_volume(clear, other) < 1e-3, direction
        assert cadutil.common_volume(hit, other) > 1e-4, direction


@pytest.mark.parametrize("lock", [False, True])
def test_pressure_plate_clears_the_gate_and_the_lid(built, lock):
    plate = model.build(p, lock)["pressure_plate"]
    assert cadutil.common_volume(plate, built["gate_front"]) < 1e-3
    assert cadutil.common_volume(plate, built["gate_body"]) < 1e-3
    assert cadutil.common_volume(plate, built["gate_lid"]) < 1e-3


# ---- pads ----------------------------------------------------------------------------


def pad_probe(zc, yc, x0, thickness_slab=None):
    """The probe over one pad's footprint (and a margin) on the plate's back face: nothing but pad in it."""
    z0, z1 = (zc - 3, zc + 3) if thickness_slab is None else thickness_slab
    return probe(x0, x0 + 3, yc - 3, yc + 3, z0, z1)


def pad_thickness(plate, zc, yc, z, back):
    """x thickness of the pad at z, from a 0.002 wide slab."""
    b = cadutil.common_bounds(plate, pad_probe(zc, yc, back, (z, z + 0.002)))
    return b[1] - back


def test_four_pads_with_the_right_footprints(plate):
    back = face_x(plate, 1)
    assert filled(plate, back, back + 3, 0, 80, -50, 50) > 0
    for zc, yc in PADS:
        x0, x1, y0, y1, z0, z1 = cadutil.common_bounds(plate, pad_probe(zc, yc, back))
        assert (y0, y1, z0, z1) == pytest.approx((yc - 2, yc + 2, zc - 2, zc + 2), abs=EPS)
        assert x0 == pytest.approx(back, abs=EPS)
    assert [(zc, yc - p.axis) for zc, yc in PADS] == [(-22, -15), (-22, 15), (22, -15), (22, 15)]
    # the lower ones on the plate's strip between the sill and the window: 0.25 over its bottom edge, up to the window
    low = cadutil.bounds(plate)[2]
    assert (PADS[0][1] - 2 - low, p.axis - p.win_h / 2 - (PADS[0][1] + 2)) == pytest.approx((0.25, 0), abs=EPS)
    # exactly those four: all the pad material is in those footprints
    in_footprints = sum(cadutil.common_volume(plate, pad_probe(zc, yc, back)) for zc, yc in PADS)
    assert in_footprints == pytest.approx(cadutil.common_volume(plate, probe(back, back + 3, 0, 80, -50, 50)), rel=1e-9)


def test_pad_thickness_at_the_pad_centre_is_pad_t(plate):
    back = face_x(plate, 1)
    for zc, yc in PADS:
        assert pad_thickness(plate, zc, yc, zc - 0.001, back) == pytest.approx(p.pad_t, abs=FACE_TOL)
    assert p.pad_t == pytest.approx(0.7417, abs=1e-4)


def test_pad_back_faces_slope_like_the_ramps(plate):
    back = face_x(plate, 1)
    s = SLOPE
    for zc, yc in PADS:
        lo = pad_thickness(plate, zc, yc, zc - 2, back)
        hi = pad_thickness(plate, zc, yc, zc + 2 - 0.002, back)
        assert lo == pytest.approx(p.pad_t - 2 * s, abs=FACE_TOL)
        assert hi == pytest.approx(p.pad_t + 2 * s, abs=FACE_TOL)
        assert (hi - lo) / 4 == pytest.approx(s, abs=FACE_TOL / 4)


def test_at_slide_the_pad_faces_lie_on_the_ramp_faces_without_overlap(plate):
    # switch at -sw_travel/2: each ramp is centred sw_travel/2 toward -z of its pad
    shift = -p.sw_travel / 2
    assert sum(cadutil.common_volume(plate, r) for r in ramps(shift)) < 1e-3
    # ... and they are touching, not apart: nudge the plate 0.01 toward the ramps and they overlap
    pushed = plate.translate((0.01, 0, 0))
    assert all(cadutil.common_volume(pushed, r) > 1e-3 for r in ramps(shift))


def test_at_lock_the_pads_overlap_the_ramps_by_a_uniform_preload(plate_lock):
    shift = p.sw_travel / 2
    assert p.preload == pytest.approx(0.1133, abs=1e-4)
    for zc, yc in PADS:
        r = ramp(zc + shift, yc - p.pad / 2)
        # the pad and ramp meet from zc - 1 (the ramp's thick end) to zc + 2 (the pad's far edge)
        for z in (zc - 0.99, zc + 0.5, zc + 1.99):
            slab = probe(p.x_film, p.x_film + 20, 0, 100, z, z + 0.002)
            x0, x1, *_ = cadutil.common_bounds(plate_lock.intersect(slab), r)
            assert x1 - x0 == pytest.approx(p.preload, abs=2 * 0.002 * SLOPE)       # the slab itself is 0.002 wide
        # so the overlap is a prism of that thickness over the 3 x 4 where pad and ramp meet in z
        assert cadutil.common_volume(plate_lock, r) == pytest.approx(p.preload * 3 * p.pad, rel=1e-6)


def test_the_pads_are_the_same_for_the_two_pad_columns(plate):
    back = face_x(plate, 1)
    for dy in (-p.pad_dy, p.pad_dy):
        near = pad_thickness(plate, -p.pad_z, p.axis + dy, -p.pad_z + 1, back)
        far = pad_thickness(plate, p.pad_z, p.axis + dy, p.pad_z + 1, back)
        assert near == pytest.approx(far, abs=FACE_TOL)


# ---- lid -----------------------------------------------------------------------------


def test_lid_bounds_at_default(lid):
    # 0.2 short of the gate front (x 240.7) and of the rear wall (x 263), and of each rail (z +-46, F22)
    assert cadutil.bounds(lid) == pytest.approx((240.9, 262.8, 73.5, 76.5, -45.8, 45.8), abs=EPS)


def test_the_lid_rests_on_the_side_walls_and_drops_in_with_0_2_to_the_gate_front_and_the_rear_wall(front, body, lid):
    assert cadutil.common_bounds(body, probe(244, 252, 73.5 - 0.1, 73.5, -46, 46))[3] == pytest.approx(73.5, abs=EPS)
    for dx in (-0.199, 0.199):
        moved = lid.translate((dx, 0, 0))
        assert cadutil.common_volume(moved, front) + cadutil.common_volume(moved, body) < 1e-3, dx
    assert cadutil.common_volume(lid.translate((-0.201, 0, 0)), front) > 1e-4
    assert cadutil.common_volume(lid.translate((0.201, 0, 0)), body) > 1e-4


def test_the_rails_stop_the_lid_0_2_along_z_so_the_tab_cannot_drag_it(body, lid):
    # F22: before, the lid could move +-20 along z and the tab dragged it past the slot's end (FB3)
    for dz in (-0.199, 0.199):
        assert cadutil.common_volume(lid.translate((0, 0, dz)), body) < 1e-3, dz
    for dz in (-0.201, 0.201):
        assert cadutil.common_volume(lid.translate((0, 0, dz)), body) > 1e-4, dz
    # and it still drops straight in from above
    for dy in (1, 5, 20):
        assert cadutil.common_volume(lid.translate((0, dy, 0)), body) < 1e-3, dy
    # it still covers the side walls' tops (43 .. 46) but for the 0.2 beside each rail
    assert_full(lid, 241, 262, 73.5, 76.5, -45.8, -43)
    assert_full(lid, 241, 262, 73.5, 76.5, 43, 45.8)


def test_lid_slot_is_2_by_16_for_the_tab(lid):
    # as wide as the 2 thick tab (x_wedge .. x_wedge + 2, F25; 3 until then), and 3 beyond the +-5 switch travel at each end
    assert_opening(lid, across_y(73.5, 76.5), 2, 16, ca=p.x_wedge + 1, cb=0)


def test_lid_volume_is_the_plate_less_the_slot():
    lid = model.gate_lid(Params(mark_depth=0))                          # the padlocks: tests/test_marks.py
    assert cadutil.volume(lid) == pytest.approx(21.9 * 3 * 91.6 - 2 * 16 * 3, rel=1e-9)


# ---- printing ------------------------------------------------------------------------


@pytest.mark.parametrize("name", NAMES)
def test_fits_the_bed_in_print_pose(built, name):
    posed = cadutil.print_pose(built[name], model.PRINT_UP[name])
    assert cadutil.fits_bed(posed, p)
    assert cadutil.bounds(posed)[4] == pytest.approx(0, abs=EPS)


def test_print_pose_sizes(built):
    size = lambda name: cadutil.size(cadutil.print_pose(built[name], model.PRINT_UP[name]))
    assert size("gate_front") == pytest.approx((110, 76.5, 23.7), abs=EPS)          # F24
    assert size("gate_body") == pytest.approx((110, 76.5, 25.3), abs=EPS)
    assert size("gate_lid") == pytest.approx((21.9, 91.6, 3), abs=EPS)
    assert size("pressure_plate") == pytest.approx((85.5, 50, 1.8 + p.pad_t + 2 * SLOPE), abs=FACE_TOL)


def bed_layer(posed):
    """The material in the first 0.01 above the bed, as (its area, its bounds)."""
    sl = cadutil.solid(posed).intersect(cadutil.solid(probe(-200, 200, -200, 200, 0, 0.01)))
    return sl.Volume() / 0.01, cadutil.shape_bounds(sl)


@pytest.mark.parametrize("name", ["gate_front", "pressure_plate"])
def test_the_faces_that_meet_the_film_print_on_the_bed(built, name):
    # F5, F7: the film lies on the gate front's rear face and the pressure plate's front face presses it; both are the
    # first layer, so they are as smooth and flat as the bed
    posed = cadutil.print_pose(built[name], model.PRINT_UP[name])
    area, _ = bed_layer(posed)
    if name == "gate_front":
        assert area == pytest.approx(76.5 * 110 - 38 * 26 - 4 * math.pi * 1.7**2, rel=1e-4)     # the pose sits ~1e-7 off Z = 0
    else:
        # less the lead-ins (F21), each 0.005 narrower at the middle of the 0.01 slab than on the bed
        assert area == pytest.approx((85.5 - 2 * (0.6 - 0.005)) * 50 - 38 * 26, rel=1e-4)
    # the face on the bed is the one the film meets: the gate front prints -x up, so its +x face (x_ref) is down; the
    # pressure plate prints +x up, so its -x face is down
    film = cadutil.bounds(probe(p.x_film - 0.3, p.x_film - 0.3 + p.film_t, 0, 1, 0, 1))
    if name == "gate_front":
        assert cadutil.bounds(built[name])[1] == pytest.approx(film[0], abs=EPS)
    else:
        assert cadutil.bounds(built[name])[0] == pytest.approx(p.x_film + p.channel / 2, abs=EPS)


@pytest.mark.parametrize("name", ["gate_front", "gate_body", "gate_lid", "pressure_plate"])
def test_nothing_prints_over_air(built, name):
    # no face leans out more than 45 degrees
    posed = cadutil.print_pose(built[name], model.PRINT_UP[name])
    assert cadutil.overhangs(posed) == []


def test_the_pads_print_as_the_top_layers_stepped_by_them(built):
    # the price of F7: the pads' backs slope 1:17 like the ramps and face up, so the layers step them (ironing helps)
    posed = cadutil.print_pose(built["pressure_plate"], model.PRINT_UP["pressure_plate"])
    sloped = cadutil.sloped_faces(posed)
    up = [f for f in sloped if f.normalAt().z > 0.99]
    lead_ins = [f for f in sloped if f.normalAt().z == pytest.approx(-math.sqrt(0.5), abs=1e-9)]    # F21, at 45 degrees
    assert (len(up), len(lead_ins), len(sloped)) == (4, 2, 6)


def test_pressure_plate_volume_is_the_plate_plus_four_pads(plate):
    plate_only = 85.5 * 50 * 1.8 - 1.8 * 38 * 26 - 2 * 0.6**2 / 2 * 50      # less the two lead-ins (F21)
    pads = 4 * p.pad * p.pad * p.pad_t               # linear slope about the centre: mean thickness is pad_t
    mark = 3 * 3 / 2 * 0.36                          # the ▲ (F18)
    assert cadutil.volume(plate) == pytest.approx(plate_only + pads - mark, rel=1e-9)


# ---- follows the params --------------------------------------------------------------


@pytest.mark.parametrize("q", [Params(wd=150), Params(axis=40), Params(wd=100, axis=50)])
def test_gate_follows_wd_and_axis(q):
    solids = model.build(q)
    assert all(cadutil.is_valid(s) for s in solids.values())
    assert cadutil.bounds(solids["gate_front"]) == pytest.approx((q.x_gate, q.x_ref, 0, q.gh, -55, 55), abs=EPS)
    assert cadutil.bounds(solids["gate_body"]) == pytest.approx((q.x_ref, q.x_light, 0, q.gh, -55, 55), abs=EPS)
    assert cadutil.bounds(solids["gate_lid"]) == pytest.approx((q.x_ref + 0.2, q.x_light - 3.2, q.gh - 3, q.gh, -45.8, 45.8), abs=EPS)
    assert cadutil.bounds(solids["pressure_plate"])[2:] == pytest.approx((q.sill_y + 0.25, q.gh - 3.25, -42.75, 42.75), abs=EPS)
    # the film-plane geometry moves with x_film, the sill with the axis
    below = (q.sill_y + 1, q.axis - q.win_h / 2 - 0.5)
    assert cadutil.common_bounds(solids["gate_front"], probe(q.x_film - 6, q.x_film + 6, *below, -10, 10))[1] == pytest.approx(
        q.x_film - 0.3, abs=EPS
    )
    assert cadutil.common_bounds(solids["pressure_plate"], probe(q.x_film - 6, q.x_film + 6, *below, -10, 10))[0] == pytest.approx(
        q.x_film + 0.3, abs=EPS
    )
    assert cadutil.common_bounds(solids["gate_body"], probe(q.x_ref, q.x_ref + 1, 0, q.axis, -10, 10))[3] == pytest.approx(
        q.axis - q.film_w / 2, abs=EPS
    )
    for a, b in (("gate_front", "gate_body"), ("pressure_plate", "gate_body"), ("pressure_plate", "gate_front"),
                 ("gate_lid", "gate_body"), ("gate_lid", "gate_front")):
        assert cadutil.common_volume(solids[a], solids[b]) < 1e-3, (a, b)
