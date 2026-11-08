"""Light dock: floor, front wall, lips and cheeks, the film gate inset between the front wall and the CS-Lite (F10, F11).

Everything is measured on the built solid with probes (thin boxes), the way the film gate and lock
switch tests do it. The dock is mated against the real gate parts (the gate body standing in its notch,
flush on the panel) and against a stand-in for the CS-Lite, which is bought, not printed.
"""

import math
from itertools import product

import cadquery as cq
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
X0 = 236.8                                          # the front wall's front face: x_gate (241) - 0.2 - 4
NX = 240.8                                          # its rear face, where the notch starts: 0.2 in front of the gate front
U_R = 37                                            # the tube's U: its 36 plus 1
NOTCH = 55.2                                        # the notch's sides: the gate front's 110, plus 0.2 each side


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


def test_one_solid_and_its_print_direction():
    assert list(model.build(p)) == ["light_dock"]
    assert model.PRINT_UP == {"light_dock": "+y"}


@pytest.mark.parametrize("lock", [False, True])
def test_one_valid_closed_solid(lock):
    built = model.build(p, lock)["light_dock"]
    solid = cadutil.solid(built)      # raises unless exactly one
    assert solid.isValid()
    assert all(shell.Closed() for shell in solid.Shells())
    assert solid.Volume() > 0
    assert cadutil.non_manifold_edges(built) == []


def test_it_does_not_move_with_lock():
    a, b = model.build(p)["light_dock"], model.build(p, lock=True)["light_dock"]
    assert cadutil.bounds(a) == cadutil.bounds(b)
    assert cadutil.volume(a) == cadutil.volume(b)


def test_params_defaults():
    assert (p.floor_t, p.lip_h, p.lip_t, p.cheek_top, p.cheek_clear, p.dock_gate_clear) == (4, 12, 4, 62, 0.5, 0.2)
    assert (p.dock_extra_w, p.dock_tail, p.csl_clear) == (16, 6, 0.5)
    assert p.dock_w == p.csl_l + p.dock_extra_w == 181
    assert p.dock_x1 == p.x_light + p.csl_t + p.csl_clear + p.dock_tail == 306.5
    assert (p.dock_front_t, p.dock_tube_clear) == (4, 1)
    assert p.dock_x0 == pytest.approx(p.x_gate - p.dock_gate_clear - p.dock_front_t) == X0
    assert p.gate_d == p.gate_front + p.gap == 39             # the gate reaches the lit face (F10)
    assert not hasattr(p, "shroud_w")


# ---- the dock ------------------------------------------------------------------------


def test_dock_bounds_at_defaults(dock):
    # x: the front wall's front face .. 6 past the slot's back edge; y: floor underside .. the cheeks' top
    assert cadutil.bounds(dock) == pytest.approx((X0, 306.5, 0, 62, -90.5, 90.5), abs=EPS)


def test_floor_is_4_thick_and_181_wide_with_the_gate_notch_cut_from_its_front_edge(dock):
    floor = cadutil.common_bounds(dock, probe(220, 320, 0, 4, -100, 100))
    assert floor == pytest.approx((X0, 306.5, 0, 4, -90.5, 90.5), abs=EPS)
    assert_full(dock, p.x_light, 306.5, 0, 4, -90.5, 90.5)              # behind the lit face, full width
    assert_full(dock, X0, p.x_light, 0, 4, NOTCH, 90.5)                 # the two arms beside the gate
    assert_full(dock, X0, p.x_light, 0, 4, -90.5, -NOTCH)


def test_the_gate_notch_runs_from_the_front_wall_to_the_lit_face_through_floor_and_front_lip(dock):
    assert_void(dock, NX, p.x_light, 0, 100, -NOTCH, NOTCH)
    for grown in ((NX - 0.001, p.x_light, 0, 4, -NOTCH, NOTCH), (NX, p.x_light + 0.001, 0, 4, -NOTCH, NOTCH),
                  (NX, p.x_light, 0, 4, -NOTCH - 0.001, NOTCH), (NX, p.x_light, 0, 4, -NOTCH, NOTCH + 0.001)):
        assert cadutil.common_volume(dock, probe(*grown)) > 1e-6, grown


def test_the_floor_ends_6_past_the_slots_back_edge(dock):
    back_lip_front = cadutil.common_bounds(dock, probe(p.x_light + 1, 320, 4.001, 15, -80, 80))[0]
    assert cadutil.bounds(dock)[1] - back_lip_front == pytest.approx(6, abs=EPS)


def test_lips_are_12_tall_the_back_one_full_width_the_front_one_beside_the_notch(dock):
    back = cadutil.common_bounds(dock, probe(290, 330, 4.001, 100, -CHEEK_IN + 0.001, CHEEK_IN - 0.001))
    assert back == pytest.approx((300.5, 304.5, 4.001, 16, -CHEEK_IN + 0.001, CHEEK_IN - 0.001), abs=EPS)
    assert_full(dock, 300.5, 304.5, 4, 16, -HW, HW)
    for z in ((NOTCH, CHEEK_IN), (-CHEEK_IN, -NOTCH)):
        front = cadutil.common_bounds(dock, probe(NX, p.x_light, 4.001, 100, *z))
        assert front == pytest.approx((276, 280, 4.001, 16, *z), abs=EPS)


def test_nothing_of_the_dock_stands_above_the_lips_between_the_cheeks(dock):
    assert_void(dock, NX, 310, 16.001, 100, -CHEEK_IN + 0.001, CHEEK_IN - 0.001)
    assert_void(dock, NX, 276, 4.001, 100, -HW, HW)                    # the arms are floor only


def test_the_slot_between_the_lips_is_the_cs_lites_20_and_half_a_millimetre(dock):
    assert_void(dock, p.x_light, p.x_light + 20.5, 4.001, 100, -CHEEK_IN + 0.001, CHEEK_IN - 0.001)
    back = cadutil.common_bounds(dock, probe(p.x_light, 310, 4.001, 15, -80, 80))
    front = cadutil.common_bounds(dock, probe(240, p.x_light, 4.001, 15, -80, 80))
    assert back[0] - front[1] == pytest.approx(20.5, abs=EPS)
    assert front[1] == pytest.approx(p.x_light, abs=EPS)          # the front lip, and so the lit face, has not moved


def test_the_cs_lite_drops_in_against_the_front_lip_with_half_a_millimetre_behind_it(dock):
    light = csl()
    assert cadutil.common_volume(dock, light) < 1e-3
    assert cadutil.common_volume(dock, light.translate((-0.01, 0, 0))) > 1e-3       # on what is left of the front lip
    assert cadutil.common_volume(dock, light.translate((0.499, 0, 0))) < 1e-3       # room to drop it in
    assert cadutil.common_volume(dock, light.translate((0.501, 0, 0))) > 1e-3       # then the back lip
    assert cadutil.common_volume(dock, light.translate((0, -0.01, 0))) > 1e-3       # rests on the floor


@pytest.mark.parametrize("sign", [-1, 1])
def test_cheeks_are_62_tall_from_the_cs_lites_end_plus_half_a_millimetre_to_the_floors_edge(dock, sign):
    z0, z1 = sorted((sign * CHEEK_IN, sign * HW))
    above_lips = cadutil.common_bounds(dock, probe(NX, 330, 16.001, 100, z0, z1))
    assert above_lips == pytest.approx((276, 304.5, 16.001, 62, z0, z1), abs=EPS)
    assert_full(dock, 276, 304.5, 4, 62, z0, z1)
    assert_void(dock, 220, 330, 62.001, 100, z0, z1)
    assert z1 - z0 == pytest.approx(7.5, abs=EPS)


def test_cheeks_span_the_lips_and_the_slot_in_x(dock):
    assert_full(dock, 276, 304.5, 4, 62, CHEEK_IN, HW)
    assert_void(dock, NX, 275.999, 4.001, 62, CHEEK_IN, HW)
    assert_void(dock, 304.501, 306.5, 4.001, 62, CHEEK_IN, HW)


def test_cheek_inner_faces_are_half_a_millimetre_clear_of_the_cs_lites_ends(dock):
    light = csl()
    for dz in (-0.499, 0.499):
        assert cadutil.common_volume(dock, light.translate((0, 0, dz))) < 1e-3
    for dz in (-0.501, 0.501):
        assert cadutil.common_volume(dock, light.translate((0, 0, dz))) > 1e-3


def test_dock_volume_is_floor_plus_front_wall_plus_cheeks_plus_lips_less_the_notch(dock):
    floor = 69.7 * 4 * 181 - 39.2 * 4 * 110.4
    front = 4 * (58 * 181 - (math.pi * U_R**2 / 2 + 2 * U_R * (62 - p.axis)))     # above the floor, less the U
    cheeks = 2 * (28.5 * 58 * 7.5)
    lips = 4 * 12 * 166 + 4 * 12 * (166 - 110.4)           # between the cheeks; the front one less the notch
    assert cadutil.volume(dock) == pytest.approx(floor + front + cheeks + lips, rel=1e-6)


# ---- the front wall ------------------------------------------------------------------


def test_front_wall_is_4_thick_full_width_and_62_tall_beside_the_tube(dock):
    for z in ((U_R, HW), (-HW, -U_R)):
        assert_full(dock, X0, NX, 0, 62, *z)
        assert_void(dock, X0 - 10, X0, 0, 100, *z)                         # nothing in front of it
        assert_void(dock, NX, NX + 10, 4.001, 100, *z)                     # the gate front stands right behind it
    assert_full(dock, X0, NX, 0, p.axis - U_R, -U_R, U_R)                  # under the tube


def test_front_wall_has_a_u_for_the_tube_1_clear_of_it(dock):
    u = (cq.Workplane("YZ", origin=(X0, 0, 0)).center(p.axis, 0).circle(U_R).extrude(4)
         .union(probe(X0, NX, p.axis, 100, -U_R, U_R)))
    assert cadutil.common_volume(dock, u) < 1e-3
    # 0.01 bigger all round and it takes material: the U is exactly 37 around the axis, open at the top
    assert cadutil.common_volume(dock, probe(X0, NX, p.axis - U_R - 0.01, p.axis, -1, 1)) > 1e-4
    assert cadutil.common_volume(dock, probe(X0, NX, p.axis, 62, U_R, U_R + 0.01)) > 1e-4
    assert_void(dock, X0, NX, p.axis, 100, -U_R + 0.001, U_R - 0.001)


def test_the_gate_is_held_between_the_front_wall_and_the_cs_lite_with_0_2_play(dock, gate):
    front, body = gate["gate_front"], gate["gate_body"]
    assert cadutil.bounds(front)[0] - cadutil.bounds(dock)[0] == pytest.approx(4.2, abs=EPS)
    for part in (front, body):
        assert cadutil.common_volume(dock, part) < 1e-3
        assert cadutil.common_volume(dock, part.translate((-0.199, 0, 0))) < 1e-3
    assert cadutil.common_volume(dock, front.translate((-0.201, 0, 0))) > 1e-4      # then the front wall stops it
    assert cadutil.common_volume(body, csl()) < 1e-3
    assert cadutil.common_volume(body.translate((0.01, 0, 0)), csl()) > 1e-3        # the panel stops it at the back


# ---- the gate in the dock ------------------------------------------------------------


def test_the_gate_bodys_rear_face_is_the_lit_face(gate):
    body = gate["gate_body"]
    assert cadutil.bounds(body)[1] == pytest.approx(p.x_light, abs=EPS)
    light = csl()
    assert cadutil.common_volume(body, light) < 1e-3
    assert cadutil.common_volume(body.translate((0.01, 0, 0)), light) > 1e-3        # flush: touching


def test_the_cs_lite_covers_the_rear_window(gate):
    # the panel's face closes the window all round, with its lit area over it (149 x 95, centred on the panel)
    rear_x = (p.x_light - p.wall, p.x_light)
    window = (p.axis - p.rear_win_h / 2, p.axis + p.rear_win_h / 2, -p.rear_win_w / 2, p.rear_win_w / 2)
    assert cadutil.common_volume(gate["gate_body"], probe(*rear_x, *window)) < EPS
    lit_y = (p.floor_t + (p.csl_h - p.csl_lit_h) / 2, p.floor_t + (p.csl_h + p.csl_lit_h) / 2)
    assert lit_y[0] < window[0] and window[1] < lit_y[1]
    assert -p.csl_lit_w / 2 < window[2] and window[3] < p.csl_lit_w / 2


def test_the_gate_body_stands_in_the_notch_0_2_clear_each_side(dock, gate):
    body = gate["gate_body"]
    assert cadutil.common_volume(dock, body) < 1e-3
    for dz in (-0.199, 0.199):
        assert cadutil.common_volume(dock, body.translate((0, 0, dz))) < 1e-3, dz
    for dz in (-0.201, 0.201):
        assert cadutil.common_volume(dock, body.translate((0, 0, dz))) > 1e-4, dz
    assert cadutil.bounds(body)[2] == pytest.approx(0, abs=EPS)                     # it stands on the table


@pytest.mark.parametrize("lock", [False, True])
def test_it_touches_none_of_the_other_printed_parts(lock, dock, gate, gate_lock, switch, switch_lock):
    parts = {**(gate_lock if lock else gate), **(switch_lock if lock else switch)}
    for name, other in parts.items():
        assert cadutil.common_volume(dock, other) < 1e-3, name


# ---- printing ------------------------------------------------------------------------


def test_dock_prints_floor_down_and_fits_the_bed(dock):
    posed = cadutil.print_pose(dock, model.PRINT_UP["light_dock"])
    assert cadutil.fits_bed(posed, p)
    assert cadutil.size(posed) == pytest.approx((69.7, 181, 62), abs=EPS)
    assert_full(posed, *(-34.85, 34.85, 55.2, 90.5, 0, 3))


def test_nothing_prints_over_air(dock):
    assert cadutil.overhangs(cadutil.print_pose(dock, model.PRINT_UP["light_dock"])) == []


# ---- elsewhere ----------------------------------------------------------------------


@pytest.mark.parametrize("q", [Params(wd=150, axis=50), Params(axis=40), Params(wd=100, axis=45)])
def test_the_dock_and_gate_follow_wd_and_axis(q):
    d = model.build(q)["light_dock"]
    assert cadutil.solid(d).isValid()
    assert cadutil.bounds(d) == pytest.approx((q.x_gate - 4.2, q.dock_x1, 0, 62, -q.dock_w / 2, q.dock_w / 2), abs=EPS)
    assert q.dock_x1 - q.dock_x0 == pytest.approx(69.7, abs=EPS)
    assert cadutil.common_volume(d, gate_model.gate_front(q)) < 1e-3
    assert cadutil.common_volume(d, csl(q)) < 1e-3
    assert cadutil.common_volume(d, csl(q).translate((-0.01, 0, 0))) > 1e-3
    assert cadutil.common_volume(d, csl(q).translate((0.501, 0, 0))) > 1e-3
    body = gate_model.gate_body(q)
    assert cadutil.bounds(body)[1] == pytest.approx(q.x_light, abs=EPS)
    assert cadutil.common_volume(d, body) < 1e-3
    assert cadutil.common_volume(body, csl(q)) < 1e-3
    assert cadutil.common_volume(body.translate((0.01, 0, 0)), csl(q)) > 1e-3


@pytest.mark.parametrize("wd, axis", list(product([100, 130, 150], [39, 42.5, 50])))      # 39: the lowest axis Params allows
def test_valid_solids_across_the_range(wd, axis):
    q = Params(wd=wd, axis=axis)
    d = model.build(q)["light_dock"]
    assert cadutil.is_valid(d) and cadutil.volume(d) > 0
    assert cadutil.common_volume(d, gate_model.gate_body(q)) < 1e-3
