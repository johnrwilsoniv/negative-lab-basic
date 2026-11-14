"""The changes after the first print (2026-11-14), measured on the built solids.

The print was of main's clamp gate (lid, plates, lock switch). Its fit fixes for the tube and the gate front's socket
carry over to this gate (D1, D2) unchanged; the lid's slot (F25) and the screws' counterbores have no home here.

F23: the tube is Ø68.5, a friction fit in the Ø68.6 sockets, which keep their size.
F24: the gate front's socket is 9 deep, the extra 5 toward the camera. The tube keeps its 98 length and its place: the
socket's floor has not moved, and the film is 5 further from the lens (wd 116), so the gate front grows 5 at each end.
Everything from the reference plane back (the gate body, the film drive, the spools, the dock) only moves 5 with the
film: the drive is untouched.
"""

import cadquery as cq
import pytest

import assembly
import cadutil
import fits
from cadutil import probe
from params import DEFAULT, Params
from parts.film_drive import model as drive
from parts.film_gate import model as gate
from parts.lens_adapter import model as adapter
from parts.light_dock import model as dock
from parts.spools import model as spools
from parts.tube import model as tube

p = DEFAULT
EPS = 1e-6
T = 0.02
# the dimensions as first printed: wd 111, the gate front's socket 4 deep, the tube Ø68 in Ø68.6 sockets
BEFORE = Params(wd=111, gate_front=14, front_wall=4, tube_ro=34, fit_clear=0.3)


@pytest.fixture(scope="module")
def framed():
    return assembly.placed(p)


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
def test_the_tube_has_0_05_all_round_in_each_socket(framed, socket):
    x0 = cadutil.bounds(framed["tube" if socket == "adapter" else socket])[0]
    gap, note = fits._radial_clearance(framed["tube"], framed[socket], p, x0)
    assert gap == pytest.approx(0.05, abs=1e-5)
    assert note == ""                                                    # walled on every side: R8 still closed


def test_the_tube_goes_into_each_socket_without_touching_it(framed):
    for name in ("adapter", "gate_front"):
        assert cadutil.common_volume(framed["tube"], framed[name]) < 1e-3, name


def test_the_socket_still_leaves_1_7_over_it():
    assert p.gh - p.axis - p.fit_r == pytest.approx(1.7)


def test_the_dock_floor_is_still_1_clear_of_the_wider_tube():
    d = dock.build(p)["light_dock"]
    x0, x1 = p.dock_x0, p.x_gate - p.dock_gate_clear
    clear = cq.Workplane("YZ", origin=(x0, 0, 0)).center(p.axis, 0).circle(p.tube_ro + 1).extrude(x1 - x0)
    assert cadutil.common_volume(d, clear) < 1e-3
    assert p.axis - p.tube_ro - p.dock_tube_clear == pytest.approx(5.25)       # 1.25 above the floor's top: no trough
    assert filled(d, x0, x1, 0, p.floor_t, -40, 40) > 1 - EPS


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
    assert p.x_ref == pytest.approx(BEFORE.x_ref + 5) == pytest.approx(240.85)
    assert p.x_film - p.x_front == 116
    f = gate.gate_front(p)
    assert cadutil.bounds(f) == pytest.approx((217, 240.85, 0, 76.5, -46, 46), abs=EPS)
    assert cadutil.size(cadutil.print_pose(f, gate.PRINT_UP["gate_front"])) == pytest.approx((92, 76.5, 23.85), abs=EPS)


def test_the_gate_front_socket_is_9_deep_and_the_tube_sits_on_its_floor():
    f = gate.gate_front(Params(mark_depth=0))                               # the ▲ (F18) is 0.36 into this floor
    assert cadutil.common_volume(f, rod(217, 9, p.fit_r - T)) < 1e-3       # clear from the front face to the floor
    assert cadutil.common_volume(f, rod(217, 9, p.fit_r + T)) > 1.0         # and walled beyond
    ring = rod(226, 0.5, p.tube_ro).cut(rod(226, 0.5, p.tube_ri + 1e-4))      # the floor under the whole tube wall
    assert cadutil.common_volume(f, ring) == pytest.approx(cadutil.volume(ring), rel=1e-6)
    assert cadutil.bounds(tube.build(p)["tube"])[1] == pytest.approx(226, abs=EPS)


def test_the_tube_is_held_9_deep_at_each_end(framed):
    t = cadutil.bounds(framed["tube"])
    assert (p.x_front + p.flange + p.socket_depth) - t[0] == pytest.approx(9)        # in the adapter
    assert t[1] - cadutil.bounds(framed["gate_front"])[0] == pytest.approx(9)         # in the gate front
    assert cadutil.bounds(framed["gate_front"])[0] - (p.x_front + p.flange + p.socket_depth) == pytest.approx(80)


def test_the_light_passage_is_5_longer_and_still_only_widens_toward_the_camera():
    f = gate.gate_front(p)
    floor, window = p.x_gate + p.front_wall, p.x_ref - p.win_depth
    assert floor == 226
    assert window - floor == pytest.approx(13.05)
    assert window - floor == pytest.approx((BEFORE.x_ref - BEFORE.win_depth) - (BEFORE.x_gate + BEFORE.front_wall) + 5)
    a = p.axis
    assert filled(f, floor, p.x_ref, a - 13 + T, a + 13 - T, -19 + T, 19 - T) < EPS        # the window's outline, all the way
    # it prints as before: only the four tooth grooves are bridged (D3)
    assert len(cadutil.overhangs(cadutil.print_pose(f, gate.PRINT_UP["gate_front"]))) == 4


def test_the_peg_holes_still_run_right_through_the_deeper_front():
    f = gate.gate_front(p)
    h = p.peg_d / 2 / 2 ** 0.5 - T
    for y, z in p.peg_points:
        assert filled(f, p.x_gate, p.x_ref, y - h, y + h, z - h, z + h) < EPS
    assert [y for y, _ in p.peg_points] == pytest.approx([10, 10, 68.5, 68.5])
    assert p.peg_len < p.x_ref - p.x_gate


def test_the_dock_moved_back_5_with_the_film_and_its_notch_is_10_longer(framed):
    assert p.dock_x0 == pytest.approx(BEFORE.dock_x0 + 5) and p.dock_x1 == pytest.approx(BEFORE.dock_x1 + 5) == 292.5
    now, then = dock.build(p)["light_dock"], dock.build(BEFORE)["light_dock"]
    assert cadutil.bounds(now) == pytest.approx(cadutil.bounds(then.translate((5, 0, 0))), abs=EPS)
    notch_w = p.gw + 2 * p.dock_gate_clear
    assert cadutil.volume(then) - cadutil.volume(now) == pytest.approx(10 * p.floor_t * notch_w, rel=1e-6)
    # the floor in front of the gate, which stops the gate front, is 17 long (27 before)
    assert (p.x_gate - p.dock_gate_clear) - p.dock_x0 == pytest.approx(BEFORE.x_gate - 0.2 - BEFORE.dock_x0 - 10)
    seat = fits._gate_seat(framed, p)
    assert seat["front"] == pytest.approx(p.dock_gate_clear, abs=1e-5)
    assert seat["light"] == pytest.approx(0, abs=1e-5)
    assert cadutil.fits_bed(cadutil.print_pose(now, dock.PRINT_UP["light_dock"]), p)


def test_the_gate_body_the_drive_and_the_spools_only_moved_back_5():
    """Everything from the reference plane back is the same solid, 5 further from the lens: the sprockets, the gears,
    the idler and its axle, the deck, the spools and their caps, and the body they stand in."""
    now = {"gate_body": gate.gate_body(p), **drive.build(p), **spools.build(p)}
    then = {"gate_body": gate.gate_body(BEFORE), **drive.build(BEFORE), **spools.build(BEFORE)}
    assert sorted(now) == sorted([
        "gate_body", "sprocket_supply", "gear_supply", "sprocket_takeup", "gear_takeup", "idler", "idler_axle", "deck",
        "spool_supply", "cap_supply", "spool_takeup", "cap_takeup"])
    for name in now:
        assert cadutil.bounds(now[name]) == pytest.approx(cadutil.bounds(then[name].translate((5, 0, 0))), abs=EPS), name
        assert cadutil.volume(now[name]) == pytest.approx(cadutil.volume(then[name]), rel=1e-9), name
        assert cadutil.common_volume(now[name], then[name].translate((5, 0, 0))) == pytest.approx(
            cadutil.volume(now[name]), rel=1e-6), name


def test_the_spools_are_still_3_clear_of_the_longer_gate_front():
    flange = cadutil.bounds(spools.spool(p, "takeup"))
    assert flange[4] - p.gw / 2 == pytest.approx(p.spool_gap) == 3
    assert flange[0] < p.x_ref and flange[1] > p.x_gate            # beside the gate front, not in front of it


def test_the_tube_and_the_adapter_grew_only_by_the_wider_tube():
    then, now = tube.build(BEFORE)["tube"], tube.build(p)["tube"]
    assert cadutil.bounds(now)[:2] == pytest.approx(cadutil.bounds(then)[:2], abs=EPS)
    ring = 3.14159265358979 * (34.25**2 - 34**2) * 98
    assert cadutil.volume(now) - cadutil.volume(then) == pytest.approx(ring, rel=1e-6)
    assert cadutil.volume(adapter.build(p)["adapter"]) == pytest.approx(cadutil.volume(adapter.build(BEFORE)["adapter"]), rel=1e-9)
