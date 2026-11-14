"""website.py: embedded STLs moved out to hashed mesh files, the slot's pages and files, the site's links."""

import base64
import hashlib
import json
import re

import pytest

import print_preview
import viewer
import website
from params import DEFAULT

STL_A, STL_B = b"solid a" + bytes(80), b"solid b" + bytes(120)
ICON_FILES = ["favicon.ico", "favicon-96x96.png", "apple-touch-icon.png", "icon-192.png", "icon-512.png",
              "icon-maskable-512.png", "site.webmanifest"]
B64 = lambda raw: base64.b64encode(raw).decode()     # noqa: E731


def page_data(html: str) -> dict:
    """The JSON a page was filled with (the template's mark, replaced)."""
    m = re.search(r"const (?:RIG|DATA) = (\{.*?\});?\n", html)
    assert m, "no data in the page"
    return json.loads(m.group(1).rstrip(";"))


# ---- externalize ----------------------------------------------------------------------------


def test_externalize_moves_every_embedded_stl_to_a_hashed_file(tmp_path):
    d = {"solids": [{"name": "a", "stl": B64(STL_A)}], "assembly": {"refs": [{"name": "b", "stl": B64(STL_B)},
                                                                            {"name": "box", "box": [0, 1]}]}}
    assert website.externalize(d, tmp_path, "/main/files/mesh/") == 2
    a, b = d["solids"][0], d["assembly"]["refs"][0]
    assert "stl" not in a and "stl" not in b
    assert a["mesh"] == f"/main/files/mesh/{hashlib.sha256(STL_A).hexdigest()[:20]}.stl"
    assert (tmp_path / a["mesh"].rsplit("/", 1)[1]).read_bytes() == STL_A
    assert (a["bytes"], b["bytes"]) == (len(STL_A), len(STL_B))
    assert d["assembly"]["refs"][1] == {"name": "box", "box": [0, 1]}      # nothing embedded: untouched


def test_the_same_mesh_twice_is_one_file(tmp_path):
    d = [{"stl": B64(STL_A)}, {"stl": B64(STL_A)}]
    website.externalize(d, tmp_path, "/x/")
    assert d[0]["mesh"] == d[1]["mesh"]
    assert len(list(tmp_path.iterdir())) == 1


# ---- links ---------------------------------------------------------------------------------


def test_main_is_the_site_root_and_other_slots_are_folders():
    assert website.links("main")["home"] == "/"
    assert website.links("main")["print_preview"] == "/main/print-preview/"
    assert website.links("fix-a")["home"] == "/fix-a/"
    assert website.links("fix-a")["files"] == "/fix-a/files/"


@pytest.mark.parametrize("slot", ["", "Main", "../x", "a/b", "a_b", "-a", "x" * 41])
def test_a_slot_is_a_plain_folder_name(tmp_path, slot):
    with pytest.raises(ValueError, match="slot"):
        website.write(DEFAULT, slot, tmp_path / "out", tmp_path)


# ---- write: the pages and files, with stand-ins for the CAD ------------------------------------


@pytest.fixture
def exports(tmp_path, monkeypatch):
    """exports/stl and exports/step with two parts, and viewer/print_preview data that embeds their STLs."""
    ex = tmp_path / "exports"
    for kind in ("stl", "step"):
        (ex / kind).mkdir(parents=True)
        for name in ("tube", "adapter"):
            (ex / kind / f"{name}.{kind}").write_bytes(STL_A if name == "tube" else STL_B)
    (ex / "step" / "nlb-scan-rig-assembly.step").write_bytes(b"assembly")

    def pp_data(p, stl_dir):
        assert stl_dir == ex / "stl"
        parts = [{"name": n, "num": num, "label": n.title(), "group": "1 · Lens adapter",
                  "stl": B64((stl_dir / f"{n}.stl").read_bytes())} for n, num in (("tube", "1b"), ("adapter", "1"))]
        return {"parts": parts, "assembly": {"solids": [{"name": "tube", "stl": B64(b"coarse" + bytes(90))}],
                                             "refs": [{"name": "cs_lite", "box": [0] * 6}]},
                "built": "wd 111 · axis 40.5 · abc1234 · 2026-11-09"}

    def rig_data(p, stl_dir):
        return {"p": {"wd": p.wd}, "solids": [{"name": "tube", "stl": B64(b"posed" + bytes(90))}]}

    monkeypatch.setattr(print_preview, "data", pp_data)
    monkeypatch.setattr(viewer, "data", rig_data)
    return ex


def test_main_writes_both_pages_the_files_and_the_root(tmp_path, exports):
    out = tmp_path / "out"
    here = website.write(DEFAULT, "main", out, exports)
    home, pp = (here / "index.html").read_text(), (here / "print-preview" / "index.html").read_text()
    assert (out / "index.html").read_text() == home
    for page in (home, pp):
        assert not re.search(r'"stl":"(?!/)', page)        # nothing embedded: an "stl" is only ever a download link
        assert "__RIG_DATA__" not in page and "__PRINT_DATA__" not in page
    rig, prev = page_data(home), page_data(pp)
    assert rig["built"] == prev["built"]
    assert rig["site"]["print_preview"] == "/main/print-preview/"
    for entry in (rig["solids"][0], prev["parts"][0], prev["assembly"]["solids"][0]):
        assert (here / entry["mesh"].removeprefix("/main/")).is_file()
    assert prev["parts"][1]["download"] == {"stl": "/main/files/stl/adapter.stl", "step": "/main/files/step/adapter.step"}
    assert (here / "files" / "stl" / "adapter.stl").read_bytes() == STL_B
    assert (here / "files" / "step" / "nlb-scan-rig-assembly.step").is_file()


def test_main_puts_the_icons_at_the_site_root_and_every_page_links_them(tmp_path, exports):
    out = tmp_path / "out"
    here = website.write(DEFAULT, "main", out, exports)
    for name in ICON_FILES:
        assert (out / name).read_bytes() == (website.ICONS / name).read_bytes()
    for page in (out / "index.html", here / "index.html", here / "print-preview" / "index.html"):
        html = page.read_text()
        assert 'href="data:' not in html                     # the standalone page's inline icon is gone
        for href in ("/favicon.ico", "/favicon-96x96.png", "/apple-touch-icon.png", "/site.webmanifest"):
            assert f'href="{href}"' in html


def test_the_manifest_names_icons_that_exist():
    manifest = json.loads((website.ICONS / "site.webmanifest").read_text())
    assert manifest["display"] == "standalone" and manifest["start_url"] == "/"
    assert {i.get("purpose", "any") for i in manifest["icons"]} >= {"any", "maskable"}
    for icon in manifest["icons"]:
        assert (website.ICONS / icon["src"].lstrip("/")).is_file()


def test_the_iphone_icon_is_180px_and_opaque():
    from PIL import Image
    with Image.open(website.ICONS / "apple-touch-icon.png") as im:
        assert im.size == (180, 180) and im.mode == "RGB"


def test_each_proposal_is_a_page_of_its_own_with_the_sites_icons(tmp_path, exports, monkeypatch):
    proposals = tmp_path / "proposals"
    proposals.mkdir()
    (proposals / "fb1-fix.html").write_text("<!doctype html><html><head><title>Fix</title></head><body>drawings</body></html>")
    monkeypatch.setattr(website, "PROPOSALS", proposals)
    here = website.write(DEFAULT, "a-branch", tmp_path / "out", exports)
    html = (here / "proposals" / "fb1-fix" / "index.html").read_text()
    assert "drawings" in html and html.index('href="/favicon.ico"') < html.index("</head>")


def test_the_repos_proposals_are_published():
    """Any there are: this branch has none (main's proposals/fb5-fb6.html draws the clamp gate, which D1 removed)."""
    for page in website.PROPOSALS.glob("*.html"):
        assert page.read_text().count("</head>") == 1, page.name


def test_a_slot_builds_without_a_proposals_folder(tmp_path, exports, monkeypatch):
    monkeypatch.setattr(website, "PROPOSALS", tmp_path / "no-proposals")
    here = website.write(DEFAULT, "a-branch", tmp_path / "out", exports)
    assert (here / "index.html").is_file() and not (here / "proposals").exists()


def test_another_slot_leaves_the_root_alone_and_rebuilds_its_folder(tmp_path, exports):
    out = tmp_path / "out"
    (out / "fix-a" / "stale").mkdir(parents=True)
    here = website.write(DEFAULT, "fix-a", out, exports)
    assert not (out / "index.html").exists()
    assert not (out / "favicon.ico").exists()
    assert not (here / "stale").exists()
    assert page_data((here / "index.html").read_text())["site"]["home"] == "/fix-a/"


@pytest.mark.parametrize("slot", ["main", "fix-a"])
def test_every_page_loads_its_slots_branch_switcher(tmp_path, exports, slot):
    out = tmp_path / "out"
    here = website.write(DEFAULT, slot, out, exports)
    assert (here / "slots.js").read_text() == website.SWITCHER.read_text()
    pages = [here / "index.html", here / "print-preview" / "index.html", here / "files" / "index.html"]
    for page in pages + ([out / "index.html"] if slot == "main" else []):
        assert f'<script src="/{slot}/slots.js" data-slot="{slot}" defer></script>' in page.read_text()


def test_the_switcher_lists_the_slots_nginx_lists():
    conf = (website.ROOT / "deploy" / "nginx.conf").read_text()
    block = re.search(r"location = /slots/ \{(.*?)\}", conf, re.DOTALL)
    assert block, "nginx.conf has no /slots/ listing"
    assert "autoindex_format json" in block.group(1) and "alias /usr/share/nginx/html/" in block.group(1)
    js = website.SWITCHER.read_text()
    assert "fetch('/slots/'" in js and "e.type === 'directory'" in js


def test_missing_exports_say_run_build(tmp_path, exports):
    with pytest.raises(FileNotFoundError, match="build.py"):
        website.write(DEFAULT, "main", tmp_path / "out", tmp_path / "nowhere")


# ---- the templates know the site -----------------------------------------------------------


@pytest.mark.parametrize("template", [viewer.TEMPLATE, print_preview.TEMPLATE])
def test_templates_fetch_meshes_and_link_the_site(template):
    page = template.read_text()
    assert "o.mesh" in page and "fetch(" in page
    assert 'id="siteNav"' in page
    assert "github.com/johnrwilsoniv/negative-lab-basic" in page


@pytest.mark.parametrize("template", [viewer.TEMPLATE, print_preview.TEMPLATE])
def test_the_standalone_pages_inline_icon_is_the_sites_favicon(template):
    """The standalone pages can't reach the site root, so they carry icons/favicon-96x96.png inline."""
    m = website.INLINE_ICON.search(template.read_text())
    assert m, "no inline icon"
    inline = base64.b64decode(m.group(0).split("data:image/png;base64,", 1)[1].rstrip('">'))
    assert inline == (website.ICONS / "favicon-96x96.png").read_bytes()


# ---- the files page and its zips ----------------------------------------------------------


def test_files_has_its_own_page_linking_every_file_by_part(tmp_path, exports):
    (exports / "stl" / ".gitkeep").write_bytes(b"")
    here = website.write(DEFAULT, "main", tmp_path / "out", exports)
    page = (here / "files" / "index.html").read_text()
    for href in ("/main/files/stl/tube.stl", "/main/files/step/tube.step", "/main/files/stl/adapter.stl",
                 "/main/files/step/nlb-scan-rig-assembly.step"):
        assert f'href="{href}"' in page
        assert (here / href.removeprefix("/main/")).is_file()
    assert ".gitkeep" not in page
    assert page.index("tube.stl") < page.index("adapter.stl")              # print_preview's order, not the alphabet
    assert '<a href="/main/files/" aria-current="page">Files</a>' in page
    assert 'href="/favicon.ico"' in page
    assert re.findall(r"<script[^>]*>", page) == ['<script src="/main/slots.js" data-slot="main" defer>']
    assert "wd 111 · axis 40.5" in page


def test_the_zips_hold_every_download_under_one_folder(tmp_path, exports):
    import zipfile
    (exports / "step" / ".gitkeep").write_bytes(b"")
    files = website.write(DEFAULT, "main", tmp_path / "out", exports) / "files"
    names = lambda z: sorted(zipfile.ZipFile(files / z).namelist())     # noqa: E731
    stl = ["nlb-scan-rig/stl/adapter.stl", "nlb-scan-rig/stl/tube.stl"]
    step = ["nlb-scan-rig/step/adapter.step", "nlb-scan-rig/step/nlb-scan-rig-assembly.step", "nlb-scan-rig/step/tube.step"]
    assert names("nlb-scan-rig.zip") == sorted(stl + step)
    assert names("nlb-scan-rig-stl.zip") == stl
    assert names("nlb-scan-rig-step.zip") == step
    assert zipfile.ZipFile(files / "nlb-scan-rig.zip").read("nlb-scan-rig/stl/adapter.stl") == STL_B
    page = (files / "index.html").read_text()
    for z in ("nlb-scan-rig.zip", "nlb-scan-rig-stl.zip", "nlb-scan-rig-step.zip"):
        assert f'href="/main/files/{z}"' in page


def test_a_preview_slots_files_page_says_so(tmp_path, exports):
    page = (website.write(DEFAULT, "fix-a", tmp_path / "out", exports) / "files" / "index.html").read_text()
    assert "preview: fix-a" in page and 'href="/fix-a/files/nlb-scan-rig.zip"' in page
