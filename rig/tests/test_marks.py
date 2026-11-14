"""The assembly mark (F18): where it is, how deep, and that it stays out of the film's way.

Main's clamp gate has padlocks on its lid and a ▲ on each plate too. This gate (D1, D2) has no lid and no plates, so
the gate front's ▲ is the only mark. The knob's turn-counting groove is not an assembly mark: it has its own
`knob_mark_w` and `knob_mark_depth`, and `mark_depth=0` leaves it alone.
"""

import pytest

import cadutil
from cadutil import probe
from params import DEFAULT, Params
from parts.film_drive import model as drive
from parts.film_gate import model as gate

p = DEFAULT
BARE = Params(mark_depth=0)
EPS = 1e-3


@pytest.fixture(scope="module")
def cut():
    """What the mark takes out of the gate front: (marked, bare, the volume removed, the bounds of what was removed)."""
    marked, bare = gate.gate_front(p), gate.gate_front(BARE)
    return marked, bare, cadutil.volume(bare) - cadutil.volume(marked), cadutil.shape_bounds(bare.cut(marked).val())


def test_params():
    assert (p.mark_depth, p.mark_tri) == (0.36, 3)              # 3 layers at 0.12, 2 at 0.2
    assert (p.knob_mark_w, p.knob_mark_depth) == (1.2, 0.6)     # the knob's groove, not an assembly mark


def test_the_gate_front_is_still_one_valid_solid_with_only_the_grooves_bridged(cut):
    marked, bare = cut[0], cut[1]
    assert cadutil.is_valid(marked)
    up = gate.PRINT_UP["gate_front"]
    over = cadutil.overhangs(cadutil.print_pose(marked, up))
    assert len(over) == len(cadutil.overhangs(cadutil.print_pose(bare, up))) == 4      # the tooth grooves' bridges (D3)


def test_removed_volume(cut):
    assert cut[2] == pytest.approx(1.5 * 3 * 0.36, rel=1e-6)


def test_the_gate_front_triangle_is_on_the_socket_floor_inside_the_tube(cut):
    x0, x1, y0, y1, z0, z1 = cut[3]
    floor = p.x_gate + p.front_wall
    assert (x0, x1) == pytest.approx((floor, floor + 0.36), abs=EPS)                # the socket floor, a top layer
    assert (z0, z1) == pytest.approx((-1.5, 1.5), abs=EPS)                         # centred on the axis
    assert y1 - y0 == pytest.approx(3, abs=EPS)
    assert y0 > p.axis + p.flare_scale * p.win_h / 2                               # above the light passage ...
    assert y1 < p.axis + p.tube_ri - 0.5                                           # ... and inside the tube's bore


def test_it_points_up(cut):
    marked = cut[0]
    x0, x1, y0, y1, _, _ = cut[3]
    x = (x0 + 0.05, x1 - 0.05)
    wide = cadutil.volume(probe(*x, y0, y0 + 0.2, -1.5, 1.5)) - cadutil.common_volume(marked, probe(*x, y0, y0 + 0.2, -1.5, 1.5))
    narrow = cadutil.volume(probe(*x, y1 - 0.2, y1, -1.5, 1.5)) - cadutil.common_volume(marked, probe(*x, y1 - 0.2, y1, -1.5, 1.5))
    assert wide > 5 * narrow > 0                                                   # its base is at the bottom


def test_the_mark_stays_clear_of_the_film_the_grooves_and_the_peg_holes(cut):
    x0, x1, y0, y1, z0, z1 = cut[3]
    assert x1 < p.x_ref - p.relief_depth - 5                                       # far in front of the teeth's grooves
    assert x1 < p.x_ref - p.win_depth                                              # and of the frame window
    assert y0 > p.axis + p.film_w / 2                                              # above the film band
    for y, z in p.peg_points:
        assert abs(z) - p.peg_d / 2 > z1 + 20


def test_the_gate_body_has_no_mark():
    assert cadutil.volume(gate.gate_body(p)) == pytest.approx(cadutil.volume(gate.gate_body(BARE)), rel=1e-12)


def test_mark_depth_0_leaves_the_triangle_off_and_the_knob_groove_alone(cut):
    bare = cut[1]
    floor = p.x_gate + p.front_wall
    y = p.axis + (p.flare_scale * p.win_h / 2 + p.tube_ri) / 2
    box = probe(floor, floor + 0.36, y - 1.4, y + 1.4, -0.2, 0.2)
    assert cadutil.common_volume(bare, box) == pytest.approx(cadutil.volume(box), rel=1e-6)
    marked_idler, bare_idler = drive.idler(p), drive.idler(BARE)
    assert cadutil.volume(marked_idler) == pytest.approx(cadutil.volume(bare_idler), rel=1e-12)
    # the groove is there either way: 0.6 deep in the knob's top, from the axle's bore toward +x
    top = p.y_gear + p.gear_t + p.knob_h
    groove = probe(p.x_sprocket + 5, p.x_sprocket + 8, top - 0.5, top, -0.4, 0.4)
    for idler in (marked_idler, bare_idler):
        assert cadutil.common_volume(idler, groove) < 1e-6
    for name, wp in drive.build(BARE).items():
        assert cadutil.volume(wp) == pytest.approx(cadutil.volume(drive.build(p)[name]), rel=1e-12), name


@pytest.mark.parametrize("q", [Params(wd=150), Params(axis=50), Params(axis=39)])
def test_the_mark_follows_wd_and_axis(q):
    marked = gate.gate_front(q)
    bare = gate.gate_front(Params(wd=q.wd, axis=q.axis, mark_depth=0))
    assert cadutil.is_valid(marked)
    assert cadutil.volume(bare) - cadutil.volume(marked) == pytest.approx(1.5 * 3 * 0.36, rel=1e-6)
    x0, _, y0, _, _, _ = cadutil.shape_bounds(bare.cut(marked).val())
    assert x0 == pytest.approx(q.x_gate + q.front_wall, abs=EPS)
    assert y0 > q.axis + q.flare_scale * q.win_h / 2
