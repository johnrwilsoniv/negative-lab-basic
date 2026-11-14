"""The changes after the first print (2026-11-14), measured on the built solids.

F23: the tube is Ø68.5, a friction fit in the Ø68.6 sockets, which keep their size.
F24: the gate front's socket is 9 deep, the extra 5 toward the camera. The tube keeps its 98 length and its place: the
socket's floor has not moved, and the film is 5 further from the lens (wd 116), so the gate front grows 5 at each end.
F25: the lid's slot is as wide as the tab, so the tab locates the lid along x.
"""

import cadquery as cq
import pytest

import assembly
import cadutil
import fits
from cadutil import probe
from params import DEFAULT, Params
from parts.film_gate import model as gate
from parts.lens_adapter import model as adapter
from parts.light_dock import model as dock
from parts.lock_switch import model as switch
from parts.tube import model as tube

p = DEFAULT
EPS = 1e-6
T = 0.02
# the design as first printed: wd 111, the gate front's socket 4 deep, the tube Ø68 in Ø68.6 sockets, the tab 0.5 clear
# each side in the lid's slot, the gate screws' counterbores 3.5 deep
BEFORE = Params(wd=111, gate_front=14, front_wall=4, tube_ro=34, fit_clear=0.3, tab_clear=0.5, cbore_depth=3.5)


@pytest.fixture(scope="module")
def slide():
    return assembly.placed(p, False)


@pytest.fixture(scope="module")
def locked():
    return assembly.placed(p, True)


def rod(x, length, r):
    return cq.Workplane("YZ", origin=(x, p.axis, 0)).circle(r).extrude(length)


def filled(wp, *ranges):
    pr = probe(*ranges)
    return cadutil.common_volume(wp, pr) / cadutil.volume(pr)


# ---- F23 · the tube is a friction fit --------------------------------------------------------------------


def test_the_tube_is_68_5_across_and_its_bore_is_unchanged():
    assert (2 * p.tube_ro, 2 * p.tube_ri) == (68.5, 64)
    t = tube.build(p)["tube"]
    _, _, y0, y1, z0, z1 = cadutil.bounds(t)
    assert (y1 - y0, z1 - z0) == pytest.approx((68.5, 68.5), abs=EPS)
    assert p.tube_ri - p.baffle_h == p.adapter_bore_r                    # the ribs still stop at the adapter's bore


def test_the_sockets_keep_their_68_6():
    assert 2 * p.fit_r == pytest.approx(68.6)
    assert p.fit_clear == pytest.approx(0.05)
    a = adapter.build(p)["adapter"]
    floor = p.x_front + p.flange
    assert cadutil.common_volume(a, rod(floor, p.socket_depth, p.fit_r - T)) < 1e-3
    assert cadutil.common_volume(a, rod(floor, p.socket_depth, p.fit_r + T)) > 1.0


@pytest.mark.parametrize("socket", ["adapter", "gate_front"])
def test_the_tube_has_0_05_all_round_in_each_socket(slide, socket):
    x0 = cadutil.bounds(slide["tube" if socket == "adapter" else socket])[0]
    gap, note = fits._radial_clearance(slide["tube"], slide[socket], p, x0)
    assert gap == pytest.approx(0.05, abs=1e-5)
    assert note == ""                                                    # walled on every side: R8 still closed


def test_the_tube_goes_into_each_socket_without_touching_it(slide):
    for name in ("adapter", "gate_front"):
        assert cadutil.common_volume(slide["tube"], slide[name]) < 1e-3, name


def test_the_socket_still_leaves_1_7_over_it():
    assert p.gh - p.axis - p.fit_r == pytest.approx(1.7)


def test_the_dock_u_is_still_1_clear_of_the_wider_tube():
    d = dock.build(p)["light_dock"]
    x0, x1 = p.dock_x0, p.x_gate - p.dock_gate_clear
    clear = cq.Workplane("YZ", origin=(x0, 0, 0)).center(p.axis, 0).circle(p.tube_ro + 1).extrude(x1 - x0)
    assert cadutil.common_volume(d, clear) < 1e-3
    assert cadutil.common_volume(d, clear.translate((0, -T, 0))) > 0    # and no more than 1 below it
    assert p.axis - p.tube_ro - p.dock_tube_clear == pytest.approx(5.25)


# ---- F24 · a 9 deep gate socket, wd 116 ------------------------------------------------------------------


def test_wd_is_116_and_the_tube_still_98():
    assert p.wd == 116
    assert (p.tube_x0, p.tube_x1, p.tube_len) == (128, 226, 98)
    assert p.tube_len == p.wd - 18
    t = tube.build(p)["tube"]
    assert cadutil.bounds(t)[:2] == pytest.approx((128, 226), abs=EPS)


def test_the_socket_floor_and_the_tube_have_not_moved():
    assert (p.tube_x0, p.tube_x1) == (BEFORE.tube_x0, BEFORE.tube_x1)
    assert BEFORE.tube_len == p.tube_len


def test_the_gate_front_grew_5_toward_the_camera_and_5_toward_the_light():
    assert (p.gate_front, p.front_wall) == (24, 9)
    assert p.x_gate == BEFORE.x_gate - 5 == 217
    assert p.x_ref == BEFORE.x_ref + 5 == 240.7
    assert p.x_film - p.x_front == 116
    f = gate.gate_front(p)
    assert cadutil.bounds(f) == pytest.approx((217, 240.7, 0, 76.5, -55, 55), abs=EPS)
    assert cadutil.size(cadutil.print_pose(f, gate.PRINT_UP["gate_front"])) == pytest.approx((110, 76.5, 23.7), abs=EPS)


def test_the_gate_front_socket_is_9_deep_and_the_tube_sits_on_its_floor():
    f = gate.gate_front(p)
    assert cadutil.common_volume(f, rod(217, 9, p.fit_r - T)) < 1e-3       # clear from the front face to the floor
    assert cadutil.common_volume(f, rod(217, 9, p.fit_r + T)) > 1.0         # and walled beyond
    ring = rod(226, 0.5, p.tube_ro).cut(rod(226, 0.5, p.tube_ri + 1e-4))      # the floor under the whole tube wall
    assert cadutil.common_volume(f, ring) == pytest.approx(cadutil.volume(ring), rel=1e-6)
    assert cadutil.bounds(tube.build(p)["tube"])[1] == pytest.approx(226, abs=EPS)


def test_the_tube_is_held_9_deep_at_each_end(slide):
    t = cadutil.bounds(slide["tube"])
    assert (p.x_front + p.flange + p.socket_depth) - t[0] == pytest.approx(9)        # in the adapter
    assert t[1] - cadutil.bounds(slide["gate_front"])[0] == pytest.approx(9)         # in the gate front
    assert cadutil.bounds(slide["gate_front"])[0] - (p.x_front + p.flange + p.socket_depth) == pytest.approx(80)


def test_the_light_passage_is_5_longer_and_still_only_widens_toward_the_camera():
    f = gate.gate_front(p)
    floor, window = 226, p.x_ref - p.plate_t
    assert window - floor == pytest.approx(12.9)
    a = p.axis
    assert filled(f, floor, p.x_ref, a - 13 + T, a + 13 - T, -19 + T, 19 - T) < EPS        # the window's outline, all the way
    assert cadutil.overhangs(cadutil.print_pose(f, gate.PRINT_UP["gate_front"])) == []


def test_the_m3_x_20_screws_still_bite_9_8():
    f = gate.gate_front(p)
    shank = (p.x_ref - p.x_gate) - p.cbore_depth
    assert (p.cbore_depth, shank, 20 - shank) == pytest.approx((13.5, 10.2, 9.8))
    assert 20 - shank < p.pilot_depth
    for y, z in p.screw_points:                         # the counterbore r 3.25 to 13.5 deep, then the r 1.7 hole
        assert filled(f, 217, 230.49, y - 3.2, y + 3.2, z - 0.05, z + 0.05) < EPS
        assert filled(f, 230.51, 240.7, y + 1.71, y + 1.71 + T, z - 0.05, z + 0.05) > 1 - EPS
        assert filled(f, 230.51, 240.7, y - 1.65, y + 1.65, z - 0.05, z + 0.05) < EPS


def test_the_dock_runs_10_further_forward_and_still_holds_the_gate(slide):
    assert p.dock_x0 == pytest.approx(212.8)
    assert p.dock_x1 - p.dock_x0 == pytest.approx(79.7)
    seat = fits._gate_seat(slide, p)
    assert seat["front"] == pytest.approx(p.dock_gate_clear, abs=1e-5)
    assert seat["light"] == pytest.approx(0, abs=1e-5)
    assert cadutil.fits_bed(cadutil.print_pose(dock.build(p)["light_dock"], dock.PRINT_UP["light_dock"]), p)


def test_the_gate_body_and_plates_only_moved_back_5():
    for name, build in (("gate_body", gate.gate_body), ("pressure_plate", gate.pressure_plate),
                        ("wedge_plate", switch.wedge_plate)):
        now, then = build(p), build(BEFORE)
        assert cadutil.bounds(now) == pytest.approx(cadutil.bounds(then.translate((5, 0, 0))), abs=EPS), name
        assert cadutil.volume(now) == pytest.approx(cadutil.volume(then), rel=1e-6), name


def test_the_tube_and_the_adapter_grew_only_by_the_wider_tube():
    then, now = tube.build(BEFORE)["tube"], tube.build(p)["tube"]
    assert cadutil.bounds(now)[:2] == pytest.approx(cadutil.bounds(then)[:2], abs=EPS)
    ring = 3.14159265358979 * (34.25**2 - 34**2) * 98
    assert cadutil.volume(now) - cadutil.volume(then) == pytest.approx(ring, rel=1e-6)
    assert cadutil.volume(adapter.build(p)["adapter"]) == pytest.approx(cadutil.volume(adapter.build(BEFORE)["adapter"]), rel=1e-9)


# ---- F25 · the lid's slot is as wide as the tab ----------------------------------------------------------


def test_the_lid_slot_is_the_tab_s_2_by_16():
    assert (p.tab_t, p.tab_clear) == (2, 0)
    lid = gate.gate_lid(p)
    y = (p.gh - p.wall + 0.5, p.gh - 0.5)                               # within the lid's thickness, under its top
    half = p.sw_travel / 2 + p.slot_end
    x0, x1 = p.x_wedge, p.x_wedge + p.tab_t
    assert filled(lid, x0 + T, x1 - T, *y, -half + T, half - T) < EPS                 # open over the tab's 2
    assert filled(lid, x0 - T, x0, *y, -half + T, half - T) > 1 - EPS                  # and no wider
    assert filled(lid, x1, x1 + T, *y, -half + T, half - T) > 1 - EPS
    assert filled(lid, x0 + T, x1 - T, *y, half, half + T) > 1 - EPS                   # still 16 long
    assert filled(lid, x0 + T, x1 - T, *y, -half - T, -half) > 1 - EPS


@pytest.mark.parametrize("lock", [False, True])
def test_the_tab_fills_the_slot_s_width_without_interfering(slide, locked, lock):
    s = locked if lock else slide
    gap = fits._tab_slot(s, p)
    assert (gap["front"], gap["rear"]) == pytest.approx((0, 0), abs=1e-5)
    assert gap["z"] == pytest.approx(p.slot_end - p.tab_w / 2, abs=1e-5)                # along z it still slides
    assert cadutil.common_volume(s["wedge_plate"], s["gate_lid"]) < 1e-3


def test_only_the_slot_changed_on_the_lid():
    now, then = gate.gate_lid(p), gate.gate_lid(BEFORE).translate((5, 0, 0))
    assert cadutil.bounds(now) == pytest.approx(cadutil.bounds(then), abs=EPS)
    assert cadutil.volume(now) - cadutil.volume(then) == pytest.approx(1 * 16 * 3, rel=1e-6)     # 1 narrower, 16 x 3
    half = p.sw_travel / 2 + p.slot_end
    for z0, z1 in ((half + 0.01, 46), (-46, -half - 0.01)):          # beyond the slot's ends, padlocks and all: the same
        box = probe(p.x_ref, p.x_light, p.gh - p.wall, p.gh, z0, z1)
        assert cadutil.common_volume(now, box) == pytest.approx(cadutil.common_volume(then, box), rel=1e-6)
