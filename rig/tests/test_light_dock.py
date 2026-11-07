"""Light dock: floor, lips and cheeks; and the shroud, its own print, that runs from the gate's rear window to the light.

Everything is measured on the built solid with probes (thin boxes), the way the film gate and lock
switch tests do it. The dock and the shroud are mated against the real gate parts (their front faces
against the gate's rear face, the shroud against the rear window), against each other (the shroud in its
pocket, straddling the front lip) and against a stand-in for the CS-Lite, which is bought, not printed.
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
POCKET = (271, 276, 3, 4, -30.2, 30.2)               # the shroud's seat in the floor, open at the floor's front edge


@pytest.fixture(scope="module")
def dock():
    return model.build(p)["light_dock"]


@pytest.fixture(scope="module")
def shroud():
    return model.build(p)["shroud"]


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


def test_solid_names_and_print_directions():
    assert list(model.build(p)) == ["light_dock", "shroud"]
    assert model.PRINT_UP == {"light_dock": "+y", "shroud": "+x"}


@pytest.mark.parametrize("name", ["light_dock", "shroud"])
@pytest.mark.parametrize("lock", [False, True])
def test_one_valid_closed_solid_each(name, lock):
    built = model.build(p, lock)[name]
    solid = cadutil.solid(built)      # raises unless exactly one
    assert solid.isValid()
    assert all(shell.Closed() for shell in solid.Shells())
    assert solid.Volume() > 0
    assert cadutil.non_manifold_edges(built) == []


@pytest.mark.parametrize("name", ["light_dock", "shroud"])
def test_neither_moves_with_lock(name):
    a, b = model.build(p)[name], model.build(p, lock=True)[name]
    assert cadutil.bounds(a) == cadutil.bounds(b)
    assert cadutil.volume(a) == cadutil.volume(b)


def test_new_params_defaults_and_the_ones_that_were_literals():
    assert (p.floor_t, p.lip_h, p.lip_t, p.cheek_top, p.cheek_clear) == (4, 12, 4, 62, 0.5)
    assert (p.shroud_w, p.shroud_h, p.shroud_t, p.shroud_seat, p.shroud_clear) == (60, 46, 2, 1, 0.2)
    assert (p.dock_extra_w, p.dock_tail, p.csl_clear) == (16, 6, 0.5)
    # the literals Task 1 left inside dock_w and dock_x1, unchanged; the slot is the panel plus csl_clear
    assert p.dock_w == p.csl_l + p.dock_extra_w == 181
    assert p.dock_x1 == p.x_light + p.csl_t + p.csl_clear + p.dock_tail == 306.5
    # reused, not duplicated
    assert (p.csl_l, p.csl_t, p.csl_h, p.rear_win_w, p.rear_win_h) == (165, 20, 112, 46, 34)


# ---- the dock ------------------------------------------------------------------------


def test_dock_bounds_at_defaults(dock):
    # x: the gate's rear face .. 6 past the slot's back edge; y: floor underside .. the cheeks' top; z: +-dock_w/2
    assert cadutil.bounds(dock) == pytest.approx((271, 306.5, 0, 62, -90.5, 90.5), abs=EPS)


def test_floor_is_4_thick_and_181_wide_and_runs_dock_x0_to_dock_x1_but_for_the_pocket(dock):
    floor = cadutil.common_bounds(dock, probe(250, 320, 0, 4, -100, 100))
    assert floor == pytest.approx((271, 306.5, 0, 4, -90.5, 90.5), abs=EPS)
    assert_full(dock, 271, 306.5, 0, 3, -90.5, 90.5)
    assert_full(dock, 276, 306.5, 0, 4, -90.5, 90.5)
    assert_full(dock, 271, 276, 0, 4, 30.2, 90.5)
    assert_full(dock, 271, 276, 0, 4, -90.5, -30.2)


def test_the_pocket_is_1_deep_and_the_shroud_and_0_4_wide_from_the_floors_front_edge_to_the_front_lip(dock):
    assert_void(dock, *POCKET)
    x0, x1, y0, y1, z0, z1 = POCKET
    for grown in ((x0, x1 + 0.001, y0, y1, z0, z1), (x0, x1, y0 - 0.001, y1, z0, z1),
                  (x0, x1, y0, y1, z0 - 0.001, z1), (x0, x1, y0, y1, z0, z1 + 0.001)):
        assert cadutil.common_volume(dock, probe(*grown)) > 1e-5, grown


def test_the_floor_ends_6_past_the_slots_back_edge(dock):
    back_lip_front = cadutil.common_bounds(dock, probe(p.x_light + 1, 320, 4.001, 15, -80, 80))[0]
    assert cadutil.bounds(dock)[1] - back_lip_front == pytest.approx(6, abs=EPS)


def test_front_and_back_lips_are_12_tall_and_full_width(dock):
    front = cadutil.common_bounds(dock, probe(270, 290, 4.001, 100, -CHEEK_IN + 0.001, CHEEK_IN - 0.001))
    assert front == pytest.approx((276, 280, 4.001, 16, -CHEEK_IN + 0.001, CHEEK_IN - 0.001), abs=EPS)
    back = cadutil.common_bounds(dock, probe(290, 330, 4.001, 100, -CHEEK_IN + 0.001, CHEEK_IN - 0.001))
    assert back == pytest.approx((300.5, 304.5, 4.001, 16, -CHEEK_IN + 0.001, CHEEK_IN - 0.001), abs=EPS)
    assert_full(dock, 276, 280, 4, 16, -HW, HW)                    # full width, floor edge to floor edge
    assert_full(dock, 300.5, 304.5, 4, 16, -HW, HW)


def test_nothing_of_the_dock_stands_above_the_lips_between_the_cheeks(dock):
    assert_void(dock, 270, 310, 16.001, 100, -CHEEK_IN + 0.001, CHEEK_IN - 0.001)
    assert_void(dock, 271, 276, 4.001, 100, -CHEEK_IN + 0.001, CHEEK_IN - 0.001)      # in front of the front lip


def test_the_slot_between_the_lips_is_the_cs_lites_20_and_half_a_millimetre(dock):
    assert_void(dock, p.x_light, p.x_light + 20.5, 4.001, 100, -CHEEK_IN + 0.001, CHEEK_IN - 0.001)
    assert cadutil.common_volume(dock, probe(p.x_light - 0.001, p.x_light + 20.5, 4.001, 15, -80, 80)) > 1e-3
    assert cadutil.common_volume(dock, probe(p.x_light, p.x_light + 20.5 + 0.001, 4.001, 15, -80, 80)) > 1e-3
    back = cadutil.common_bounds(dock, probe(p.x_light, 310, 4.001, 15, -80, 80))
    front = cadutil.common_bounds(dock, probe(270, p.x_light, 4.001, 15, -80, 80))
    assert back[0] - front[1] == pytest.approx(20.5, abs=EPS)
    assert front[1] == pytest.approx(p.x_light, abs=EPS)          # the front lip, and so the lit face, has not moved


def test_the_cs_lite_drops_in_against_the_front_lip_with_half_a_millimetre_behind_it(dock):
    light = csl()
    assert cadutil.common_volume(dock, light) < 1e-3
    assert cadutil.common_volume(dock, light.translate((-0.01, 0, 0))) > 1e-3       # on the front lip
    assert cadutil.common_volume(dock, light.translate((0.499, 0, 0))) < 1e-3       # room to drop it in
    assert cadutil.common_volume(dock, light.translate((0.501, 0, 0))) > 1e-3       # then the back lip
    assert cadutil.common_volume(dock, light.translate((0, -0.01, 0))) > 1e-3       # rests on the floor


@pytest.mark.parametrize("sign", [-1, 1])
def test_cheeks_are_62_tall_from_the_cs_lites_end_plus_half_a_millimetre_to_the_floors_edge(dock, sign):
    z0, z1 = sorted((sign * CHEEK_IN, sign * HW))
    above_lips = cadutil.common_bounds(dock, probe(250, 330, 16.001, 100, z0, z1))
    assert above_lips == pytest.approx((276, 304.5, 16.001, 62, z0, z1), abs=EPS)
    assert_full(dock, 276, 304.5, 4, 62, z0, z1)
    assert_void(dock, 250, 330, 62.001, 100, z0, z1)
    assert z1 - z0 == pytest.approx(7.5, abs=EPS)


def test_cheeks_span_the_lips_and_the_slot_in_x(dock):
    assert_full(dock, 276, 304.5, 4, 62, CHEEK_IN, HW)
    assert_void(dock, 271, 275.999, 4.001, 62, CHEEK_IN, HW)
    assert_void(dock, 304.501, 306.5, 4.001, 62, CHEEK_IN, HW)


def test_cheek_inner_faces_are_half_a_millimetre_clear_of_the_cs_lites_ends(dock):
    light = csl()
    for dz in (-0.499, 0.499):
        assert cadutil.common_volume(dock, light.translate((0, 0, dz))) < 1e-3
    for dz in (-0.501, 0.501):
        assert cadutil.common_volume(dock, light.translate((0, 0, dz))) > 1e-3


def test_dock_volume_is_floor_less_pocket_plus_cheeks_plus_lips(dock):
    floor = 35.5 * 4 * 181 - 5 * 1 * 60.4
    cheeks = 2 * (28.5 * 58 * 7.5)
    lips = 2 * (4 * 12 * 166)                            # between the cheeks
    assert cadutil.volume(dock) == pytest.approx(floor + cheeks + lips, rel=1e-9)


# ---- the shroud ----------------------------------------------------------------------


def test_shroud_bounds_runs_from_the_gates_rear_face_to_the_light_face(shroud):
    assert cadutil.bounds(shroud) == pytest.approx((271, 280, 3, 67.5, -30, 30), abs=EPS)
    assert (p.dock_x0, p.x_light, p.axis + 25) == (271, 280, 67.5)
    assert p.axis + 25 > p.cheek_top                     # its top still stands above the cheeks (R9)


def test_shroud_interior_is_56_wide_and_46_tall_on_the_axis(shroud):
    assert_void(shroud, 271, 280, SHROUD_Y0, SHROUD_Y1, -28, 28)
    for lo, hi in ((28, 30), (-30, -28)):
        assert_full(shroud, 271, 280, SHROUD_Y0, SHROUD_Y1, lo, hi)
    assert_full(shroud, 271, 280, SHROUD_Y1, SHROUD_Y1 + 2, -30, 30)
    assert_full(shroud, 271, 275.8, 3, SHROUD_Y0, -30, 30)            # solid below, down into the pocket
    for grown in (
        (271, 280, SHROUD_Y0 - 0.001, SHROUD_Y1, -28, 28),
        (271, 280, SHROUD_Y0, SHROUD_Y1 + 0.001, -28, 28),
        (271, 280, SHROUD_Y0, SHROUD_Y1, -28.001, 28),
        (271, 280, SHROUD_Y0, SHROUD_Y1, -28, 28.001),
    ):
        assert cadutil.common_volume(shroud, probe(*grown)) > 1e-4, grown


def test_shroud_is_open_at_both_ends(shroud):
    assert_void(shroud, 270, 310, SHROUD_Y0 + 0.001, SHROUD_Y1 - 0.001, -28 + 0.001, 28 - 0.001)


def test_shroud_straddles_the_front_lip_with_a_notch_0_2_clear_of_it(shroud):
    # the notch: x 275.8 .. 280, up to the lip's top (16) + 0.2, the shroud's whole width
    assert_void(shroud, 275.8, 280, 3, 16.2, -30, 30)
    assert_full(shroud, 275.8 - 0.02, 275.8 - 0.001, 3, 16.2, -30, 30)
    assert_full(shroud, 275.8, 280, 16.201, SHROUD_Y0, -30, 30)       # over the lip, under the opening


def test_shroud_sits_in_its_pocket_on_the_lip_side_with_0_2_all_round(dock, shroud):
    assert cadutil.common_volume(dock, shroud) < 1e-3
    assert cadutil.common_volume(dock, shroud.translate((0, -0.01, 0))) > 1e-3       # resting on the pocket's floor
    for d in ((0.199, 0, 0), (0, 0, 0.199), (0, 0, -0.199), (0, 0.199, 0)):
        assert cadutil.common_volume(dock, shroud.translate(d)) < 1e-3, d
    for d in ((0.201, 0, 0), (0, 0, 0.201), (0, 0, -0.201)):
        assert cadutil.common_volume(dock, shroud.translate(d)) > 1e-4, d


def test_the_cs_lites_lit_face_closes_the_shroud(shroud):
    light = csl()
    assert cadutil.common_volume(shroud, light) < 1e-3
    assert cadutil.common_volume(shroud, light.translate((-0.01, 0, 0))) > 1e-3


def test_shroud_volume(shroud):
    tunnel = 9 * (60 * 64.5 - 56 * 46)
    notch = 4.2 * 13.2 * 60
    assert cadutil.volume(shroud) == pytest.approx(tunnel - notch, rel=1e-9)


# ---- the gate, the dock and the shroud ----------------------------------------------


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
def test_shroud_interior_surrounds_the_gates_rear_window_with_5_each_side_in_z_and_6_in_y(shroud, gate, side, room):
    body = gate["gate_body"]
    rear_x = (p.x_gate + p.gate_d - p.wall, p.x_gate + p.gate_d)
    window = (p.axis - p.rear_win_h / 2, p.axis + p.rear_win_h / 2, -p.rear_win_w / 2, p.rear_win_w / 2)
    assert cadutil.common_volume(body, probe(*rear_x, *window)) < EPS
    assert cadutil.common_volume(body, probe(*rear_x, *grown(window, side, 0.001))) > 1e-4
    through = (p.dock_x0, p.x_light)
    assert cadutil.common_volume(shroud, probe(*through, *grown(window, side, room - 0.001))) < EPS
    assert cadutil.common_volume(shroud, probe(*through, *grown(window, side, room + 0.001))) > 1e-4


@pytest.mark.parametrize("name", ["light_dock", "shroud"])
def test_touches_the_gates_rear_face_without_overlapping_it(name, gate):
    part, body = model.build(p)[name], gate["gate_body"]
    assert cadutil.bounds(body)[1] == pytest.approx(p.dock_x0, abs=EPS)
    assert cadutil.bounds(part)[0] == pytest.approx(p.dock_x0, abs=EPS)
    assert cadutil.common_volume(part, body) < 1e-3
    assert cadutil.common_volume(part.translate((-0.01, 0, 0)), body) > 1e-3


@pytest.mark.parametrize("lock", [False, True])
def test_neither_touches_the_other_printed_parts(lock, dock, shroud, gate, gate_lock, switch, switch_lock):
    parts = {**(gate_lock if lock else gate), **(switch_lock if lock else switch)}
    for name, other in parts.items():
        for mine in (dock, shroud):
            assert cadutil.common_volume(mine, other) < 1e-3, name
        assert cadutil.bounds(other)[1] <= p.dock_x0 + EPS, name


# ---- printing ------------------------------------------------------------------------


def test_dock_prints_floor_down_and_fits_the_bed(dock):
    posed = cadutil.print_pose(dock, model.PRINT_UP["light_dock"])
    assert cadutil.fits_bed(posed, p)
    assert cadutil.size(posed) == pytest.approx((35.5, 181, 62), abs=EPS)
    assert_full(posed, *(-17.75, 17.75, -90.5, 90.5, 0, 3))


def test_shroud_prints_on_its_gate_end_and_fits_the_bed(shroud):
    posed = cadutil.print_pose(shroud, model.PRINT_UP["shroud"])
    assert cadutil.fits_bed(posed, p)
    assert cadutil.size(posed) == pytest.approx((60, 64.5, 9), abs=EPS)
    # its first layer is the whole face that seals against the gate's rear wall
    sl = cadutil.solid(posed).intersect(cadutil.solid(probe(-100, 100, -100, 100, 0, 0.01)))
    assert sl.Volume() / 0.01 == pytest.approx(60 * 64.5 - 56 * 46, rel=1e-4)


@pytest.mark.parametrize("name", ["light_dock", "shroud"])
def test_nothing_prints_over_air(name):
    # F6: the shroud's top plate was a 56 bridge when it was part of the dock; standing on its end it is a wall
    built = model.build(p)[name]
    assert cadutil.overhangs(cadutil.print_pose(built, model.PRINT_UP[name])) == []


# ---- elsewhere ----------------------------------------------------------------------


@pytest.mark.parametrize("q", [Params(wd=150, axis=50), Params(axis=40), Params(wd=100, axis=45)])
def test_the_dock_and_shroud_follow_wd_and_axis(q):
    built = model.build(q)
    d, s = built["light_dock"], built["shroud"]
    assert cadutil.solid(d).isValid() and cadutil.solid(s).isValid()
    assert cadutil.bounds(d) == pytest.approx((q.dock_x0, q.dock_x1, 0, 62, -q.dock_w / 2, q.dock_w / 2), abs=EPS)
    assert cadutil.bounds(s) == pytest.approx((q.dock_x0, q.x_light, 3, q.axis + 25, -30, 30), abs=EPS)
    assert q.dock_x1 - q.dock_x0 == 35.5
    y0, y1 = q.axis - 23, q.axis + 23
    assert_void(s, q.dock_x0, q.x_light, y0, y1, -28, 28)
    assert_full(s, q.dock_x0, q.x_light, y1, y1 + 2, -30, 30)
    assert cadutil.common_volume(d, s) < 1e-3
    assert cadutil.common_volume(d, csl(q)) < 1e-3
    assert cadutil.common_volume(d, csl(q).translate((-0.01, 0, 0))) > 1e-3
    assert cadutil.common_volume(d, csl(q).translate((0.501, 0, 0))) > 1e-3
    body = gate_model.gate_body(q)
    for part in (d, s):
        assert cadutil.common_volume(part, body) < 1e-3
        assert cadutil.common_volume(part.translate((-0.01, 0, 0)), body) > 1e-3
    hole = probe(q.dock_x0, q.x_light, q.axis - q.rear_win_h / 2, q.axis + q.rear_win_h / 2, -q.rear_win_w / 2, q.rear_win_w / 2)
    assert cadutil.common_volume(s, hole) < EPS


@pytest.mark.parametrize("wd, axis", list(product([100, 130, 150], [39, 42.5, 50])))      # 39: the lowest axis Params allows
def test_valid_solids_across_the_range(wd, axis):
    q = Params(wd=wd, axis=axis)
    built = model.build(q)
    for name, wp in built.items():
        assert cadutil.is_valid(wp) and cadutil.volume(wp) > 0, name
    assert cadutil.common_volume(built["light_dock"], built["shroud"]) < 1e-3
