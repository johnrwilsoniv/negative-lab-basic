"""Film drive: the sprockets, their gears, the knobbed idler, its axle and the deck (D3, D4).

The gears are checked on their outline (tooth count, radii, the tooth's thickness at the pitch circle) and in mesh
(the phase that lets the same prints work on both sides, and no collision through a range of knob positions). The
sprockets are probed for their teeth, the D-flat, and the way they turn.
"""

import math

import pytest

import cadutil
from cadutil import probe
from params import DEFAULT, Params
from parts.film_drive import model
from parts.film_gate import model as gate_model

p = DEFAULT
Q = Params(wd=150, axis=50)
EPS = 1e-6
NAMES = ["sprocket_supply", "gear_supply", "sprocket_takeup", "gear_takeup", "idler", "idler_axle", "deck"]


@pytest.fixture(scope="module")
def built():
    return model.build(p)


def filled(wp, *ranges):
    pr = probe(*ranges)
    return cadutil.common_volume(wp, pr) / cadutil.volume(pr)


def has(wp, *ranges):
    return filled(wp, *ranges) > EPS


# ---- the solids ------------------------------------------------------------------------------


def test_the_solids_and_their_print_directions(built):
    assert list(built) == NAMES
    assert set(model.PRINT_UP) == set(NAMES)
    assert all(up == "+y" for up in model.PRINT_UP.values())


@pytest.mark.parametrize("q", [p, Q], ids=["defaults", "other"])
def test_each_is_one_valid_solid(q):
    for name, wp in model.build(q).items():
        assert cadutil.is_valid(wp), name
        assert cadutil.volume(wp) > 0, name


@pytest.mark.parametrize("name", NAMES)
def test_each_prints_with_no_overhangs(built, name):
    posed = cadutil.print_pose(built[name], model.PRINT_UP[name])
    assert cadutil.overhangs(posed) == [], name


def test_the_two_sides_are_the_same_prints(built):
    for kind in ("sprocket", "gear"):
        a, b = built[f"{kind}_supply"], built[f"{kind}_takeup"]
        assert cadutil.volume(a) == pytest.approx(cadutil.volume(b), rel=1e-9), kind
        # the take-up side's is the supply side's turned half round about its own axis, and moved across
        moved = a.rotate((p.x_sprocket, 0, -p.sprocket_z), (p.x_sprocket, 1, -p.sprocket_z), 180).translate(
            (0, 0, 2 * p.sprocket_z))
        assert cadutil.common_volume(moved, b) == pytest.approx(cadutil.volume(b), rel=1e-6), kind


# ---- the gear outline ------------------------------------------------------------------------


def test_the_gear_outline_has_its_teeth_and_radii():
    pts = model.gear_outline(p)
    radii = [math.hypot(u, v) for u, v in pts]
    assert max(radii) == pytest.approx(p.gear_tip_r, abs=1e-9)
    assert min(radii) == pytest.approx(p.gear_root_r, abs=1e-9)
    assert len(pts) == p.gear_teeth * 2 * (model.FLANK_POINTS + 2)     # each flank: the root, then the involute
    # tooth 0 is centred on +v
    first = pts[: 2 * (model.FLANK_POINTS + 2)]
    assert sum(u for u, _ in first) == pytest.approx(0, abs=1e-9)


def test_the_tooth_is_half_the_pitch_less_half_the_backlash_at_the_pitch_circle(built):
    # measured on the built gear: the straight chord across tooth 0 whose ends are on the pitch circle
    gear = built["gear_supply"]
    xs, zs, r = p.x_sprocket, -p.sprocket_z, p.gear_r
    y = p.y_gear + p.gear_t / 2
    t = 1e-3
    half_angle = (math.pi * r / p.gear_teeth - p.gear_backlash / 2) / (2 * r)
    expected = 2 * r * math.sin(half_angle)
    zc = zs + r * math.cos(half_angle)
    hit = cadutil.common_bounds(gear, probe(xs - 1.5, xs + 1.5, y - t, y + t, zc - t, zc + t))   # not its neighbours
    width = hit[1] - hit[0]
    assert width == pytest.approx(expected, abs=2e-3)      # a polyline flank, so nearly


# ---- the mesh --------------------------------------------------------------------------------


def test_the_gears_are_in_a_row_centre_to_centre_two_pitch_radii(built):
    for name, z in (("gear_supply", -p.sprocket_z), ("idler", 0), ("gear_takeup", p.sprocket_z)):
        x0, x1, _, _, z0, z1 = cadutil.bounds(built[name])
        assert ((x0 + x1) / 2, (z0 + z1) / 2) == pytest.approx((p.x_sprocket, z), abs=0.05), name
    assert p.sprocket_z == pytest.approx(2 * p.gear_r)


def test_each_gear_shows_the_idler_a_tooth_and_the_idler_a_gap(built):
    xs, y = p.x_sprocket, p.y_gear + p.gear_t / 2
    for name, sign in (("gear_supply", -1), ("gear_takeup", 1)):
        pitch_point = sign * (p.sprocket_z - p.gear_r)          # where the pitch circles touch, on the line of centres
        ranges = (xs - 0.1, xs + 0.1, y - 0.5, y + 0.5, pitch_point - 0.1, pitch_point + 0.1)
        assert has(built[name], *ranges), name
        assert not has(built["idler"], *ranges), name


@pytest.mark.parametrize("turn", [0, 1 / 96, 1 / 64, 1 / 48, 1 / 32, 1 / 16, 0.1, 0.3])
def test_the_gears_never_collide_as_the_knob_turns(turn):
    solids = model.build(p, turn)
    for gear in ("gear_supply", "gear_takeup"):
        assert cadutil.common_volume(solids[gear], solids["idler"]) < 1e-6, (turn, gear)


def test_one_knob_turn_is_one_frame_and_brings_everything_back(built):
    again = model.build(p, 1.0)
    for name in NAMES:
        assert cadutil.common_volume(again[name], built[name]) == pytest.approx(cadutil.volume(built[name]), rel=1e-6)


def test_the_teeth_at_the_film_move_toward_plus_z_as_the_knob_turns():
    turned = model.build(p, 1 / 32)
    for name, sign in (("sprocket_supply", -1), ("sprocket_takeup", 1)):
        zs = sign * p.sprocket_z
        # only the tooth that has come furthest through the film reaches this far forward
        hit = cadutil.common_bounds(turned[name], probe(p.x_film - 2, p.x_film - 0.6, 20, 65, zs - 4, zs + 4))
        assert (hit[4] + hit[5]) / 2 > zs + 0.5, name           # the film-side tooth has gone toward +z


def test_the_idler_turns_the_other_way():
    # its turn-counting groove points +x with a frame centred; a quarter turn on, the idler has turned against the
    # sprockets (which turn right-handed about +y), so the groove points +z
    y = p.y_gear + p.gear_t + p.knob_h - p.knob_mark_depth / 2
    xs = p.x_sprocket
    groove = lambda wp, x0, x1, z0, z1: filled(wp, x0, x1, y - 0.1, y + 0.1, z0, z1)     # noqa: E731
    at0, at_quarter = model.idler(p, 0.0), model.idler(p, 0.25)
    assert groove(at0, xs + 5, xs + 8, -0.3, 0.3) < EPS and groove(at0, xs - 8, xs - 5, -0.3, 0.3) > 1 - EPS
    assert groove(at_quarter, xs - 0.3, xs + 0.3, 5, 8) < EPS


# ---- the sprocket ----------------------------------------------------------------------------


def test_eight_teeth_on_each_ring_one_pointing_at_the_film(built):
    sp = built["sprocket_supply"]
    xs, zs = p.x_sprocket, -p.sprocket_z
    for y in (p.axis - p.perf_dy, p.axis + p.perf_dy):
        for k in range(p.sprocket_teeth):
            a = math.pi + 2 * math.pi * k / p.sprocket_teeth     # from -x, as the teeth are spaced
            r = p.r_tip - 0.2
            cx, cz = xs + r * math.cos(a), zs + r * math.sin(a)
            assert has(sp, cx - 0.05, cx + 0.05, y - 0.05, y + 0.05, cz - 0.05, cz + 0.05), (y, k)
            b = a + math.pi / p.sprocket_teeth                   # between two teeth, nothing at that radius
            cx, cz = xs + r * math.cos(b), zs + r * math.sin(b)
            assert not has(sp, cx - 0.05, cx + 0.05, y - 0.05, y + 0.05, cz - 0.05, cz + 0.05), (y, k)
    x0 = cadutil.bounds(sp)[0]
    assert x0 == pytest.approx(xs - p.r_tip, abs=1e-6)


def test_the_teeth_narrow_to_a_ridge_that_fits_the_perforation(built):
    sp = built["sprocket_supply"]
    xs, zs, y = p.x_sprocket, -p.sprocket_z, p.axis - p.perf_dy
    hit = cadutil.common_bounds(sp, probe(p.x_film - p.film_t / 2, p.x_film + p.film_t / 2, y - 3, y + 3, zs - 2, zs + 2))
    assert hit[3] - hit[2] < p.perf_w - 0.25        # across the film, in the film's thickness
    assert hit[5] - hit[4] < p.perf_l - 0.5         # along it


def test_the_rings_carry_the_film_edges_outside_the_frame_and_the_hub_is_clear(built):
    sp = built["sprocket_supply"]
    xs, zs = p.x_sprocket, -p.sprocket_z
    ring = cadutil.common_bounds(sp, probe(xs - 10, xs, p.y_ring_lo[0] + 0.1, p.y_ring_lo[0] + 0.5, zs - 1e-3, zs + 1e-3))
    assert ring[0] == pytest.approx(xs - p.r_ring, abs=1e-6)
    hub = cadutil.common_bounds(sp, probe(xs - 10, xs, p.axis - 1, p.axis + 1, zs - 1e-3, zs + 1e-3))
    assert hub[0] == pytest.approx(xs - p.hub_r, abs=1e-6)
    assert p.y_ring_lo[1] < p.axis - p.frame_h / 2 and p.y_ring_hi[0] > p.axis + p.frame_h / 2


@pytest.mark.parametrize("side, sign", [("supply", -1), ("takeup", 1)])
def test_each_shafts_flat_faces_the_idler(built, side, sign):
    sp, xs, zs = built[f"sprocket_{side}"], p.x_sprocket, sign * p.sprocket_z
    y = p.y_gear + p.gear_t / 2
    toward, away = -sign, sign
    reach = lambda d: cadutil.common_bounds(sp, probe(xs - 1e-3, xs + 1e-3, y - 0.5, y + 0.5,      # noqa: E731
                                                      *sorted((zs, zs + d * 10))))
    near = reach(toward)
    far = reach(away)
    assert abs((near[5] if toward > 0 else near[4]) - zs) == pytest.approx(p.shaft_d / 2 - p.shaft_flat, abs=1e-6)
    assert abs((far[5] if away > 0 else far[4]) - zs) == pytest.approx(p.shaft_d / 2, abs=1e-6)


def test_the_shaft_stands_on_the_bearing_floor_and_ends_with_its_gear(built):
    _, _, y0, y1, _, _ = cadutil.bounds(built["sprocket_supply"])
    assert (y0, y1) == pytest.approx((p.shaft_floor, p.y_shaft_top))
    _, _, g0, g1, _, _ = cadutil.bounds(built["gear_supply"])
    assert (g0, g1) == pytest.approx((p.y_gear, p.y_shaft_top))


# ---- with the gate ---------------------------------------------------------------------------


def test_the_deck_lies_on_the_gate_body_and_the_gears_on_the_deck(built):
    body = gate_model.gate_body(p)
    assert cadutil.bounds(built["deck"])[2] == pytest.approx(cadutil.bounds(body)[3])
    assert cadutil.bounds(built["deck"])[3] == pytest.approx(p.y_gear)
    assert cadutil.bounds(built["deck"])[1] == pytest.approx(p.x_light - p.deck_clear)


def test_the_gear_tips_and_the_knob_stay_clear_of_the_cs_lite(built):
    for name in ("gear_supply", "gear_takeup", "idler"):
        assert cadutil.bounds(built[name])[1] < p.x_light - 2, name


def test_the_knob_is_above_the_sprocket_gears_and_clear_of_them(built):
    knob_r = p.knob_r
    for gear in ("gear_supply", "gear_takeup"):
        nearest = p.sprocket_z - p.gear_tip_r
        assert nearest > knob_r, gear
        assert cadutil.common_volume(built["idler"], built[gear]) < 1e-6


def test_the_axle_reaches_from_the_gate_body_into_the_knob(built):
    _, _, y0, y1, _, _ = cadutil.bounds(built["idler_axle"])
    assert y0 == pytest.approx(p.gh - p.axle_hole_depth)
    assert y1 == pytest.approx(p.y_gear + p.gear_t + p.knob_h - p.axle_top_clear)
