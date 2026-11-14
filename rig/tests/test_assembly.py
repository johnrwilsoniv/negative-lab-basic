"""Assembly: every printed part in place with the film, the rolls and the CS-Lite, at both knob positions.

assembly.py collects the parts and proves they do not intersect; fits.py measures the mating
fits on the assembled solids. The probes below measure the same things independently of fits.py.
Each parameter set is built once per module (the thread is slow).
"""

import math
from types import SimpleNamespace

import cadquery as cq
import pytest

import assembly
import cadutil
import fits
from params import DEFAULT, Params

p = DEFAULT
Q = Params(wd=150, axis=50)        # not the defaults, so nothing is right by coincidence
PRINTED = ["adapter", "tube", "gate_front", "gate_body", "sprocket_supply", "gear_supply", "sprocket_takeup",
           "gear_takeup", "idler", "idler_axle", "deck", "spool_supply", "cap_supply", "spool_takeup", "cap_takeup",
           "light_dock"]
FRAMES = [f"film_frame_{i}" for i in range(1, 4)]
REFERENCES = ["film", *FRAMES, "roll_supply", "roll_takeup", "cs_lite"]
TURNING = ["sprocket_supply", "gear_supply", "sprocket_takeup", "gear_takeup", "idler"]
EPS = 1e-6
HALF = assembly.TURNS["HALF TOOTH"]


@pytest.fixture(scope="module")
def framed():
    return assembly.placed(p)


@pytest.fixture(scope="module")
def half():
    return assembly.placed(p, HALF)


@pytest.fixture(scope="module")
def found(framed):
    return assembly.interference(p, 0.0, framed)


@pytest.fixture(scope="module")
def found_half(half):
    return assembly.interference(p, HALF, half)


@pytest.fixture(scope="module")
def framed_q():
    return assembly.placed(Q)


def box(x0, x1, y0, y1, z0, z1):
    return cadutil.probe(x0, x1, y0, y1, z0, z1)


def fake_module(solids):
    return SimpleNamespace(build=lambda p=DEFAULT, turn=0.0: solids, PRINT_UP={})


# ---- what is in the assembly -----------------------------------------------------------


def test_every_printed_solid_is_there_and_the_thread_coupon_is_not(framed):
    printed = assembly.parts(p)
    assert sorted(printed) == sorted(PRINTED) == sorted(assembly.PRINTED)
    assert "thread_coupon" not in printed
    assert sorted(assembly.references(p)) == sorted(REFERENCES)
    assert sorted(framed) == sorted(PRINTED + REFERENCES)


def test_placed_is_the_printed_solids_and_the_references(framed):
    assert list(framed) == list(assembly.parts(p)) + list(assembly.references(p))


def test_every_solid_is_one_valid_solid_at_both_knob_positions(framed, half):
    for solids in (framed, half):
        for name, wp in solids.items():
            assert cadutil.is_valid(wp), name
            assert cadutil.volume(wp) > 0, name


def test_the_knob_positions_are_a_frame_centred_and_half_a_sprocket_tooth_on():
    assert assembly.TURNS == {"FRAME": 0.0, "HALF TOOTH": pytest.approx(0.5 / p.sprocket_teeth)}


def test_duplicate_solid_names_fail_loudly():
    twins = {
        "a": fake_module({"same": box(0, 1, 0, 1, 0, 1)}),
        "b": fake_module({"same": box(2, 3, 0, 1, 0, 1)}),
    }
    with pytest.raises(ValueError, match="same"):
        assembly.parts(p, modules=twins)


def test_parts_asks_each_module_for_the_knob_position():
    asked = []

    def build(q=DEFAULT, turn=0.0):
        asked.append(turn)
        return {"slab": box(0, 1, 0, 1, 0, 1)}

    mod = SimpleNamespace(build=build, PRINT_UP={})
    assembly.parts(p, 0.25, modules={"m": mod})
    assembly.parts(p, modules={"m": mod})
    assert asked == [0.25, 0.0]


def test_extras_are_not_assembled():
    mod = fake_module({"main": box(0, 1, 0, 1, 0, 1)})
    mod.extras = lambda q=DEFAULT: {"coupon": box(5, 6, 0, 1, 0, 1)}
    assert list(assembly.parts(p, modules={"m": mod})) == ["main"]


# ---- the reference solids ---------------------------------------------------------------


def test_film_runs_124_along_z_centred_on_the_window_its_mid_plane_the_film_plane(framed):
    x0, x1, y0, y1, z0, z1 = cadutil.bounds(framed["film"])
    assert (x0, x1) == pytest.approx((p.x_film - p.film_t / 2, p.x_film + p.film_t / 2), abs=EPS)
    assert (y0, y1) == pytest.approx((p.axis - 17.5, p.axis + 17.5), abs=EPS)
    assert (z0, z1) == pytest.approx((-62, 62), abs=EPS)


def test_three_frames_36_by_24_on_a_38_pitch_the_middle_one_in_the_window(framed):
    x0 = p.x_film - p.film_t / 2
    for i, name in enumerate(FRAMES):
        z = (i - 1) * 38
        assert cadutil.bounds(framed[name]) == pytest.approx(
            (x0, x0 + p.film_t, p.axis - 12, p.axis + 12, z - 18, z + 18), abs=EPS), name


def test_the_frames_fill_their_holes_in_the_film(framed):
    for name in FRAMES:
        assert cadutil.common_volume(framed["film"], framed[name]) < 1e-6, name


def test_film_has_two_rows_of_26_ks_perforations_through_it(framed):
    x0 = p.x_film - p.film_t / 2
    film = framed["film"]
    # a probe inside a perforation finds no film; one between two perforations does
    for y in (p.axis - 14.1, p.axis + 14.1):
        hole = cadutil.probe(x0 - 1, x0 + 1, y - 1, y + 1, 2.375 - 0.5, 2.375 + 0.5)
        web = cadutil.probe(x0 - 1, x0 + 1, y - 1, y + 1, -0.5, 0.5)
        assert cadutil.common_volume(film, hole) == 0
        assert cadutil.common_volume(film, web) == pytest.approx(1 * 2 * p.film_t, rel=1e-6)
    perf = 2.79 * 1.98 - (4 - math.pi) * 0.5 ** 2
    expected = (124 * 35 - 52 * perf - 3 * 36 * 24) * p.film_t
    assert cadutil.volume(film) == pytest.approx(expected, rel=1e-6)
    assert cadutil.is_valid(film)


def test_a_perforation_is_centred_on_each_sprocket_with_a_frame_in_the_window(framed):
    x0 = p.x_film - p.film_t / 2
    for z in (-p.sprocket_z, p.sprocket_z):
        for y in (p.axis - p.perf_dy, p.axis + p.perf_dy):
            hole = cadutil.probe(x0 - 1, x0 + 1, y - 1.2, y + 1.2, z - 0.8, z + 0.8)      # clear of the 0.5 corners
            assert cadutil.common_volume(framed["film"], hole) == 0, (y, z)


def test_the_film_runs_with_the_knob(framed, half):
    a, b = cadutil.bounds(framed["film"]), cadutil.bounds(half["film"])
    assert (b[4] - a[4], b[5] - a[5]) == pytest.approx((HALF * 38, HALF * 38), abs=EPS)     # toward +z
    assert b[:4] == pytest.approx(a[:4], abs=EPS)


def test_the_sprockets_gears_and_idler_turn_and_nothing_else_moves(framed, half):
    for name in PRINTED:
        same = cadutil.common_volume(framed[name], half[name]) == pytest.approx(cadutil.volume(framed[name]), rel=1e-6)
        assert same != (name in TURNING), name


def test_half_the_roll_is_on_each_spool_between_its_flanges(framed):
    for side, sign in (("supply", -1), ("takeup", 1)):
        x0, x1, y0, y1, z0, z1 = cadutil.bounds(framed[f"roll_{side}"])
        assert ((x0 + x1) / 2, (z0 + z1) / 2) == pytest.approx((p.x_spool, sign * p.spool_z), abs=EPS)
        assert (x1 - x0) / 2 == pytest.approx(p.roll_r_half, abs=EPS)
        assert (y0, y1) == pytest.approx((p.axis - 17.5, p.axis + 17.5), abs=EPS)
        # the roll's area is half the film's length times its thickness, packed loosely
        area = cadutil.volume(framed[f"roll_{side}"]) / p.film_w
        assert area == pytest.approx(p.film_roll_len / 2 * p.film_t * p.roll_pack, rel=1e-6)


def test_the_film_runs_straight_from_a_half_roll_into_the_channel():
    # x_spool puts a half-full roll's outside, on average over empty to full, on the film plane: within 1.2 of it
    # either way, so the film leaves each roll within a few degrees of the channel's line
    for r in (p.spool_core_r, p.roll_r_full):
        assert abs(p.x_spool + r - p.x_film) < 1.2
    run = p.spool_z - p.gw / 2                  # the free run from roll to gate is at least this long
    assert math.degrees(math.atan(1.2 / run)) < 3


def test_cs_lite_is_165_by_112_by_20_standing_on_the_docks_floor(framed):
    x0, x1, y0, y1, z0, z1 = cadutil.bounds(framed["cs_lite"])
    assert (x0, x1) == pytest.approx((p.x_light, p.x_light + 20), abs=EPS)
    assert (y0, y1) == pytest.approx((4, 4 + 112), abs=EPS)
    assert (z0, z1) == pytest.approx((-82.5, 82.5), abs=EPS)


# ---- the parts are seated ---------------------------------------------------------------


def test_tube_starts_on_the_adapters_socket_floor(framed):
    # the socket is radius 34.3, so material of the adapter at radius 32..34 ends at the floor
    floor = cadutil.common_bounds(
        framed["adapter"], cadutil.probe(p.x_front, p.x_front + 20, p.axis + 32, p.axis + 34, -0.1, 0.1)
    )[1]
    assert cadutil.bounds(framed["tube"])[0] == pytest.approx(floor, abs=EPS)


def test_tube_ends_on_the_gate_fronts_socket_floor(framed):
    # the socket is radius 34.3, so material of the gate front at radius 32.5..34 (inside it, beyond the light
    # passage's corners at 32) starts at the socket's floor, 9 in (F24)
    floor = cadutil.common_bounds(
        framed["gate_front"], cadutil.probe(p.x_gate, p.x_gate + 20, p.axis - 34, p.axis - 32.5, -0.1, 0.1)
    )[0]
    assert floor == pytest.approx(p.x_gate + p.front_wall, abs=EPS)
    assert cadutil.bounds(framed["gate_front"])[0] == pytest.approx(p.x_gate, abs=EPS)
    assert cadutil.bounds(framed["tube"])[1] == pytest.approx(floor, abs=EPS)


# ---- interference -----------------------------------------------------------------------


def test_nothing_intersects_with_a_frame_centred(found):
    assert found == []


def test_nothing_intersects_half_a_tooth_on(found_half):
    assert found_half == []


def test_every_printed_pair_and_every_printed_against_a_reference_is_checked(framed):
    pairs = assembly.pairs(framed)
    n, r = len(PRINTED), len(REFERENCES)
    assert len(pairs) == n * (n - 1) // 2 + n * r


@pytest.mark.parametrize("turn", [0.0, HALF, 0.25, 0.5])
def test_the_teeth_stay_in_the_perforations_as_the_knob_turns(turn):
    """The rack and pinion: at any knob position each sprocket's teeth only touch the film inside its perforations."""
    solids = {**assembly.parts(p, turn), **assembly.references(p, turn)}
    for side in ("supply", "takeup"):
        assert cadutil.common_volume(solids[f"sprocket_{side}"], solids["film"]) < assembly.CONTACT_VOLUME, (turn, side)


def test_a_tooth_stands_through_the_film_in_each_row_on_each_sprocket(framed):
    film_front = p.x_film - p.film_t / 2
    for z in (-p.sprocket_z, p.sprocket_z):
        sprocket = framed["sprocket_supply" if z < 0 else "sprocket_takeup"]
        for y in (p.axis - p.perf_dy, p.axis + p.perf_dy):
            tip = cadutil.common_bounds(sprocket, cadutil.probe(p.x_film - 3, film_front, y - 1.5, y + 1.5, z - 2, z + 2))
            assert tip is not None and tip[0] == pytest.approx(p.x_sprocket - p.r_tip, abs=1e-6)


# ---- the interference check itself ----------------------------------------------------


def test_interference_reports_a_pair_that_overlaps_with_its_volume():
    placed = dict(
        a=box(0, 10, 0, 10, 0, 10),
        b=box(8, 20, 2, 6, 1, 5),       # x 8..10, y 2..6, z 1..5: 2 x 4 x 4
    )
    ((a, b, volume),) = assembly.interference(p, 0.0, placed)
    assert (a, b) == ("a", "b")
    assert volume == pytest.approx(32)


def test_interference_ignores_touching_and_separate_solids():
    placed = dict(
        a=box(0, 10, 0, 10, 0, 10),
        face=box(10, 20, 0, 10, 0, 10),         # shares the x = 10 face
        edge=box(10, 20, 10, 20, 0, 10),        # shares only an edge
        far=box(100, 110, 0, 10, 0, 10),
    )
    assert assembly.interference(p, 0.0, placed) == []


def test_the_bounding_box_prefilter_never_hides_a_thin_overlap():
    placed = dict(a=box(0, 10, 0, 10, 0, 10), b=box(9.99, 20, 0, 10, 0, 10))
    ((_, _, volume),) = assembly.interference(p, 0.0, placed)
    assert volume == pytest.approx(0.01 * 100)


def test_interference_checks_references_against_printed_but_not_against_each_other():
    placed = dict(part=box(0, 10, 0, 10, 0, 10), film=box(5, 15, 0, 10, 0, 10), cs_lite=box(6, 16, 0, 10, 0, 10))
    found = assembly.interference(p, 0.0, placed)
    assert {frozenset(f[:2]) for f in found} == {frozenset({"part", "film"}), frozenset({"part", "cs_lite"})}


def test_interference_below_the_contact_threshold_is_contact():
    placed = dict(a=box(0, 10, 0, 10, 0, 10), b=box(10 - 5e-6, 20, 0, 10, 0, 10))     # 5e-6 x 100 = 5e-4
    assert assembly.interference(p, 0.0, placed) == []


def test_problems_are_every_overlap():
    assert assembly.problems([]) == []
    (message,) = assembly.problems([("idler", "deck", 0.5)])
    assert "idler" in message and "deck" in message and "0.5" in message


# ---- not the defaults -------------------------------------------------------------------


def test_other_params_same_names_and_no_interference(framed_q):
    assert sorted(framed_q) == sorted(PRINTED + REFERENCES)
    assert assembly.interference(Q, 0.0, framed_q) == []


def test_other_params_nothing_intersects_half_a_tooth_on():
    assert assembly.interference(Q, HALF) == []


def test_other_params_the_references_follow_the_rig(framed_q):
    x0, x1, y0, y1, _, _ = cadutil.bounds(framed_q["film"])
    assert ((x0 + x1) / 2, (y0 + y1) / 2) == pytest.approx((Q.x_film, Q.axis), abs=EPS)
    assert cadutil.bounds(framed_q["cs_lite"])[0] == pytest.approx(Q.x_light, abs=EPS)


# ---- the assembly STEP -------------------------------------------------------------------


@pytest.fixture(scope="module")
def step(framed, tmp_path_factory):
    path = tmp_path_factory.mktemp("asm") / "step" / "rig.step"
    assembly.write_step(p, path, framed)
    return path


def test_the_default_assembly_step_path_is_in_exports_step():
    assert assembly.STEP_PATH.name == "nlb-scan-rig-assembly.step"
    assert assembly.STEP_PATH.parent.name == "step" and assembly.STEP_PATH.parent.parent.name == "exports"


def test_onshape_frame_is_z_up_from_the_table_under_the_film():
    # mockup (x along the axis, y up, z across) -> Onshape X = z, Y = x - x_film, Z = y: the camera end toward -Y, so
    # Onshape's default isometric (from +X, -Y, +Z) looks into the adapter
    corner = cadutil.probe(p.x_film + 1, p.x_film + 2, 3, 5, 10, 13)
    assert cadutil.bounds(assembly.to_onshape(p, corner)) == pytest.approx((10, 13, 1, 2, 3, 5), abs=1e-9)


def test_assembly_step_holds_every_solid_by_name_in_the_onshape_frame(framed, step):
    read = cadutil.step_assembly(step)
    assert sorted(read) == sorted(PRINTED + [f"ref_{n}" for n in REFERENCES])
    total = 0.0
    for name, wp in framed.items():
        got = read[name if name in PRINTED else f"ref_{name}"].solid
        assert cadutil.volume(got) == pytest.approx(cadutil.volume(wp), rel=cadutil.STEP_VOLUME_RTOL), name
        assert cadutil.bounds(got) == pytest.approx(cadutil.bounds(assembly.to_onshape(p, wp)), abs=1e-6), name
        total += cadutil.volume(got)
    assert total == pytest.approx(sum(cadutil.volume(wp) for wp in framed.values()), rel=cadutil.STEP_VOLUME_RTOL)


def test_assembly_step_colours_are_distinct_and_the_references_translucent(step):
    read = cadutil.step_assembly(step)
    printed = [read[n].color for n in PRINTED]
    refs = [read[f"ref_{n}"].color for n in REFERENCES]
    assert all(c is not None for c in printed + refs)

    def rgb(colors):
        return {tuple(round(v, 3) for v in c[:3]) for c in colors}

    assert len(rgb(printed)) == len(PRINTED)                  # all different
    assert all(c[3] == pytest.approx(1) for c in printed)     # opaque
    assert all(c[3] < 1 for c in refs)                        # translucent
    assert not rgb(refs) & rgb(printed)


def test_assembly_step_has_a_frame_in_the_window(step):
    read = cadutil.step_assembly(step)
    x0, x1, *_ = cadutil.bounds(read["ref_film_frame_2"].solid)      # X = z: the middle frame, centred on the window
    assert (x0 + x1) / 2 == pytest.approx(0, abs=1e-6)


def test_assembly_step_sits_on_the_top_plane_with_the_film_on_the_front_plane(step):
    read = cadutil.step_assembly(step)
    assert min(cadutil.bounds(part.solid)[4] for part in read.values()) == pytest.approx(0, abs=1e-6)  # table: Z = 0
    xmin, xmax, ymin, ymax, zmin, zmax = cadutil.bounds(read["ref_film"].solid)
    assert (ymin, ymax) == pytest.approx((-p.film_t / 2, p.film_t / 2))     # the film's mid-plane on Y = 0
    assert (zmin + zmax) / 2 == pytest.approx(p.axis)                       # optical axis at Z = axis
    assert (xmin + xmax) / 2 == pytest.approx(0, abs=1e-6)                  # X = z
    assert cadutil.bounds(read["adapter"].solid)[3] < 0 < cadutil.bounds(read["ref_cs_lite"].solid)[2]  # camera at -Y


def test_assembly_step_has_no_overlaps_when_read_back(step):
    read = cadutil.step_assembly(step)
    placed = {n.removeprefix("ref_"): s.solid for n, s in read.items()}
    assert assembly.interference(p, 0.0, placed) == []


def test_check_step_passes_the_file_it_wrote(framed, step):
    check = assembly.check_step(step, framed)
    assert check.problems == []
    assert check.count == len(PRINTED + REFERENCES)       # 23
    assert check.volume == pytest.approx(sum(cadutil.volume(wp) for wp in framed.values()), rel=cadutil.STEP_VOLUME_RTOL)
    assert check.error < cadutil.STEP_VOLUME_RTOL


def test_check_step_flags_a_solid_missing_from_the_file(framed, step):
    wrote_more = {**framed, "extra": box(0, 1, 0, 1, 0, 1)}
    (message, *_) = assembly.check_step(step, wrote_more).problems
    assert "extra" in message and "not in the STEP" in message


def test_check_step_flags_a_solid_that_is_not_what_was_written(framed, step):
    changed = {**framed, "idler": box(0, 1, 0, 1, 0, 1)}
    messages = assembly.check_step(step, changed).problems
    assert any("idler" in m and "volume" in m for m in messages)
    assert any("total" in m for m in messages)


def test_check_step_flags_a_solid_in_the_file_that_was_not_written(framed, step):
    fewer = {k: v for k, v in framed.items() if k != "tube"}
    assert any("tube" in m for m in assembly.check_step(step, fewer).problems)


# ---- fit numbers, measured on the assembled solids --------------------------------------


def by_label(report):
    return {f.label: f for f in report}


@pytest.fixture(scope="module")
def report(framed):
    return fits.report(p, framed)


@pytest.fixture(scope="module")
def report_q(framed_q):
    return fits.report(Q, framed_q)


def test_every_fit_is_met_at_the_defaults(report):
    assert report and all(f.ok for f in report), [f for f in report if not f.ok]


def test_every_fit_is_met_at_other_params(report_q):
    assert all(f.ok for f in report_q), [f for f in report_q if not f.ok]


def test_fit_labels_are_unique(report):
    assert len({f.label for f in report}) == len(report)


def test_the_measured_numbers_are_the_designs(report):
    got = {f.label: f.measured for f in report}
    want = {
        "tube / adapter socket, radial clearance": 0.05,
        "tube / gate front socket, radial clearance": 0.05,
        "film channel, gate front to gate body": 0.3,
        "film / gate front (reference plane)": 0.085,
        "film channel height less the film": 0.2,
        "peg / hole in the gate front, radial": 0,
        "film / sprocket rings": 0.05,
        "tooth tip / groove in the gate front": 0.35,
        "tooth tip / sprocket pocket, radial": 0.4,
        "sprocket shaft / deck bearing, radial": 0.2,
        "sprocket shaft / gate body bearing, radial": 0.2,
        "gear's D-bore / shaft's flat": 0.1,
        "idler / its axle, radial": 0.2,
        "idler axle / deck (pressed)": 0,
        "spool's lower flange / roll": 0.5,
        "cap / roll": 0.5,
        "spool / dock pin, radial": 0.2,
        "cap spigot / spool socket (pressed)": 0,
        "CS-Lite slot, width less the panel": 0.5,
        "gate body / dock notch, z clearance (the smaller)": 0.2,
        "gate body rear face / CS-Lite lit face": 0,
        "gate front / dock floor's edge, x clearance": 0.2,
    }
    assert set(got) == set(want)
    for label, value in want.items():
        assert got[label] == pytest.approx(value, abs=1e-5), label


def test_the_gate_hole_is_closed_all_round(report):
    # R8 closed: the r34.3 socket stays 1.7 under the gate front's top, so no side is noted open
    (hole,) = [f for f in report if f.label == "tube / gate front socket, radial clearance"]
    assert hole.note == ""


def test_a_fit_that_is_off_is_not_ok():
    assert fits.Fit("x", 0.3, 0.3).ok
    assert not fits.Fit("x", 0.31, 0.3).ok
    assert not fits.Fit("x", None, 0.3).ok


def test_the_fits_measure_the_solids_not_the_params(framed):
    # a tube 0.03 too fat for its socket: the measured clearance drops, whatever params say
    fat = cq.Workplane("YZ", origin=(p.tube_x0, p.axis, 0)).circle(p.tube_ro + 0.03).extrude(10)
    report = by_label(fits.report(p, {**framed, "tube": fat}))
    assert report["tube / adapter socket, radial clearance"].measured == pytest.approx(0.02, abs=1e-5)
    assert not report["tube / adapter socket, radial clearance"].ok


@pytest.mark.parametrize("label, name, moved, measured", [
    ("film channel, gate front to gate body", "gate_front", (-0.1, 0, 0), 0.4),
    ("film / gate front (reference plane)", "film", (0.05, 0, 0), 0.135),
    ("film / sprocket rings", "sprocket_supply", (0.02, 0, 0), 0.07),
    ("tooth tip / groove in the gate front", "gate_front", (0.1, 0, 0), 0.25),
    ("sprocket shaft / deck bearing, radial", "deck", (0.05, 0, 0), 0.25),
    ("idler / its axle, radial", "idler_axle", (0.05, 0, 0), 0.15),
    ("spool's lower flange / roll", "roll_supply", (0, 0.1, 0), 0.6),
    ("spool / dock pin, radial", "light_dock", (0.05, 0, 0), 0.15),
    ("gate body / dock notch, z clearance (the smaller)", "light_dock", (0, 0, 0.05), 0.15),
    ("gate body rear face / CS-Lite lit face", "cs_lite", (0.05, 0, 0), 0.05),
    ("gate front / dock floor's edge, x clearance", "light_dock", (0.05, 0, 0), 0.15),
])
def test_the_clearances_are_measured_on_the_solids(framed, label, name, moved, measured):
    report = by_label(fits.report(p, {**framed, name: framed[name].translate(moved)}))
    assert report[label].measured == pytest.approx(measured, abs=1e-5)
    assert not report[label].ok


def test_the_cs_lite_slot_is_measured_against_the_panel(framed):
    # a panel 0.2 thicker than the CS-Lite's 20 leaves 0.3 of the slot
    thick = cadutil.probe(p.x_light, p.x_light + 20.2, 4, 116, -82.5, 82.5)
    report = by_label(fits.report(p, {**framed, "cs_lite": thick}))
    assert report["CS-Lite slot, width less the panel"].measured == pytest.approx(0.3, abs=1e-5)


def test_a_fit_whose_solids_are_missing_fails_instead_of_raising(framed):
    without = {k: v for k, v in framed.items() if k not in ("tube", "idler")}
    report = by_label(fits.report(p, without))
    for label in ("tube / adapter socket, radial clearance", "idler / its axle, radial"):
        assert report[label].measured is None and not report[label].ok, label


def test_fits_with_nothing_to_measure_fail_instead_of_raising(framed):
    blocks = {name: box(i * 20, i * 20 + 10, 0, 10, 0, 10) for i, name in enumerate(framed)}      # no windows, no holes

    report = fits.report(p, blocks)

    assert report and not any(f.ok for f in report)
    assert all("not measured" in f.note for f in report if f.measured is None)
    assert any(f.measured is None for f in report)


def test_format_report_lists_every_fit(report):
    text = fits.format_report(report)
    for f in report:
        assert f.label in text
    assert "FAIL" not in text
