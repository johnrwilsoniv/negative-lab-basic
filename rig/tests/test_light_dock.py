"""Light dock: floor, lips, cheeks and the shroud that runs from the gate's rear window to the light.

Everything is measured on the built solid with probes (thin boxes), the way the film gate and lock
switch tests do it. The dock is mated against the real gate parts (its front face against the gate's
rear face, the shroud against the rear window) and against a stand-in for the CS-Lite, which is
bought, not printed.
"""

from itertools import product

import pytest

import cadutil
from cadutil import probe
from params import DEFAULT, Params
from parts.film_gate import model as gate_model
from parts.light_dock import model
from parts.lock_switch import model as switch_model

p = DEFAULT
EPS = 1e-6
HW = p.dock_w / 2                                   # 90.5
CHEEK_IN = p.csl_l / 2 + 0.5                        # 83: cheek inner faces
SHROUD_Y0, SHROUD_Y1 = p.axis - 23, p.axis + 23     # interior, 46 tall: 19.5 .. 65.5


@pytest.fixture(scope="module")
def dock():
    return model.build(p)["light_dock"]


@pytest.fixture(scope="module")
def gate():
    return gate_model.build(p)


@pytest.fixture(scope="module")
def gate_lock():
    return gate_model.build(p, lock=True)


@pytest.fixture(scope="module")
def switch():
    return switch_model.build(p)


@pytest.fixture(scope="module")
def switch_lock():
    return switch_model.build(p, lock=True)


def filled(wp, *ranges):
    """Fraction of the probe box (x0, x1, y0, y1, z0, z1) that is material."""
    pr = probe(*ranges)
    return cadutil.common_volume(wp, pr) / cadutil.volume(pr)


def assert_void(wp, *ranges):
    assert filled(wp, *ranges) < EPS, ranges


def assert_full(wp, *ranges):
    assert filled(wp, *ranges) > 1 - EPS, ranges


def csl(q: Params = p):
    """The CS-Lite standing in its slot: 165 x 112 x 20, on its long edge on the floor."""
    return probe(q.x_light, q.x_light + q.csl_t, q.floor_t, q.floor_t + q.csl_h, -q.csl_l / 2, q.csl_l / 2)


# ---- solids and parameters -----------------------------------------------------------


def test_solid_name_and_print_direction(dock):
    assert list(model.build(p)) == ["light_dock"]
    assert model.PRINT_UP == {"light_dock": "+y"}


@pytest.mark.parametrize("lock", [False, True])
def test_one_valid_closed_solid(lock):
    solid = cadutil.solid(model.build(p, lock)["light_dock"])      # raises unless exactly one
    assert solid.isValid()
    assert all(shell.Closed() for shell in solid.Shells())
    assert solid.Volume() > 0


def test_the_dock_ignores_lock(dock):
    locked = model.build(p, lock=True)["light_dock"]
    assert cadutil.bounds(locked) == cadutil.bounds(dock)
    assert cadutil.volume(locked) == cadutil.volume(dock)


def test_new_params_defaults_and_the_ones_that_were_literals():
    assert (p.floor_t, p.lip_h, p.lip_t, p.cheek_top, p.cheek_clear) == (4, 12, 4, 62, 0.5)
    assert (p.shroud_w, p.shroud_h, p.shroud_t) == (60, 46, 2)
    assert (p.dock_extra_w, p.dock_tail, p.csl_clear) == (16, 6, 0.5)
    # the literals Task 1 left inside dock_w and dock_x1, unchanged; the slot is the panel plus csl_clear
    assert p.dock_w == p.csl_l + p.dock_extra_w == 181
    assert p.dock_x1 == p.x_light + p.csl_t + p.csl_clear + p.dock_tail == 306.5
    # reused, not duplicated
    assert (p.csl_l, p.csl_t, p.csl_h, p.rear_win_w, p.rear_win_h) == (165, 20, 112, 46, 34)


# ---- bounding box --------------------------------------------------------------------


def test_bounds_at_defaults(dock):
    # x: the gate's rear face .. 6 past the slot's back edge; y: floor underside .. shroud top (axis + 25); z: +-dock_w/2
    assert cadutil.bounds(dock) == pytest.approx((271, 306.5, 0, 67.5, -90.5, 90.5), abs=EPS)
    assert cadutil.size(dock) == pytest.approx((35.5, 67.5, 181), abs=0.05)


def test_the_shroud_top_is_the_highest_point_and_stands_above_the_cheeks(dock):
    assert cadutil.bounds(dock)[3] == pytest.approx(p.axis + 25, abs=EPS)
    assert p.axis + 25 > p.cheek_top
    assert_void(dock, 270, 310, 67.5, 100, -100, 100)


# ---- floor ---------------------------------------------------------------------------


def test_floor_is_4_thick_and_181_wide_and_runs_dock_x0_to_dock_x1(dock):
    floor = cadutil.common_bounds(dock, probe(250, 320, 0, 4, -100, 100))
    assert floor == pytest.approx((271, 306.5, 0, 4, -90.5, 90.5), abs=EPS)
    assert_full(dock, 271, 306.5, 0, 4, -90.5, 90.5)
    assert floor[1] - floor[0] == pytest.approx(35.5, abs=EPS)


def test_the_floor_ends_6_past_the_slots_back_edge(dock):
    back_lip_front = cadutil.common_bounds(dock, probe(p.x_light + 1, 320, 4.001, 15, -80, 80))[0]
    assert cadutil.bounds(dock)[1] - back_lip_front == pytest.approx(6, abs=EPS)


# ---- lips and the slot ---------------------------------------------------------------


def test_front_and_back_lips_are_12_tall_and_full_width(dock):
    # the shroud's top plate stands over the front lip's middle, so measure that lip beside it
    front = cadutil.common_bounds(dock, probe(270, 290, 4.001, 100, 31, CHEEK_IN - 0.001))
    assert front == pytest.approx((276, 280, 4.001, 16, 31, CHEEK_IN - 0.001), abs=EPS)
    back = cadutil.common_bounds(dock, probe(290, 330, 4.001, 100, -CHEEK_IN + 0.001, CHEEK_IN - 0.001))
    assert back == pytest.approx((300.5, 304.5, 4.001, 16, -CHEEK_IN + 0.001, CHEEK_IN - 0.001), abs=EPS)
    assert_full(dock, 276, 280, 4, 16, -HW, HW)                    # full width, floor edge to floor edge
    assert_full(dock, 300.5, 304.5, 4, 16, -HW, HW)
    assert p.lip_h == 12


def test_the_lips_are_4_thick_and_nothing_stands_above_them_between_the_cheeks(dock):
    assert_void(dock, 276, 280, 16.001, 100, 30.001, CHEEK_IN - 0.001)       # beside the shroud
    assert_void(dock, 276, 280, 16.001, 100, -CHEEK_IN + 0.001, -30.001)
    assert_void(dock, 300.5, 304.5, 16.001, 100, -CHEEK_IN + 0.001, CHEEK_IN - 0.001)


def test_the_slot_between_the_lips_is_the_cs_lites_20_and_half_a_millimetre(dock):
    assert_void(dock, p.x_light, p.x_light + 20.5, 4.001, 100, -CHEEK_IN + 0.001, CHEEK_IN - 0.001)
    # the lips are where the slot ends: widen the probe 0.001 each side and it meets them
    assert cadutil.common_volume(dock, probe(p.x_light - 0.001, p.x_light + 20.5, 4.001, 15, -80, 80)) > 1e-3
    assert cadutil.common_volume(dock, probe(p.x_light, p.x_light + 20.5 + 0.001, 4.001, 15, -80, 80)) > 1e-3
    back = cadutil.common_bounds(dock, probe(p.x_light, 310, 4.001, 15, -80, 80))
    front = cadutil.common_bounds(dock, probe(270, p.x_light, 4.001, 15, 40, 80))            # clear of the shroud
    assert back[0] - front[1] == pytest.approx(20.5, abs=EPS)
    assert front[1] == pytest.approx(p.x_light, abs=EPS)          # the front lip, and so the lit face, has not moved


def test_the_cs_lite_drops_in_against_the_front_lip_with_half_a_millimetre_behind_it(dock):
    light = csl()
    assert cadutil.common_volume(dock, light) < 1e-3
    assert cadutil.common_volume(dock, light.translate((-0.01, 0, 0))) > 1e-3       # on the front lip
    assert cadutil.common_volume(dock, light.translate((0.499, 0, 0))) < 1e-3       # room to drop it in
    assert cadutil.common_volume(dock, light.translate((0.501, 0, 0))) > 1e-3       # then the back lip
    assert cadutil.common_volume(dock, light.translate((0, -0.01, 0))) > 1e-3       # rests on the floor


# ---- cheeks --------------------------------------------------------------------------


@pytest.mark.parametrize("sign", [-1, 1])
def test_cheeks_are_62_tall_from_the_cs_lites_end_plus_half_a_millimetre_to_the_floors_edge(dock, sign):
    z0, z1 = sorted((sign * CHEEK_IN, sign * HW))
    above_lips = cadutil.common_bounds(dock, probe(250, 330, 16.001, 100, z0, z1))
    assert above_lips == pytest.approx((276, 304.5, 16.001, 62, z0, z1), abs=EPS)
    assert_full(dock, 276, 304.5, 4, 62, z0, z1)
    assert_void(dock, 250, 330, 62.001, 100, z0, z1)
    assert z1 - z0 == pytest.approx(7.5, abs=EPS)
    # the inner face is where it should be: nothing above the lips just inside it, all of it just outside
    inside = sorted((sign * (CHEEK_IN - 0.001), sign * 30.001))
    assert_void(dock, 250, 330, 16.001, 100, *inside)


def test_cheeks_span_the_lips_and_the_slot_in_x(dock):
    # x_light - 4 .. the back lip's back face: the cheek faces are flush with the lips' outer faces
    assert_full(dock, 276, 304.5, 4, 62, CHEEK_IN, HW)
    assert_void(dock, 271, 275.999, 4.001, 62, CHEEK_IN, HW)
    assert_void(dock, 304.501, 306.5, 4.001, 62, CHEEK_IN, HW)


def test_cheek_inner_faces_are_half_a_millimetre_clear_of_the_cs_lites_ends(dock):
    light = csl()
    for dz in (-0.499, 0.499):
        assert cadutil.common_volume(dock, light.translate((0, 0, dz))) < 1e-3
    for dz in (-0.501, 0.501):
        assert cadutil.common_volume(dock, light.translate((0, 0, dz))) > 1e-3


# ---- shroud --------------------------------------------------------------------------


def test_shroud_runs_from_the_gates_rear_face_to_the_light_face(dock):
    # its x extent is that of the part of the dock above the lips' height: within |z| < 30 and above y 20
    shroud = cadutil.common_bounds(dock, probe(250, 330, 20, 100, -30, 30))
    assert (shroud[0], shroud[1]) == pytest.approx((p.dock_x0, p.x_light), abs=EPS)
    assert shroud[0] == pytest.approx(271) and shroud[1] == pytest.approx(280)
    assert_full(dock, 271, 280, 4, 67.5, 28, 30)                # a wall at the front face and at the light face


def test_shroud_is_60_wide_outside_and_its_top_is_axis_plus_25(dock):
    shroud = cadutil.common_bounds(dock, probe(250, 330, 20, 100, -50, 50))
    assert shroud == pytest.approx((271, 280, 20, 67.5, -30, 30), abs=EPS)
    assert_void(dock, 271, 280, 16.001, 100, 30.001, CHEEK_IN - 0.001)
    assert_void(dock, 271, 280, 16.001, 100, -CHEEK_IN + 0.001, -30.001)


def test_shroud_interior_is_56_wide_and_46_tall_on_the_axis(dock):
    assert_void(dock, 271, 280, SHROUD_Y0, SHROUD_Y1, -28, 28)
    # walls: 2 thick each side, 2 thick above, solid block below
    for lo, hi in ((28, 30), (-30, -28)):
        assert_full(dock, 271, 280, SHROUD_Y0, SHROUD_Y1, lo, hi)
    assert_full(dock, 271, 280, SHROUD_Y1, SHROUD_Y1 + 2, -30, 30)
    assert_full(dock, 271, 280, 4, SHROUD_Y0, -30, 30)
    # and the opening is no bigger: grown 0.001 each way it meets material
    for grown in (
        (271, 280, SHROUD_Y0 - 0.001, SHROUD_Y1, -28, 28),
        (271, 280, SHROUD_Y0, SHROUD_Y1 + 0.001, -28, 28),
        (271, 280, SHROUD_Y0, SHROUD_Y1, -28.001, 28),
        (271, 280, SHROUD_Y0, SHROUD_Y1, -28, 28.001),
    ):
        assert cadutil.common_volume(dock, probe(*grown)) > 1e-4, grown


def test_the_opening_clears_the_front_lip_at_the_default_axis(dock):
    # the opening's floor is 3.5 above the lip's top (axis 42.5; flush at the lowest axis Params allows, 39)
    assert SHROUD_Y0 - (p.floor_t + p.lip_h) == pytest.approx(3.5, abs=EPS)
    assert_void(dock, p.x_light - p.lip_t, p.x_light, SHROUD_Y0, SHROUD_Y1, -28, 28)


def test_shroud_is_open_at_both_ends(dock):
    # the interior reaches the front face (x = dock_x0) and the light face (x = x_light)
    assert_void(dock, p.dock_x0, p.dock_x0 + 0.01, SHROUD_Y0, SHROUD_Y1, -28, 28)
    assert_void(dock, p.x_light - 0.01, p.x_light, SHROUD_Y0, SHROUD_Y1, -28, 28)
    assert_void(dock, 270, 310, SHROUD_Y0 + 0.001, SHROUD_Y1 - 0.001, -28 + 0.001, 28 - 0.001)   # clear through, camera to light


# ---- the gate and the shroud ---------------------------------------------------------


def grown(window, side, extra):
    """The window (y0, y1, z0, z1) grown `extra` toward `side`."""
    y0, y1, z0, z1 = window
    return {
        "+z": (y0, y1, z0, z1 + extra),
        "-z": (y0, y1, z0 - extra, z1),
        "+y": (y0, y1 + extra, z0, z1),
        "-y": (y0 - extra, y1, z0, z1),
    }[side]


@pytest.mark.parametrize("side, room", [("+z", 5), ("-z", 5), ("+y", 6), ("-y", 6)])
def test_shroud_interior_surrounds_the_gates_rear_window_with_5_each_side_in_z_and_6_in_y(dock, gate, side, room):
    box = gate["gate_box"]
    rear_x = (p.x_gate + p.gate_d - p.wall, p.x_gate + p.gate_d)
    window = (p.axis - p.rear_win_h / 2, p.axis + p.rear_win_h / 2, -p.rear_win_w / 2, p.rear_win_w / 2)   # 34 tall (y) by 46 wide (z)
    assert cadutil.common_volume(box, probe(*rear_x, *window)) < EPS
    assert cadutil.common_volume(box, probe(*rear_x, *grown(window, side, 0.001))) > 1e-4
    # carried through the shroud, the window's projection is clear of the dock for `room` more in this direction, not beyond
    through = (p.dock_x0, p.x_light)
    assert cadutil.common_volume(dock, probe(*through, *grown(window, side, room - 0.001))) < EPS
    assert cadutil.common_volume(dock, probe(*through, *grown(window, side, room + 0.001))) > 1e-4


def test_the_dock_touches_the_gates_rear_face_without_overlapping_it(dock, gate):
    box = gate["gate_box"]
    assert cadutil.bounds(box)[1] == pytest.approx(p.dock_x0, abs=EPS)             # the gate's rear face
    assert cadutil.bounds(dock)[0] == pytest.approx(cadutil.bounds(box)[1], abs=EPS)
    assert cadutil.common_volume(dock, box) < 1e-3
    # touching, not apart: 0.01 closer and the shroud's ring and the floor meet the rear wall
    assert cadutil.common_volume(dock.translate((-0.01, 0, 0)), box) > 1e-3


@pytest.mark.parametrize("lock", [False, True])
def test_the_dock_touches_none_of_the_other_printed_parts(lock, dock, gate, gate_lock, switch, switch_lock):
    parts = {**(gate_lock if lock else gate), **(switch_lock if lock else switch)}
    for name, other in parts.items():
        assert cadutil.common_volume(dock, other) < 1e-3, name
        assert cadutil.bounds(other)[1] <= p.dock_x0 + EPS, name


# ---- volume --------------------------------------------------------------------------


def test_volume_is_floor_plus_cheeks_plus_lips_plus_shroud(dock):
    floor = 35.5 * 4 * 181
    cheeks = 2 * (28.5 * 58 * 7.5)
    lips = 2 * (4 * 12 * 166) - 4 * 12 * 60              # between the cheeks; the shroud fills the front lip's middle
    shroud = 9 * (60 * 63.5 - 56 * 46)
    assert cadutil.volume(dock) == pytest.approx(floor + cheeks + lips + shroud, rel=1e-9)


# ---- print orientation and bed ------------------------------------------------------


def test_prints_floor_down_and_fits_the_bed(dock):
    posed = cadutil.print_pose(dock, model.PRINT_UP["light_dock"])
    assert cadutil.fits_bed(posed, p)
    assert cadutil.bounds(posed)[4] == pytest.approx(0, abs=EPS)
    assert cadutil.size(posed) == pytest.approx((35.5, 181, 67.5), abs=EPS)     # x, the 181 wide floor, height
    # the floor is the bottom 4: a full 35.5 x 181 slab on the bed, everything else stands on it
    assert_full(posed, *(-17.75, 17.75, -90.5, 90.5, 0, 4))


# ---- elsewhere ----------------------------------------------------------------------


@pytest.mark.parametrize("q", [Params(wd=150, axis=50), Params(axis=40), Params(wd=100, axis=45)])
def test_the_dock_follows_wd_and_axis(q):
    d = model.build(q)["light_dock"]
    assert cadutil.solid(d).isValid()
    assert cadutil.bounds(d) == pytest.approx(
        (q.dock_x0, q.dock_x1, 0, q.axis + 25, -q.dock_w / 2, q.dock_w / 2), abs=EPS
    )     # the shroud top: above the cheeks at any axis Params allows (39 + 25 > 62)
    assert q.dock_x1 - q.dock_x0 == 35.5                                         # wd moves it, doesn't change it
    # the shroud interior sits on the axis, 46 tall (clear of the front lip's top at any allowed axis), and the cheek tops stay at 62
    y0, y1 = q.axis - 23, q.axis + 23
    assert_void(d, q.dock_x0, q.x_light, y0, y1, -28, 28)
    assert_full(d, q.dock_x0, q.x_light, y1, y1 + 2, -30, 30)
    assert_full(d, q.dock_x0, q.x_light, q.floor_t, y0, -30, 30)
    assert cadutil.common_bounds(d, probe(q.x_light - 4, q.x_light + 24, 4.001, 100, q.csl_l / 2 + 0.5, 100))[3] == pytest.approx(62, abs=EPS)
    # the CS-Lite slot follows x_light
    assert cadutil.common_volume(d, csl(q)) < 1e-3
    assert cadutil.common_volume(d, csl(q).translate((-0.01, 0, 0))) > 1e-3
    assert cadutil.common_volume(d, csl(q).translate((0.501, 0, 0))) > 1e-3
    # and it still abuts the gate built for the same wd and axis
    box = gate_model.gate_box(q)
    assert cadutil.common_volume(d, box) < 1e-3
    assert cadutil.common_volume(d.translate((-0.01, 0, 0)), box) > 1e-3
    # the window still sits inside the opening
    hole = probe(q.dock_x0, q.x_light, q.axis - q.rear_win_h / 2, q.axis + q.rear_win_h / 2, -q.rear_win_w / 2, q.rear_win_w / 2)
    assert cadutil.common_volume(d, hole) < EPS


@pytest.mark.parametrize("wd, axis", list(product([100, 130, 150], [39, 42.5, 50])))      # 39: the lowest axis Params allows
def test_a_valid_solid_across_the_range(wd, axis):
    d = model.build(Params(wd=wd, axis=axis))["light_dock"]
    assert cadutil.solid(d).isValid() and cadutil.volume(d) > 0
