"""The site's files/ page, in place of nginx's autoindex: every part's STL and STEP by subassembly, the assembly STEP,
and the zips (everything, the STLs, the STEPs). website.py writes the zips and the page; its one script is the
branch switcher in its head (slots.js)."""

import html
import zipfile
from pathlib import Path

KINDS = ("stl", "step")
ZIP_NAME = "nlb-scan-rig"           # nlb-scan-rig.zip unpacks to nlb-scan-rig/stl/ and nlb-scan-rig/step/
ZIPS = (                            # file, what's in it, title, line under it
    (f"{ZIP_NAME}.zip", KINDS, "Everything", "Every STL and STEP, the assembly included"),
    (f"{ZIP_NAME}-stl.zip", ("stl",), "STL", "Print pose, for the slicer"),
    (f"{ZIP_NAME}-step.zip", ("step",), "STEP", "For CAD, the assembly included"),
)


def listing(files: Path, kind: str) -> list[Path]:
    """files/<kind>/'s downloads, by name: no dotfiles (exports/ keeps a .gitkeep)."""
    return sorted(f for f in (files / kind).iterdir() if f.is_file() and not f.name.startswith("."))


def write_zips(files: Path) -> dict[str, int]:
    """files/<zip> for each of ZIPS, each file under nlb-scan-rig/<kind>/; returns each zip's size."""
    sizes = {}
    for name, kinds, _, _ in ZIPS:
        with zipfile.ZipFile(files / name, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
            for kind in kinds:
                for f in listing(files, kind):
                    z.write(f, f"{ZIP_NAME}/{kind}/{f.name}")
        sizes[name] = (files / name).stat().st_size
    return sizes


def size(n: int) -> str:
    return f"{n / 1e6:.1f} MB" if n >= 1e6 else f"{max(1, round(n / 1e3))} KB"


def nav(site: dict) -> str:
    items = (("home", "Model"), ("print_preview", "Print preview"), ("files", "Files"), ("repo", "Source"))
    current = ' aria-current="page"'
    links = "".join(f'<a href="{html.escape(site[k])}"{current if k == "files" else ""}>{t}</a>' for k, t in items)
    if site["slot"] != "main":
        links += f'<span class="slot" title="A design branch, not the current rig">preview: {site["slot"]}</span>'
    return links


def file_link(href: str, f: Path, kind: str) -> str:
    return (f'<a class="f" href="{html.escape(href)}" download><span class="k">{kind.upper()}</span>'
            f'<span class="v">{size(f.stat().st_size)}</span></a>')


def render(files: Path, parts: list[dict], site: dict, built: str, zips: dict[str, int], head: str) -> str:
    """The page, from files/ as written (sizes come from the files) and print_preview's parts (order, groups, labels)."""
    base = site["files"]
    known = {p["name"] for p in parts}
    on_disk = {kind: {f.stem: f for f in listing(files, kind)} for kind in KINDS}

    cards = "".join(
        f'<a class="zip{" main" if kinds == KINDS else ""}" href="{base}{name}" download>'
        f'<span class="zt">{title}<small>{blurb}</small></span>'
        f'<span class="zf">{name}</span><span class="v">{size(zips[name])}</span></a>'
        for name, kinds, title, blurb in ZIPS
    )

    groups: dict[str, list[str]] = {}
    for p in parts:
        cells = "".join(file_link(f"{base}{kind}/{p['name']}.{kind}", on_disk[kind][p["name"]], kind)
                        for kind in KINDS if p["name"] in on_disk[kind])
        groups.setdefault(p["group"], []).append(
            f'<li><span class="n">{html.escape(p["num"])}</span>'
            f'<span class="t">{html.escape(p["label"])}<small>{html.escape(p["name"])}</small></span>'
            f'<span class="fs">{cells}</span></li>')
    # anything exported that isn't a printed part: the assembly STEP
    extra = sorted({stem for kind in KINDS for stem in on_disk[kind]} - known)
    for stem in extra:
        cells = "".join(file_link(f"{base}{kind}/{stem}.{kind}", on_disk[kind][stem], kind)
                        for kind in KINDS if stem in on_disk[kind])
        label = "Assembled rig" if stem.endswith("-assembly") else stem
        groups.setdefault("Assembly", []).append(
            f'<li><span class="n">—</span><span class="t">{html.escape(label)}<small>{html.escape(stem)}</small></span>'
            f'<span class="fs">{cells}</span></li>')
    sections = "".join(f'<section><h3>{html.escape(g)}</h3><ul>{"".join(rows)}</ul></section>'
                       for g, rows in groups.items())

    count = sum(len(v) for v in on_disk.values())
    return PAGE.format(head=head, home=html.escape(site["home"]), nav=nav(site), built=html.escape(built),
                       cards=cards, sections=sections, count=count)


PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>NLB Scan Rig · Files</title>
<meta name="description" content="Download the NLB scan rig: every printed part as STL and STEP, the assembly STEP, or all of it zipped.">
{head}
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans+Condensed:wght@400;500;600;700&display=swap">
<style>
:root {{
  --bg: #e8ebe9; --panel: #f5f7f6; --fg: #1a1f1d; --muted: #5a6460; --line: #cbd3cf; --print: #d4891f;
  --f-ui: "IBM Plex Sans Condensed", "Arial Narrow", system-ui, sans-serif;
  --f-num: "IBM Plex Mono", ui-monospace, Menlo, Consolas, monospace;
  color-scheme: light;
}}
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {{
    --bg: #111413; --panel: #171b1a; --fg: #e3e8e5; --muted: #95a19c; --line: #2a312e; --print: #e9a23b;
    color-scheme: dark;
  }}
}}
:root[data-theme="dark"] {{
  --bg: #111413; --panel: #171b1a; --fg: #e3e8e5; --muted: #95a19c; --line: #2a312e; --print: #e9a23b;
  color-scheme: dark;
}}
* {{ box-sizing: border-box; }}
html, body {{ margin: 0; }}
body {{ background: var(--bg); color: var(--fg); font: 15px/1.45 var(--f-ui); }}
a {{ color: inherit; text-decoration: none; }}
a:focus-visible {{ outline: 2px solid var(--print); outline-offset: 2px; border-radius: 3px; }}

header {{
  display: flex; align-items: center; gap: 18px; flex-wrap: wrap;
  padding: 12px max(18px, env(safe-area-inset-left, 0px)); border-bottom: 1px solid var(--line); background: var(--panel);
}}
header h1 {{ font: 700 19px/1.1 var(--f-ui); margin: 0; letter-spacing: -0.01em; }}
header h1 span {{ color: var(--muted); font-weight: 500; }}
header h1 a:hover {{ color: var(--print); }}
nav.site {{ display: flex; flex-wrap: wrap; align-items: center; gap: 4px 14px; margin-left: auto; font: 500 13px/1.2 var(--f-ui); }}
nav.site a {{ color: var(--muted); }}
nav.site a:hover {{ color: var(--fg); }}
nav.site a[aria-current] {{ color: var(--fg); box-shadow: inset 0 -2px 0 var(--print); }}
nav.site .slot {{ font: 500 11.5px/1 var(--f-num); color: var(--print); border: 1px solid; border-radius: 3px; padding: 3px 5px; }}

main {{ max-width: 920px; margin: 0 auto; padding: 28px max(16px, env(safe-area-inset-left, 0px)) max(40px, env(safe-area-inset-bottom, 0px)); }}
h2 {{ font: 600 11.5px/1 var(--f-ui); text-transform: uppercase; letter-spacing: 0.09em; color: var(--muted); margin: 0 0 10px; }}
.lede {{ margin: 0 0 18px; color: var(--muted); font-size: 14px; }}
.lede b {{ font: 500 12.5px var(--f-num); color: var(--fg); }}

.zips {{ display: grid; grid-template-columns: 1.4fr 1fr 1fr; gap: 10px; margin-bottom: 36px; }}
a.zip {{
  display: grid; grid-template-columns: 1fr auto; grid-template-rows: 1fr auto; gap: 10px 8px;
  padding: 14px 16px; border: 1px solid var(--line); border-radius: 6px; background: var(--panel);
}}
a.zip:hover {{ border-color: var(--muted); }}
a.zip.main {{ border-color: var(--print); background: color-mix(in srgb, var(--print) 12%, var(--panel)); }}
a.zip.main:hover {{ background: color-mix(in srgb, var(--print) 20%, var(--panel)); }}
.zt {{ grid-column: 1 / -1; font: 700 18px/1.15 var(--f-ui); letter-spacing: -0.01em; }}
.zt small {{ display: block; margin-top: 3px; font: 400 13px/1.3 var(--f-ui); color: var(--muted); letter-spacing: 0; }}
.zf {{ font: 12px var(--f-num); color: var(--muted); min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; align-self: end; }}
.v {{ font: 500 12px var(--f-num); color: var(--muted); font-variant-numeric: tabular-nums; white-space: nowrap; align-self: end; }}
a.zip .v::after, a.f::after {{ content: " ↓"; color: var(--print); }}

.parts section {{ margin-bottom: 22px; }}
.parts h3 {{ font: 600 13.5px/1.2 var(--f-ui); margin: 0 0 4px; }}
.parts ul {{ list-style: none; margin: 0; padding: 0; border-top: 1px solid var(--line); }}
.parts li {{
  display: grid; grid-template-columns: 2.6em minmax(0, 1fr) auto; gap: 0 10px; align-items: center;
  padding: 7px 0; border-bottom: 1px solid var(--line);
}}
.parts .n {{ font: 500 12px var(--f-num); color: var(--print); }}
.parts .t {{ font-weight: 600; font-size: 14.5px; min-width: 0; }}
.parts .t small {{ display: block; font: 400 11.5px var(--f-num); color: var(--muted); overflow-wrap: anywhere; }}
.fs {{ display: flex; gap: 6px; }}
a.f {{
  display: inline-flex; align-items: baseline; gap: 8px; padding: 6px 10px; min-width: 132px; justify-content: space-between;
  border: 1px solid var(--line); border-radius: 4px; background: var(--panel);
}}
a.f:hover {{ border-color: var(--print); background: color-mix(in srgb, var(--print) 12%, var(--panel)); }}
a.f .k {{ font: 600 12px/1 var(--f-ui); letter-spacing: 0.06em; }}
a.f .v {{ align-self: baseline; }}
.foot {{ margin: 28px 0 0; font: 12px var(--f-num); color: var(--muted); }}

@media (max-width: 680px) {{
  nav.site {{ margin-left: 0; }}
  .zips {{ grid-template-columns: 1fr 1fr; }}
  a.zip.main {{ grid-column: 1 / -1; }}
  .parts li {{ grid-template-columns: 2.2em minmax(0, 1fr); row-gap: 6px; }}
  .fs {{ grid-column: 2; }}
  a.f {{ min-width: 0; flex: 1; }}
}}
</style>
</head>
<body>
<header>
  <h1><a href="{home}">NLB scan rig</a> <span>· files</span></h1>
  <nav class="site" aria-label="Site">{nav}</nav>
</header>
<main>
  <h2>Download everything</h2>
  <p class="lede">The whole rig in one zip, or just one format. Built at <b>{built}</b>.</p>
  <div class="zips">{cards}</div>

  <h2>Each part</h2>
  <p class="lede">STLs are in print pose (Z up, the bed at Z = 0); STEPs open in Onshape or any CAD. {count} files.</p>
  <div class="parts">{sections}</div>
</main>
</body>
</html>
"""
