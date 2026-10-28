"""Tube: placement, slip fits, the sawtooth baffle ribs inside, and printing upright without supports.

Rib positions and radii are read off the solid's circle edges (every rib is a revolved profile, so
each corner is a full circle) and its face normals, not recomputed from the params.
"""

import math

import cadquery as cq
import pytest

import cadutil
from params import DEFAULT, Params
from parts.lens_adapter import model as adapter_model
from parts.tube import model

p = DEFAULT
EDGE_TOL = 1e-6
FLANK_DEGREES = 45       # steepest overhang that prints without supports
ANGLE_TOL = 1e-6


@pytest.fixture(scope="module")
def built():
    return model.build(p)


@pytest.fixture(scope="module")
def tube(built):
    return built["tube"]


@pytest.fixture(scope="module")
def adapter():
    return adapter_model.build(p)["adapter"]


def circles(wp):
    return [e for e in cadutil.solid(wp).Edges() if e.geomType() == "CIRCLE"]


def ribs(wp, q=p):
    """(start x, end x) of each rib, from the circles where the ribs meet the r = tube_ri bore."""
    xs = sorted(e.arcCenter().x for e in circles(wp) if abs(e.radius() - q.tube_ri) < EDGE_TOL)
    inner = [x for x in xs if abs(x - q.tube_x0) > EDGE_TOL and abs(x - q.tube_x1) > EDGE_TOL]
    return list(zip(inner[::2], inner[1::2]))


def tips(wp, q=p):
    """x of each rib tip: the circles at the minimum free radius."""
    r = q.tube_ri - q.baffle_h
    return sorted(e.arcCenter().x for e in circles(wp) if abs(e.radius() - r) < EDGE_TOL)


def disc(x, r, thickness, q=p):
    """A thin disc of radius r across the tube axis, from x to x + thickness."""
    return cq.Workplane("YZ", origin=(x, q.axis, 0)).circle(r).extrude(thickness)


def rod(r, q=p):
    """A cylinder of radius r along the tube axis, the whole length of the tube."""
    return disc(q.tube_x0, r, q.tube_len, q)


def overhangs(wp, up):
    """(degrees from horizontal, face) of each face that faces down, posed with `up` on top,
    other than the one lying on the bed."""
    found = []
    for face in cadutil.solid(cadutil.print_pose(wp, up)).Faces():
        normal = face.normalAt()
        if normal.z >= -1e-9:
            continue
        if all(abs(v.Z) < 1e-6 for v in face.Vertices()):
            continue
        found.append((math.degrees(math.acos(-normal.z)), face))
    return found


# ---- solid ---------------------------------------------------------------------------


def test_solid_name_and_print_direction(built):
    assert list(built) == ["tube"]
    assert model.PRINT_UP == {"tube": "+x"}


def test_one_valid_closed_solid(tube):
    solid = cadutil.solid(tube)          # raises unless exactly one
    assert solid.isValid()
    assert all(shell.Closed() for shell in solid.Shells())
    assert solid.Volume() > 0


def test_bounds_at_default(tube):
    r = p.tube_ro
    assert cadutil.bounds(tube) == pytest.approx((128, 245, p.axis - r, p.axis + r, -r, r), abs=0.05)
    assert cadutil.size(tube) == pytest.approx((117, 72, 72), abs=0.05)
    assert (p.tube_x0, p.tube_x1, p.tube_len) == (128, 245, 117)


def test_length_follows_wd():
    q = Params(wd=150)
    tube = model.build(q)["tube"]
    assert cadutil.size(tube) == pytest.approx((137, 72, 72), abs=0.05)
    assert cadutil.bounds(tube)[:2] == pytest.approx((q.tube_x0, q.tube_x1), abs=0.05)


def test_prints_upright_and_fits_the_bed(tube):
    posed = cadutil.print_pose(tube, model.PRINT_UP["tube"])
    assert cadutil.fits_bed(posed, p)
    assert cadutil.size(posed) == pytest.approx((72, 72, 117), abs=0.05)


# ---- fits ----------------------------------------------------------------------------


@pytest.mark.parametrize("wd", [p.wd, 150])
def test_od_is_a_slip_fit_in_the_socket_and_the_gate_hole(wd):
    q = Params(wd=wd)
    tube_r = max(e.radius() for e in circles(model.build(q)["tube"]))
    socket_r = min(
        e.radius()
        for e in circles(adapter_model.build(q)["adapter"])
        if e.arcCenter().x >= q.tube_x0 - EDGE_TOL and e.radius() > tube_r
    )
    assert tube_r == pytest.approx(q.tube_ro, abs=EDGE_TOL)
    assert socket_r - tube_r == pytest.approx(0.3, abs=EDGE_TOL)
    assert q.fit_r - tube_r == pytest.approx(0.3, abs=EDGE_TOL)       # the gate's front-wall hole


def test_tube_end_sits_on_the_socket_floor_without_touching_the_adapter(tube, adapter):
    assert cadutil.bounds(tube)[0] == pytest.approx(p.x_front + p.flange, abs=EDGE_TOL)
    assert cadutil.common_volume(tube, adapter) < 1e-3


# ---- bore and baffles ----------------------------------------------------------------


def test_ribs_close_in_no_further_than_the_adapter_bore(tube):
    assert p.tube_ri - p.baffle_h == p.adapter_bore_r
    assert min(e.radius() for e in circles(tube)) == pytest.approx(p.adapter_bore_r, abs=EDGE_TOL)


def test_free_radius_is_r31_at_the_rib_tips(tube):
    assert cadutil.common_volume(tube, rod(p.adapter_bore_r - 0.1)) < 1e-3
    assert cadutil.common_volume(tube, rod(p.adapter_bore_r + 0.1)) > 1.0


def test_bore_between_ribs_is_r32(tube):
    found = ribs(tube)
    gaps = [(found[0][1], found[1][0]), (found[-2][1], found[-1][0]), (p.tube_x0, found[0][0]), (found[-1][1], p.tube_x1)]
    for start, end in gaps:
        width = end - start
        assert width > 1
        x = start + 0.25 * width
        assert cadutil.common_volume(tube, disc(x, p.tube_ri - 0.01, width / 2)) < 1e-3
        assert cadutil.common_volume(tube, disc(x, p.tube_ri + 0.01, width / 2)) > 1.0


@pytest.mark.parametrize("wd, count", [(p.wd, 15), (150, 17)])
def test_rib_layout(wd, count):
    q = Params(wd=wd)
    tube = model.build(q)["tube"]
    found = ribs(tube, q)
    assert len(found) == count == q.baffle_count
    assert len(tips(tube, q)) == count
    for (start, end), tip in zip(found, tips(tube, q)):
        assert end - start == pytest.approx(q.baffle_h, abs=EDGE_TOL)      # 45 degree flank runs h
        assert tip == pytest.approx(end, abs=EDGE_TOL)                     # the step is square to the axis
    starts = [start for start, _ in found]
    assert all(b - a == pytest.approx(q.baffle_pitch, abs=EDGE_TOL) for a, b in zip(starts, starts[1:]))
    assert starts[0] - q.tube_x0 >= q.baffle_margin - EDGE_TOL
    assert q.tube_x1 - found[-1][1] >= q.baffle_margin - EDGE_TOL


def test_ribs_sit_centred_between_the_end_margins():
    q = Params(wd=150)
    found = ribs(model.build(q)["tube"], q)
    assert found[0][0] - q.tube_x0 == pytest.approx(q.tube_x1 - found[-1][1], abs=EDGE_TOL)


def test_volume_is_the_plain_tube_plus_the_triangular_ribs(tube):
    plain = math.pi * (p.tube_ro**2 - p.tube_ri**2) * p.tube_len
    h = p.baffle_h
    one_rib = 2 * math.pi * (p.tube_ri - h / 3) * h * h / 2       # Pappus: triangle area h^2/2, centroid r_i - h/3
    assert cadutil.volume(tube) == pytest.approx(plain + 15 * one_rib, rel=1e-9)


def test_no_baffles_gives_the_plain_tube():
    q = Params(baffle_h=0)
    tube = model.build(q)["tube"]
    assert cadutil.is_valid(tube)
    assert cadutil.volume(tube) == pytest.approx(math.pi * (36**2 - 32**2) * 117, rel=1e-3)
    assert ribs(tube, q) == []
    assert min(e.radius() for e in circles(tube)) == pytest.approx(q.tube_ri, abs=EDGE_TOL)


# ---- support-free print --------------------------------------------------------------


def test_every_rib_has_a_down_facing_flank_no_flatter_than_45_degrees(tube):
    found = overhangs(tube, model.PRINT_UP["tube"])
    assert len(found) == p.baffle_count
    assert all(face.geomType() == "CONE" for _, face in found)
    assert all(angle >= FLANK_DEGREES - ANGLE_TOL for angle, _ in found)


def test_the_overhang_check_catches_a_tube_printed_the_other_way_up(tube):
    wrong = "-x" if model.PRINT_UP["tube"] == "+x" else "+x"
    assert min(angle for angle, _ in overhangs(tube, wrong)) < FLANK_DEGREES - 1


# ---- refusals ------------------------------------------------------------------------


def test_tube_longer_than_the_bed_is_refused():
    longest = Params(wd=p.tube_max_len + (p.wd - p.tube_len))
    assert longest.tube_len == longest.tube_max_len
    assert cadutil.size(model.build(longest)["tube"])[0] == pytest.approx(longest.tube_max_len, abs=0.05)
    with pytest.raises(ValueError, match="spigot"):
        model.build(Params(wd=longest.wd + 1))


@pytest.mark.parametrize("h", [-0.5, 8, 9])
def test_ribs_that_cannot_be_drawn_are_refused(h):
    with pytest.raises(ValueError, match="baffle_h"):
        model.build(Params(baffle_h=h))
