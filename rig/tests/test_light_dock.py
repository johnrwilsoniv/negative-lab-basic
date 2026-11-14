"""Light dock: floor, lips and cheeks, the film gate inset against the CS-Lite (F10), the spools' stands (D5).

Everything is measured on the built solid with probes (thin boxes), the way the film gate tests do it. The dock
is mated against the real gate and spool parts (the gate body standing in its notch, flush on the panel; the
spools on their pins) and against a stand-in for the CS-Lite, which is bought, not printed.
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
from parts.film_drive import model as drive_model
from parts.spools import model as spool_model
from parts.tube import model as tube_model

p = DEFAULT
EPS = 1e-6
HW = p.dock_w / 2                                   # 95.5
CHEEK_IN = p.csl_l / 2 + 0.5                        # 83: cheek inner faces
X0 = p.dock_x0                                      # the floor's front edge: 4 in front of the spools' flanges
NX = 216.8                                          # where the notch starts: 0.2 in front of the gate front
NOTCH = 46.2                                        # the notch's sides: the gate's 92, plus 0.2 each side
SX = p.x_spool + p.pedestal_r + 0.01                # behind the spools' stands


@pytest.fixture(scope="module")
def dock():
    return model.build(p)["light_dock"]


@pytest.fixture(scope="module")
def gate():
    return gate_model.build(p)


@pytest.fixture(scope="module")
def others():
    """Every other printed part that stands near the dock: the gate, the drive, the spools."""
    return {**gate_model.build(p), **drive_model.build(p), **spool_model.build(p)}


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


@pytest.mark.parametrize("turn", [0.0, 0.3])
def test_one_valid_closed_solid(turn):
    built = model.build(p, turn)["light_dock"]
    solid = cadutil.solid(built)      # raises unless exactly one
    assert solid.isValid()
    assert all(shell.Closed() for shell in solid.Shells())
    assert solid.Volume() > 0
    assert cadutil.non_manifold_edges(built) == []


def test_it_does_not_move_with_the_knob():
    a, b = model.build(p)["light_dock"], model.build(p, 0.3)["light_dock"]
    assert cadutil.bounds(a) == cadutil.bounds(b)
    assert cadutil.volume(a) == cadutil.volume(b)


def test_params_defaults():
    assert (p.floor_t, p.lip_h, p.lip_t, p.cheek_top, p.cheek_clear, p.dock_gate_clear) == (4, 12, 4, 62, 0.5, 0.2)
    assert p.dock_tube_clear == 1                             # the floor's trough under the tube (F17)
    assert (p.dock_extra_w, p.dock_tail, p.csl_clear, p.dock_margin) == (26, 6, 0.5, 4)
    assert p.dock_w == p.csl_l + p.dock_extra_w == 191
    assert p.dock_x1 == p.x_light + p.csl_t + p.csl_clear + p.dock_tail == 292.5
    assert p.dock_x0 == pytest.approx(p.x_spool - p.spool_flange_r - 4)
    assert p.gate_d == p.gate_front + p.gap == 49             # the gate reaches the lit face (F10)
    assert not hasattr(p, "dock_front_t")                     # no front wall (D5): the spools stand there


# ---- the dock ------------------------------------------------------------------------


def test_dock_bounds_at_defaults(dock):
    # x: in front of the spools .. 6 past the slot's back edge; y: floor underside .. the cheeks' top
    assert cadutil.bounds(dock) == pytest.approx((X0, 292.5, 0, 62, -HW, HW), abs=EPS)


def test_floor_is_4_thick_and_191_wide_with_the_gate_notch_cut_into_it(dock):
    floor = cadutil.common_bounds(dock, probe(X0 - 10, 320, 0, 4, -100, 100))
    assert floor == pytest.approx((X0, 292.5, 0, 4, -HW, HW), abs=EPS)
    assert_full(dock, p.x_light, 292.5, 0, 4, -HW, HW)                  # behind the lit face, full width
    assert_full(dock, X0, NX, 0, 4, -HW, HW)                            # in front of the gate, full width
    assert_full(dock, X0, p.x_light, 0, 4, NOTCH, HW)                   # the two arms beside the gate
    assert_full(dock, X0, p.x_light, 0, 4, -HW, -NOTCH)


def test_the_gate_notch_runs_from_the_gate_front_to_the_lit_face_through_floor_and_front_lip(dock):
    assert_void(dock, NX, p.x_light, 0, 100, -NOTCH, NOTCH)
    for grown in ((NX - 0.001, p.x_light, 0, 4, -NOTCH, NOTCH), (NX, p.x_light + 0.001, 0, 4, -NOTCH, NOTCH),
                  (NX, p.x_light, 0, 4, -NOTCH - 0.001, NOTCH), (NX, p.x_light, 0, 4, -NOTCH, NOTCH + 0.001)):
        assert cadutil.common_volume(dock, probe(*grown)) > 1e-6, grown


def test_the_floor_ends_6_past_the_slots_back_edge(dock):
    back_lip_front = cadutil.common_bounds(dock, probe(p.x_light + 1, 320, 4.001, 15, -80, 80))[0]
    assert cadutil.bounds(dock)[1] - back_lip_front == pytest.approx(6, abs=EPS)


def test_lips_are_12_tall_the_back_one_full_width_the_front_one_beside_the_notch(dock):
    back = cadutil.common_bounds(dock, probe(276, 330, 4.001, 100, -CHEEK_IN + 0.001, CHEEK_IN - 0.001))
    assert back == pytest.approx((286.5, 290.5, 4.001, 16, -CHEEK_IN + 0.001, CHEEK_IN - 0.001), abs=EPS)
    assert_full(dock, 286.5, 290.5, 4, 16, -HW, HW)
    for z in ((NOTCH, CHEEK_IN), (-CHEEK_IN, -NOTCH)):
        front = cadutil.common_bounds(dock, probe(SX, p.x_light, 4.001, 100, *z))
        assert front == pytest.approx((262, 266, 4.001, 16, *z), abs=EPS)


def test_nothing_of_the_dock_stands_above_the_lips_between_the_cheeks(dock):
    assert_void(dock, SX, 310, 16.001, 100, -CHEEK_IN + 0.001, CHEEK_IN - 0.001)
    assert_void(dock, SX, 262, 4.001, 100, -HW, HW)                    # the arms are floor only


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
    assert above_lips == pytest.approx((262, 290.5, 16.001, 62, z0, z1), abs=EPS)
    assert_full(dock, 262, 290.5, 4, 62, z0, z1)
    assert_void(dock, 220, 330, 62.001, 100, z0, z1)
    assert z1 - z0 == pytest.approx(12.5, abs=EPS)


def test_cheeks_span_the_lips_and_the_slot_in_x(dock):
    assert_full(dock, 262, 290.5, 4, 62, CHEEK_IN, HW)
    assert_void(dock, NX, 261.999, 4.001, 62, CHEEK_IN, HW)
    assert_void(dock, 290.501, 292.5, 4.001, 62, CHEEK_IN, HW)


def test_cheek_inner_faces_are_half_a_millimetre_clear_of_the_cs_lites_ends(dock):
    light = csl()
    for dz in (-0.499, 0.499):
        assert cadutil.common_volume(dock, light.translate((0, 0, dz))) < 1e-3
    for dz in (-0.501, 0.501):
        assert cadutil.common_volume(dock, light.translate((0, 0, dz))) > 1e-3


def test_dock_volume_is_floor_plus_cheeks_plus_lips_less_the_notch_plus_the_stands(dock):
    length = 292.5 - X0
    floor = length * 4 * 191 - 49.2 * 4 * 92.4
    cheeks = 2 * (28.5 * 58 * 12.5)
    lips = 4 * 12 * 166 + 4 * 12 * (166 - 92.4)            # between the cheeks; the front one less the notch
    stands = sum(cadutil.volume(s) for s in model._spool_stands(p)) - 2 * math.pi * p.pedestal_r ** 2 * 0.01  # sunk in
    assert cadutil.volume(dock) == pytest.approx(floor + cheeks + lips + stands, rel=1e-6)


# ---- the spools' stands --------------------------------------------------------------


@pytest.mark.parametrize("sign", [-1, 1])
def test_each_spool_stands_on_a_pedestal_and_turns_on_a_pin(dock, sign):
    x, z = p.x_spool, sign * p.spool_z
    pr = p.pedestal_r / math.sqrt(2) - 0.01
    assert_full(dock, x - pr, x + pr, 4, p.y_pedestal, z - pr, z + pr)
    pin = p.spool_pin_d / 2 / math.sqrt(2) - 0.01
    top = model.pin_top(p)
    assert_full(dock, x - pin, x + pin, p.y_pedestal, top - model.PIN_CHAMFER, z - pin, z + pin)
    assert_void(dock, x - 5, x + 5, top, 100, z - 5, z + 5)
    assert_void(dock, x + p.spool_pin_d / 2 + 0.01, x + 7, p.y_pedestal + 0.01, 100, z - 0.5, z + 0.5)
    assert top < p.y_spool + p.spool_core_h - p.cap_spigot_h      # under the cap's spigot


def test_the_spools_sit_on_their_pedestals_and_clear_everything(dock, others):
    for side in ("supply", "takeup"):
        spool = others[f"spool_{side}"]
        assert cadutil.common_volume(dock, spool) < 1e-3, side
        assert cadutil.common_volume(dock, spool.translate((0, -0.01, 0))) > 1e-4, side     # standing on it
        assert cadutil.bounds(spool)[2] == pytest.approx(p.y_pedestal)


# ---- the tube over the floor ---------------------------------------------------------


@pytest.mark.parametrize("axis", [39, 40.5, 42.5, 50])
def test_the_tube_is_1_clear_of_the_dock_at_every_axis(axis):
    """A trough along the tube is cut from the floor in front of the gate (F17: on main it is the round of the front
    wall's U), so the floor never comes within 1 of the tube. With the Ø68.5 tube (F23) it dips 0.25 into the floor's
    top at axis 39, the lowest allowed, and nowhere else."""
    q = Params(wd=p.wd, axis=axis)
    d = model.build(q)["light_dock"]
    x0, x1 = q.dock_x0, q.x_gate - q.dock_gate_clear
    r = q.tube_ro + q.dock_tube_clear
    clear = cq.Workplane("YZ", origin=(x0, 0, 0)).center(q.axis, 0).circle(r).extrude(x1 - x0)
    assert cadutil.common_volume(d, clear) < 1e-3
    assert cadutil.common_volume(d, tube_model.build(q)["tube"]) < 1e-3
    # under the tube the floor is full up to the trough's bottom, or to its own top where the trough is above it,
    # and void from there up: nothing else of the dock stands under the tube
    under = min(q.floor_t, q.axis - r)
    assert (under < q.floor_t) == (axis < 39.25)
    assert_full(d, x0, x1, 0, under - 0.001, -1, 1)
    assert_void(d, x0, x1, under + 0.02, q.axis, -1, 1)       # 0.02: the trough is round, 0.014 higher at z = +-1
    # the trough is no wider than the tube's clearance: beside it the floor is whole, and it takes 23.7 mm3 at axis 39
    assert_full(d, x0, x1, 0, q.floor_t, r, q.dock_w / 2 - 30)
    under_tube = probe(x0, x1, 0, q.floor_t, -r, r)
    cut = cadutil.volume(under_tube) - cadutil.common_volume(d, under_tube)
    assert cut == pytest.approx(23.7 if axis < 39.25 else 0, abs=0.05)
    # the spools' stands are whole
    pr = q.pedestal_r / math.sqrt(2) - 0.01
    for z in (-q.spool_z, q.spool_z):
        assert_full(d, q.x_spool - pr, q.x_spool + pr, q.floor_t, q.y_pedestal, z - pr, z + pr)


# ---- the gate in the dock ------------------------------------------------------------


def test_the_gate_sits_between_the_notchs_front_edge_and_the_cs_lite_with_0_2_play(dock, gate):
    front, body = gate["gate_front"], gate["gate_body"]
    for part in (front, body):
        assert cadutil.common_volume(dock, part) < 1e-3
        assert cadutil.common_volume(dock, part.translate((-0.199, 0, 0))) < 1e-3
    assert cadutil.common_volume(dock, front.translate((-0.201, 0, 0))) > 1e-4      # then the floor's edge stops it
    assert cadutil.common_volume(body, csl()) < 1e-3
    assert cadutil.common_volume(body.translate((0.01, 0, 0)), csl()) > 1e-3        # the panel stops it at the back



def test_the_gate_bodys_rear_face_is_the_lit_face(gate):
    body = gate["gate_body"]
    assert cadutil.bounds(body)[1] == pytest.approx(p.x_light, abs=EPS)
    light = csl()
    assert cadutil.common_volume(body, light) < 1e-3
    assert cadutil.common_volume(body.translate((0.01, 0, 0)), light) > 1e-3        # flush: touching


def test_the_cs_lite_covers_the_rear_window(gate):
    # the panel's face closes the window all round, with its lit area over it (149 x 95, centred on the panel)
    rear_x = (p.x_light - 0.01, p.x_light)          # the rear face, where the passage is widest
    window = (p.axis - p.rear_win_h / 2 + 0.05, p.axis + p.rear_win_h / 2 - 0.05, -p.rear_win_w / 2 + 0.05,
              p.rear_win_w / 2 - 0.05)
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


def test_it_touches_none_of_the_other_printed_parts(dock, others):
    for name, other in others.items():
        assert cadutil.common_volume(dock, other) < 1e-3, name


# ---- printing ------------------------------------------------------------------------


def test_dock_prints_floor_down_and_fits_the_bed(dock):
    posed = cadutil.print_pose(dock, model.PRINT_UP["light_dock"])
    assert cadutil.fits_bed(posed, p)
    assert cadutil.size(posed) == pytest.approx((292.5 - X0, 191, 62), abs=EPS)


def test_nothing_prints_over_air(dock):
    assert cadutil.overhangs(cadutil.print_pose(dock, model.PRINT_UP["light_dock"])) == []


# ---- elsewhere ----------------------------------------------------------------------


@pytest.mark.parametrize("q", [Params(wd=150, axis=50), Params(axis=40), Params(wd=100, axis=45)])
def test_the_dock_and_gate_follow_wd_and_axis(q):
    d = model.build(q)["light_dock"]
    assert cadutil.solid(d).isValid()
    top = max(q.cheek_top, model.pin_top(q))       # the spools' pins rise with the axis, past the cheeks at 50
    assert cadutil.bounds(d) == pytest.approx((q.dock_x0, q.dock_x1, 0, top, -q.dock_w / 2, q.dock_w / 2), abs=EPS)
    assert q.dock_x1 - q.dock_x0 == pytest.approx(292.5 - X0, abs=EPS)
    assert cadutil.common_volume(d, gate_model.gate_front(q)) < 1e-3
    assert cadutil.common_volume(d, csl(q)) < 1e-3
    assert cadutil.common_volume(d, csl(q).translate((-0.01, 0, 0))) > 1e-3
    assert cadutil.common_volume(d, csl(q).translate((0.501, 0, 0))) > 1e-3
    body = gate_model.gate_body(q)
    assert cadutil.bounds(body)[1] == pytest.approx(q.x_light, abs=EPS)
    assert cadutil.common_volume(d, body) < 1e-3
    assert cadutil.common_volume(body, csl(q)) < 1e-3
    assert cadutil.common_volume(body.translate((0.01, 0, 0)), csl(q)) > 1e-3


@pytest.mark.parametrize("wd, axis", list(product([100, 116, 130, 150], [39, 40.5, 42.5, 50])))      # 39: the lowest axis Params allows
def test_valid_solids_across_the_range(wd, axis):
    q = Params(wd=wd, axis=axis)
    d = model.build(q)["light_dock"]
    assert cadutil.is_valid(d) and cadutil.volume(d) > 0
    assert cadutil.common_volume(d, gate_model.gate_body(q)) < 1e-3
