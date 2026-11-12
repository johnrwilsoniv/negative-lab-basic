"""print_preview.py: the "Latest feedback" findings, the STL sizes it reads, and the guard on stale exports."""

import dataclasses
import re

import cadquery as cq
import pytest

import cadutil
import print_preview as pp
from params import DEFAULT, Params

FIELDS = {f.name for f in dataclasses.fields(Params)}


def sizes_at(p: Params) -> dict[str, list[float]]:
    """Plausible print-pose sizes: the tube wd - 13 tall, the gate front gh tall on the bed, the rest as built."""
    sizes = {name: [50.0, 50.0, 10.0] for name in pp.ORDER}
    sizes["tube"] = [68.0, 68.0, p.tube_len]
    sizes["gate_front"] = [110.0, p.gh, 13.7]
    sizes["light_dock"] = [69.7, 181.0, 62.0]
    return sizes


def write_stls(folder, sizes):
    for name, (dx, dy, dz) in sizes.items():
        box = cq.Workplane("XY").box(dx, dy, dz, centered=False)
        cadutil.export(box, folder / "step" / f"{name}.step", folder / "stl" / f"{name}.stl")
    return folder / "stl"


# ---- the findings -----------------------------------------------------------------------


def test_every_finding_has_what_the_page_shows():
    fb = pp.feedback(DEFAULT)
    severities = [s["id"] for s in fb["severities"]]
    ids = [it["id"] for it in fb["items"]]
    assert len(ids) == len(set(ids)) == 16
    template = pp.TEMPLATE.read_text()
    for it in fb["items"]:
        assert it["sev"] in severities, it["id"]
        assert it["title"] and it["what"] and it["risk"] and it["basis"] and it["where"], it["id"]
        assert set(it["parts"]) <= set(pp.ORDER), it["id"]
        assert it["nums"] and all(q["label"] and q["value"] and q["tag"] in ("", "bad") for q in it["nums"]), it["id"]
        assert f"\n    {it['id']}: {{\n" in template, f"no drawing for {it['id']}"
    assert fb["clean"] and fb["known"] and fb["unchecked"]


def test_findings_are_numbered_most_serious_first():
    fb = pp.feedback(DEFAULT)
    assert [it["num"] for it in fb["items"]] == [f"FB{i}" for i in range(1, 17)]
    order = [s["id"] for s in fb["severities"]]
    ranks = [order.index(it["sev"]) for it in fb["items"]]
    assert ranks == sorted(ranks)
    assert [sum(it["sev"] == s for it in fb["items"]) for s in order] == [0, 6, 10]


def test_the_measures_are_the_reviews_at_its_wd_and_axis():
    """Each number the review measured on the built solids, against the same number worked out from Params."""
    assert (DEFAULT.wd, DEFAULT.axis) == (pp.REVIEW["wd"], pp.REVIEW["axis"])
    m = pp.measures(DEFAULT)
    review = {
        "notch_gap": 0.0, "pocket": 39.2, "room": 5.350, "stack": 5.4133, "squeeze": 0.063, "squeeze_over": 0.122,
        "body_h": 25.30, "backer_h": 19.95, "reach": 8.06, "reach_play": 8.91, "tab_stop": 6, "wall_stop": 8,
        "covered": 35, "contact": 840, "frame_area": 864, "tilt": 3.8, "drop": 4.1, "margin": 1, "behind": 0.80,
        "plate_edge": 42.75, "lit": 14155, "past_pct": 57, "side": 28.5, "above": 31, "tab_slot": 48, "tab_open": 40,
        "lid_slit_l": 86, "lid_slit": 17, "settled": 12.5, "tab_proud": 12.2, "perf_show": 0.30, "perf_count": 16,
        "perf_area": 9.5, "ledge": 3.30, "u_bottom": 5.50, "film_face": 235.700, "film_off": 0.3, "rim_to_film": 110.700,
        "over_socket": 1.70, "cbore_wall": 1.25, "tube_wall": 2,
    }
    for name, value in review.items():          # to the precision the review gave each
        digits = len(repr(value).partition(".")[2].rstrip("0")) if isinstance(value, float) else 0
        assert m[name] == pytest.approx(value, abs=0.51 * 10 ** -digits), name
    assert m["past"] == pytest.approx(8100, abs=50)
    assert m["ledge_area"] == pytest.approx(676.7, abs=0.5)         # the review measured the mesh
    assert m["on_ramp"] == {"lock": 3, "tab": 2, "wall": 0}


def test_the_clamp_is_rounded_to_whole_layers():
    assert pp._to_layers(19.95, 0.2) == [20.0]
    assert pp._to_layers(25.3, 0.2) == [25.2, 25.4]                 # exactly half a layer: either
    rows = {row["layer"]: row for row in pp.measures(DEFAULT)["layers"]}
    assert rows[0.12]["squeeze"] == pytest.approx([0.0133], abs=1e-3)
    assert rows[0.16]["squeeze"] == pytest.approx([0.1333], abs=1e-3)
    assert rows[0.2]["squeeze"] == pytest.approx([0.2133, 0.0133], abs=1e-3)


def test_values_and_wording_follow_the_params():
    p = Params(wd=150, axis=45)
    fb = pp.feedback(p)
    assert not fb["same"] and pp.feedback(DEFAULT)["same"]
    assert (fb["p"]["wd"], fb["p"]["axis"], fb["p"]["tube_len"], fb["p"]["gh"]) == (150, 45, 137, 81)
    xfilm = next(it for it in fb["items"] if it["id"] == "xfilm")
    assert "149.7 from the lens's rim, not 150" in xfilm["what"]
    assert fb["m"]["u_bottom"] == 10


def test_the_drawings_get_every_param():
    props = {name for name, v in vars(Params).items() if isinstance(v, property)}
    got = pp.fig_params(DEFAULT)
    assert set(got) == FIELDS | props
    assert got["x_film"] == DEFAULT.x_film and got["fit_r"] == DEFAULT.fit_r and len(got["screw_points"]) == 4


def test_the_plan_lists_the_findings_as_the_page_does():
    plan = (pp.ROOT / "PLAN.md").read_text()
    section = plan[plan.index("## Latest feedback"):plan.index("## Check before printing")]
    items = pp.feedback(DEFAULT)["items"]
    entries = re.split(r"^- \*\*(?=FB\d+ · )", section, flags=re.M)[1:]
    assert len(entries) == len(items)
    for it, entry in zip(items, entries):
        assert entry.startswith(f"{it['num']} · {it['title']}."), it["num"]
    assert pp.REVIEW["date"] in section


# ---- STL sizes and stale exports -------------------------------------------------------


def test_stl_size_is_the_bounding_box_of_the_exported_mesh(tmp_path):
    stl = write_stls(tmp_path, {"slab": [30, 20, 7.5]})
    assert pp.stl_size(stl / "slab.stl") == pytest.approx([30, 20, 7.5], abs=1e-4)


def test_data_carries_the_findings_and_the_stls_on_disk(tmp_path, monkeypatch):
    monkeypatch.setattr(pp, "assembled", lambda p: {"solids": [], "refs": []})
    stl = write_stls(tmp_path, sizes_at(DEFAULT))
    d = pp.data(DEFAULT, stl)
    assert [part["name"] for part in d["parts"]] == pp.ORDER
    assert [it["id"] for it in d["feedback"]["items"]] == [it["id"] for it in pp.feedback(DEFAULT)["items"]]


@pytest.mark.parametrize("p, what", [(Params(wd=150), "wd"), (Params(axis=45), "axis")])
def test_data_refuses_stls_built_at_another_wd_or_axis(tmp_path, monkeypatch, p, what):
    monkeypatch.setattr(pp, "assembled", lambda p: {"solids": [], "refs": []})
    stl = write_stls(tmp_path, sizes_at(DEFAULT))
    with pytest.raises(ValueError, match=f"another {what}.*--wd and --axis"):
        pp.data(p, stl)


def test_an_axis_too_low_is_one_line_on_stderr(capsys):
    assert pp.main(["--axis", "35"]) == 2
    out, err = capsys.readouterr()
    assert out == "" and len(err.strip().splitlines()) == 1 and "adapter" in err
