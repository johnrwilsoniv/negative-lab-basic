"""Write nlb.jrwiv.com: the CAD viewer as the home page, the print preview, and the files to download.

    uv run python build.py [--wd W] [--axis A]                  # first: exports/stl/ and exports/step/
    uv run python website.py [--slot S] [--wd W] [--axis A]     # the same values
    ./publish.sh [S] [--wd W] [--axis A]                        # both, then rsync to bunbun

Writes site-out/<slot>/, served at nlb.jrwiv.com/<slot>/ (slot main is the site itself; any other slot is a
preview of a design branch):

    index.html                 viewer.py's page: the assembled CAD, with the abstract and the site's links
    print-preview/index.html   print_preview.py's page: each part on the bed, and "Latest feedback"
    files/index.html           files_page.py's page: every STL and STEP by subassembly, and the zips
    files/stl/, files/step/    every print-pose STL and STEP in exports/, to download
    files/nlb-scan-rig*.zip    all of them, the STLs, the STEPs
    files/mesh/<hash>.stl      the meshes the two pages draw, named by their content so they cache forever
    proposals/<name>/index.html  each design proposal in proposals/ (standalone drawings), with the site's icons

and, for main only, at the site root: site-out/index.html, the same home page, and the icons from icons/
(make_icons.py): favicon.ico, favicon-96x96.png, apple-touch-icon.png, the PWA icons and site.webmanifest, at the names
browsers and iOS look for. Every page links them from the root, in place of the standalone page's inline icon. The two pages are the
standalone pages' own data, with each embedded STL (`stl`, base64) moved out to a mesh file the page
fetches (`mesh`), so a page is tens of KB instead of MBs. Every link is absolute (/<slot>/...), so the
root copy of the home page needs no rewriting.
"""

import argparse
import base64
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Sequence

import build
import files_page
import print_preview
import viewer
from params import Params

ROOT = Path(__file__).parent
OUT = ROOT / "site-out"
REPO = "https://github.com/johnrwilsoniv/negative-lab-basic"
SLOT = re.compile(r"[a-z0-9][a-z0-9-]{0,39}")
ICONS = ROOT / "icons"
PROPOSALS = ROOT / "proposals"
INLINE_ICON = re.compile(r'<link rel="icon"(?: type="[^"]*")? href="data:[^"]*">')
ICON_TAGS = """<link rel="icon" href="/favicon.ico" sizes="32x32">
<link rel="icon" href="/favicon-96x96.png" type="image/png" sizes="96x96">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<link rel="manifest" href="/site.webmanifest">
<meta name="theme-color" content="#f5f7f6" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#111413" media="(prefers-color-scheme: dark)">
<meta name="apple-mobile-web-app-title" content="NLB Rig">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="default">"""


def externalize(node, mesh_dir: Path, prefix: str) -> int:
    """Move every embedded STL under node ({"stl": base64}) to mesh_dir/<hash>.stl; the entry gets "mesh" (its URL,
    prefix + file name) and "bytes" instead. Returns how many it moved."""
    moved = 0
    if isinstance(node, dict):
        if isinstance(node.get("stl"), str):
            raw = base64.b64decode(node.pop("stl"))
            name = hashlib.sha256(raw).hexdigest()[:20] + ".stl"
            mesh_dir.mkdir(parents=True, exist_ok=True)
            (mesh_dir / name).write_bytes(raw)
            node["mesh"], node["bytes"] = prefix + name, len(raw)
            moved += 1
        for value in node.values():
            moved += externalize(value, mesh_dir, prefix)
    elif isinstance(node, list):
        for value in node:
            moved += externalize(value, mesh_dir, prefix)
    return moved


def links(slot: str) -> dict:
    """The site's links as the pages show them: absolute, so a page works wherever it is copied on the site."""
    base = f"/{slot}/"
    return {
        "slot": slot,
        "home": "/" if slot == "main" else base,
        "print_preview": base + "print-preview/",
        "files": base + "files/",
        "repo": REPO,
    }


def fill(template: Path, mark: str, data: dict) -> str:
    """The template with its data filled in and its inline icon swapped for the site's icons."""
    page = template.read_text()
    if mark not in page:
        raise ValueError(f"{template} has no {mark} to fill in")
    page, icons = INLINE_ICON.subn(lambda _: ICON_TAGS, page)
    if icons != 1:
        raise ValueError(f"{template} has {icons} inline icons, not one")
    return page.replace(mark, json.dumps(data, separators=(",", ":")))


def write(p: Params, slot: str = "main", out: Path = OUT, exports: Path = build.EXPORTS) -> Path:
    """Build the slot's pages into out/<slot>/ (and out/index.html for main); returns out/<slot>."""
    if not SLOT.fullmatch(slot):
        raise ValueError(f"slot {slot!r}: use lowercase letters, digits and hyphens")
    here = out / slot
    if here.exists():
        shutil.rmtree(here)
    files = here / "files"
    site = links(slot)

    for kind in ("stl", "step"):
        src = exports / kind
        if not src.is_dir():
            raise FileNotFoundError(f"{src} is missing: run build.py first")
        shutil.copytree(src, files / kind)

    preview = print_preview.data(p, exports / "stl")
    rig = viewer.data(p, exports / "viewer")
    for d in (rig, preview):
        externalize(d, files / "mesh", site["files"] + "mesh/")
    for part in preview["parts"]:       # after externalize: these "stl" keys are links, not embedded STLs
        part["download"] = {kind: f"{site['files']}{kind}/{part['name']}.{kind}" for kind in ("stl", "step")}
    rig["built"] = preview["built"]
    rig["site"] = preview["site"] = site

    zips = files_page.write_zips(files)
    (files / "index.html").write_text(files_page.render(files, preview["parts"], site, preview["built"], zips, ICON_TAGS))

    home = fill(viewer.TEMPLATE, viewer.MARK, rig)
    (here / "index.html").write_text(home)
    (here / "print-preview").mkdir()
    (here / "print-preview" / "index.html").write_text(fill(print_preview.TEMPLATE, print_preview.MARK, preview))
    for page in sorted(PROPOSALS.glob("*.html")):
        html = page.read_text()
        if html.count("</head>") != 1:
            raise ValueError(f"{page} has no single </head> for the site's icons")
        (here / "proposals" / page.stem).mkdir(parents=True)
        (here / "proposals" / page.stem / "index.html").write_text(html.replace("</head>", ICON_TAGS + "\n</head>"))
    if slot == "main":
        (out / "index.html").write_text(home)
        for icon in ICONS.iterdir():
            shutil.copy(icon, out / icon.name)
    return here


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--slot", default="main", help="the site folder: main, or a design branch to preview")
    ap.add_argument("--wd", type=float, help="lens front to film, mm (default: params.py); as given to build.py")
    ap.add_argument("--axis", type=float, help="table to lens centre, mm (default: params.py); as given to build.py")
    args = ap.parse_args(argv)
    try:
        p = Params(**{k: v for k, v in (("wd", args.wd), ("axis", args.axis)) if v is not None})
        here = write(p, args.slot)
    except (ValueError, FileNotFoundError) as err:
        print(f"{ap.prog}: {err}", file=sys.stderr)
        return 2
    pages = sorted(here.rglob("index.html"))
    meshes = sum(f.stat().st_size for f in (here / "files" / "mesh").iterdir())
    print(f"wd={p.wd:g}  axis={p.axis:g}  slot={args.slot}  -> {here}")
    for page in pages:
        print(f"  {page.relative_to(here)}  {page.stat().st_size / 1e3:.0f} KB")
    print(f"  files/mesh/  {meshes / 1e6:.1f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
