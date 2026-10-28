"""Lock switch: the wedge plate (with its tab and four ramps) and the knob.

Everything is measured on the built solids with probes (thin boxes), the way the film gate tests
do it, and the wedge plate is mated against the real gate parts: its ramps against the pressure
plate's pads at SLIDE and LOCK, its tab against the lid slot, its window against the frame
window. The mockup-drawn ramps (the interface Task 4 built the pads for) are an independent
oracle for the ramps' shape.
"""

from itertools import combinations

import cadquery as cq
import pytest

import cadutil
from cadutil import probe
from params import DEFAULT, Params
from parts.film_gate import model as gate_model
from parts.lock_switch import model

p = DEFAULT
EPS = 1e-6
FACE_TOL = 1e-3
SLOPE = p.ramp_rise / p.ramp_len
SLIDE_Z, LOCK_Z = -p.sw_travel / 2, p.sw_travel / 2
RAMPS = [(zc, p.axis + dy) for zc in (-p.pad_z, p.pad_z) for dy in (-p.pad_dy, p.pad_dy)]
GATE_PARTS = ["gate_box", "gate_lid", "pressure_plate"]
ALL = GATE_PARTS + ["wedge_plate", "knob"]


@pytest.fixture(scope="module")
def switch():
    return model.build(p)


@pytest.fixture(scope="module")
def switch_lock():
    return model.build(p, lock=True)


@pytest.fixture(scope="module")
def gate():
    return gate_model.build(p)


@pytest.fixture(scope="module")
def gate_lock():
    return gate_model.build(p, lock=True)


@pytest.fixture(scope="module")
def wedge(switch):
    return switch["wedge_plate"]


@pytest.fixture(scope="module")
def wedge_lock(switch_lock):
    return switch_lock["wedge_plate"]


@pytest.fixture(scope="module")
def knob(switch):
    return switch["knob"]


def filled(wp, *ranges):
    """Fraction of the probe box (x0, x1, y0, y1, z0, z1) that is material."""
    pr = probe(*ranges)
    return cadutil.common_volume(wp, pr) / cadutil.volume(pr)


def assert_void(wp, *ranges):
    assert filled(wp, *ranges) < EPS, ranges


def assert_full(wp, *ranges):
    assert filled(wp, *ranges) > 1 - EPS, ranges


def mockup_ramp(zr, y0):
    """A ramp as the mockup draws it (rebuild(), the wedge plate's ramps): 4 high from y0, spanning
    ramp_len about zr, its face ramp_t(u) in front of the wedge plate, thick toward -z. Independent of
    the model's own ramp, and the same as film_gate's tests draw."""
    h = p.ramp_len / 2
    pts = [
        (p.x_wedge, zr - h),
        (p.x_wedge - p.ramp_t(-h), zr - h),
        (p.x_wedge - p.ramp_t(h), zr + h),
        (p.x_wedge, zr + h),
    ]
    return cq.Workplane("XZ", origin=(0, y0 + p.pad, 0)).polyline(pts).close().extrude(p.pad)


def ramp_thickness(wp, yc, z):
    """The ramp's x thickness at z, from a 0.002 wide slab (read at the slab's thick, -z, edge)."""
    b = cadutil.common_bounds(wp, probe(p.x_wedge - 2, p.x_wedge, yc - 3, yc + 3, z, z + 0.002))
    return p.x_wedge - b[0]


def solids(gate_, switch_):
    return {**gate_, **switch_}


# ---- solids and parameters -----------------------------------------------------------


def test_solid_names_and_print_directions(switch):
    assert list(switch) == ["wedge_plate", "knob"]
    assert model.PRINT_UP == {"wedge_plate": "+y", "knob": "+y"}


@pytest.mark.parametrize("name", ["wedge_plate", "knob"])
@pytest.mark.parametrize("lock", [False, True])
def test_each_solid_is_one_valid_closed_solid(name, lock):
    solid = cadutil.solid(model.build(p, lock)[name])      # raises unless exactly one
    assert solid.isValid()
    assert all(shell.Closed() for shell in solid.Shells())
    assert solid.Volume() > 0


def test_new_params_defaults():
    assert (p.wedge_t, p.wedge_w, p.wedge_win_w, p.wedge_clear) == (2, 70, 52, 0.5)
    assert p.tab_w == 4
    assert (p.knob_w, p.knob_h, p.knob_l) == (10, 5, 12)
    assert (p.ridges, p.ridge_w, p.ridge_h, p.ridge_pitch) == (3, 1.2, 0.8, 3)
    # reused, not duplicated: the lid slot's tab values, the pad footprint, the window height
    assert (p.tab_t, p.tab_clear, p.slot_end, p.pad, p.win_h) == (2, 0.5, 3, 4, 26)


def test_lock_moves_the_switch_sw_travel_along_z_and_nothing_else(switch, switch_lock):
    for name in switch:
        slide, lock = cadutil.bounds(switch[name]), cadutil.bounds(switch_lock[name])
        assert lock == pytest.approx(tuple(b + (p.sw_travel if i >= 4 else 0) for i, b in enumerate(slide)), abs=EPS)
        assert cadutil.volume(switch_lock[name]) == pytest.approx(cadutil.volume(switch[name]), rel=1e-12)


# ---- wedge plate: the plate, its window, the tab -------------------------------------


def test_wedge_plate_bounds_at_slide(wedge):
    # plate 2 x 71.5 x 70 plus the 0.8 ramps in front and the tab above: 2.8 x 75 x 70
    assert cadutil.bounds(wedge) == pytest.approx((257.2, 260, 3.5, 78.5, -40, 30), abs=EPS)
    assert cadutil.size(wedge) == pytest.approx((2.8, 75, 70), abs=EPS)


def test_the_plate_is_2_thick_70_wide_and_71_5_tall(wedge):
    # the plate proper: behind the ramps' root and below the tab
    plate = cadutil.common_bounds(wedge, probe(p.x_wedge, 270, 0, 75, -50, 50))
    assert plate == pytest.approx((258, 260, 3.5, 75, -40, 30), abs=EPS)
    assert plate[3] - plate[2] == pytest.approx(71.5, abs=EPS)                   # gh - 7
    assert plate[5] - plate[4] == pytest.approx(70, abs=EPS)
    assert_full(wedge, p.x_wedge, p.x_wedge + 2, 3.5, 25, -40, 30)                # below the ramps and the window
    assert_full(wedge, p.x_wedge, p.x_wedge + 2, 60.5, 75, -40, 30)              # above them
    assert_void(wedge, p.x_wedge - 5, p.x_wedge - 0.9, 0, 80, -50, 50)           # nothing farther than the thickest ramp


def test_the_plate_clears_the_floor_and_the_lid_by_half_a_millimetre(wedge, gate):
    floor_top, lid_bottom = p.wall, p.gh - p.wall
    plate = cadutil.common_bounds(wedge, probe(p.x_wedge, p.x_wedge + 2, 0, 80, 10, 25))      # away from the tab
    assert plate[2] - floor_top == pytest.approx(0.5, abs=EPS)
    assert lid_bottom - plate[3] == pytest.approx(0.5, abs=EPS)
    assert cadutil.common_volume(wedge, gate["gate_lid"]) < 1e-3
    assert cadutil.common_volume(wedge, gate["gate_box"]) < 1e-3


@pytest.mark.parametrize("lock", [False, True])
def test_the_window_is_52_by_26_on_the_axis_and_carried_with_the_switch(lock):
    w = model.build(p, lock)["wedge_plate"]
    s = LOCK_Z if lock else SLIDE_Z
    x0, x1 = p.x_wedge, p.x_wedge + 2
    y0, y1 = p.axis - 13, p.axis + 13
    t = 0.02
    assert_void(w, x0, x1, y0 + t, y1 - t, s - 26 + t, s + 26 - t)
    for edge in (-1, 1):                                       # solid just outside each edge
        z = sorted((s + edge * 26.001, s + edge * (26 + t)))
        assert_full(w, x0, x1, y0 + t, y1 - t, *z)
        y = sorted((p.axis + edge * 13.001, p.axis + edge * (13 + t)))
        assert_full(w, x0, x1, *y, s - 26 + t, s + 26 - t)


@pytest.mark.parametrize("lock", [False, True])
def test_the_shifted_window_still_clears_the_38_by_26_frame_window(lock):
    w = model.build(p, lock)["wedge_plate"]
    x0, x1 = p.x_wedge - 1, p.x_wedge + 3
    y0, y1 = p.axis - 13, p.axis + 13
    assert cadutil.common_volume(w, probe(x0, x1, y0, y1, -19, 19)) < 1e-3
    # the room each way along z: the frame window grown 1.99 clears, grown 2.01 does not
    assert cadutil.common_volume(w, probe(x0, x1, y0, y1, -19 - 1.99, 19 + 1.99)) < 1e-3
    assert cadutil.common_volume(w, probe(x0, x1, y0, y1, -19 - 2.01, 19 + 2.01)) > 1e-3


def test_the_tab_is_2_by_4_on_the_plates_top_up_to_the_lid_top(wedge):
    tab = cadutil.common_bounds(wedge, probe(250, 270, 75.01, 80, -50, 50))
    assert tab == pytest.approx((258, 260, 75.01, 78.5, -7, -3), abs=EPS)
    assert_full(wedge, 258, 260, 75, 78.5, -7, -3)
    assert_void(wedge, 258, 260, 75.01, 78.5, -50, -7.01)
    assert_void(wedge, 258, 260, 75.01, 78.5, -2.99, 50)
    assert cadutil.bounds(wedge)[3] == pytest.approx(p.gh, abs=EPS)                  # flush with the lid top


@pytest.mark.parametrize("lock, z", [(False, (-40, 30)), (True, (-30, 40))])
def test_the_wedge_plate_stays_inside_the_gate_interior_at_both_ends(lock, z, gate):
    # interior: between the side walls' inner faces (z +-43) and the floor and the lid (y 3 .. gh - 3).
    # Measured against the box: the plate (below its tab) clears every wall of it.
    w = model.build(p, lock)["wedge_plate"]
    plate = cadutil.common_bounds(w, probe(0, 400, 0, p.gh - p.wall, -100, 100))      # the tab is above the lid's underside
    assert (plate[4], plate[5]) == pytest.approx(z, abs=EPS)
    assert plate[2] >= 3 and plate[3] <= p.gh - 3
    assert -43 <= plate[4] and plate[5] <= 43
    assert cadutil.common_volume(w, gate["gate_box"]) < 1e-3


# ---- wedge plate: the ramps ----------------------------------------------------------


@pytest.mark.parametrize("lock", [False, True])
def test_four_ramps_under_the_four_pads_on_the_front_face(lock):
    w = model.build(p, lock)["wedge_plate"]
    s = LOCK_Z if lock else SLIDE_Z
    in_ramps = 0.0
    for zc, yc in RAMPS:
        zr = zc + s
        pr = probe(p.x_wedge - 2, p.x_wedge, yc - 3, yc + 3, zr - 8, zr + 8)
        x0, x1, y0, y1, z0, z1 = cadutil.common_bounds(w, pr)
        assert (y0, y1, z0, z1) == pytest.approx((yc - 2, yc + 2, zr - 6, zr + 6), abs=EPS)     # 4 tall, 12 long
        assert (x0, x1) == pytest.approx((p.x_wedge - 0.8, p.x_wedge), abs=EPS)
        in_ramps += cadutil.common_volume(w, pr)
    # exactly those four: all the material in front of the plate is in those footprints
    assert in_ramps == pytest.approx(cadutil.common_volume(w, probe(p.x_wedge - 2, p.x_wedge, 0, 100, -100, 100)), rel=1e-9)
    assert in_ramps == pytest.approx(4 * 4 * 12 * 0.45, rel=1e-9)             # mean thickness (0.8 + 0.1) / 2


def test_ramp_thickness_is_0_8_at_the_minus_z_end_and_0_1_at_the_plus_z_end(wedge):
    for zc, yc in RAMPS:
        zr = zc + SLIDE_Z
        assert ramp_thickness(wedge, yc, zr - 6) == pytest.approx(0.8, abs=EPS)
        assert ramp_thickness(wedge, yc, zr + 6 - 0.002) == pytest.approx(0.1 + 0.002 * SLOPE, abs=EPS)
        assert ramp_thickness(wedge, yc, zr) == pytest.approx(0.45, abs=EPS)         # linear in between
        assert ramp_thickness(wedge, yc, zr - 3) == pytest.approx(0.45 + 3 * SLOPE, abs=EPS)


def test_ramps_are_the_mockups(wedge):
    for zc, yc in RAMPS:
        r = mockup_ramp(zc + SLIDE_Z, yc - p.pad / 2)
        assert cadutil.common_volume(wedge, r) == pytest.approx(cadutil.volume(r), rel=1e-9)


def test_wedge_plate_volume_is_the_plate_less_the_window_plus_the_tab_and_four_ramps(wedge):
    plate = 2 * 70 * 71.5 - 2 * 52 * 26
    tab = 2 * 4 * 3.5
    ramps = 4 * (4 * 12 * 0.45)
    assert cadutil.volume(wedge) == pytest.approx(plate + tab + ramps, rel=1e-9)


# ---- mating with the pressure plate --------------------------------------------------


def test_at_slide_each_pad_lies_on_its_ramp_without_overlap(gate, wedge):
    plate = gate["pressure_plate"]
    assert cadutil.common_volume(plate, wedge) < 1e-3
    # ... and they touch, not apart: nudge the plate 0.01 toward the wedge plate and every pad meets its ramp
    pushed = plate.translate((0.01, 0, 0))
    for zc, yc in RAMPS:
        ramp_zone = probe(p.x_wedge - 2, p.x_wedge, yc - 3, yc + 3, zc - 8, zc + 8)
        assert cadutil.common_volume(pushed, wedge.intersect(ramp_zone)) > 1e-3


def test_at_lock_the_pads_overlap_the_ramps_by_a_uniform_preload(gate_lock, wedge_lock):
    plate = gate_lock["pressure_plate"]
    shift = LOCK_Z
    assert p.preload == pytest.approx(0.1133, abs=1e-4)
    overlap = 0.0
    for zc, yc in RAMPS:
        ramp_zone = probe(p.x_wedge - 2, p.x_wedge, yc - 3, yc + 3, zc + shift - 8, zc + shift + 8)
        ramp = wedge_lock.intersect(ramp_zone)
        # the pad and ramp meet from zc - 1 (the ramp's thick end) to zc + 2 (the pad's far edge)
        for z in (zc - 0.99, zc + 0.5, zc + 1.99):
            slab = probe(p.x_film, p.x_film + 20, 0, 100, z, z + 0.002)
            x0, x1, *_ = cadutil.common_bounds(plate.intersect(slab), ramp)
            assert x1 - x0 == pytest.approx(p.preload, abs=2 * 0.002 * SLOPE)
        # so the overlap is a prism of that thickness over the 3 x 4 where pad and ramp meet in z
        v = cadutil.common_volume(plate, ramp)
        assert v == pytest.approx(p.preload * 3 * p.pad, rel=1e-6)
        overlap += v
    assert cadutil.common_volume(plate, wedge_lock) == pytest.approx(overlap, rel=1e-9)
    assert overlap == pytest.approx(4 * 3 * 4 * 0.1133, abs=0.005 * 48)


def test_the_overlap_is_the_pads_into_the_ramps_and_nothing_else_of_the_plate(gate_lock, wedge_lock):
    # the pressure plate's body is behind the ramps' thick ends by more than the preload; only pads reach them
    plate = gate_lock["pressure_plate"]
    body = probe(p.x_film, p.x_pp - p.lock_shift, 0, 100, -50, 50)
    assert cadutil.common_volume(wedge_lock, body) < 1e-3
    assert cadutil.common_volume(plate, probe(p.x_wedge - 0.8 - 1, p.x_wedge, 0, 100, -50, 50)) > 1e-3


@pytest.mark.parametrize("lock", [False, True])
def test_the_only_overlap_among_the_gate_and_the_switch_is_the_pads_in_the_ramps(lock, gate, gate_lock, switch, switch_lock):
    parts = solids(gate_lock, switch_lock) if lock else solids(gate, switch)
    for a, b in combinations(ALL, 2):
        v = cadutil.common_volume(parts[a], parts[b])
        if lock and {a, b} == {"pressure_plate", "wedge_plate"}:
            assert v == pytest.approx(48 * p.preload, rel=1e-6), (a, b)
        else:
            assert v < 1e-3, (a, b, v)


@pytest.mark.parametrize("q", [Params(wd=150), Params(axis=40), Params(wd=100, axis=50)])
def test_pads_and_ramps_mate_wherever_the_rig_is_set(q):
    slide, lock = model.build(q)["wedge_plate"], model.build(q, lock=True)["wedge_plate"]
    plate, plate_lock = gate_model.pressure_plate(q), gate_model.pressure_plate(q, lock=True)
    assert cadutil.common_volume(plate, slide) < 1e-3
    assert cadutil.common_volume(plate.translate((0.01, 0, 0)), slide) > 1e-3
    assert cadutil.common_volume(plate_lock, lock) == pytest.approx(48 * q.preload, rel=1e-6)


# ---- tab and the lid slot ------------------------------------------------------------


@pytest.mark.parametrize("lock", [False, True])
def test_the_tab_clears_the_lid_slot_half_a_millimetre_each_side_in_x(lock, gate, switch, switch_lock):
    w = (switch_lock if lock else switch)["wedge_plate"]
    lid = gate["gate_lid"]
    assert cadutil.common_volume(w, lid) < 1e-3
    for dx in (-0.499, 0.499):
        assert cadutil.common_volume(w.translate((dx, 0, 0)), lid) < 1e-3
    for dx in (-0.501, 0.501):
        assert cadutil.common_volume(w.translate((dx, 0, 0)), lid) > 1e-3


@pytest.mark.parametrize("lock", [False, True])
def test_the_tab_stays_in_the_slot_in_z_with_a_millimetre_to_spare_at_the_end(lock, gate, switch, switch_lock):
    w = (switch_lock if lock else switch)["wedge_plate"]
    lid = gate["gate_lid"]
    toward_end = 1 if lock else -1           # LOCK is at +z, SLIDE at -z
    # 1 mm to the slot's end it is travelling to (slot_end 3 less the tab's half width 2), 11 to the other
    assert cadutil.common_volume(w.translate((0, 0, toward_end * 0.999)), lid) < 1e-3
    assert cadutil.common_volume(w.translate((0, 0, toward_end * 1.001)), lid) > 1e-3
    assert cadutil.common_volume(w.translate((0, 0, -toward_end * 10.999)), lid) < 1e-3
    assert cadutil.common_volume(w.translate((0, 0, -toward_end * 11.001)), lid) > 1e-3


# ---- knob ----------------------------------------------------------------------------


def test_knob_bounds_at_slide(knob):
    assert cadutil.bounds(knob) == pytest.approx((254, 264, 78.5, 84.3, -11, 1), abs=EPS)
    assert cadutil.size(knob) == pytest.approx((10, 5.8, 12), abs=EPS)


def test_knob_is_at_minus_z_at_slide_and_plus_z_at_lock(knob, switch_lock):
    b, bl = cadutil.bounds(knob), cadutil.bounds(switch_lock["knob"])
    assert (b[4] + b[5]) / 2 == pytest.approx(-5, abs=EPS)
    assert (bl[4] + bl[5]) / 2 == pytest.approx(5, abs=EPS)
    assert (b[0] + b[1]) / 2 == pytest.approx(p.x_knob, abs=EPS)


def test_knob_body_is_10_by_5_by_12_on_the_lid_top(knob):
    assert_full(knob, 254, 264, p.gh, p.gh + 5, -11, 1)
    assert_void(knob, 250, 270, p.gh - 5, p.gh - 0.001, -20, 20)


def test_three_grip_ridges_on_top(knob):
    ridge_zone = knob.intersect(probe(250, 270, p.gh + 5.01, p.gh + 6, -20, 20))
    ridges = sorted(ridge_zone.val().Solids(), key=lambda s: cadutil.shape_bounds(s)[0])
    assert len(ridges) == 3
    for ridge, centre in zip(ridges, (p.x_knob - 3, p.x_knob, p.x_knob + 3)):
        x0, x1, _, y1, z0, z1 = cadutil.shape_bounds(ridge)
        assert (x0, x1) == pytest.approx((centre - 0.6, centre + 0.6), abs=EPS)       # 1.2 wide
        assert y1 == pytest.approx(p.gh + 5.8, abs=EPS)                               # 0.8 tall
        assert (z0, z1) == pytest.approx((-11, 1), abs=EPS)                           # the full 12
    assert_full(knob, p.x_knob - 3.6, p.x_knob - 2.4, p.gh + 5, p.gh + 5.8, -11, 1)
    assert_void(knob, p.x_knob - 2.4 + 0.01, p.x_knob - 0.6 - 0.01, p.gh + 5.001, p.gh + 6, -11, 1)


def test_knob_volume_is_the_body_plus_the_ridges(knob):
    assert cadutil.volume(knob) == pytest.approx(10 * 5 * 12 + 3 * 1.2 * 0.8 * 12, rel=1e-9)


@pytest.mark.parametrize("lock", [False, True])
def test_knob_sits_on_the_lid_and_the_tab_by_contact_only(lock, gate, switch, switch_lock):
    sw = switch_lock if lock else switch
    k, w, lid = sw["knob"], sw["wedge_plate"], gate["gate_lid"]
    for part in (w, lid):
        assert cadutil.common_volume(k, part) < 1e-3
        assert cadutil.common_volume(k.translate((0, -0.01, 0)), part) > 1e-3        # touching, not floating


@pytest.mark.parametrize("lock", [False, True])
def test_the_lid_under_the_knob_is_not_engraved(lock, gate, switch, switch_lock):
    k = (switch_lock if lock else switch)["knob"]
    kx0, kx1, _, _, kz0, kz1 = cadutil.bounds(k)
    under = probe(kx0, kx1, p.gh - 0.5, p.gh, kz0, kz1)
    slot = cadutil.common_volume(under, probe(p.x_wedge - 0.5, p.x_wedge + 2.5, 0, 100, -8, 8))
    assert cadutil.common_volume(gate["gate_lid"], under) == pytest.approx(cadutil.volume(under) - slot, rel=1e-9)


# ---- print orientation, bed and volumes ----------------------------------------------


@pytest.mark.parametrize("name", ["wedge_plate", "knob"])
def test_fits_the_bed_in_print_pose(switch, name):
    posed = cadutil.print_pose(switch[name], model.PRINT_UP[name])
    assert cadutil.fits_bed(posed, p)
    assert cadutil.bounds(posed)[4] == pytest.approx(0, abs=EPS)


def test_print_pose_sizes(switch):
    # the wedge plate stands 75 tall (tab up) on a 2.8 x 70 footprint
    assert cadutil.size(cadutil.print_pose(switch["wedge_plate"], "+y")) == pytest.approx((2.8, 70, 75), abs=EPS)
    assert cadutil.size(cadutil.print_pose(switch["knob"], "+y")) == pytest.approx((10, 12, 5.8), abs=EPS)


def test_wedge_plate_prints_on_its_bottom_edge_with_the_ramp_slopes_in_the_bed_plane(switch):
    posed = cadutil.print_pose(switch["wedge_plate"], model.PRINT_UP["wedge_plate"])
    # +y up: the first layers are the plate's bottom edge, 2 x 70, and nothing else; the tab is at the top
    x0, x1, y0, y1, *_ = cadutil.common_bounds(posed, probe(-100, 100, -100, 100, 0, 0.2))
    assert (x1 - x0, y1 - y0) == pytest.approx((2, 70), abs=EPS)
    assert filled(posed, x0, x1, y0, y1, 0, 0.2) > 1 - EPS
    tab = cadutil.common_bounds(posed, probe(-100, 100, -100, 100, 75 - 3.5 + 0.01, 80))
    assert (tab[1] - tab[0], tab[3] - tab[2]) == pytest.approx((2, 4), abs=EPS)
    # the ramps' sloped faces stand upright, so each layer traces the 0.1 -> 0.8 slope instead of stepping it
    assert cadutil.sloped_faces(posed) == []
    assert len(cadutil.sloped_faces(cadutil.print_pose(switch["wedge_plate"], "-x"))) == 4      # printed flat, they were


def test_knob_prints_flat_with_the_ridges_up(switch):
    posed = cadutil.print_pose(switch["knob"], "+y")
    assert cadutil.bounds(posed)[5] == pytest.approx(5.8, abs=EPS)
    assert cadutil.common_volume(posed, probe(-100, 100, -100, 100, 5, 6)) == pytest.approx(3 * 1.2 * 0.8 * 12, rel=1e-6)
    assert_full(posed, -5, 5, -6, 6, 0, 5)


# ---- follows the params --------------------------------------------------------------


@pytest.mark.parametrize("q", [Params(wd=150), Params(axis=40), Params(wd=100, axis=50)])
def test_switch_follows_wd_and_axis(q):
    built = model.build(q)
    assert all(cadutil.is_valid(s) for s in built.values())
    assert cadutil.bounds(built["wedge_plate"]) == pytest.approx(
        (q.x_wedge - 0.8, q.x_wedge + 2, q.wall + 0.5, q.gh, -40, 30), abs=EPS
    )
    assert cadutil.bounds(built["knob"]) == pytest.approx(
        (q.x_knob - 5, q.x_knob + 5, q.gh, q.gh + 5.8, -11, 1), abs=EPS
    )
    for zc, yc in [(zc, q.axis + dy) for zc in (-q.pad_z, q.pad_z) for dy in (-q.pad_dy, q.pad_dy)]:
        zr = zc - q.sw_travel / 2
        b = cadutil.common_bounds(
            built["wedge_plate"], probe(q.x_wedge - 2, q.x_wedge, yc - 3, yc + 3, zr - 8, zr + 8)
        )
        assert b[2:] == pytest.approx((yc - 2, yc + 2, zr - 6, zr + 6), abs=EPS)
