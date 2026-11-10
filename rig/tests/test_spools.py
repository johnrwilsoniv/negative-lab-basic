"""Spools: the supply and take-up spools and their caps (D5), probed on the built solids."""

import math

import pytest

import cadutil
from cadutil import probe
from params import DEFAULT, Params
from parts.spools import model

p = DEFAULT
EPS = 1e-6
T = 0.02
NAMES = ["spool_supply", "cap_supply", "spool_takeup", "cap_takeup"]


@pytest.fixture(scope="module")
def built():
    return model.build(p)


def filled(wp, *ranges):
    pr = probe(*ranges)
    return cadutil.common_volume(wp, pr) / cadutil.volume(pr)


def test_the_solids_and_their_print_directions(built):
    assert list(built) == NAMES
    assert model.PRINT_UP == {"spool_supply": "+y", "spool_takeup": "+y", "cap_supply": "-y", "cap_takeup": "-y"}


@pytest.mark.parametrize("q", [p, Params(wd=150, axis=50)], ids=["defaults", "other"])
def test_each_is_one_valid_solid_that_prints_with_no_overhangs(q):
    for name, wp in model.build(q).items():
        assert cadutil.is_valid(wp) and cadutil.volume(wp) > 0, name
        assert cadutil.overhangs(cadutil.print_pose(wp, model.PRINT_UP[name])) == [], name


def test_the_knob_does_not_turn_the_spools(built):
    turned = model.build(p, 0.4)
    for name in NAMES:
        assert cadutil.bounds(turned[name]) == pytest.approx(cadutil.bounds(built[name])), name


@pytest.mark.parametrize("side, sign", [("supply", -1), ("takeup", 1)])
def test_each_spool_stands_beside_the_gate_its_flanges_either_side_of_the_film(built, side, sign):
    x0, x1, y0, y1, z0, z1 = cadutil.bounds(built[f"spool_{side}"])
    assert ((x0 + x1) / 2, (z0 + z1) / 2) == pytest.approx((p.x_spool, sign * p.spool_z), abs=EPS)
    assert (x1 - x0) / 2 == pytest.approx(p.spool_flange_r)
    assert (y0, y1) == pytest.approx((p.y_pedestal, p.y_spool + p.spool_core_h))
    assert min(abs(z0), abs(z1)) > p.gw / 2 + 2.9             # its flange 3 clear of the gate's side
    _, _, c0, c1, _, _ = cadutil.bounds(built[f"cap_{side}"])
    assert c1 == pytest.approx(p.y_spool + p.spool_core_h + p.cap_t)
    # between the bottom flange and the cap: the film, 0.5 clear at each edge
    assert p.y_spool == pytest.approx(p.axis - p.film_w / 2 - 0.5)
    assert p.y_spool + p.spool_core_h == pytest.approx(p.axis + p.film_w / 2 + 0.5)


def test_the_core_has_a_bore_a_socket_and_a_slit(built):
    sp, x, z = built["spool_supply"], p.x_spool, -p.spool_z
    y_mid = p.axis
    rb = (p.spool_pin_d / 2 + p.bearing_clear) / math.sqrt(2) - T
    assert filled(sp, x - rb, x + rb, p.y_pedestal, p.y_spool + p.spool_core_h, z - rb, z + rb) < EPS
    top = p.y_spool + p.spool_core_h
    rs = p.cap_spigot_r / math.sqrt(2) - T
    assert filled(sp, x - rs, x + rs, top - p.cap_spigot_h + T, top, z - rs, z + rs) < EPS
    # the slit, on the side away from the film, open for the whole height of the core
    w = p.spool_slit_w / 2 - T
    assert filled(sp, x - p.spool_core_r, x - p.spool_core_r + p.spool_slit_depth - T, p.y_spool, top, z - w, z + w) < EPS
    assert filled(sp, x - p.spool_core_r + 1, x - p.spool_core_r + 2, y_mid - 1, y_mid + 1, z + 1, z + 2) > 1 - EPS
    assert p.spool_core_r - p.spool_slit_depth > p.cap_spigot_r      # the slit stops short of the socket


def test_the_cap_presses_its_spigot_into_the_socket(built):
    common = cadutil.common_volume(built["spool_supply"], built["cap_supply"])
    assert common < 1e-6
    _, _, y0, _, _, _ = cadutil.bounds(built["cap_supply"])
    assert y0 == pytest.approx(p.y_spool + p.spool_core_h - p.cap_spigot_h)


def test_the_cap_is_scalloped_for_a_grip(built):
    cap = built["cap_supply"]
    full = math.pi * p.spool_flange_r ** 2 * p.cap_t + math.pi * p.cap_spigot_r ** 2 * p.cap_spigot_h
    assert cadutil.volume(cap) < full - p.grip_n * 0.5 * math.pi * p.grip_r ** 2 * p.cap_t * 0.9


def test_a_whole_roll_fits_inside_the_flanges():
    assert p.roll_r_full < p.spool_flange_r - 3
