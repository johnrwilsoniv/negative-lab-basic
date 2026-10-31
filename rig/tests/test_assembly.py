"""Assembly: every printed part in place with the film and the CS-Lite, in both switch positions.

assembly.py collects the parts and proves they do not intersect; fits.py measures the mating
fits on the assembled solids. The probes below measure the same things independently of fits.py.
Each parameter set is built once per module (the thread and the lettering are slow).
"""

from types import SimpleNamespace

import cadquery as cq
import pytest

import assembly
import cadutil
import fits
from params import DEFAULT, Params

p = DEFAULT
Q = Params(wd=150, axis=50)        # not the defaults, so nothing is right by coincidence
PRINTED = ["adapter", "tube", "gate_box", "gate_lid", "pressure_plate", "wedge_plate", "knob", "light_dock"]
REFERENCES = ["film", "cs_lite"]
EPS = 1e-6


@pytest.fixture(scope="module")
def slide():
    return assembly.placed(p, False)


@pytest.fixture(scope="module")
def lock():
    return assembly.placed(p, True)


@pytest.fixture(scope="module")
def found_slide(slide):
    return assembly.interference(p, False, slide)


@pytest.fixture(scope="module")
def found_lock(lock):
    return assembly.interference(p, True, lock)


@pytest.fixture(scope="module")
def slide_q():
    return assembly.placed(Q, False)


@pytest.fixture(scope="module")
def lock_q():
    return assembly.placed(Q, True)


def box(x0, x1, y0, y1, z0, z1):
    return cadutil.probe(x0, x1, y0, y1, z0, z1)


def fake_module(solids):
    return SimpleNamespace(build=lambda p=DEFAULT, lock=False: solids, PRINT_UP={})


# ---- what is in the assembly -----------------------------------------------------------


def test_every_printed_solid_is_there_and_the_thread_coupon_is_not(slide):
    printed = assembly.parts(p)
    assert sorted(printed) == sorted(PRINTED)
    assert "thread_coupon" not in printed
    assert sorted(assembly.references(p)) == sorted(REFERENCES)
    assert sorted(slide) == sorted(PRINTED + REFERENCES)


def test_placed_is_the_printed_solids_and_the_references(slide):
    assert list(slide) == list(assembly.parts(p)) + list(assembly.references(p))


def test_every_solid_is_one_valid_solid_in_both_positions(slide, lock):
    for solids in (slide, lock):
        for name, wp in solids.items():
            assert cadutil.is_valid(wp), name
            assert cadutil.volume(wp) > 0, name


def test_duplicate_solid_names_fail_loudly():
    twins = {
        "a": fake_module({"same": box(0, 1, 0, 1, 0, 1)}),
        "b": fake_module({"same": box(2, 3, 0, 1, 0, 1)}),
    }
    with pytest.raises(ValueError, match="same"):
        assembly.parts(p, modules=twins)


def test_parts_asks_each_module_for_the_switch_position():
    asked = []

    def build(q=DEFAULT, lock=False):
        asked.append(lock)
        return {"slab": box(0, 1, 0, 1, 0, 1)}

    mod = SimpleNamespace(build=build, PRINT_UP={})
    assembly.parts(p, True, modules={"m": mod})
    assembly.parts(p, modules={"m": mod})
    assert asked == [True, False]


def test_extras_are_not_assembled():
    mod = fake_module({"main": box(0, 1, 0, 1, 0, 1)})
    mod.extras = lambda q=DEFAULT: {"coupon": box(5, 6, 0, 1, 0, 1)}
    assert list(assembly.parts(p, modules={"m": mod})) == ["main"]


# ---- the reference solids ---------------------------------------------------------------


def test_film_strip_is_228_along_z_centred_at_z19_on_the_axis(slide):
    x0, x1, y0, y1, z0, z1 = cadutil.bounds(slide["film"])
    assert (x0, x1) == pytest.approx((p.x_film - p.channel / 2, p.x_film - p.channel / 2 + p.film_t), abs=EPS)
    assert (y0, y1) == pytest.approx((p.axis - 17.5, p.axis + 17.5), abs=EPS)
    assert (z0, z1) == pytest.approx((19 - 114, 19 + 114), abs=EPS)


def test_film_lies_against_the_front_plates_rear_face(slide):
    plate = cadutil.common_bounds(
        slide["gate_box"], cadutil.probe(p.x_film - 6, p.x_film + 6, 4, 8, -10, 10)
    )
    assert cadutil.bounds(slide["film"])[0] == pytest.approx(plate[1], abs=EPS)


def test_cs_lite_is_165_by_112_by_20_standing_on_the_docks_floor(slide):
    x0, x1, y0, y1, z0, z1 = cadutil.bounds(slide["cs_lite"])
    assert (x0, x1) == pytest.approx((p.x_light, p.x_light + 20), abs=EPS)
    assert (y0, y1) == pytest.approx((4, 4 + 112), abs=EPS)
    assert (z0, z1) == pytest.approx((-82.5, 82.5), abs=EPS)


def test_the_film_stays_put_at_lock(slide, lock):
    assert cadutil.bounds(lock["film"]) == pytest.approx(cadutil.bounds(slide["film"]), abs=EPS)


# ---- the parts are seated ---------------------------------------------------------------


def test_tube_starts_on_the_adapters_socket_floor(slide):
    # the socket is radius 36.3, so material of the adapter at radius 33..35 ends at the floor
    floor = cadutil.common_bounds(
        slide["adapter"], cadutil.probe(p.x_front, p.x_front + 20, p.axis + 33, p.axis + 35, -0.1, 0.1)
    )[1]
    assert cadutil.bounds(slide["tube"])[0] == pytest.approx(floor, abs=EPS)


def test_tube_ends_on_the_gate_front_walls_back_face(slide):
    # below the hole (which starts at axis - 36.3 = 6.2) and above the floor, the only box material
    # in this slice of z is the front wall
    wall = cadutil.common_bounds(
        slide["gate_box"], cadutil.probe(p.x_gate, p.x_gate + 10, 3.5, 5.5, -10, 10)
    )
    assert wall[0] == pytest.approx(p.x_gate, abs=EPS)
    assert cadutil.bounds(slide["tube"])[1] == pytest.approx(wall[1], abs=EPS)


# ---- interference -----------------------------------------------------------------------


def test_slide_nothing_intersects(found_slide):
    assert found_slide == []


def test_every_printed_pair_and_every_printed_against_a_reference_is_checked(slide):
    pairs = assembly.pairs(slide)
    assert len(pairs) == 28 + 16                     # 8 printed: 28 pairs; each against the 2 references: 16
    assert len({frozenset(pair) for pair in pairs}) == len(pairs)
    assert not any(a in REFERENCES and b in REFERENCES for a, b in pairs)


def test_lock_only_the_pads_overlap_the_ramps(found_lock):
    assert len(found_lock) == 1
    a, b, volume, thickness = found_lock[0]
    assert {a, b} == {"pressure_plate", "wedge_plate"}
    assert thickness == pytest.approx(p.preload, abs=0.005)
    assert volume == pytest.approx(48 * p.preload, rel=2e-3)      # 4 pads x 12 mm2 of overlap, 5.44 mm3


def test_lock_overlap_is_a_real_overlap_not_a_sliver(found_lock):
    assert found_lock[0][2] > 1


def test_lock_film_is_touched_by_both_plates_and_overlapped_by_neither(lock):
    film = lock["film"]
    assert cadutil.common_volume(film, lock["pressure_plate"]) < 1e-3
    assert cadutil.common_volume(film, lock["gate_box"]) < 1e-3
    # touched: the pressure plate's front face is the film's rear face; the box's plate is its front face
    plate_front = cadutil.common_bounds(
        lock["pressure_plate"], cadutil.probe(p.x_film - 6, p.x_film + 6, 4, 8, -10, 10)
    )[0]
    assert plate_front == pytest.approx(cadutil.bounds(film)[1], abs=EPS)
    front_plate_rear = cadutil.common_bounds(
        lock["gate_box"], cadutil.probe(p.x_film - 6, p.x_film + 6, 4, 8, -10, 10)
    )[1]
    assert front_plate_rear == pytest.approx(cadutil.bounds(film)[0], abs=EPS)


def test_slide_leaves_the_film_free_of_the_pressure_plate(slide):
    plate_front = cadutil.common_bounds(
        slide["pressure_plate"], cadutil.probe(p.x_film - 6, p.x_film + 6, 4, 8, -10, 10)
    )[0]
    assert plate_front - cadutil.bounds(slide["film"])[1] == pytest.approx(p.channel - p.film_t, abs=EPS)


def test_the_wedge_plate_moves_with_the_switch_the_plate_with_the_clamp(slide, lock):
    assert cadutil.bounds(lock["wedge_plate"])[4] - cadutil.bounds(slide["wedge_plate"])[4] == pytest.approx(10)
    assert cadutil.bounds(slide["pressure_plate"])[0] - cadutil.bounds(lock["pressure_plate"])[0] == pytest.approx(
        p.lock_shift
    )
    assert cadutil.bounds(lock["light_dock"]) == cadutil.bounds(slide["light_dock"])


# ---- the interference check itself ----------------------------------------------------


def test_interference_reports_a_pair_that_overlaps_with_volume_and_x_thickness():
    placed = dict(
        a=box(0, 10, 0, 10, 0, 10),
        b=box(8, 20, 2, 6, 1, 5),       # x 8..10, y 2..6, z 1..5: 2 x 4 x 4
    )
    ((a, b, volume, thickness),) = assembly.interference(p, False, placed)
    assert (a, b) == ("a", "b")
    assert volume == pytest.approx(32)
    assert thickness == pytest.approx(2)


def sloped(x_of_z, z_end):
    """The region x <= x_of_z(z) (from x = 0), z 0..z_end, y 0..4, as the mockup's pads and ramps are drawn."""
    outline = [(0, 0), (x_of_z(0), 0), (x_of_z(z_end), z_end), (0, z_end)]
    return cq.Workplane("XZ", origin=(0, 4, 0)).polyline(outline).close().extrude(4)


def test_x_thickness_is_the_depth_of_the_overlap_not_the_x_extent_of_a_slope():
    # two faces parallel, both rising 0.1 per mm of z; the first goes 0.2 past the second. Over 10 mm of z
    # the overlap's x-extent is 0.2 + 1.0, but it is 0.2 deep everywhere.
    a = sloped(lambda z: 10 + 0.1 * z, 10)
    b = sloped(lambda z: 20, 10).cut(sloped(lambda z: 10 + 0.1 * z - 0.2, 10))      # x from the sloped face to 20
    assert cadutil.common_bounds(a, b)[1] - cadutil.common_bounds(a, b)[0] == pytest.approx(1.2)
    ((_, _, volume, thickness),) = assembly.interference(p, False, {"a": a, "b": b})
    assert thickness == pytest.approx(0.2, abs=1e-6)
    assert volume == pytest.approx(0.2 * 4 * 10, abs=1e-6)


def test_x_thickness_of_several_pieces_is_their_volume_over_their_footprints():
    # a comb whose teeth go 2 and 5 deep into a plate, each over 10 x 5
    comb = box(0, 20, 0, 10, 0, 1).union(box(2, 4, 0, 10, 0, 10)).union(box(14, 19, 0, 10, 0, 10))
    plate = box(0, 20, 0, 10, 5, 10)
    ((_, _, volume, thickness),) = assembly.interference(p, False, {"comb": comb, "plate": plate})
    assert volume == pytest.approx(100 + 250)
    assert thickness == pytest.approx(350 / 100)


def test_interference_ignores_touching_and_separate_solids():
    placed = dict(
        a=box(0, 10, 0, 10, 0, 10),
        face=box(10, 20, 0, 10, 0, 10),         # shares the x = 10 face
        edge=box(10, 20, 10, 20, 0, 10),        # shares only an edge
        far=box(100, 110, 0, 10, 0, 10),
    )
    assert assembly.interference(p, False, placed) == []


def test_the_bounding_box_prefilter_never_hides_a_thin_overlap():
    placed = dict(a=box(0, 10, 0, 10, 0, 10), b=box(9.99, 20, 0, 10, 0, 10))
    ((_, _, volume, thickness),) = assembly.interference(p, False, placed)
    assert volume == pytest.approx(0.01 * 100)
    assert thickness == pytest.approx(0.01)


def test_interference_checks_references_against_printed_but_not_against_each_other():
    placed = dict(part=box(0, 10, 0, 10, 0, 10), film=box(5, 15, 0, 10, 0, 10), cs_lite=box(6, 16, 0, 10, 0, 10))
    found = assembly.interference(p, False, placed)
    assert {frozenset(f[:2]) for f in found} == {frozenset({"part", "film"}), frozenset({"part", "cs_lite"})}


def test_interference_below_the_contact_threshold_is_contact():
    placed = dict(a=box(0, 10, 0, 10, 0, 10), b=box(10 - 5e-6, 20, 0, 10, 0, 10))     # 5e-6 x 100 = 5e-4
    assert assembly.interference(p, False, placed) == []


# ---- what is allowed ------------------------------------------------------------------


def test_allowed_slide_is_nothing_and_lock_is_the_pads_in_the_ramps():
    assert assembly.allowed(p, False) == []
    ((a, b, thickness),) = assembly.allowed(p, True)
    assert {a, b} == {"pressure_plate", "wedge_plate"}
    assert thickness == pytest.approx(p.preload)


def test_problems_none_for_the_designed_result(found_slide, found_lock):
    assert assembly.problems(p, False, found_slide) == []
    assert assembly.problems(p, True, found_lock) == []


def test_problems_flags_any_overlap_at_slide():
    found = [("pressure_plate", "wedge_plate", 1.0, p.preload)]
    assert assembly.problems(p, False, found)


def test_problems_flags_a_second_overlap_at_lock():
    found = [("wedge_plate", "pressure_plate", 5.44, p.preload), ("tube", "adapter", 3.0, 0.5)]
    (message,) = assembly.problems(p, True, found)
    assert "tube" in message and "adapter" in message


def test_problems_flags_a_preload_that_is_not_the_designed_one():
    assert assembly.problems(p, True, [("pressure_plate", "wedge_plate", 5.44, p.preload + 0.01)])
    assert assembly.problems(p, True, [("pressure_plate", "wedge_plate", 5.44, p.preload - 0.01)])
    assert not assembly.problems(p, True, [("pressure_plate", "wedge_plate", 5.44, p.preload + 0.004)])


def test_problems_flags_a_lock_with_no_clamp():
    (message,) = assembly.problems(p, True, [])
    assert "pressure_plate" in message and "wedge_plate" in message


def test_problems_accepts_the_pair_in_either_order():
    assert assembly.problems(p, True, [("wedge_plate", "pressure_plate", 5.44, p.preload)]) == []


# ---- not the defaults -------------------------------------------------------------------


def test_other_params_same_names_and_no_slide_interference(slide_q):
    assert sorted(slide_q) == sorted(PRINTED + REFERENCES)
    assert assembly.interference(Q, False, slide_q) == []


def test_other_params_lock_only_the_pads_overlap_the_ramps(lock_q):
    found = assembly.interference(Q, True, lock_q)
    assert assembly.problems(Q, True, found) == []
    assert len(found) == 1 and found[0][3] == pytest.approx(Q.preload, abs=0.005)


def test_other_params_the_references_follow_the_rig(slide_q):
    assert cadutil.bounds(slide_q["film"])[0] == pytest.approx(Q.x_film - Q.channel / 2)
    assert cadutil.bounds(slide_q["film"])[2] == pytest.approx(Q.axis - 17.5)
    assert cadutil.bounds(slide_q["cs_lite"])[0] == pytest.approx(Q.x_light)


# ---- the assembly STEP -------------------------------------------------------------------


@pytest.fixture(scope="module")
def step(slide, tmp_path_factory):
    path = tmp_path_factory.mktemp("asm") / "step" / "rig.step"
    assembly.write_step(p, path, slide)
    return path


def test_the_default_assembly_step_path_is_in_exports_step():
    assert assembly.STEP_PATH.name == "nlb-scan-rig-assembly.step"
    assert assembly.STEP_PATH.parent.name == "step" and assembly.STEP_PATH.parent.parent.name == "exports"


def test_onshape_frame_is_z_up_from_the_table_under_the_film():
    # mockup (x along the axis, y up, z across) -> Onshape X = z, Y = x - x_film, Z = y: the camera end toward -Y, so
    # Onshape's default isometric (from +X, -Y, +Z) looks into the adapter
    corner = cadutil.probe(p.x_film + 1, p.x_film + 2, 3, 5, 10, 13)
    assert cadutil.bounds(assembly.to_onshape(p, corner)) == pytest.approx((10, 13, 1, 2, 3, 5), abs=1e-9)


def test_assembly_step_holds_every_solid_by_name_in_the_onshape_frame(slide, step):
    read = cadutil.step_assembly(step)
    assert sorted(read) == sorted(["adapter", "tube", "gate_box", "gate_lid", "pressure_plate", "wedge_plate",
                                   "knob", "light_dock", "ref_film", "ref_cs_lite"])
    total = 0.0
    for name, wp in slide.items():
        got = read[name if name in PRINTED else f"ref_{name}"].solid
        assert cadutil.volume(got) == pytest.approx(cadutil.volume(wp), rel=cadutil.STEP_VOLUME_RTOL), name
        assert cadutil.bounds(got) == pytest.approx(cadutil.bounds(assembly.to_onshape(p, wp)), abs=1e-6), name
        total += cadutil.volume(got)
    assert total == pytest.approx(sum(cadutil.volume(wp) for wp in slide.values()), rel=cadutil.STEP_VOLUME_RTOL)


def test_assembly_step_colours_are_distinct_and_the_references_translucent(step):
    read = cadutil.step_assembly(step)
    printed = [read[n].color for n in PRINTED]
    refs = [read["ref_film"].color, read["ref_cs_lite"].color]
    assert all(c is not None for c in printed + refs)

    def rgb(colors):
        return {tuple(round(v, 3) for v in c[:3]) for c in colors}

    assert len(rgb(printed)) == len(PRINTED)                  # all different
    assert all(c[3] == pytest.approx(1) for c in printed)     # opaque
    assert all(c[3] < 1 for c in refs)                        # translucent
    assert not rgb(refs) & rgb(printed)


def test_assembly_step_is_the_slide_position(slide, step):
    read = cadutil.step_assembly(step)
    assert cadutil.bounds(read["wedge_plate"].solid)[0] == pytest.approx(-p.sw_travel / 2 - p.wedge_w / 2)  # X = z
    assert cadutil.bounds(read["pressure_plate"].solid)[2] == pytest.approx(p.channel / 2)                 # Y = x - x_film


def test_assembly_step_sits_on_the_top_plane_with_the_film_on_the_front_plane(step):
    read = cadutil.step_assembly(step)
    assert min(cadutil.bounds(part.solid)[4] for part in read.values()) == pytest.approx(0, abs=1e-6)  # table: Z = 0
    xmin, xmax, ymin, ymax, zmin, zmax = cadutil.bounds(read["ref_film"].solid)
    assert (ymin, ymax) == pytest.approx((-p.channel / 2, -p.channel / 2 + p.film_t))   # film plane at Y = 0
    assert (zmin + zmax) / 2 == pytest.approx(p.axis)                                   # optical axis at Z = axis
    assert (xmin + xmax) / 2 == pytest.approx(p.film_strip_z)                           # X = z
    assert cadutil.bounds(read["adapter"].solid)[3] < 0 < cadutil.bounds(read["light_dock"].solid)[2]  # camera at -Y


def test_assembly_step_has_no_overlaps_when_read_back(step):
    read = cadutil.step_assembly(step)
    placed = {n.removeprefix("ref_"): s.solid for n, s in read.items()}
    assert assembly.interference(p, False, placed) == []


def test_check_step_passes_the_file_it_wrote(slide, step):
    check = assembly.check_step(step, slide)
    assert check.problems == []
    assert check.count == 10
    assert check.volume == pytest.approx(sum(cadutil.volume(wp) for wp in slide.values()), rel=cadutil.STEP_VOLUME_RTOL)
    assert check.error < cadutil.STEP_VOLUME_RTOL


def test_check_step_flags_a_solid_missing_from_the_file(slide, step):
    wrote_more = {**slide, "extra": box(0, 1, 0, 1, 0, 1)}
    (message, *_) = assembly.check_step(step, wrote_more).problems
    assert "extra" in message and "not in the STEP" in message


def test_check_step_flags_a_solid_that_is_not_what_was_written(slide, step):
    changed = {**slide, "knob": box(0, 1, 0, 1, 0, 1)}
    messages = assembly.check_step(step, changed).problems
    assert any("knob" in m and "volume" in m for m in messages)
    assert any("total" in m for m in messages)


def test_check_step_flags_a_solid_in_the_file_that_was_not_written(slide, step):
    fewer = {k: v for k, v in slide.items() if k != "tube"}
    assert any("tube" in m for m in assembly.check_step(step, fewer).problems)


# ---- fit numbers, measured on the assembled solids --------------------------------------


def by_label(report):
    return {f.label: f for f in report}


@pytest.fixture(scope="module")
def report(slide, lock):
    return fits.report(p, slide, lock)


@pytest.fixture(scope="module")
def report_q(slide_q, lock_q):
    return fits.report(Q, slide_q, lock_q)


def test_every_fit_is_met_at_the_defaults(report):
    assert report and all(f.ok for f in report), [f for f in report if not f.ok]


def test_every_fit_is_met_at_other_params(report_q):
    assert all(f.ok for f in report_q), [f for f in report_q if not f.ok]


def test_fit_labels_are_unique(report):
    assert len({f.label for f in report}) == len(report)


def test_the_measured_numbers_are_the_designs(report):
    got = {f.label: f.measured for f in report}
    assert got["tube / adapter socket, radial clearance"] == pytest.approx(0.3, abs=1e-5)
    assert got["tube / gate hole, radial clearance"] == pytest.approx(0.3, abs=1e-5)
    assert got["film channel, SLIDE"] == pytest.approx(0.6, abs=1e-5)
    assert got["film channel, LOCK"] == pytest.approx(0.13, abs=1e-5)
    assert got["film / pressure plate, SLIDE"] == pytest.approx(0.47, abs=1e-5)
    assert got["film / pressure plate, LOCK"] == pytest.approx(0, abs=1e-5)
    assert got["film / front plate"] == pytest.approx(0, abs=1e-5)
    assert got["wedge window / frame window, z clearance, SLIDE"] == pytest.approx(2.0, abs=1e-5)
    assert got["wedge window / frame window, z clearance, LOCK"] == pytest.approx(2.0, abs=1e-5)
    assert got["tab / lid slot, x clearance, front"] == pytest.approx(0.5, abs=1e-5)
    assert got["tab / lid slot, x clearance, rear"] == pytest.approx(0.5, abs=1e-5)
    assert got["tab / lid slot, z clearance to the end, SLIDE"] == pytest.approx(1.0, abs=1e-5)
    assert got["tab / lid slot, z clearance to the end, LOCK"] == pytest.approx(1.0, abs=1e-5)
    assert got["shroud opening / rear window, z margin per side"] == pytest.approx(5.0, abs=1e-5)
    assert got["shroud opening / rear window, y margin per side"] == pytest.approx(6.0, abs=1e-5)
    assert got["pressure plate / floor, clearance"] == pytest.approx(0.25, abs=1e-5)
    assert got["pressure plate / lid, clearance"] == pytest.approx(0.25, abs=1e-5)
    assert got["pressure plate / side walls, clearance (the smaller)"] == pytest.approx(0.25, abs=1e-5)
    assert got["lid / front wall, x clearance"] == pytest.approx(0.2, abs=1e-5)
    assert got["lid / rear wall, x clearance"] == pytest.approx(0.2, abs=1e-5)
    assert got["CS-Lite slot, width less the panel"] == pytest.approx(0.5, abs=1e-5)


def test_the_gate_holes_open_top_is_noted(report):
    (hole,) = [f for f in report if f.label == "tube / gate hole, radial clearance"]
    assert "top" in hole.note


def test_a_fit_that_is_off_is_not_ok():
    assert fits.Fit("x", 0.3, 0.3).ok
    assert not fits.Fit("x", 0.31, 0.3).ok
    assert not fits.Fit("x", None, 0.3).ok


def test_the_fits_measure_the_solids_not_the_params(slide, lock):
    # a tube 0.1 too fat for its socket: the measured clearance drops, whatever params say
    fat = cq.Workplane("YZ", origin=(p.tube_x0, p.axis, 0)).circle(p.tube_ro + 0.1).extrude(10)
    report = by_label(fits.report(p, {**slide, "tube": fat}, lock))
    assert report["tube / adapter socket, radial clearance"].measured == pytest.approx(0.2, abs=1e-5)
    assert not report["tube / adapter socket, radial clearance"].ok


@pytest.mark.parametrize("label, name, moved, measured", [
    ("pressure plate / floor, clearance", "pressure_plate", (0, -0.1, 0), 0.15),
    ("pressure plate / lid, clearance", "pressure_plate", (0, 0.1, 0), 0.15),
    ("pressure plate / side walls, clearance (the smaller)", "pressure_plate", (0, 0, -0.1), 0.15),
    ("lid / front wall, x clearance", "gate_lid", (-0.05, 0, 0), 0.15),
    ("lid / rear wall, x clearance", "gate_lid", (-0.05, 0, 0), 0.25),
])
def test_the_new_clearances_are_measured_on_the_solids(slide, lock, label, name, moved, measured):
    report = by_label(fits.report(p, {**slide, name: slide[name].translate(moved)}, lock))
    assert report[label].measured == pytest.approx(measured, abs=1e-5)
    assert not report[label].ok


def test_the_cs_lite_slot_is_measured_against_the_panel(slide, lock):
    # a panel 0.2 thicker than the CS-Lite's 20 leaves 0.3 of the slot
    thick = cadutil.probe(p.x_light, p.x_light + 20.2, 4, 116, -82.5, 82.5)
    report = by_label(fits.report(p, {**slide, "cs_lite": thick}, lock))
    assert report["CS-Lite slot, width less the panel"].measured == pytest.approx(0.3, abs=1e-5)


def test_a_fit_whose_solids_are_missing_fails_instead_of_raising(slide, lock):
    without_tube = {k: v for k, v in slide.items() if k != "tube"}
    report = by_label(fits.report(p, without_tube, lock))
    assert report["tube / adapter socket, radial clearance"].measured is None
    assert not report["tube / adapter socket, radial clearance"].ok


def test_fits_with_nothing_to_measure_fail_instead_of_raising(slide, lock):
    blocks = {name: box(i * 20, i * 20 + 10, 0, 10, 0, 10) for i, name in enumerate(slide)}      # no windows, no holes

    report = fits.report(p, blocks, {**blocks})

    assert report and not any(f.ok for f in report)
    assert all("not measured" in f.note for f in report if f.measured is None)
    assert any(f.measured is None for f in report)


def test_format_report_lists_every_fit(report):
    text = fits.format_report(report)
    for f in report:
        assert f.label in text
    assert "FAIL" not in text
