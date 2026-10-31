"""cadutil helpers, checked on solids with known answers."""

import math

import cadquery as cq
import numpy as np
import pytest

import cadutil
from params import DEFAULT, Params


def box(dx, dy, dz, at=(0, 0, 0)):
    """A dx x dy x dz box with its minimum corner at `at`."""
    return cq.Workplane("XY").box(dx, dy, dz, centered=False).translate(at)


def cylinder(r, h):
    return cq.Workplane("XY").circle(r).extrude(h)


# ---- solid / validity / volume ------------------------------------------------------


def test_solid_returns_the_single_solid():
    assert isinstance(cadutil.solid(box(1, 2, 3)), cq.Solid)


def test_solid_unwraps_a_compound_of_one_solid():
    wp = box(1, 1, 1).union(box(1, 1, 1, at=(0.5, 0, 0)))
    assert isinstance(cadutil.solid(wp), cq.Solid)


def test_solid_rejects_two_solids():
    wp = box(1, 1, 1).union(box(1, 1, 1, at=(5, 0, 0)))
    with pytest.raises(ValueError, match="2 solids"):
        cadutil.solid(wp)


def test_solid_rejects_nothing():
    with pytest.raises(ValueError, match="0 solids"):
        cadutil.solid(cq.Workplane("XY"))


def two_cubes_touching_on_an_edge():
    """One solid (a base joins them) whose two cubes meet only along the edge x = y = 10: that edge has 4 faces."""
    return box(20, 20, 2).union(box(10, 10, 10, at=(0, 0, 2))).union(box(10, 10, 10, at=(10, 10, 2)))


def test_non_manifold_edges_finds_an_edge_with_four_faces():
    wp = two_cubes_touching_on_an_edge()
    assert cadutil.solid(wp).isValid()                # OCC's own check lets it through; Onshape's does not
    (edge,) = cadutil.non_manifold_edges(wp)
    ends = sorted(tuple(v.toTuple()) for v in (edge.startPoint(), edge.endPoint()))
    assert ends == [pytest.approx((10, 10, 2)), pytest.approx((10, 10, 12))]


def test_non_manifold_edges_is_empty_on_a_plain_solid():
    assert cadutil.non_manifold_edges(box(10, 20, 30)) == []
    assert cadutil.non_manifold_edges(cylinder(5, 10)) == []        # the seam edge is one face's, twice


def test_is_valid_rejects_a_non_manifold_solid():
    assert not cadutil.is_valid(two_cubes_touching_on_an_edge())


def test_is_valid_and_volume():
    assert cadutil.is_valid(box(10, 20, 30))
    assert cadutil.volume(box(10, 20, 30)) == pytest.approx(6000)
    assert cadutil.volume(cylinder(5, 10)) == pytest.approx(math.pi * 25 * 10)


# ---- bounds / size -------------------------------------------------------------------


def test_bounds_and_size_of_a_translated_box():
    wp = box(10, 20, 30, at=(1, -2, 3))
    assert cadutil.bounds(wp) == pytest.approx((1, 11, -2, 18, 3, 33), abs=1e-9)
    assert cadutil.size(wp) == pytest.approx((10, 20, 30), abs=1e-9)


def test_bounds_of_a_cylinder_are_exact_even_after_meshing(tmp_path):
    wp = cylinder(10, 5)
    assert cadutil.bounds(wp) == pytest.approx((-10, 10, -10, 10, 0, 5), abs=1e-9)
    # A coarse mesh makes CadQuery's own bounding box grow by the mesh deflection (10.07 here).
    cadutil.solid(wp).exportStl(str(tmp_path / "c.stl"), tolerance=0.5, angularTolerance=0.5, relative=False)
    assert cadutil.bounds(wp) == pytest.approx((-10, 10, -10, 10, 0, 5), abs=1e-9)
    assert cadutil.size(wp) == pytest.approx((20, 20, 5), abs=1e-9)


def test_shape_bounds_of_a_compound_of_several_solids():
    two = cq.Compound.makeCompound([cadutil.solid(box(1, 2, 3)), cadutil.solid(box(1, 1, 1, at=(5, -4, 0)))])
    assert cadutil.shape_bounds(two) == pytest.approx((0, 6, -4, 2, 0, 3), abs=1e-9)


# ---- boolean common ------------------------------------------------------------------


def test_common_volume_of_overlapping_boxes():
    a, b = box(10, 10, 10), box(10, 10, 10, at=(5, 0, 0))
    assert cadutil.common_volume(a, b) == pytest.approx(500)


def test_common_volume_of_touching_boxes_is_zero():
    a, b = box(10, 10, 10), box(10, 10, 10, at=(10, 0, 0))
    assert cadutil.common_volume(a, b) == pytest.approx(0, abs=1e-9)


def test_common_volume_of_separate_boxes_is_zero():
    a, b = box(10, 10, 10), box(10, 10, 10, at=(30, 0, 0))
    assert cadutil.common_volume(a, b) == 0.0


def test_common_bounds_of_overlapping_boxes():
    a, b = box(10, 10, 10), box(10, 10, 10, at=(5, 2, 0))
    assert cadutil.common_bounds(a, b) == pytest.approx((5, 10, 2, 10, 0, 10), abs=1e-9)


@pytest.mark.parametrize("at", [(10, 0, 0), (30, 0, 0)], ids=["touching", "separate"])
def test_common_bounds_is_none_without_overlap(at):
    assert cadutil.common_bounds(box(10, 10, 10), box(10, 10, 10, at=at)) is None


def test_common_pieces_lists_each_solid_of_the_intersection():
    # a comb: a spine along x with two teeth standing up in z, cut across both teeth by a plate
    comb = box(20, 10, 1).union(box(2, 10, 10, at=(2, 0, 0))).union(box(5, 10, 10, at=(14, 0, 0)))
    plate = box(20, 10, 5, at=(0, 0, 5))
    pieces = sorted(cadutil.common_pieces(comb, plate))
    assert [v for v, _ in pieces] == pytest.approx([100, 250])
    assert [b for _, b in pieces] == [pytest.approx((2, 4, 0, 10, 5, 10)), pytest.approx((14, 19, 0, 10, 5, 10))]


@pytest.mark.parametrize("at", [(10, 0, 0), (30, 0, 0)], ids=["touching", "separate"])
def test_common_pieces_is_empty_without_overlap(at):
    assert cadutil.common_pieces(box(10, 10, 10), box(10, 10, 10, at=at)) == []


# ---- probe ---------------------------------------------------------------------------


def test_probe_is_a_box_with_the_given_ranges():
    wp = cadutil.probe(1, 4, 10, 12, -3, 5)
    assert cadutil.bounds(wp) == pytest.approx((1, 4, 10, 12, -3, 5))
    assert cadutil.volume(wp) == pytest.approx(3 * 2 * 8)


def test_probe_finds_the_edge_of_a_solid():
    # the bounds of what a probe takes from a solid are that solid's face, wherever the probe is
    cyl = cylinder(10, 5).translate((0, 0, 1))
    hit = cadutil.common_bounds(cyl, cadutil.probe(8, 20, -0.001, 0.001, 0, 10))
    assert hit[1] == pytest.approx(10, abs=1e-5)


# ---- print pose ----------------------------------------------------------------------

DIMS = {"x": 10, "y": 20, "z": 40}   # all different, so a wrong axis shows up
UPS = ["+x", "-x", "+y", "-y", "+z", "-z"]


def tipped_box(up):
    """The 10 x 20 x 40 box with a 2 x 2 x 2 tip stuck on its `up` face, then moved off the origin."""
    axis = "xyz".index(up[1])
    sign = 1 if up[0] == "+" else -1
    offset = [0.0, 0.0, 0.0]
    offset[axis] = sign * (DIMS[up[1]] / 2 + 1)
    base = cq.Workplane("XY").box(10, 20, 40)
    tip = cq.Workplane("XY").box(2, 2, 2).translate(tuple(offset))
    return base.union(tip).translate((13, -7, 5))


@pytest.mark.parametrize("up", UPS)
def test_print_pose_puts_the_up_face_on_top(up):
    posed = cadutil.print_pose(tipped_box(up), up)
    x0, x1, y0, y1, z0, z1 = cadutil.bounds(posed)
    assert z0 == pytest.approx(0, abs=1e-9)
    assert (x0 + x1) / 2 == pytest.approx(0, abs=1e-9)
    assert (y0 + y1) / 2 == pytest.approx(0, abs=1e-9)
    assert z1 == pytest.approx(DIMS[up[1]] + 2, abs=1e-9)
    other = sorted(v for k, v in DIMS.items() if k != up[1])
    assert sorted([x1 - x0, y1 - y0]) == pytest.approx(other, abs=1e-9)
    # the tip (volume 2 x 2 x 1 within its top millimetre) is up, the wide base is down
    top = box(100, 100, 1, at=(-50, -50, z1 - 1))
    bottom = box(100, 100, 1, at=(-50, -50, 0))
    assert cadutil.common_volume(posed, top) == pytest.approx(4, abs=1e-9)
    assert cadutil.common_volume(posed, bottom) > 100


def test_print_pose_keeps_the_volume():
    wp = tipped_box("+x")
    assert cadutil.volume(cadutil.print_pose(wp, "+x")) == pytest.approx(cadutil.volume(wp))


def test_print_pose_rejects_an_unknown_direction():
    with pytest.raises(ValueError, match="up"):
        cadutil.print_pose(box(1, 1, 1), "up")


def wedge(rise, run=10, width=4):
    """A wedge in (x, z), its top face rising `rise` over `run` along x, extruded `width` along y."""
    outline = [(0, 0), (run, 0), (run, 1 + rise), (0, 1)]
    return cq.Workplane("XZ").polyline(outline).close().extrude(-width)


def test_sloped_faces_are_the_plane_faces_neither_level_nor_upright():
    assert cadutil.sloped_faces(box(10, 20, 30)) == []
    (face,) = cadutil.sloped_faces(wedge(0.7))
    assert face.normalAt().z == pytest.approx(1 / math.hypot(1, 0.07))
    # stood on its side (+y up), the slope is drawn in the bed plane: no face is inclined to the bed
    assert cadutil.sloped_faces(cadutil.print_pose(wedge(0.7), "+y")) == []
    # stood on its end (-x up), the slope still climbs with the layers
    assert len(cadutil.sloped_faces(cadutil.print_pose(wedge(0.7), "-x"))) == 1
    assert cadutil.sloped_faces(cylinder(5, 10)) == []          # curved faces are not judged


# ---- export / STEP round trip --------------------------------------------------------


def test_export_writes_step_and_stl_and_the_step_round_trips(tmp_path):
    # curved faces and a hole, so the round trip is not just planes
    wp = cylinder(10, 5).faces(">Z").workplane().hole(4)
    step, stl = tmp_path / "step" / "p.step", tmp_path / "stl" / "p.stl"
    cadutil.export(wp, step, stl)
    assert step.stat().st_size > 0 and stl.stat().st_size > 0
    assert cadutil.step_volume(step) == pytest.approx(cadutil.volume(wp), rel=cadutil.STEP_VOLUME_RTOL)


def test_export_stl_is_fine_enough(tmp_path):
    wp = cylinder(10, 5)
    cadutil.export(wp, tmp_path / "c.step", tmp_path / "c.stl")
    record = np.dtype([("normal", "<f4", 3), ("v", "<f4", (3, 3)), ("attr", "<u2")])
    tris = np.fromfile(tmp_path / "c.stl", dtype=record, offset=84)["v"].astype(float)
    mesh_volume = abs(np.einsum("ij,ij->i", tris[:, 0], np.cross(tris[:, 1], tris[:, 2])).sum()) / 6
    assert mesh_volume == pytest.approx(cadutil.volume(wp), rel=2e-3)


# ---- multi-solid STEP ---------------------------------------------------------------


def named_assembly():
    asm = cq.Assembly(name="rig")
    asm.add(box(10, 10, 10), name="red_box", color=cq.Color(1, 0, 0, 1))
    asm.add(cylinder(5, 7).translate((30, 0, 0)), name="glass", color=cq.Color(0.5, 0.5, 0.5, 0.4))
    return asm


def test_step_assembly_reads_back_names_solids_and_colours(tmp_path):
    path = tmp_path / "rig.step"
    named_assembly().export(str(path))

    read = cadutil.step_assembly(path)

    assert sorted(read) == ["glass", "red_box"]
    assert cadutil.volume(read["red_box"].solid) == pytest.approx(1000, rel=cadutil.STEP_VOLUME_RTOL)
    assert cadutil.volume(read["glass"].solid) == pytest.approx(math.pi * 25 * 7, rel=cadutil.STEP_VOLUME_RTOL)
    assert cadutil.bounds(read["glass"].solid)[0] == pytest.approx(25, abs=1e-6)     # kept its place
    assert read["red_box"].color == pytest.approx((1, 0, 0, 1), abs=1e-6)
    assert read["glass"].color == pytest.approx((0.5, 0.5, 0.5, 0.4), abs=1e-6)


def test_step_assembly_has_no_colour_where_none_was_given(tmp_path):
    asm = cq.Assembly(name="rig")
    asm.add(box(1, 1, 1), name="plain")
    asm.export(str(tmp_path / "plain.step"))
    assert cadutil.step_assembly(tmp_path / "plain.step")["plain"].color is None


def test_step_assembly_rejects_a_file_with_two_solids_in_one_part(tmp_path):
    asm = cq.Assembly(name="rig")
    asm.add(cq.Workplane("XY").add(box(1, 1, 1).val()).add(box(1, 1, 1, at=(5, 0, 0)).val()), name="pair")
    asm.export(str(tmp_path / "pair.step"))
    with pytest.raises(ValueError, match="2 solids"):
        cadutil.step_assembly(tmp_path / "pair.step")


# ---- text table ----------------------------------------------------------------------


def test_format_table_aligns_columns_and_drops_trailing_blanks():
    text = cadutil.format_table([("name", "n", "note"), ("a", "10", ""), ("long name", "2", "x")])
    assert text.splitlines() == ["name       n   note", "a          10", "long name  2   x"]


# ---- bed fit -------------------------------------------------------------------------


def test_fits_bed():
    assert cadutil.fits_bed(box(200, 200, 100), DEFAULT)
    assert cadutil.fits_bed(box(220, 220, 5), DEFAULT)          # exactly the bed
    assert not cadutil.fits_bed(box(221, 100, 5), DEFAULT)
    assert not cadutil.fits_bed(box(100, 221, 5), DEFAULT)


def test_fits_bed_follows_the_bed_params():
    wp = box(150, 150, 5)
    assert cadutil.fits_bed(wp, DEFAULT)
    assert not cadutil.fits_bed(wp, Params(bed_x=140))
    assert not cadutil.fits_bed(wp, Params(bed_y=140))
