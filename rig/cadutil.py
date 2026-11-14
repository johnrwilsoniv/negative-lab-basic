"""Shared helpers for measuring, posing and exporting the rig's solids.

Every function takes a `cq.Workplane` holding exactly one solid. Lengths are mm.
"""

import math
from pathlib import Path
from typing import NamedTuple, Sequence

import cadquery as cq
from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepGProp import BRepGProp_Face
from OCP.gp import gp_Pnt, gp_Vec
from OCP.IFSelect import IFSelect_ReturnStatus
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
from OCP.TopExp import TopExp_Explorer
from OCP.TopTools import TopTools_IndexedMapOfShape

from params import Params

Bounds = tuple[float, float, float, float, float, float]   # xmin xmax ymin ymax zmin zmax

# A STEP round trip keeps the exact BRep, so volumes agree to ~1e-13 on planes and cylinders.
# 1e-6 leaves headroom for integrating thread (BSpline) surfaces (the M67 thread measures 1.0e-7
# on the adapter, 3.4e-7 on the coupon), yet any lost or reshaped feature, or a unit mix-up,
# changes a volume by far more.
STEP_VOLUME_RTOL = 1e-6

# STL deflection: fine enough for the 0.75 mm thread pitch. Absolute, not relative to edge size.
STL_LINEAR_TOL = 0.01
STL_ANGULAR_TOL = 0.1

# For each print-up direction, the rotation (axis, degrees) that takes it to +Z.
_UP_ROTATION: dict[str, tuple[tuple[float, float, float], float]] = {
    "+z": ((0, 0, 1), 0),
    "-z": ((1, 0, 0), 180),
    "+x": ((0, 1, 0), -90),
    "-x": ((0, 1, 0), 90),
    "+y": ((1, 0, 0), 90),
    "-y": ((1, 0, 0), -90),
}


def solid(wp: cq.Workplane) -> cq.Solid:
    """The one solid in `wp`; ValueError if there are none or several."""
    solids = [s for shape in wp.vals() for s in shape.Solids()]
    if len(solids) != 1:
        raise ValueError(f"expected exactly 1 solid, found {len(solids)} solids")
    return solids[0]


def non_manifold_edges(wp: cq.Workplane) -> list[cq.Edge]:
    """The edges not used exactly twice by the solid's faces (a seam is used twice by its one face).

    OCC's isValid() passes a solid whose parts meet only along an edge (4 faces on it); Onshape's Parasolid
    marks it faulty, so a solid with any of these will not import cleanly.
    """
    edges = TopTools_IndexedMapOfShape()
    uses: dict[int, int] = {}
    faces = TopExp_Explorer(solid(wp).wrapped, TopAbs_FACE)
    while faces.More():
        found = TopExp_Explorer(faces.Current(), TopAbs_EDGE)
        while found.More():
            i = edges.Add(found.Current())          # same index for the same edge, whatever its orientation
            uses[i] = uses.get(i, 0) + 1
            found.Next()
        faces.Next()
    return [cq.Edge(edges.FindKey(i)) for i, n in sorted(uses.items()) if n != 2]


def is_valid(wp: cq.Workplane) -> bool:
    """OCC's check, and every edge between exactly two faces (see non_manifold_edges)."""
    return solid(wp).isValid() and not non_manifold_edges(wp)


def volume(wp: cq.Workplane) -> float:
    return solid(wp).Volume()


def _bounds(shape: cq.Shape) -> Bounds:
    # CadQuery's BoundingBox() asks for the triangulation, which grows the box by the mesh
    # deflection once a shape has been exported. Measure the geometry alone.
    box = Bnd_Box()
    BRepBndLib.AddOptimal_s(shape.wrapped, box, False, False)
    xmin, ymin, zmin, xmax, ymax, zmax = box.Get()
    return xmin, xmax, ymin, ymax, zmin, zmax


def bounds(wp: cq.Workplane) -> Bounds:
    """Exact (xmin, xmax, ymin, ymax, zmin, zmax)."""
    return _bounds(solid(wp))


def shape_bounds(shape: cq.Shape) -> Bounds:
    """Exact bounds of any shape, such as a compound of several solids (`bounds` takes one solid)."""
    return _bounds(shape)


def size(wp: cq.Workplane) -> tuple[float, float, float]:
    xmin, xmax, ymin, ymax, zmin, zmax = bounds(wp)
    return xmax - xmin, ymax - ymin, zmax - zmin


def _common(a: cq.Workplane, b: cq.Workplane) -> cq.Shape | None:
    common = solid(a).intersect(solid(b))
    return common if common.Solids() else None


def common_volume(a: cq.Workplane, b: cq.Workplane) -> float:
    """Volume of the boolean intersection; 0.0 when they only touch or are apart."""
    common = _common(a, b)
    return 0.0 if common is None else common.Volume()


def common_bounds(a: cq.Workplane, b: cq.Workplane) -> Bounds | None:
    """Bounds of the intersection, or None when they only touch or are apart."""
    common = _common(a, b)
    return None if common is None else _bounds(common)


def common_pieces(a: cq.Workplane, b: cq.Workplane) -> list[tuple[float, Bounds]]:
    """Volume and exact bounds of each separate solid in the intersection; empty when they only touch or are apart."""
    common = _common(a, b)
    return [] if common is None else [(s.Volume(), _bounds(s)) for s in common.Solids()]


def probe(x0: float, x1: float, y0: float, y1: float, z0: float, z1: float) -> cq.Workplane:
    """A box over the given ranges, to take a slice out of a solid with `common_bounds` / `common_volume`."""
    return cq.Workplane("XY").box(x1 - x0, y1 - y0, z1 - z0, centered=False).translate((x0, y0, z0))


# ---- assembly marks (F18): shallow recesses cut into a face that prints as a top layer, or along an upright one ----
MARK_OVERCUT = 0.1          # each mark's cutter starts this far outside the face, so the cut leaves no skin


def face_plane(origin: tuple[float, float, float], normal: tuple[float, float, float],
               up: tuple[float, float, float]) -> cq.Plane:
    """The plane of a face, MARK_OVERCUT outside it, with +u to the right and +v up for someone looking at the face."""
    n, u = cq.Vector(normal), cq.Vector(up)
    return cq.Plane(origin=(cq.Vector(origin) + n * MARK_OVERCUT).toTuple(), xDir=(-n).cross(u).toTuple(), normal=n.toTuple())


def _into(wp: cq.Workplane, depth: float) -> cq.Workplane:
    return wp.extrude(-(depth + MARK_OVERCUT))


def mark_triangle(plane: cq.Plane, u: float, v: float, size: float, depth: float) -> cq.Workplane:
    """A ▲ `size` wide and tall centred on (u, v), pointing +v, `depth` into the face."""
    h = size / 2
    return _into(cq.Workplane(plane).polyline([(u, v + h), (u - h, v - h), (u + h, v - h)]).close(), depth)


def mark_padlock(plane: cq.Plane, u: float, v: float, depth: float, shut: bool) -> cq.Workplane:
    """A padlock, shackle toward +v: a 4.4 x 3.4 body (0.6 corners) under a Ø3.2 shackle of 0.8 strokes (two 0.4
    lines). Shut, both legs run into the body; open, the shackle stands 1 higher and its +u leg stops short. (u, v)
    is 1.2 above the body's centre, so either one spans v - 2.9 .. v + 2.9 (shut) or v + 3.9 (open)."""
    R, r, body_top = 1.6, 0.8, v + 0.5
    ac = body_top + 0.8 + (0 if shut else 1.0)          # the shackle's centre
    leg_w, leg_u = R - r, (R + r) / 2

    def wp():
        return cq.Workplane(plane)

    def leg(lu: float, v0: float, v1: float) -> cq.Workplane:
        return _into(wp().center(lu, (v0 + v1) / 2).rect(leg_w, v1 - v0), depth)

    body = _into(wp().center(u, v - 1.2).sketch().rect(4.4, 3.4).vertices().fillet(0.6).finalize(), depth)
    arc = _into(wp().center(u, ac).circle(R).circle(r), depth).intersect(
        _into(wp().center(u, ac + R).rect(2 * R + 1, 2 * R), depth))
    icon = body.union(arc).union(leg(u - leg_u, body_top - 0.3, ac))
    return icon.union(leg(u + leg_u, (body_top - 0.3) if shut else (ac - 0.5), ac))


def cut_marks(wp: cq.Workplane, marks: Sequence[cq.Workplane]) -> cq.Workplane:
    """`wp` less each mark's cutter."""
    for m in marks:
        wp = wp.cut(m)
    return wp


def print_pose(wp: cq.Workplane, up: str) -> cq.Workplane:
    """Rotate so mockup direction `up` ("+x" ... "-z") points +Z.

    The result sits on Z = 0, centred on X = Y = 0.
    """
    if up not in _UP_ROTATION:
        raise ValueError(f"up must be one of {sorted(_UP_ROTATION)}, got {up!r}")
    axis, degrees = _UP_ROTATION[up]
    rotated = cq.Workplane("XY").add(solid(wp).rotate(cq.Vector(0, 0, 0), cq.Vector(*axis), degrees))
    xmin, xmax, ymin, ymax, zmin, _ = bounds(rotated)
    return rotated.translate((-(xmin + xmax) / 2, -(ymin + ymax) / 2, -zmin))


def sloped_faces(wp: cq.Workplane, tol: float = 1e-9) -> list[cq.Face]:
    """The plane faces of the solid, as it is posed, that are neither level nor upright: the ones printing in
    layers along Z turns into steps. Curved faces are not judged."""
    return [
        face for face in solid(wp).Faces()
        if face.geomType() == "PLANE" and tol < abs(face.normalAt().z) < 1 - tol
    ]


OVERHANG_ANGLE = 45.0      # degrees from vertical: a face leaning out further than this needs support or bridging


def overhangs(wp: cq.Workplane, angle: float = OVERHANG_ANGLE, on_bed: float = 1e-3) -> list[cq.Face]:
    """The faces of the solid, as it is posed (Z up, on Z = 0), that lean out more than `angle` from vertical
    somewhere: downward faces that would print over air. Faces lying on the bed are not counted (a face that only
    touches it still is). Curved faces are sampled on a 5 x 5 grid of their parameters, plane faces at their normal."""
    limit = -math.sin(math.radians(angle)) - 1e-6
    found = []
    for face in solid(wp).Faces():
        if _bounds(face)[5] < on_bed:
            continue
        if face.geomType() == "PLANE":
            normals = [face.normalAt()]
        else:
            u0, u1, v0, v1 = face._uvBounds()
            props, pnt, vec = BRepGProp_Face(face.wrapped), gp_Pnt(), gp_Vec()
            normals = []
            for i in range(5):
                for j in range(5):
                    props.Normal(u0 + (u1 - u0) * i / 4, v0 + (v1 - v0) * j / 4, pnt, vec)     # outward, as oriented
                    if vec.Magnitude() > 1e-12:
                        normals.append(cq.Vector(vec.X(), vec.Y(), vec.Z()).normalized())
        if any(n.z < limit for n in normals):
            found.append(face)
    return found


def export(wp: cq.Workplane, step_path: str | Path, stl_path: str | Path) -> None:
    """Write the solid as STEP and STL, creating folders as needed."""
    shape = solid(wp)
    for path in (step_path, stl_path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    if shape.exportStep(str(step_path)) != IFSelect_ReturnStatus.IFSelect_RetDone:
        raise RuntimeError(f"STEP export to {step_path} failed")
    if not shape.exportStl(
        str(stl_path), tolerance=STL_LINEAR_TOL, angularTolerance=STL_ANGULAR_TOL, relative=False
    ):
        raise RuntimeError(f"STL export to {stl_path} failed")


def step_volume(path: str | Path) -> float:
    """Volume of the solid in a STEP file; ValueError unless it holds exactly one."""
    return volume(cq.importers.importStep(str(path)))


class StepPart(NamedTuple):
    solid: cq.Workplane
    color: tuple[float, float, float, float] | None     # RGBA, or None if the file gives it none


def step_assembly(path: str | Path) -> dict[str, StepPart]:
    """The named solids of a multi-solid STEP file, in the file's coordinates, with their colours.

    ValueError if a named part is not exactly one solid, or two parts share a name.
    """
    read: dict[str, StepPart] = {}
    for child in cq.Assembly.importStep(str(path)).children:
        if child.name in read:
            raise ValueError(f"{path}: two parts are named {child.name!r}")
        wp = cq.Workplane("XY").add(child.obj)
        solid(wp)       # exactly one solid
        read[child.name] = StepPart(wp, None if child.color is None else child.color.toTuple())
    return read


def format_table(lines: Sequence[Sequence[str]]) -> str:
    """Text columns, each as wide as its widest cell; the first line is the header."""
    widths = [max(len(line[i]) for line in lines) for i in range(len(lines[0]))]
    return "\n".join("  ".join(c.ljust(w) for c, w in zip(line, widths)).rstrip() for line in lines)


def fits_bed(wp: cq.Workplane, p: Params) -> bool:
    """Whether the footprint, as the solid is posed, is within the bed (`bed_x` by `bed_y`)."""
    dx, dy, _ = size(wp)
    return dx <= p.bed_x + 1e-6 and dy <= p.bed_y + 1e-6


def box(x0: float, x1: float, y0: float, y1: float, z0: float, z1: float) -> cq.Workplane:
    """A solid box over the given ranges (the same as `probe`, named for building)."""
    return probe(x0, x1, y0, y1, z0, z1)


def cylinder_y(x: float, z: float, r: float, y0: float, y1: float) -> cq.Workplane:
    """A cylinder of radius r along y, from y0 to y1, on the line (x, z)."""
    return cq.Workplane("XZ", origin=(0, y1, 0)).center(x, z).circle(r).extrude(y1 - y0)


def teardrop_y(x: float, z: float, r: float, y0: float, y1: float, point: str = "-x") -> cq.Workplane:
    """A cylinder of radius r along y, from y0 to y1, with a 45 degree point toward `point` ("-x" or "+x"): a hole
    through a part that prints with that side up, so its roof leans 45 degrees instead of hanging flat."""
    s = {"-x": -1, "+x": 1}[point]
    k = r / math.sqrt(2)
    kite = [(x + s * r * math.sqrt(2), z), (x + s * k, z + k), (x, z), (x + s * k, z - k)]
    wedge = cq.Workplane("XZ", origin=(0, y1, 0)).polyline(kite).close().extrude(y1 - y0)
    return cylinder_y(x, z, r, y0, y1).union(wedge)
