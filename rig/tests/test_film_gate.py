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
    """x of the plate's front (0) or back (1) face, probed where there is only plate: below the window. On the gate
    front, 1 is the reference plane."""
    bounds = cadutil.common_bounds(wp, probe(p.x_film - 6, p.x_film + 6, 10, 20, -10, 10))
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
REF = 235.7                     # x_ref: the film reference plane, the gate front's rear face
REAR = 261                      # the body's rear face: the CS-Lite's lit face (F10)
PILLARS = [(0, 9, -55, -46), (0, 9, 46, 55), (64.5, 73.5, -55, -46), (64.5, 73.5, 46, 55)]     # y0 y1 z0 z1


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
    assert (p.film_slot_w, p.film_slot_h, p.film_slot_y0) == (3.2, 35.2, p.axis - 17.5)
    assert (p.rear_win_w, p.rear_win_h) == (46, 34)
    assert (p.tab_t, p.tab_clear, p.slot_end) == (2, 0.5, 3)
    assert (p.pad, p.pad_z, p.pad_dy) == (4, 22, 15.5)
    assert (p.ear_w, p.ear_h, p.joint_hole_d, p.cbore_d, p.cbore_depth, p.pilot_d, p.pilot_depth) == (9, 9, 3.4, 6.5, 3.5, 2.5, 12)
    assert (p.x_ref, p.gate_front_w) == (REF, 110)
    assert p.screw_points == [(4.5, -50.5), (4.5, 50.5), (69, -50.5), (69, 50.5)]


# ---- gate front ----------------------------------------------------------------------


def test_front_bounds_at_default(front):
    assert cadutil.bounds(front) == pytest.approx((222, REF, 0, 76.5, -55, 55), abs=EPS)
    assert (p.x_gate, p.gh) == (222, 76.5)


def test_socket_is_the_tube_slip_fit_and_on_the_axis(front):
    tube = tube_model.build(p)["tube"]
    tube_r = cadutil.size(tube)[1] / 2
    arcs = [e for e in cadutil.solid(front).Edges() if e.geomType() == "CIRCLE" and e.radius() > 30]
    assert len(arcs) == 2                                        # the socket's two rims
    for arc in arcs:
        assert arc.radius() - tube_r == pytest.approx(0.3, abs=EPS)
        centre = arc.arcCenter()
        assert (centre.y, centre.z) == pytest.approx((p.axis, 0), abs=EPS)
    assert sorted(arc.arcCenter().x for arc in arcs) == pytest.approx([222, 226], abs=EPS)


def test_socket_is_clear_to_r36_3_and_solid_beyond(front):
    assert cadutil.common_volume(front, rod(222, 4, 36.3 - T)) < 1e-3
    assert cadutil.common_volume(front, rod(222, 4, 36.3 + T)) > 1.0


def test_socket_breaks_through_the_top_edge(front):
    # R8: gate height kept at axis + 36, so the r36.3 socket opens a notch in the top
    assert p.axis + p.fit_r > p.gh
    assert_void(front, 222, 226, 76.4, 76.5, -4.5, 4.5)
    assert_full(front, 222, 226, 76.4, 76.5, 5.5, 8)
    assert_full(front, 222, 226, 76.4, 76.5, -8, -5.5)


def test_tube_light_end_rests_on_the_socket_floor_all_round(front):
    tube = tube_model.build(p)["tube"]
    assert cadutil.bounds(tube)[1] == pytest.approx(226, abs=EPS)       # ends on the socket's floor
    assert cadutil.common_volume(front, tube) < 1e-3
    # the floor is solid under the whole tube wall (r 32 .. 36): the light passage's corners reach r 32, no further
    ring = rod(226, 0.5, 36).cut(rod(226, 0.5, 32 + 1e-4))
    assert cadutil.common_volume(front, ring) == pytest.approx(cadutil.volume(ring), rel=1e-6)
    assert p.flare_scale * math.hypot(38, 26) / 2 == pytest.approx(32, abs=EPS)


def test_frame_window_is_38_by_26_straight_for_1_8_from_the_reference_plane(front):
    assert_opening(front, across_x(REF - 1.8, REF), 38, 26)
    assert face_x(front, 1) == pytest.approx(REF, abs=EPS)
    assert face_x(front, 1) == pytest.approx(p.x_film - p.channel / 2, abs=EPS)


def test_light_passage_flares_from_the_window_to_the_socket(front):
    # halfway along the flare (x 230) the opening is the window scaled by (1 + k) / 2
    k = (1 + p.flare_scale) / 2
    x = (226 + REF - 1.8) / 2
    assert_opening(front, across_x(x - 0.0001, x + 0.0001), 38 * k, 26 * k)     # thin: the walls lean ~0.94 in x
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
        assert_void(front, 222, REF, y - 1.65, y + 1.65, z - 0.05, z + 0.05)
        assert_full(front, 225.51, REF, y + 1.71, y + 1.71 + T, z - 0.05, z + 0.05)
        assert_void(front, 222, 225.49, y - 3.2, y + 3.2, z - 0.05, z + 0.05)
        assert_full(front, 222, 225.5, y + 3.26, y + 3.26 + T, z - 0.05, z + 0.05)


def segment_area(r, d):
    """Area of the circle of radius r on the far side of a chord d from its centre."""
    return r * r * math.acos(d / r) - d * math.sqrt(r * r - d * d)


def test_front_volume(front):
    a1, k = 38 * 26, p.flare_scale
    a2 = k * k * a1
    flare = 7.9 / 3 * (a1 + a2 + math.sqrt(a1 * a2))
    socket = 4 * (math.pi * 36.3**2 - segment_area(36.3, 36.0))         # breaks 0.3 through the top
    holes = 4 * (13.7 * math.pi * 1.7**2 + 3.5 * math.pi * (3.25**2 - 1.7**2))
    assert cadutil.volume(front) == pytest.approx(13.7 * 76.5 * 110 - socket - 1.8 * a1 - flare - holes, rel=1e-6)


def test_front_top_is_plain_behind_the_socket(front):
    # F14: no lettering; the top is solid from the socket's notch to x_ref.
    assert_full(front, 226, REF, 76, 76.5, -55, 55)


# ---- gate body -----------------------------------------------------------------------


def test_body_bounds_at_default(body):
    assert cadutil.bounds(body) == pytest.approx((REF, REAR, 0, 76.5, -55, 55), abs=EPS)


def test_front_and_body_meet_on_the_reference_plane_and_only_touch(front, body):
    assert cadutil.common_volume(front, body) < 1e-3
    # touching over the walls' ends, not apart: 0.01 closer and they overlap
    assert cadutil.common_volume(front, body.translate((-0.01, 0, 0))) > 1e-3


def test_body_is_open_topped_and_open_toward_the_gate_front(body):
    # side walls stop 3 below the top and the floor is 3 thick: the lid and the floor close the rest
    assert_void(body, REF, 258, 73.5 + EPS, 76.5, -46, 46)
    assert_full(body, REF, 258, 0, 3, -46, 46)
    for sign in (-1, 1):
        z = sorted((sign * 43, sign * 46))
        assert_full(body, 239, 258, 3, 73.5, *z)
    assert_void(body, REF, 258, 23, 73.5, -42.99, 42.99)                  # hollow between the walls above the backer
    assert_void(body, REF, 241.05, 3, 23, -42.99, 42.99)                  # and in front of it: no front wall


def test_rear_wall_is_full_height_and_full_width_with_its_window(body):
    assert_full(body, 258, REAR, 0, 76.5, -46, -37)
    assert_full(body, 258, REAR, 0, 76.5, 37, 46)
    assert_full(body, 258, REAR, 0, 20, -10, 10)                          # below the window
    assert_opening(body, across_x(258, REAR), 46, 34)


@pytest.mark.parametrize("sign", [-1, 1])
def test_film_slots_are_3_2_by_35_2_notches_open_toward_the_gate_front(body, front, sign):
    z = sorted((sign * 43, sign * 46))
    lo, hi = p.axis - 17.5, p.axis + 17.7        # floor flush under the film's lower edge, roof 0.2 over its upper (F13)
    assert_void(body, REF, REF + 3.2 - T, lo + T, hi - T, *z)
    assert_full(body, REF + 3.2 + 0.001, REF + 3.2 + T, lo + T, hi - T, *z)
    assert_full(body, REF, REF + 3.2, hi + 0.001, hi + T, *z)
    assert_full(body, REF, REF + 3.2, lo - T, lo - 0.001, *z)
    # the gate front closes the notch: the film (x 235.7 .. 235.83) lies on the reference plane through the wall
    assert_full(front, REF - T, REF, lo, hi, *z)
    assert p.film_slot_x0 == pytest.approx(REF, abs=EPS)


@pytest.mark.parametrize("sign", [-1, 1])
def test_side_walls_are_3_thick_and_solid_elsewhere(body, sign):
    z = sorted((sign * 43, sign * 46))
    assert_full(body, 238.9, 258, 3, 73.5, *z)
    assert_full(body, REF, 238.9, 3, 21.9, *z)
    assert_full(body, REF, 238.9, 59.1, 73.5, *z)


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
    assert_void(body, REF, REAR, 73.501, 76.5, 46.001, 55)                 # nor beside the lid


def test_body_volume_is_the_sum_of_its_walls_and_pillars(body):
    t = 3
    floor = 22.3 * 3 * 92
    sides = 2 * (22.3 * 70.5 * t - 3.2 * 35.2 * t)
    rear = 3 * 76.5 * 92 - 3 * 46 * 34
    pillars = 4 * (25.3 * 9 * 9 - 12 * math.pi * 1.25**2)
    backer = 16.95 * 20 * 86
    assert cadutil.volume(body) == pytest.approx(floor + sides + rear + pillars + backer, rel=1e-6)


# ---- the backer behind the wedge plate (F12) -----------------------------------------


def test_backer_fills_the_floor_behind_the_wedge_plate_up_to_the_films_bottom_edge(body):
    # x: 0.05 behind the wedge plate's back face (241) to the rear wall; y: the floor to the film (axis - 17.5)
    assert (p.x_wedge + p.wedge_t, p.wedge_back_clear, p.axis - p.film_w / 2) == pytest.approx((241, 0.05, 23))
    assert_full(body, 241.05, 258, 3, 23, -43, 43)
    assert_void(body, 239, 241.05, 3, 73.5, -42.99, 42.99)                 # the wedge plate's room
    assert_void(body, 241.05, 258, 23, 73.5, -42.99, 42.99)                # nothing above it: the light path is open
    assert cadutil.common_volume(body, probe(241.04, 241.05, 3, 23, -43, 43)) < EPS
    assert cadutil.common_volume(body, probe(241.05, 258, 23, 23.01, -43, 43)) < EPS


def test_backer_stays_below_the_film_and_the_rear_window(body):
    top = cadutil.common_bounds(body, probe(242, 257, 3, 73.5, -42, 42))[3]
    assert top == pytest.approx(23, abs=EPS)
    assert top <= p.axis - p.film_w / 2 <= p.axis - p.rear_win_h / 2


@pytest.mark.parametrize("lock", [False, True])
def test_the_wedge_plate_slides_0_05_in_front_of_the_backer(body, lock):
    wedge = switch_model.build(p, lock)["wedge_plate"]
    assert cadutil.common_volume(wedge, body) < 1e-3
    assert cadutil.common_volume(wedge.translate((0.049, 0, 0)), body) < 1e-3
    assert cadutil.common_volume(wedge.translate((0.051, 0, 0)), body) > 1e-4     # pushed back, it bears on the backer


# ---- pressure plate and the channel --------------------------------------------------


def test_pressure_plate_bounds_at_slide(plate):
    # 0.25 inside the interior (floor 3, lid 73.5, side walls +-43) all round
    xmin, xmax, ymin, ymax, zmin, zmax = cadutil.bounds(plate)
    assert (xmin, ymin, ymax, zmin, zmax) == pytest.approx((236.3, 3.25, 73.25, -42.75, 42.75), abs=EPS)
    assert xmax == pytest.approx(238.1 + 0.7417 + 2 * SLOPE, abs=FACE_TOL)     # the pads' thick edge


def test_pressure_plate_front_face_is_a_half_channel_behind_the_film(plate):
    assert face_x(plate, 0) == pytest.approx(p.x_film + 0.3, abs=EPS)
    assert face_x(plate, 1) == pytest.approx(238.1, abs=EPS)


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
    assert_opening(plate, across_x(236.3, 238.1), 38, 26)
    assert_full(plate, 236.3, 238.1, 3.25, 73.25, -42.75, -20)
    assert_full(plate, 236.3, 238.1, 3.25, 73.25, 20, 42.75)


def test_the_pressure_plate_drops_in_with_a_quarter_millimetre_to_the_floor_the_lid_and_each_side_wall(plate, body, lid):
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
    assert [(zc, yc - p.axis) for zc, yc in PADS] == [(-22, -15.5), (-22, 15.5), (22, -15.5), (22, 15.5)]
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
    # 0.2 short of the gate front (x 235.7) and of the rear wall (x 258)
    assert cadutil.bounds(lid) == pytest.approx((235.9, 257.8, 73.5, 76.5, -46, 46), abs=EPS)


def test_the_lid_rests_on_the_side_walls_and_drops_in_with_0_2_to_the_gate_front_and_the_rear_wall(front, body, lid):
    assert cadutil.common_bounds(body, probe(239, 247, 73.5 - 0.1, 73.5, -46, 46))[3] == pytest.approx(73.5, abs=EPS)
    for dx in (-0.199, 0.199):
        moved = lid.translate((dx, 0, 0))
        assert cadutil.common_volume(moved, front) + cadutil.common_volume(moved, body) < 1e-3, dx
    assert cadutil.common_volume(lid.translate((-0.201, 0, 0)), front) > 1e-4
    assert cadutil.common_volume(lid.translate((0.201, 0, 0)), body) > 1e-4


def test_lid_slot_is_3_by_16_for_the_tab(lid):
    # 0.5 each side of the 2 thick tab (x_wedge .. x_wedge + 2), and 3 beyond the +-5 switch travel at each end
    assert_opening(lid, across_y(73.5, 76.5), 3, 16, ca=p.x_wedge + 1, cb=0)


def test_lid_volume_is_the_plate_less_the_slot(lid):
    assert cadutil.volume(lid) == pytest.approx(21.9 * 3 * 92 - 3 * 16 * 3, rel=1e-9)


# ---- printing ------------------------------------------------------------------------


@pytest.mark.parametrize("name", NAMES)
def test_fits_the_bed_in_print_pose(built, name):
    posed = cadutil.print_pose(built[name], model.PRINT_UP[name])
    assert cadutil.fits_bed(posed, p)
    assert cadutil.bounds(posed)[4] == pytest.approx(0, abs=EPS)


def test_print_pose_sizes(built):
    size = lambda name: cadutil.size(cadutil.print_pose(built[name], model.PRINT_UP[name]))
    assert size("gate_front") == pytest.approx((110, 76.5, 13.7), abs=EPS)
    assert size("gate_body") == pytest.approx((110, 76.5, 25.3), abs=EPS)
    assert size("gate_lid") == pytest.approx((21.9, 92, 3), abs=EPS)
    assert size("pressure_plate") == pytest.approx((85.5, 70, 1.8 + p.pad_t + 2 * SLOPE), abs=FACE_TOL)


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
        assert area == pytest.approx(85.5 * 70 - 38 * 26, rel=1e-4)
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
    assert len(cadutil.sloped_faces(posed)) == 4
    assert all(f.normalAt().z > 0.99 for f in cadutil.sloped_faces(posed))


def test_pressure_plate_volume_is_the_plate_plus_four_pads(plate):
    plate_only = 85.5 * 70 * 1.8 - 1.8 * 38 * 26
    pads = 4 * p.pad * p.pad * p.pad_t               # linear slope about the centre: mean thickness is pad_t
    assert cadutil.volume(plate) == pytest.approx(plate_only + pads, rel=1e-9)


# ---- follows the params --------------------------------------------------------------


@pytest.mark.parametrize("q", [Params(wd=150), Params(axis=40), Params(wd=100, axis=50)])
def test_gate_follows_wd_and_axis(q):
    solids = model.build(q)
    assert all(cadutil.is_valid(s) for s in solids.values())
    assert cadutil.bounds(solids["gate_front"]) == pytest.approx((q.x_gate, q.x_ref, 0, q.gh, -55, 55), abs=EPS)
    assert cadutil.bounds(solids["gate_body"]) == pytest.approx((q.x_ref, q.x_light, 0, q.gh, -55, 55), abs=EPS)
    assert cadutil.bounds(solids["gate_lid"]) == pytest.approx((q.x_ref + 0.2, q.x_light - 3.2, q.gh - 3, q.gh, -46, 46), abs=EPS)
    assert cadutil.bounds(solids["pressure_plate"])[2:] == pytest.approx((3.25, q.gh - 3.25, -42.75, 42.75), abs=EPS)
    # the film-plane geometry moves with x_film
    assert cadutil.common_bounds(solids["gate_front"], probe(q.x_film - 6, q.x_film + 6, 10, 20, -10, 10))[1] == pytest.approx(
        q.x_film - 0.3, abs=EPS
    )
    assert cadutil.common_bounds(solids["pressure_plate"], probe(q.x_film - 6, q.x_film + 6, 10, 20, -10, 10))[0] == pytest.approx(
        q.x_film + 0.3, abs=EPS
    )
    for a, b in (("gate_front", "gate_body"), ("pressure_plate", "gate_body"), ("pressure_plate", "gate_front"),
                 ("gate_lid", "gate_body"), ("gate_lid", "gate_front")):
        assert cadutil.common_volume(solids[a], solids[b]) < 1e-3, (a, b)
