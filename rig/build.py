"""Build every printed part, export STEP and STL in print pose, and check them.

    uv run python build.py [--wd W] [--axis A]

Writes exports/step/<solid>.step and exports/stl/<solid>.stl, prints one table of numbers,
then puts the parts together: writes exports/step/nlb-scan-rig-assembly.step, checks that nothing
intersects at SLIDE or LOCK, and prints the fit numbers and the bed margins. Exits non-zero if any
check fails, and with 2 and a one-line message (nothing built) if the params are impossible, such as
an axis too low for the lens adapter.
"""

import argparse
import importlib
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from types import ModuleType
from typing import Mapping, Sequence

import cadquery as cq

import assembly
import cadutil
import fits
from params import Params

ROOT = Path(__file__).parent
EXPORTS = ROOT / "exports"
PARTS = ("lens_adapter", "tube", "film_gate", "lock_switch", "light_dock")   # build order

Size = tuple[float, float, float]


@dataclass(frozen=True)
class Row:
    part: str
    name: str
    valid: bool = False
    volume: float = 0.0
    size: Size = (0.0, 0.0, 0.0)     # mockup coordinates
    posed: Size = (0.0, 0.0, 0.0)    # print pose
    fits_bed: bool = False
    step_err: float | None = None    # relative volume error after the STEP round trip; None = not checked
    error: str = ""                  # set when the solid could not be checked at all

    def problems(self) -> list[str]:
        if self.error:
            return [self.error]
        found = []
        if not self.valid:
            found.append("invalid solid")
        if self.volume <= 0:
            found.append("volume <= 0")
        if not self.fits_bed:
            found.append("does not fit the bed")
        if self.step_err is None:
            found.append("STEP round trip not checked")
        elif self.step_err > cadutil.STEP_VOLUME_RTOL:
            found.append(f"STEP round trip changes the volume by {self.step_err:.1e}")
        return found

    @property
    def ok(self) -> bool:
        return not self.problems()


def discover(root: Path = ROOT, package: str = "parts") -> dict[str, ModuleType]:
    """Part modules in build order; parts whose model.py doesn't exist yet are skipped."""
    return {
        part: importlib.import_module(f"{package}.{part}.model")
        for part in PARTS
        if (root / package / part / "model.py").exists()
    }


def check_solid(
    part: str, name: str, wp: cq.Workplane, up: str | None, p: Params, out_dir: Path
) -> Row:
    try:
        cadutil.solid(wp)
    except ValueError as err:
        return Row(part, name, error=str(err))
    if up is None:
        return Row(part, name, error="no PRINT_UP entry for this solid")

    valid, volume, size = cadutil.is_valid(wp), cadutil.volume(wp), cadutil.size(wp)
    posed = cadutil.print_pose(wp, up)
    row = Row(part, name, valid, volume, size, cadutil.size(posed), cadutil.fits_bed(posed, p))
    if not valid or volume <= 0:
        return row     # nothing sensible to export

    step, stl = out_dir / "step" / f"{name}.step", out_dir / "stl" / f"{name}.stl"
    cadutil.export(posed, step, stl)
    step_err = abs(cadutil.step_volume(step) - volume) / volume
    return replace(row, step_err=step_err)


def build_parts(p: Params, parts: Mapping[str, ModuleType], out_dir: Path = EXPORTS) -> list[Row]:
    """Build, check and export every solid (and extra) of every part."""
    rows: list[Row] = []
    seen: set[str] = set()
    for part, model in parts.items():
        solids = dict(model.build(p))
        if hasattr(model, "extras"):
            solids.update(model.extras(p))
        for name, wp in solids.items():
            if name in seen:
                raise ValueError(f"solid name {name!r} is used by more than one part; exports would collide")
            seen.add(name)
            rows.append(check_solid(part, name, wp, model.PRINT_UP.get(name), p, out_dir))
    return rows


def _dims(size: Size) -> str:
    return " x ".join(f"{v:.2f}" for v in size)


def format_table(rows: Sequence[Row]) -> str:
    header = ("part", "solid", "volume mm3", "mockup x*y*z", "print x*y*z", "STEP dV", "result")
    cells = [
        (
            r.part,
            r.name,
            f"{r.volume:.1f}",
            _dims(r.size),
            _dims(r.posed),
            "-" if r.step_err is None else f"{r.step_err:.1e}",
            "ok" if r.ok else "FAIL: " + "; ".join(r.problems()),
        )
        for r in rows
    ]
    return cadutil.format_table([header, *cells])


def format_interference(
    p: Params, slide: Mapping[str, cq.Workplane], lock: Mapping[str, cq.Workplane]
) -> tuple[str, bool]:
    """The interference report for the assembled `slide` and `lock` solids, and whether it is as designed."""
    lines = [
        f"Interference: {len(assembly.pairs(slide))} pairs at each position; touching (a common volume of "
        f"at most {assembly.CONTACT_VOLUME:g} mm3) is fine"
    ]
    ok = True
    for position, is_lock, solids in (("SLIDE", False, slide), ("LOCK", True, lock)):
        found = assembly.interference(p, is_lock, solids)
        wrong = assembly.problems(p, is_lock, found)
        designed = {frozenset((a, b)): thickness for a, b, thickness in assembly.allowed(p, is_lock)}
        ok = ok and not wrong
        for a, b, volume, thickness in found:
            note = (
                f"designed: preload {designed[frozenset((a, b))]:.4f} +- {assembly.PRELOAD_TOL:g}"
                if frozenset((a, b)) in designed else "not allowed"
            )
            lines.append(f"  {position:<5}  {a} x {b}  {volume:.4f} mm3  x-thickness {thickness:.4f}  ({note})")
        if not found:
            lines.append(f"  {position:<5}  none")
        lines += [f"  FAIL {position}: {message}" for message in wrong]
    return "\n".join(lines), ok


def format_bed(rows: Sequence[Row], p: Params) -> str:
    """Per solid, its footprint in print pose and how much of the bed is left on each side of it."""
    header = ("solid", "footprint x*y", "margin x", "margin y")
    cells = [
        (r.name, f"{r.posed[0]:.2f} x {r.posed[1]:.2f}", f"{p.bed_x - r.posed[0]:.2f}", f"{p.bed_y - r.posed[1]:.2f}")
        for r in rows if not r.error
    ]
    return cadutil.format_table([header, *cells])


def check_assembly(p: Params, parts: Mapping[str, ModuleType], rows: Sequence[Row], out_dir: Path) -> bool:
    """Put the parts together and print what comes of it; whether every check passed.

    Writes the assembly STEP (SLIDE) into out_dir/step and reads it back. Waits for every part to exist.
    """
    if any(r.error for r in rows):
        print("\nAssembly skipped: fix the solids above first.")
        return False
    slide = assembly.placed(p, False, parts)
    missing = [name for name in assembly.PRINTED if name not in slide]
    if missing:
        print(f"\nAssembly skipped: no {', '.join(missing)} yet.")
        return True
    lock = assembly.placed(p, True, parts)

    path = out_dir / "step" / assembly.STEP_PATH.name
    assembly.write_step(p, path, slide)
    step = assembly.check_step(path, slide)
    print(f"\nAssembly STEP: {path}")
    print(
        f"  {len(slide)} solids written (SLIDE), {step.count} read back; volume {step.expected:.1f} mm3 written, "
        f"{step.volume:.1f} read back, dV {step.error:.1e}"
    )
    for message in step.problems:
        print(f"  FAIL: {message}")

    text, interference_ok = format_interference(p, slide, lock)
    print("\n" + text)

    report = fits.report(p, slide, lock)
    print("\nFit numbers, measured on the assembled solids\n" + fits.format_report(report))

    print(f"\nBed margins ({p.bed_x:g} x {p.bed_y:g}, print pose)\n" + format_bed(rows, p))
    return not step.problems and interference_ok and all(f.ok for f in report)


def main(
    argv: Sequence[str] | None = None,
    *,
    parts: Mapping[str, ModuleType] | None = None,
    out_dir: Path = EXPORTS,
) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--wd", type=float, help="lens front to film, mm (default: params.py)")
    ap.add_argument("--axis", type=float, help="table to lens centre, mm (default: params.py)")
    args = ap.parse_args(argv)
    try:
        p = Params(**{k: v for k, v in (("wd", args.wd), ("axis", args.axis)) if v is not None})
    except ValueError as err:
        print(f"{ap.prog}: {err}", file=sys.stderr)
        return 2

    print(f"wd={p.wd:g}  axis={p.axis:g}  bed={p.bed_x:g} x {p.bed_y:g}")
    parts = discover() if parts is None else parts
    if not parts:
        print("No parts yet: no parts/<part>/model.py found for " + ", ".join(PARTS) + ".")
        return 0

    rows = build_parts(p, parts, out_dir)
    print(format_table(rows))
    failed = [r for r in rows if not r.ok]
    print(f"\n{len(rows)} solids, {len(failed)} failed. Exports in {out_dir}.")

    assembled = check_assembly(p, parts, rows, out_dir)
    return 1 if failed or not assembled else 0


if __name__ == "__main__":
    raise SystemExit(main())
