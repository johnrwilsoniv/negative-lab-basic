"""Lens adapter and thread coupon: placement, fits, and a real right-hand M67 x 0.75 thread.

The thread is read off sections through the lens axis. Each corner of a section is a corner of
the profile at that angle, so crest and root radii, flat widths and crest positions (hence pitch
and hand) come out exactly rather than sampled.
"""

import math
from itertools import pairwise

import cadquery as cq
import pytest

import cadutil
from params import DEFAULT
from parts.lens_adapter import model

p = DEFAULT
P = p.thread_pitch
X0 = p.x_front - p.thread_len     # the thread's free end, 120.5
X1 = p.x_front                    # flange face, 125
MOCKUP_GLASS_R = 30               # rebuild(): the lens front element, cyl(c, LENS_LEN - 12, LENS_LEN - 10, 30, ...)
# The swept thread faces are BSplines fitted to the helix: over 36 sections the crest radius is
# off by at most 7e-6. 1e-4 is still 1/1500 of the 0.15 clearance, so it can't hide a profile error.
TOL = 1e-4
ANGLES = (0, 90, 180, 270)
NAMES = ("adapter", "thread_coupon")


@pytest.fixture(scope="module")
def built():
    return model.build(p)


@pytest.fixture(scope="module")
def extra():
    return model.extras(p)


@pytest.fixture(scope="module")
def solids(built, extra):
    return {**built, **extra}


@pytest.fixture(scope="module")
def adapter(built):
    return built["adapter"]


@pytest.fixture(scope="module")
def coupon(extra):
    return extra["thread_coupon"]


def section(wp, degrees):
    """(x, r) of each corner of the section by the half-plane from the lens axis at `degrees`.

    0 degrees points +y and 90 points +z, so a growing angle is a right-hand turn about +x.
    """
    c, s = math.cos(math.radians(degrees)), math.sin(math.radians(degrees))
    corners = [(X0 - 5, 0), (X1 + 20, 0), (X1 + 20, 50), (X0 - 5, 50)]
    half_plane = cq.Face.makeFromWires(
        cq.Wire.makePolygon([cq.Vector(x, p.axis + r * c, r * s) for x, r in corners], close=True)
    )
    cut = cadutil.solid(wp).intersect(half_plane)
    points = (vertex.Center() for vertex in cut.Vertices())
    return sorted((v.x, math.hypot(v.y - p.axis, v.z)) for v in points)


def has_corner(corners, x, r, tol=TOL):
    return any(math.dist((x, r), corner) < tol for corner in corners)


def crest_flats(wp, degrees):
    """(start, end) x of each crest flat: corners at the crest radius, taken in pairs."""
    xs = [x for x, r in section(wp, degrees) if abs(r - p.thread_crest_r) < TOL]
    return list(zip(xs[::2], xs[1::2]))


def full_crests(wp, degrees):
    """Centres of the crest flats that the lead-in hasn't cut short."""
    return [(a + b) / 2 for a, b in crest_flats(wp, degrees) if abs(b - a - p.thread_crest_flat) < TOL]


# ---- both solids ---------------------------------------------------------------------


def test_solid_names_and_print_directions(built, extra):
    assert list(built) == ["adapter"]
    assert list(extra) == ["thread_coupon"]
    # socket opening / grip ring on the bed, thread on top
    assert model.PRINT_UP == {"adapter": "-x", "thread_coupon": "-x"}


@pytest.mark.parametrize("name", NAMES)
def test_one_valid_closed_solid(solids, name):
    solid = cadutil.solid(solids[name])          # raises unless exactly one
    assert solid.isValid()
    assert all(shell.Closed() for shell in solid.Shells())
    assert solid.Volume() > 0


@pytest.mark.parametrize("name", NAMES)
def test_prints_flat_with_the_thread_up_and_fits_the_bed(solids, name):
    posed = cadutil.print_pose(solids[name], model.PRINT_UP[name])
    assert cadutil.fits_bed(posed, p)
    dx, dy, dz = cadutil.size(posed)
    assert (dx, dy) == pytest.approx((2 * p.adapter_r, 2 * p.adapter_r), abs=0.05)

    def footprint(z0, z1):
        slab = cq.Workplane("XY").box(200, 200, z1 - z0, centered=(True, True, False)).translate((0, 0, z0))
        x0, x1, *_ = cadutil.common_bounds(posed, slab)
        return x1 - x0

    assert footprint(dz - 2, dz) == pytest.approx(2 * p.thread_crest_r, abs=TOL)   # thread at the top
    assert footprint(0, 1) == pytest.approx(2 * p.adapter_r, abs=TOL)              # Ø78 rim on the bed


# ---- adapter -------------------------------------------------------------------------


def test_adapter_bounds(adapter):
    r = p.adapter_r
    assert cadutil.bounds(adapter) == pytest.approx(
        (X0, X1 + p.flange + p.socket_depth, p.axis - r, p.axis + r, -r, r), abs=0.05
    )
    assert cadutil.size(adapter) == pytest.approx((16.5, 78, 78), abs=0.05)


@pytest.mark.parametrize("degrees", ANGLES)
def test_adapter_flange_and_socket_corners(adapter, degrees):
    corners = section(adapter, degrees)
    floor = X1 + p.flange            # 128: the socket floor, where the tube end sits
    rim = floor + p.socket_depth     # 137
    assert floor == p.tube_x0
    for x, r in [
        (X0, p.adapter_bore_r),
        (X0, p.thread_root_r),
        (X1, p.adapter_r),
        (rim, p.adapter_r),
        (rim, p.fit_r),
        (floor, p.fit_r),
        (floor, p.adapter_bore_r),
    ]:
        assert has_corner(corners, x, r, tol=1e-6), (x, r)


def test_bore_clears_the_lens_front_element(adapter):
    assert p.adapter_bore_r > MOCKUP_GLASS_R
    for degrees in ANGLES:
        assert min(r for _, r in section(adapter, degrees)) == pytest.approx(p.adapter_bore_r, abs=1e-6)


def test_socket_is_a_slip_fit_on_the_tube(adapter):
    socket_r = min(r for x, r in section(adapter, 0) if x > p.tube_x0 + 1e-6)
    assert socket_r - p.tube_ro == pytest.approx(p.fit_clear, abs=1e-6)
    assert p.fit_clear == 0.3


# ---- the thread ----------------------------------------------------------------------


@pytest.mark.parametrize("degrees", ANGLES)
def test_thread_crest_and_root_radii(adapter, degrees):
    thread = [r for x, r in section(adapter, degrees) if X0 + 1e-3 < x < X1 - 1e-3]
    assert max(thread) == pytest.approx(33.5 - p.thread_clear, abs=TOL)
    # ISO 68-1 external minor diameter d3 = d - 1.226869 P (66.08), moved in by the clearance
    assert min(thread) == pytest.approx((66.08 - 2 * p.thread_clear) / 2, abs=0.005)
    assert min(thread) == pytest.approx(p.thread_root_r, abs=TOL)


@pytest.mark.parametrize("degrees", ANGLES)
def test_thread_profile_is_iso_60_degrees(adapter, degrees):
    """Crest flats P/8 wide; 60 degree flanks down to the root leave a P/6 root flat, so each
    tooth is 5P/6 wide at the root."""
    corners = section(adapter, degrees)
    crests = [c for c in full_crests(adapter, degrees) if X0 + P < c < X1 - P]
    assert len(crests) >= 3
    for c in crests:
        assert has_corner(corners, c - P / 16, p.thread_crest_r)
        assert has_corner(corners, c + P / 16, p.thread_crest_r)
        assert has_corner(corners, c - 5 * P / 12, p.thread_root_r)
        assert has_corner(corners, c + 5 * P / 12, p.thread_root_r)


@pytest.mark.parametrize("degrees", ANGLES)
def test_crests_repeat_every_pitch_along_the_whole_thread(adapter, degrees):
    crests = full_crests(adapter, degrees)
    assert all(b - a == pytest.approx(P, abs=TOL) for a, b in pairwise(crests))
    assert crests[0] < X0 + 2 * P               # full height within the lead-in and one turn
    assert crests[-1] + P + P / 16 > X1         # no room for another full crest before the flange


def test_thread_stays_between_its_free_end_and_the_flange(adapter):
    for degrees in ANGLES:
        for x, r in section(adapter, degrees):
            if p.thread_root_r + TOL < r <= p.thread_crest_r + TOL:
                assert X0 <= x <= X1 + TOL, (x, r)


@pytest.mark.parametrize("degrees", ANGLES)
def test_lead_in_chamfers_the_free_end(adapter, degrees):
    """Within the first two turns every corner lies under the lead-in cone that rises from the
    root at the free end, so the first turn grows out of the core instead of ending in a
    full-height knife edge."""
    slope = math.tan(math.radians(p.thread_lead_in))
    first = [(x, r) for x, r in section(adapter, degrees) if x < X0 + 2 * P]
    assert all(r <= p.thread_root_r + (x - X0) * slope + TOL for x, r in first)
    assert any(p.thread_root_r + TOL < r < p.thread_crest_r - TOL for _, r in first)   # cut by the cone


def test_thread_is_right_handed(adapter):
    """A right-hand turn about +x carries each crest a quarter pitch toward +x per 90 degrees.

    So, seen from the light side, turning the adapter clockwise screws it toward the camera,
    into the lens's standard right-hand filter thread. A left-hand thread would give 3P/4.
    """
    first = {d: full_crests(adapter, d)[0] for d in ANGLES}
    for d in ANGLES:
        assert (first[(d + 90) % 360] - first[d]) % P == pytest.approx(P / 4, abs=TOL)


# ---- coupon --------------------------------------------------------------------------


def test_coupon_bounds(coupon):
    r = p.adapter_r
    assert cadutil.bounds(coupon) == pytest.approx(
        (X0, X1 + p.coupon_grip, p.axis - r, p.axis + r, -r, r), abs=0.05
    )


@pytest.mark.parametrize("degrees", ANGLES)
def test_coupon_has_the_adapters_thread(adapter, coupon, degrees):
    def thread(wp):
        return [(x, r) for x, r in section(wp, degrees) if x <= X1 + TOL and r < p.adapter_r - TOL]

    ours, theirs = thread(coupon), thread(adapter)
    assert len(ours) == len(theirs)
    assert all(math.dist(a, b) < TOL for a, b in zip(ours, theirs))
    assert full_crests(coupon, degrees) == pytest.approx(full_crests(adapter, degrees), abs=TOL)


@pytest.mark.parametrize("degrees", ANGLES)
def test_coupon_grip_ring(coupon, degrees):
    corners = section(coupon, degrees)
    top = X1 + p.coupon_grip
    for x, r in [(X1, p.adapter_r), (top, p.adapter_r), (top, p.adapter_bore_r), (X0, p.adapter_bore_r)]:
        assert has_corner(corners, x, r, tol=1e-6), (x, r)
