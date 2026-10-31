"""Film gate: the box with its integral front plate, the lid with the engraved lettering, and the
floating pressure plate.

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
def box(built):
    return built["gate_box"]


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
    """x of the plate's front (0) or back (1) face, probed where there is only plate: below the window."""
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


def test_solid_names_and_print_directions(built):
    assert list(built) == ["gate_box", "gate_lid", "pressure_plate"]
    assert model.PRINT_UP == {"gate_box": "+y", "gate_lid": "+y", "pressure_plate": "+y"}


@pytest.mark.parametrize("name", ["gate_box", "gate_lid", "pressure_plate"])
@pytest.mark.parametrize("lock", [False, True])
def test_each_solid_is_one_valid_closed_solid(name, lock):
    solid = cadutil.solid(model.build(p, lock)[name])      # raises unless exactly one
    assert solid.isValid()
    assert all(shell.Closed() for shell in solid.Shells())
    assert solid.Volume() > 0
    assert cadutil.non_manifold_edges(model.build(p, lock)[name]) == []     # Onshape rejects any


def test_new_params_defaults():
    assert (p.film_slot_w, p.film_slot_h) == (3.2, 37)
    assert (p.rear_win_w, p.rear_win_h) == (46, 34)
    assert (p.tab_t, p.tab_clear, p.slot_end) == (2, 0.5, 3)
    assert (p.pad, p.pad_z, p.pad_dy) == (4, 22, 15.5)
    assert (p.lid_text_depth, p.lid_text_z, p.lid_text_back) == (0.4, 14, 11)
    assert (p.lid_text_w, p.lid_text_h) == (16, 4.4)


# ---- box -----------------------------------------------------------------------------


def test_box_bounds_at_default(box):
    assert cadutil.bounds(box) == pytest.approx((241, 271, 0, 78.5, -46, 46), abs=0.05)
    assert cadutil.size(box) == pytest.approx((30, 78.5, 92), abs=0.05)
    assert (p.x_gate, p.gh) == (241, 78.5)


def test_box_is_open_topped_between_the_end_walls(box):
    # side walls stop 3 below the top and the floor is 3 thick: the lid and the floor close the rest
    assert cadutil.bounds(box)[3] == pytest.approx(78.5, abs=EPS)
    assert_void(box, 245, 268, 75.5 + EPS, 78.5, -46, 46)
    assert_full(box, 245, 268, 0, 3, -46, 46)
    for sign in (-1, 1):
        z = sorted((sign * 43, sign * 46))
        assert_full(box, 245, 252, 3, 75.5, *z)
        assert_full(box, 258, 268, 3, 75.5, *z)
    assert_void(box, 245, 252.8, 3, 75.5, -42.99, 42.99)                  # hollow between the walls
    assert_void(box, 254.8, 268, 3, 75.5, -42.99, 42.99)


def test_front_and_rear_walls_are_full_height_and_full_width(box):
    for x0, x1 in ((241, 245), (268, 271)):
        assert_full(box, x0, x1, 0, 78.5, -46, -37)
        assert_full(box, x0, x1, 0, 78.5, 37, 46)
    assert_full(box, 241, 245, 0, 5, -10, 10)           # below the hole
    assert_full(box, 268, 271, 0, 20, -10, 10)           # below the rear window


def test_assembled_gate_bounds_and_box_and_lid_only_touch(box, lid):
    bx, bl = cadutil.bounds(box), cadutil.bounds(lid)
    union = (min(bx[0], bl[0]), max(bx[1], bl[1]), min(bx[2], bl[2]), max(bx[3], bl[3]),
             min(bx[4], bl[4]), max(bx[5], bl[5]))
    assert (union[1] - union[0], union[3] - union[2], union[5] - union[4]) == pytest.approx((30, 78.5, 92), abs=0.05)
    assert cadutil.common_volume(box, lid) < 1e-3
    # the lid rests on the side walls: its underside is the side walls' top
    assert bl[2] == pytest.approx(75.5, abs=EPS)
    assert cadutil.common_bounds(box, probe(250, 256, 75.5 - 0.1, 75.5, -46, 46))[3] == pytest.approx(75.5, abs=EPS)


def test_front_wall_hole_is_the_tube_slip_fit_and_on_the_axis(box):
    tube = tube_model.build(p)["tube"]
    tube_r = cadutil.size(tube)[1] / 2
    arcs = [e for e in cadutil.solid(box).Edges() if e.geomType() == "CIRCLE"]
    assert len(arcs) == 2                                        # the hole's two rims
    for arc in arcs:
        assert arc.radius() - tube_r == pytest.approx(0.3, abs=EPS)
        centre = arc.arcCenter()
        assert (centre.y, centre.z) == pytest.approx((p.axis, 0), abs=EPS)
    assert sorted(arc.arcCenter().x for arc in arcs) == pytest.approx([241, 245], abs=EPS)


def test_hole_is_clear_to_r36_3_and_solid_beyond(box):
    assert cadutil.common_volume(box, rod(241, 4, 36.3 - T)) < 1e-3
    assert cadutil.common_volume(box, rod(241, 4, 36.3 + T)) > 1.0


def test_hole_breaks_through_the_top_edge_of_the_front_wall(box):
    # R8: gate height kept at axis + 36, so the r36.3 hole opens a notch in the top
    assert p.axis + p.fit_r > p.gh
    assert_void(box, 241, 245, 78.4, 78.5, -4.5, 4.5)
    assert_full(box, 241, 245, 78.4, 78.5, 5.5, 8)
    assert_full(box, 241, 245, 78.4, 78.5, -8, -5.5)


def test_tube_light_end_slides_into_the_hole_without_touching_the_box(box):
    tube = tube_model.build(p)["tube"]
    assert cadutil.bounds(tube)[1] == pytest.approx(245, abs=EPS)       # ends at the front wall's rear face
    assert cadutil.common_volume(box, tube) < 1e-3


# ---- front plate ---------------------------------------------------------------------


def test_front_plate_alone(box):
    plate_only = model.front_plate(p)
    assert cadutil.is_valid(plate_only)
    assert cadutil.bounds(plate_only) == pytest.approx((252.9, 254.7, 3, 75.5, -43, 43), abs=EPS)
    assert_opening(plate_only, across_x(252.9, 254.7), 38, 26)


def test_front_plate_is_part_of_the_box_with_its_window(box):
    assert_opening(box, across_x(252.9, 254.7), 38, 26)
    assert_full(box, 252.9, 254.7, 3, 75.5, -43, -20)
    assert_full(box, 252.9, 254.7, 3, 75.5, 20, 43)
    assert_full(box, 252.9, 254.7, 3, 28, -43, 43)


def test_front_plate_rear_face_is_a_half_channel_in_front_of_the_film(box):
    assert face_x(box, 1) == pytest.approx(p.x_film - 0.3, abs=EPS)
    assert cadutil.common_bounds(box, probe(p.x_film - 6, p.x_film + 6, 10, 20, -10, 10))[0] == pytest.approx(
        p.x_film - 0.3 - 1.8, abs=EPS
    )


# ---- pressure plate and the channel --------------------------------------------------


def test_pressure_plate_bounds_at_slide(plate):
    # 0.25 inside the interior (floor 3, lid 75.5, side walls +-43) all round
    xmin, xmax, ymin, ymax, zmin, zmax = cadutil.bounds(plate)
    assert (xmin, ymin, ymax, zmin, zmax) == pytest.approx((255.3, 3.25, 75.25, -42.75, 42.75), abs=EPS)
    assert xmax == pytest.approx(257.1 + 0.7417 + 2 * SLOPE, abs=FACE_TOL)     # the pads' thick edge


def test_pressure_plate_front_face_is_a_half_channel_behind_the_film(plate):
    assert face_x(plate, 0) == pytest.approx(p.x_film + 0.3, abs=EPS)
    assert face_x(plate, 1) == pytest.approx(257.1, abs=EPS)


def test_channel_between_the_plates_at_slide_and_lock(box, plate, plate_lock):
    gap = face_x(plate, 0) - face_x(box, 1)
    assert gap == pytest.approx(0.6, abs=EPS)
    assert gap == pytest.approx(p.channel, abs=EPS)
    lock_gap = face_x(plate_lock, 0) - face_x(box, 1)
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
    for name in ("gate_box", "gate_lid"):
        assert cadutil.bounds(built_lock[name]) == pytest.approx(cadutil.bounds(built[name]), abs=EPS)
        assert cadutil.volume(built_lock[name]) == pytest.approx(cadutil.volume(built[name]), rel=1e-12)


def test_pressure_plate_window(plate):
    assert_opening(plate, across_x(255.3, 257.1), 38, 26)
    assert_full(plate, 255.3, 257.1, 3.25, 75.25, -42.75, -20)
    assert_full(plate, 255.3, 257.1, 3.25, 75.25, 20, 42.75)


def test_the_pressure_plate_drops_in_with_a_quarter_millimetre_to_the_floor_the_lid_and_each_side_wall(plate, box, lid):
    # moved 0.249 toward any of them it is still clear; 0.251 and it runs into it
    for direction, other in (((0, -1, 0), box), ((0, 1, 0), lid), ((0, 0, -1), box), ((0, 0, 1), box)):
        clear = plate.translate(tuple(0.249 * d for d in direction))
        hit = plate.translate(tuple(0.251 * d for d in direction))
        assert cadutil.common_volume(clear, other) < 1e-3, direction
        assert cadutil.common_volume(hit, other) > 1e-4, direction


@pytest.mark.parametrize("lock", [False, True])
def test_pressure_plate_clears_the_box_and_the_lid(built, lock):
    plate = model.build(p, lock)["pressure_plate"]
    assert cadutil.common_volume(plate, built["gate_box"]) < 1e-3
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


# ---- rear wall, side walls -----------------------------------------------------------


def test_rear_window_is_46_by_34_toward_the_light(box):
    assert_opening(box, across_x(268, 271), 46, 34)


@pytest.mark.parametrize("sign", [-1, 1])
def test_side_wall_film_slots_are_3_2_by_37_from_the_front_plates_rear_face(box, sign):
    z = sorted((sign * 43, sign * 46))
    plate_rear = face_x(box, 0) + p.plate_t                        # 254.7
    assert_opening(box, across_z(*z), 3.2, 37, ca=plate_rear + 1.6, cb=p.axis)
    assert plate_rear == pytest.approx(254.7, abs=EPS)              # the film (x 254.7 .. 254.83) lies against it


@pytest.mark.parametrize("sign", [-1, 1])
def test_side_walls_are_3_thick_and_solid_elsewhere(box, sign):
    z = sorted((sign * 43, sign * 46))
    assert_full(box, 245, 254.7, 3, 75.5, *z)                       # covers the front plate's end
    assert_full(box, 257.9, 268, 3, 75.5, *z)
    assert_full(box, 254.7, 257.9, 3, 23.9, *z)
    assert_full(box, 254.7, 257.9, 61.1, 75.5, *z)


@pytest.mark.parametrize("sign", [-1, 1])
def test_no_open_path_from_a_film_slot_into_the_lens_side_chamber(box, sign):
    # The chamber is the air between the front wall's rear face and the front plate's front face, inside the
    # side walls: the lens looks through it at the film. Neither film slot may open into it.
    wall_rear = cadutil.common_bounds(box, probe(p.x_gate, p.x_gate + 10, 3.5, 5.5, -10, 10))[1]    # below the hole
    plate_front = face_x(box, 0)
    side_wall = sorted((sign * 43, sign * 46))
    chamber = probe(wall_rear, plate_front, 3, 75.5, -43, 43).cut(box)
    assert cadutil.volume(chamber) == pytest.approx((plate_front - wall_rear) * 72.5 * 86, rel=1e-9)   # all air
    # the side wall is solid the whole way along the chamber ...
    assert_full(box, wall_rear, plate_front, 3, 75.5, *side_wall)
    # ... so the slot's air and the chamber's air share no face: pushed 0.01 toward each other they do not meet
    slot = probe(wall_rear, 268, 3, 75.5, *side_wall).cut(box)
    assert cadutil.volume(slot) == pytest.approx(3.2 * 37 * 3, rel=1e-9)
    assert cadutil.common_volume(chamber, slot.translate((0, 0, -sign * 0.01))) < 1e-9


# ---- lid -----------------------------------------------------------------------------


def plain_lid(lid):
    """The lid without its lettering: the lid's bounds less the switch slot."""
    xmin, xmax, ymin, ymax, zmin, zmax = (round(b, 3) for b in cadutil.bounds(lid))       # bounds carry ~1e-7 of slack
    slot = probe(p.x_wedge - 0.5, p.x_wedge + 2.5, ymin, ymax, -8, 8)
    return probe(xmin, xmax, ymin, ymax, zmin, zmax).cut(slot)


def test_lid_bounds_at_default(lid):
    # 0.2 short of the front wall (x 245) and of the rear wall (x 268)
    assert cadutil.bounds(lid) == pytest.approx((245.2, 267.8, 75.5, 78.5, -46, 46), abs=EPS)


def test_the_lid_drops_in_with_0_2_to_the_front_and_rear_walls(box, lid):
    for dx in (-0.199, 0.199):
        assert cadutil.common_volume(lid.translate((dx, 0, 0)), box) < 1e-3, dx
    for dx in (-0.201, 0.201):
        assert cadutil.common_volume(lid.translate((dx, 0, 0)), box) > 1e-4, dx


def test_lid_slot_is_3_by_16_for_the_tab(lid):
    # 0.5 each side of the 2 thick tab (x_wedge .. x_wedge + 2), and 3 beyond the +-5 switch travel at each end
    assert_opening(lid, across_y(75.5, 78.5), 3, 16, ca=p.x_wedge + 1, cb=0)
    assert_void(lid, p.x_wedge - 0.5 + T, p.x_wedge + 2.5 - T, 75.5, 78.5, -8 + T, 8 - T)
    assert_full(lid, p.x_wedge - 0.5 - T, p.x_wedge - 0.5 - 0.001, 75.5, 78.5, -8, 8)


def test_lid_volume_less_the_lettering(lid):
    area_boxes = 2 * 16 * 4.4
    engraved = cadutil.volume(plain_lid(lid)) - cadutil.volume(lid)
    assert cadutil.volume(plain_lid(lid)) == pytest.approx(22.6 * 3 * 92 - 3 * 16 * 3, rel=1e-9)
    assert 0.1 * area_boxes * 0.4 < engraved < 0.6 * area_boxes * 0.4


def engraving(lid):
    """The glyphs' material that was cut out, as one solid per letter."""
    return plain_lid(lid).val().cut(cadutil.solid(lid)).Solids()


def words(lid):
    """(SLIDE solids, LOCK solids), by which side of z = 0 they are on."""
    glyphs = engraving(lid)
    z_of = lambda s: sum(cadutil.shape_bounds(s)[4:]) / 2
    return [g for g in glyphs if z_of(g) < 0], [g for g in glyphs if z_of(g) > 0]


def word_bounds(solids):
    boxes = [cadutil.shape_bounds(s) for s in solids]
    return (min(b[0] for b in boxes), max(b[1] for b in boxes), min(b[2] for b in boxes),
            max(b[3] for b in boxes), min(b[4] for b in boxes), max(b[5] for b in boxes))


def test_lettering_is_cut_one_solid_per_letter_with_the_font_glyphs(lid):
    slide, lock = words(lid)
    assert (len(slide), len(lock)) == (5, 4)                     # S L I D E, L O C K


def test_lettering_is_engraved_0_4_deep_in_the_top_face(lid):
    for glyph in engraving(lid):
        ymin, ymax = cadutil.shape_bounds(glyph)[2:4]
        assert (ymin, ymax) == pytest.approx((78.1, 78.5), abs=EPS)


@pytest.mark.parametrize("which, zc", [(0, -14), (1, 14)])
def test_each_word_fits_its_16_by_4_4_box_in_front_of_the_knob(lid, which, zc):
    xmin, xmax, _, _, zmin, zmax = word_bounds(words(lid)[which])
    x_centre = p.x_knob - 11
    assert (xmin, xmax) == pytest.approx((x_centre - (xmax - xmin) / 2, x_centre + (xmax - xmin) / 2), abs=0.01)
    assert (zmin + zmax) / 2 == pytest.approx(zc, abs=0.01)
    assert xmax - xmin <= 4.4 + EPS
    assert zmax - zmin <= 16 + EPS
    assert x_centre == pytest.approx(248.0)


def test_the_longer_word_fills_its_box(lid):
    xmin, xmax, _, _, zmin, zmax = word_bounds(words(lid)[0])
    assert max((xmax - xmin) / 4.4, (zmax - zmin) / 16) > 0.9


def test_lettering_reads_along_plus_z_with_the_letter_tops_toward_plus_x(lid):
    # LOCK's first letter is an L: stem at the start of the reading direction (-z end), foot along
    # the bottom (-x end) pointing the way the word reads (+z)
    _, lock = words(lid)
    letter_l = min(lock, key=lambda s: cadutil.shape_bounds(s)[4])
    x0, x1, y0, y1, z0, z1 = cadutil.shape_bounds(letter_l)
    xm, zm = (x0 + x1) / 2, (z0 + z1) / 2

    def quadrant(xa, xb, za, zb):
        pr = cadutil.solid(probe(xa, xb, y0 - 1, y1 + 1, za, zb))
        return letter_l.intersect(pr).Volume()

    top_stem = quadrant(xm, x1 + 1, z0 - 1, zm)
    bottom_stem = quadrant(x0 - 1, xm, z0 - 1, zm)
    foot = quadrant(x0 - 1, xm, zm, z1 + 1)
    empty = quadrant(xm, x1 + 1, zm, z1 + 1)
    assert empty < 1e-6
    assert min(top_stem, bottom_stem, foot) > 0.05 * 0.4 * (x1 - x0) * (z1 - z0) / 4


# ---- bed and volumes -----------------------------------------------------------------


@pytest.mark.parametrize("name", ["gate_box", "gate_lid", "pressure_plate"])
def test_fits_the_bed_in_print_pose(built, name):
    posed = cadutil.print_pose(built[name], model.PRINT_UP[name])
    assert cadutil.fits_bed(posed, p)
    assert cadutil.bounds(posed)[4] == pytest.approx(0, abs=EPS)


def test_print_pose_sizes(built):
    box_pose = cadutil.size(cadutil.print_pose(built["gate_box"], "+y"))
    assert box_pose == pytest.approx((30, 92, 78.5), abs=0.05)
    plate_pose = cadutil.size(cadutil.print_pose(built["pressure_plate"], "+y"))
    assert plate_pose == pytest.approx((1.8 + p.pad_t + 2 * SLOPE, 85.5, 72), abs=FACE_TOL)     # footprint 2.66 x 85.5


def test_pressure_plate_prints_on_its_bottom_edge_with_the_pad_slopes_in_the_bed_plane(built):
    posed = cadutil.print_pose(built["pressure_plate"], model.PRINT_UP["pressure_plate"])
    # +y up: the first layers are the plate's bottom edge, 1.8 x 85.5, and nothing else
    x0, x1, y0, y1, *_ = cadutil.common_bounds(posed, probe(-100, 100, -100, 100, 0, 0.2))
    assert (x1 - x0, y1 - y0) == pytest.approx((1.8, 85.5), abs=EPS)
    assert filled(posed, x0, x1, y0, y1, 0, 0.2) > 1 - EPS
    # the pads' sloped faces stand upright, so each layer traces the slope instead of the layers stepping it
    assert cadutil.sloped_faces(posed) == []
    assert len(cadutil.sloped_faces(cadutil.print_pose(built["pressure_plate"], "+x"))) == 4      # printed flat, they were


def segment_area(r, d):
    """Area of the circle of radius r on the far side of a chord d from its centre."""
    return r * r * math.acos(d / r) - d * math.sqrt(r * r - d * d)


def test_box_volume_is_the_sum_of_its_walls(box):
    t = 3
    front = 4 * 78.5 * 92 - 4 * (math.pi * 36.3**2 - segment_area(36.3, 36.0))       # hole breaks 0.3 through the top
    floor = 23 * 3 * 92
    sides = 2 * (23 * 72.5 * t - 3.2 * 37 * t)
    rear = 3 * 78.5 * 92 - 3 * 46 * 34
    front_plate = 86 * 72.5 * 1.8 - 1.8 * 38 * 26
    assert cadutil.volume(box) == pytest.approx(front + floor + sides + rear + front_plate, rel=1e-9)


def test_pressure_plate_volume_is_the_plate_plus_four_pads(plate):
    plate_only = 85.5 * 72 * 1.8 - 1.8 * 38 * 26
    pads = 4 * p.pad * p.pad * p.pad_t               # linear slope about the centre: mean thickness is pad_t
    assert cadutil.volume(plate) == pytest.approx(plate_only + pads, rel=1e-9)


# ---- follows the params --------------------------------------------------------------


@pytest.mark.parametrize("q", [Params(wd=150), Params(axis=40), Params(wd=100, axis=50)])
def test_gate_follows_wd_and_axis(q):
    solids = model.build(q)
    assert all(cadutil.is_valid(s) for s in solids.values())
    assert cadutil.bounds(solids["gate_box"]) == pytest.approx((q.x_gate, q.x_gate + 30, 0, q.gh, -46, 46), abs=0.05)
    assert cadutil.bounds(solids["gate_lid"]) == pytest.approx((q.x_gate + 4.2, q.x_gate + 26.8, q.gh - 3, q.gh, -46, 46), abs=EPS)
    assert cadutil.bounds(solids["pressure_plate"])[2:] == pytest.approx((3.25, q.gh - 3.25, -42.75, 42.75), abs=EPS)
    # the film-plane geometry moves with x_film
    assert cadutil.common_bounds(solids["gate_box"], probe(q.x_film - 6, q.x_film + 6, 10, 20, -10, 10))[1] == pytest.approx(
        q.x_film - 0.3, abs=EPS
    )
    assert cadutil.common_bounds(solids["pressure_plate"], probe(q.x_film - 6, q.x_film + 6, 10, 20, -10, 10))[0] == pytest.approx(
        q.x_film + 0.3, abs=EPS
    )
    # the film slots start at the front plate's rear face, wherever that is
    plate_rear = cadutil.common_bounds(solids["gate_box"], probe(q.x_film - 6, q.x_film + 6, 10, 20, -10, 10))[1]
    assert_opening(solids["gate_box"], across_z(43, 46), 3.2, 37, ca=plate_rear + 1.6, cb=q.axis)
    assert cadutil.common_volume(solids["pressure_plate"], solids["gate_box"]) < 1e-3
