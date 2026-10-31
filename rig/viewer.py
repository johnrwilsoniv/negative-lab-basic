"""Write the 3D viewer: the mockup page, drawing the CadQuery solids instead of its own boxes.

    uv run python viewer.py [--wd W] [--axis A]

Writes exports/viewer/<solid>.stl (the assembled pose, mockup coordinates, at SLIDE) and
exports/nlb-scan-rig.html, one self-contained page with those STLs embedded. The page template is
mockup/viewer.html. The camera, lens, film and CS-Lite are still drawn by the page: they are bought,
so there is no CAD for them.
"""

import argparse
import base64
import json
import sys
from pathlib import Path
from typing import Sequence

import assembly
import build
import cadutil
import fits
from params import Params

ROOT = Path(__file__).parent
TEMPLATE = ROOT / "mockup" / "viewer.html"
OUT = build.EXPORTS / "nlb-scan-rig.html"
STL_DIR = build.EXPORTS / "viewer"
MARK = "/*__RIG_DATA__*/null"


def _offset(slide: cadutil.Bounds, lock: cadutil.Bounds) -> list[float]:
    """How far a solid moves from SLIDE to LOCK; ValueError unless it only moves (the page only translates)."""
    lo = [lock[i] - slide[i] for i in (0, 2, 4)]
    hi = [lock[i] - slide[i] for i in (1, 3, 5)]
    if any(abs(a - b) > 1e-6 for a, b in zip(lo, hi)):
        raise ValueError("a solid changes shape between SLIDE and LOCK")
    return [round(v + 0.0, 6) for v in lo]


def data(p: Params, stl_dir: Path = STL_DIR) -> dict:
    """Everything the page needs: each printed solid's STL and numbers, the fits, the params."""
    modules = build.discover()
    slide = assembly.placed(p, False, modules)
    lock = assembly.placed(p, True, modules)
    ups = {name: up for m in modules.values() for name, up in m.PRINT_UP.items()}
    stl_dir.mkdir(parents=True, exist_ok=True)

    solids = []
    for name in assembly.PRINTED:
        wp = slide[name]
        path = stl_dir / f"{name}.stl"
        ok = cadutil.solid(wp).exportStl(
            str(path), tolerance=cadutil.STL_LINEAR_TOL, angularTolerance=cadutil.STL_ANGULAR_TOL, relative=False
        )
        if not ok:
            raise RuntimeError(f"STL export to {path} failed")
        posed = cadutil.print_pose(wp, ups[name])
        solids.append({
            "name": name,
            "stl": base64.b64encode(path.read_bytes()).decode(),
            "lock": _offset(cadutil.bounds(wp), cadutil.bounds(lock[name])),
            "volume": round(cadutil.volume(wp), 1),
            "size": [round(v, 2) for v in cadutil.size(wp)],
            "print": [round(v, 2) for v in cadutil.size(posed)],
            "up": ups[name],
            "bed": cadutil.fits_bed(posed, p),
        })

    found = {pos: assembly.interference(p, is_lock, s) for pos, is_lock, s in (("SLIDE", False, slide), ("LOCK", True, lock))}
    return {
        "p": {
            k: getattr(p, k) for k in (
                "wd", "axis", "lens_len", "lens_r", "thread_major", "thread_pitch", "x_front", "x_film",
                "x_gate", "x_light", "gh", "gate_d", "channel", "film_t", "film_w", "film_strip_len",
                "film_strip_z", "csl_l", "csl_h", "csl_t", "csl_lit_w", "csl_lit_h", "floor_t",
                "sw_travel", "preload", "bed_x", "bed_y", "win_w", "win_h", "gap", "x_knob",
            )
        },
        "solids": solids,
        "fits": [
            {"label": f.label, "measured": f.measured, "expected": f.expected, "ok": f.ok}
            for f in fits.report(p, slide, lock)
        ],
        "interference": {pos: assembly.problems(p, pos == "LOCK", f) for pos, f in found.items()},
    }


def write(p: Params, out: Path = OUT, template: Path = TEMPLATE) -> dict:
    page = template.read_text()
    if MARK not in page:
        raise ValueError(f"{template} has no {MARK} to fill in")
    d = data(p)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page.replace(MARK, json.dumps(d, separators=(",", ":"))))
    return d


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--wd", type=float, help="lens front to film, mm (default: params.py)")
    ap.add_argument("--axis", type=float, help="table to lens centre, mm (default: params.py)")
    args = ap.parse_args(argv)
    try:
        p = Params(**{k: v for k, v in (("wd", args.wd), ("axis", args.axis)) if v is not None})
    except ValueError as err:
        print(f"{ap.prog}: {err}", file=sys.stderr)
        return 2
    d = write(p)
    bad = [f["label"] for f in d["fits"] if not f["ok"]] + [m for ms in d["interference"].values() for m in ms]
    size = OUT.stat().st_size / 1e6
    print(f"wd={p.wd:g}  axis={p.axis:g}  {len(d['solids'])} solids  {size:.1f} MB  -> {OUT}")
    for message in bad:
        print(f"  FAIL: {message}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
