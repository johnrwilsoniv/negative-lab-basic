"""Shared helpers for measuring, posing and exporting the rig's solids.

Every function takes a `cq.Workplane` holding exactly one solid. Lengths are mm.
"""

from pathlib import Path
from typing import NamedTuple, Sequence

import cadquery as cq
from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib
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
