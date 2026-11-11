"""The assembly marks (F18): where each is, how deep, and that it stays out of the film's way."""

import pytest

import cadutil
from params import DEFAULT, Params
from parts.film_gate import model as gate
from parts.lock_switch import model as switch

p = DEFAULT
BARE = Params(mark_depth=0)
BUILDERS = {
    "gate_front": gate.gate_front, "gate_body": gate.gate_body, "gate_lid": gate.gate_lid,
    "pressure_plate": gate.pressure_plate, "wedge_plate": switch.wedge_plate,
}
UP = {**gate.PRINT_UP, **switch.PRINT_UP}
EPS = 1e-3


@pytest.fixture(scope="module")
def cut():
    """What the marks take out of each part: the part built without them, less the part built with them."""
    out = {}
    for name, build in BUILDERS.items():
        marked, bare = build(p), build(BARE)
        out[name] = (marked, bare, cadutil.volume(bare) - cadutil.volume(marked), cadutil.shape_bounds(bare.cut(marked).val()))
    return out


@pytest.mark.parametrize("name", BUILDERS)
def test_each_part_is_still_one_valid_solid_that_prints_without_overhangs(cut, name):
    marked = cut[name][0]
    assert cadutil.is_valid(marked)
    assert cadutil.overhangs(cadutil.print_pose(marked, UP[name])) == []


@pytest.mark.parametrize("name, removed", [
    ("gate_front", 0.8 * 0.36 * 6.5), ("gate_body", 0.8 * 0.36 * 6),
    ("pressure_plate", 1.5 * 3 * 0.36), ("wedge_plate", 1.5 * 3 * 0.36),
])
def test_removed_volume(cut, name, removed):
    assert cut[name][2] == pytest.approx(removed, rel=1e-6)


def test_the_padlocks_are_shallow_and_beside_the_slot(cut):
    x0, x1, y0, y1, z0, z1 = cut["gate_lid"][3]
    assert (y0, y1) == pytest.approx((p.gh - 0.36, p.gh), abs=EPS)                 # top face, 0.36 deep
    assert (z0, z1) == pytest.approx((-14.7, 14.7), abs=EPS)                       # slot end 8 + 4.5 + half of 4.4
    assert x0 > p.x_ref + p.lid_clear and x1 < 245                                 # on the lid, at the slot
    assert 8 < cut["gate_lid"][2] < 20                                             # two icons' worth, not a lid's


def test_the_seam_groove_lines_up_across_the_joint(cut):
    front, body = cut["gate_front"][3], cut["gate_body"][3]
    assert front[2:] == pytest.approx(body[2:], abs=EPS)                           # same y and z
    assert front[2:] == pytest.approx((71.6, 72.4, 55 - 0.36, 55), abs=EPS)        # 3 above the upper screws, +z side
    assert front[1] == pytest.approx(p.x_ref - 1, abs=EPS)                         # clear of the bed face
    assert (body[0], body[1]) == pytest.approx((p.x_ref, p.x_ref + 6), abs=EPS)


def test_the_plates_triangles_face_each_other_above_the_film(cut):
    pp, wp = cut["pressure_plate"][3], cut["wedge_plate"][3]
    assert (pp[0], pp[1]) == pytest.approx((p.x_pp - 0.36, p.x_pp), abs=EPS)      # back face, toward the light
    assert (wp[0], wp[1]) == pytest.approx((p.x_wedge, p.x_wedge + 0.36), abs=EPS)  # front face, toward the lens
    for b in (pp, wp):
        assert (b[2], b[3]) == pytest.approx((64.5, 67.5), abs=EPS)
        assert b[2] > p.axis + p.pad_dy + p.pad / 2                                # above the pads and ramps


@pytest.mark.parametrize("name", BUILDERS)
def test_no_mark_reaches_the_film_band(cut, name):
    assert cut[name][3][2] > p.axis + p.film_w / 2


@pytest.mark.parametrize("q", [Params(wd=150), Params(axis=50)])
def test_marks_follow_wd_and_axis(q):
    for name, build in BUILDERS.items():
        marked = build(q)
        assert cadutil.is_valid(marked)
        assert cadutil.volume(marked) < cadutil.volume(build(Params(wd=q.wd, axis=q.axis, mark_depth=0))), name
