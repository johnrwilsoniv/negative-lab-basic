"""build.py: part discovery, per-solid checks, print-pose exports, report and exit status."""

import io
import subprocess
import sys
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace

import cadquery as cq
import pytest

import build
import cadutil
from params import DEFAULT


def box(dx, dy, dz):
    return cq.Workplane("XY").box(dx, dy, dz, centered=False).translate((100, 50, 7))


def fake_part(solids, up, extras=None):
    """A stand-in for a parts.<part>.model module."""
    part = SimpleNamespace(build=lambda p=DEFAULT, lock=False: solids, PRINT_UP=up)
    if extras is not None:
        part.extras = lambda p=DEFAULT: extras
    return part


# ---- discovery -----------------------------------------------------------------------


def test_discover_finds_models_in_build_order_and_skips_missing(tmp_path, monkeypatch):
    for part in ("tube", "lens_adapter"):                      # film_gate etc. have no model.py yet
        folder = tmp_path / "fakeparts" / part
        folder.mkdir(parents=True)
        (folder / "__init__.py").write_text("")
        (folder / "model.py").write_text(f"NAME = {part!r}\n")
    (tmp_path / "fakeparts" / "__init__.py").write_text("")
    (tmp_path / "fakeparts" / "film_gate").mkdir()
    monkeypatch.syspath_prepend(str(tmp_path))

    found = build.discover(tmp_path, "fakeparts")

    assert list(found) == ["lens_adapter", "tube"]
    assert found["tube"].NAME == "tube"


def test_build_order_is_the_plan_order():
    assert build.PARTS == ("lens_adapter", "tube", "film_gate", "lock_switch", "light_dock")


# ---- checks and exports --------------------------------------------------------------


def test_good_part_is_checked_and_exported_in_print_pose(tmp_path):
    # 30 x 20 x 10 with +x up: prints 10 tall, on the bed, centred
    part = fake_part({"slab": box(30, 20, 10)}, {"slab": "+x"})

    (row,) = build.build_parts(DEFAULT, {"fake": part}, tmp_path)

    assert row.ok and row.problems() == []
    assert (row.part, row.name, row.valid) == ("fake", "slab", True)
    assert row.volume == pytest.approx(6000)
    assert row.size == pytest.approx((30, 20, 10))      # mockup coordinates
    assert row.posed[2] == pytest.approx(30)
    assert sorted(row.posed[:2]) == pytest.approx([10, 20])
    assert row.fits_bed
    assert row.step_err < cadutil.STEP_VOLUME_RTOL

    reread = cq.importers.importStep(str(tmp_path / "step" / "slab.step"))
    x0, x1, y0, y1, z0, z1 = cadutil.bounds(reread)
    assert (z0, z1) == pytest.approx((0, 30), abs=1e-6)
    assert ((x0 + x1) / 2, (y0 + y1) / 2) == pytest.approx((0, 0), abs=1e-6)
    assert (tmp_path / "stl" / "slab.stl").stat().st_size > 0


def test_extras_are_built_and_exported_too(tmp_path):
    part = fake_part(
        {"main": box(10, 10, 10)}, {"main": "+z", "coupon": "+z"}, extras={"coupon": box(5, 5, 5)}
    )

    rows = build.build_parts(DEFAULT, {"fake": part}, tmp_path)

    assert [r.name for r in rows] == ["main", "coupon"]
    assert all(r.ok for r in rows)
    assert (tmp_path / "step" / "coupon.step").exists()


def test_a_part_too_big_for_the_bed_fails(tmp_path):
    part = fake_part({"huge": box(230, 50, 10)}, {"huge": "+z"})

    (row,) = build.build_parts(DEFAULT, {"fake": part}, tmp_path)

    assert not row.fits_bed and not row.ok
    assert any("bed" in problem for problem in row.problems())


def test_a_solid_with_no_print_direction_fails_without_exporting(tmp_path):
    part = fake_part({"orphan": box(10, 10, 10)}, {})

    (row,) = build.build_parts(DEFAULT, {"fake": part}, tmp_path)

    assert not row.ok
    assert any("PRINT_UP" in problem for problem in row.problems())
    assert not (tmp_path / "step" / "orphan.step").exists()


def test_two_solids_in_one_workplane_fail(tmp_path):
    two = box(10, 10, 10).union(box(10, 10, 10).translate((50, 0, 0)))
    part = fake_part({"pair": two}, {"pair": "+z"})

    (row,) = build.build_parts(DEFAULT, {"fake": part}, tmp_path)

    assert not row.ok
    assert any("2 solids" in problem for problem in row.problems())


def test_duplicate_solid_names_across_parts_are_rejected(tmp_path):
    parts = {
        "a": fake_part({"same": box(10, 10, 10)}, {"same": "+z"}),
        "b": fake_part({"same": box(10, 10, 10)}, {"same": "+z"}),
    }
    with pytest.raises(ValueError, match="same"):
        build.build_parts(DEFAULT, parts, tmp_path)


# ---- command line --------------------------------------------------------------------


def test_no_parts_runs_cleanly_and_says_so(tmp_path, capsys):
    assert build.main([], parts={}, out_dir=tmp_path) == 0
    assert "no parts" in capsys.readouterr().out.lower()


def test_main_prints_one_table_and_returns_zero_when_all_pass(tmp_path, capsys):
    part = fake_part({"slab": box(30, 20, 10)}, {"slab": "+z"})

    assert build.main([], parts={"fake": part}, out_dir=tmp_path) == 0

    out = capsys.readouterr().out
    assert "slab" in out and "FAIL" not in out
    assert out.count("slab") == 1


def test_main_returns_nonzero_when_a_check_fails(tmp_path, capsys):
    part = fake_part({"huge": box(230, 50, 10)}, {"huge": "+z"})

    assert build.main([], parts={"fake": part}, out_dir=tmp_path) == 1

    assert "FAIL" in capsys.readouterr().out


def test_wd_and_axis_reach_the_parts(tmp_path):
    seen = []

    def build_part(p=DEFAULT, lock=False):
        seen.append((p.wd, p.axis))
        return {"slab": box(10, 10, 10)}

    part = SimpleNamespace(build=build_part, PRINT_UP={"slab": "+z"})
    build.main(["--wd", "150", "--axis", "40"], parts={"fake": part}, out_dir=tmp_path)

    assert seen and set(seen) == {(150, 40)}     # the table's build, and the assembly's look at the same parts


def test_an_axis_too_low_for_the_adapter_is_one_line_on_stderr_and_a_failure(tmp_path, capsys):
    part = fake_part({"slab": box(10, 10, 10)}, {"slab": "+z"})

    assert build.main(["--axis", "35"], parts={"fake": part}, out_dir=tmp_path) != 0

    out, err = capsys.readouterr()
    assert out == ""                                     # nothing built, no table
    (line,) = err.strip().splitlines()
    assert "axis" in line and "adapter" in line and "39" in line
    assert not (tmp_path / "step").exists()


def test_the_command_line_refuses_an_impossible_axis_without_a_traceback():
    run = subprocess.run(
        [sys.executable, "build.py", "--axis", "35"],
        cwd=Path(build.__file__).parent, capture_output=True, text=True, timeout=120, check=False,
    )
    assert run.returncode != 0
    assert run.stdout == ""
    assert "Traceback" not in run.stderr
    assert len(run.stderr.strip().splitlines()) == 1


# ---- assembly stage ------------------------------------------------------------------


def stub(x0, x1):
    """A 10 x 10 slab from x0 to x1."""
    return cadutil.probe(x0, x1, 0, 10, 0, 10)


def test_main_leaves_the_assembly_out_until_every_part_exists(tmp_path, capsys):
    part = fake_part({"slab": box(30, 20, 10)}, {"slab": "+z"})

    assert build.main([], parts={"fake": part}, out_dir=tmp_path) == 0

    out = capsys.readouterr().out
    assert "assembly skipped" in out.lower() and "tube" in out
    assert not (tmp_path / "step" / "nlb-scan-rig-assembly.step").exists()


def test_main_returns_nonzero_when_the_assembly_checks_fail(tmp_path, capsys):
    # every printed solid present, none touching another, but no clamp at LOCK and none of the fits to measure
    names = ["adapter", "tube", "gate_box", "gate_lid", "pressure_plate", "wedge_plate", "knob", "light_dock"]
    solids = {name: stub(20 * i, 20 * i + 10) for i, name in enumerate(names)}
    part = fake_part(solids, {name: "+z" for name in names})

    assert build.main([], parts={"fake": part}, out_dir=tmp_path) == 1

    out = capsys.readouterr().out
    assert "should overlap" in out and "FAIL" in out
    assert (tmp_path / "step" / "nlb-scan-rig-assembly.step").exists()


def test_interference_report_at_the_designed_result():
    slide = {"pressure_plate": stub(0, 1), "wedge_plate": stub(1, 2)}      # touching
    lock = {"pressure_plate": stub(0, 1.1133), "wedge_plate": stub(1, 2)}   # 0.1133 in
    lock_p = DEFAULT

    text, ok = build.format_interference(lock_p, slide, lock)

    assert ok
    assert "SLIDE" in text and "none" in text
    assert "pressure_plate x wedge_plate" in text and "x-thickness 0.1133" in text
    assert "FAIL" not in text


def test_interference_report_fails_on_a_slide_overlap():
    slide = {"pressure_plate": stub(0, 1.5), "wedge_plate": stub(1, 2)}
    lock = {"pressure_plate": stub(0, 1.1133), "wedge_plate": stub(1, 2)}

    text, ok = build.format_interference(DEFAULT, slide, lock)

    assert not ok
    assert "FAIL" in text and "SLIDE" in text


def test_interference_report_fails_on_a_lock_without_the_clamp():
    touching = {"pressure_plate": stub(0, 1), "wedge_plate": stub(1, 2)}

    text, ok = build.format_interference(DEFAULT, touching, touching)

    assert not ok
    assert "FAIL" in text and "should overlap" in text


def test_interference_report_names_every_pair_that_intersects():
    slide = {"tube": stub(0, 5), "adapter": stub(4, 9), "film": stub(4.5, 6)}

    text, ok = build.format_interference(DEFAULT, slide, slide)

    assert not ok
    assert "tube x adapter" in text and "tube x film" in text and "adapter x film" in text


def test_bed_report_gives_every_solids_margin_on_each_side():
    rows = [
        build.Row("dock", "light_dock", True, 1.0, (35, 67.5, 181), (35, 181, 67.5), True),
        build.Row("tube", "tube", True, 1.0, (117, 72, 72), (72, 72, 117), True),
    ]

    text = build.format_bed(rows, DEFAULT)

    dock = next(line for line in text.splitlines() if "light_dock" in line)
    assert "35.00 x 181.00" in dock and "185.00" in dock and "39.00" in dock
    assert "148.00" in next(line for line in text.splitlines() if line.lstrip().startswith("tube"))


def test_bed_report_has_nothing_to_say_about_a_solid_that_could_not_be_checked():
    rows = [build.Row("p", "broken", error="expected exactly 1 solid, found 2 solids")]
    assert "broken" not in build.format_bed(rows, DEFAULT)


@pytest.fixture(scope="module")
def real_run(tmp_path_factory):
    """The whole rig through main(), once: the slowest test in the suite."""
    out_dir = tmp_path_factory.mktemp("exports")
    out = io.StringIO()
    with redirect_stdout(out):
        code = build.main([], out_dir=out_dir)
    return code, out.getvalue(), out_dir


def test_a_full_build_passes_and_writes_the_assembly_step(real_run):
    code, out, out_dir = real_run
    assert code == 0, out
    assert "FAIL" not in out
    path = out_dir / "step" / "nlb-scan-rig-assembly.step"
    assert path.stat().st_size > 0
    assert len(cadutil.step_assembly(path)) == 10


def test_a_full_build_reports_the_assembly_in_order(real_run):
    _, out, _ = real_run
    order = [out.index(text) for text in
             ("thread_coupon", "Assembly STEP", "Interference", "pressure_plate x wedge_plate",
              "radial clearance", "Bed margins")]
    assert order == sorted(order)
    assert out.count("pressure_plate x wedge_plate") == 1       # LOCK only
