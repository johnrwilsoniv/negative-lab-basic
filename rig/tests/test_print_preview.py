"""print_preview.py: the "Latest feedback" findings this rig carries, the STL sizes it reads, and the guard on stale
exports."""

import dataclasses
import re

import cadquery as cq
import pytest

import cadutil
import print_preview as pp
from params import DEFAULT, Params

FIELDS = {f.name for f in dataclasses.fields(Params)}
CARRIED = ["FB1", "FB9", "FB10", "FB14", "FB15", "FB16"]      # main's numbers for the findings whose parts exist here


def sizes_at(p: Params) -> dict[str, list[float]]:
    """Plausible print-pose sizes: the tube tube_len tall, the gate front gh tall on the bed, the rest as built."""
    sizes = {name: [50.0, 50.0, 10.0] for name in pp.ORDER}
    sizes["tube"] = [68.5, 68.5, p.tube_len]
    sizes["gate_front"] = [92.0, p.gh, 23.85]
    sizes["light_dock"] = [92.68, 191.0, 62.0]
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
    assert len(ids) == len(set(ids)) == 6
    template = pp.TEMPLATE.read_text()
    for it in fb["items"]:
        assert it["sev"] in severities, it["id"]
        assert it["title"] and it["what"] and it["risk"] and it["basis"] and it["where"], it["id"]
        assert it["parts"] and set(it["parts"]) <= set(pp.ORDER), it["id"]
        assert it["nums"] and all(q["label"] and q["value"] and q["tag"] in ("", "bad") for q in it["nums"]), it["id"]
        assert f"\n    {it['id']}: {{\n" in template, f"no drawing for {it['id']}"
    assert fb["clean"] and fb["known"] and fb["unchecked"]


def test_the_page_draws_only_the_findings_this_rig_carries():
    template = pp.TEMPLATE.read_text()
    figs = template[template.index("  const FIGS = {"):template.index("  // ---- the page: the verdict")]
    assert re.findall(r"^    (\w+): \{$", figs, flags=re.M) == [it["id"] for it in pp.feedback(DEFAULT)["items"]]
    gone = ("wall", "sw_travel", "x_wedge", "pad_t", "screw_points", "ear_w", "gate_front_w", "dock_front_t", "film_slot_w",
            "lid_clear", "tab_w", "cbore_d", "plate_t", "x_pp")
    assert not set(gone) & FIELDS                                           # the clamp gate's params: not on this rig, ...
    for name in gone:
        assert not re.search(rf"\bP\.{name}\b", template), name           # ... and no drawing reads one


def test_findings_keep_mains_numbers_most_serious_first():
    fb = pp.feedback(DEFAULT)
    assert [it["num"] for it in fb["items"]] == CARRIED
    order = [s["id"] for s in fb["severities"]]
    ranks = [order.index(it["sev"]) for it in fb["items"]]
    assert ranks == sorted(ranks)
    assert [sum(it["sev"] == s for it in fb["items"]) for s in order] == [0, 1, 5]


def test_every_one_of_the_reviews_sixteen_is_carried_dropped_or_to_measure_again():
    assert sorted([*CARRIED, *pp.DROPPED, *pp.REMEASURE], key=lambda k: int(k[2:])) == [f"FB{i}" for i in range(1, 17)]
    known = " ".join(pp.feedback(DEFAULT)["known"])
    for num in (*pp.DROPPED, *pp.REMEASURE):
        assert re.search(rf"\b{num}\b", known), num
    assert "D1" in known and "clamp gate on main" in pp.REVIEW["verdict"]


def test_the_reviewed_design_is_todays_less_what_changed_after_the_first_print():
    q = pp.reviewed()
    assert (q.wd, q.axis) == (pp.REVIEW["wd"], pp.REVIEW["axis"]) == (111, 40.5)
    changed = {f.name for f in dataclasses.fields(Params) if getattr(q, f.name) != getattr(DEFAULT, f.name)}
    assert changed == set(pp.CHANGED_SINCE) | {"wd"}            # each one a field whose default has moved on (F23, F24)
    assert pp.CHANGED_SINCE == {"gate_front": 14, "front_wall": 4, "tube_ro": 34, "fit_clear": 0.3}
    assert (q.tube_len, q.x_gate, 2 * q.fit_r) == (98, 222, pytest.approx(68.6))     # the review's tube, gate and sockets


def test_the_measures_are_the_reviews_at_its_wd_and_axis():
    """Each number the review measured on the parts this rig shares with main, against the same number worked out from
    Params."""
    m = pp.measures(pp.reviewed())
    review = {
        "notch_gap": 0.0, "pocket": 39.2, "lit": 14155, "perf_show": 0.30, "perf_count": 16, "perf_area": 9.5,
        "ledge": 3.30, "over_socket": 1.70, "tube_wall": 2,
    }
    for name, value in review.items():          # to the precision the review gave each
        digits = len(repr(value).partition(".")[2].rstrip("0")) if isinstance(value, float) else 0
        assert m[name] == pytest.approx(value, abs=0.51 * 10 ** -digits), name
    assert m["ledge_area"] == pytest.approx(676.7, abs=0.5)         # the review measured the mesh
    assert set(m) == set(review) | {"ledge_area", "past", "past_pct"}


def test_the_light_past_the_gate_is_worked_out_for_this_gate():
    """Not the review's 57%: here the gate body is solid, 92 wide, with the deck on its top."""
    p = DEFAULT
    m = pp.measures(p)
    lit_y0 = p.floor_t + (p.csl_h - p.csl_lit_h) / 2
    behind = p.gw * (p.y_deck + p.deck_t - lit_y0)
    assert m["past"] == pytest.approx(p.csl_lit_w * p.csl_lit_h - behind) == pytest.approx(7899)
    assert m["past_pct"] == pytest.approx(55.8, abs=0.05)
    assert pp.measures(Params(axis=80))["past"] == pytest.approx(149 * 95 - 92 * 95)    # the gate covers the lit height


def test_values_and_wording_follow_the_params():
    p = Params(wd=150, axis=45)
    fb = pp.feedback(p)
    assert not fb["same"] and pp.feedback(pp.reviewed())["same"] and not pp.feedback(DEFAULT)["same"]    # wd 116 (F24)
    assert (fb["p"]["wd"], fb["p"]["axis"], fb["p"]["tube_len"], fb["p"]["gh"]) == (150, 45, 132, 81)
    notch = next(it for it in fb["items"] if it["id"] == "notch")
    assert "both at x 300" in notch["what"] and "the 49 gate stands in a 49.2 pocket" in notch["what"]
    assert "front wall" not in notch["what"].replace("no front wall", "")      # D5: the stop is the floor's edge
    thin = next(it for it in fb["items"] if it["id"] == "thin")
    assert thin["nums"][-1]["value"] == "92 × 81" and "counterbore" not in " ".join(q["label"] for q in thin["nums"])


def test_the_numbers_at_the_defaults_follow_the_first_print_changes():
    m = pp.measures(DEFAULT)
    assert m["tube_wall"] == 2.25                                        # the Ø68.5 tube (F23)
    assert m["pocket"] == pytest.approx(49.2)                            # the gate, 10 deeper, in the dock's notch (F24)
    assert m["over_socket"] == pytest.approx(1.7)                        # the sockets kept their Ø68.6
    assert m["ledge"] == pytest.approx(3.3)
    known = " ".join(pp.feedback(DEFAULT)["known"])
    assert "F23" in known and "pegs" in known                            # the tube-versus-pegs risk is listed


def test_the_drawings_get_every_param():
    props = {name for name, v in vars(Params).items() if isinstance(v, property)}
    got = pp.fig_params(DEFAULT)
    assert set(got) == FIELDS | props
    assert got["x_film"] == DEFAULT.x_film and got["fit_r"] == DEFAULT.fit_r and len(got["peg_points"]) == 4
    assert got["dock_tube_clear"] == 1 and got["flare_scale"] == pytest.approx(DEFAULT.flare_scale, abs=1e-4)


def test_the_plan_lists_the_findings_as_the_page_does():
    plan = (pp.ROOT / "PLAN.md").read_text()
    section = plan[plan.index("## Latest feedback"):plan.index("## Check before printing")]
    items = pp.feedback(DEFAULT)["items"]
    entries = re.split(r"^- \*\*(?=FB\d+ · )", section, flags=re.M)[1:]
    assert len(entries) == len(items)
    for it, entry in zip(items, entries):
        assert entry.startswith(f"{it['num']} · {it['title']}."), it["num"]
    assert pp.REVIEW["date"] in section
    for num in (*pp.DROPPED, *pp.REMEASURE):                 # and says what became of the other ten
        assert re.search(rf"\b{num}\b", section), num


# ---- the solids and their groups --------------------------------------------------------


def test_the_solids_are_grouped_under_mains_numbers_then_the_drive_and_the_spools():
    groups = {name: pp.SOLIDS[name][2] for name in pp.ORDER}
    assert list(dict.fromkeys(groups.values())) == [
        "1 · Lens adapter", "2 · Film gate", "3 · Light dock", "4 · Film drive", "5 · Spools"]
    assert {pp.SOLIDS[n][0] for n in ("thread_coupon", "adapter", "tube")} == {"1a", "1", "1b"}
    assert (pp.SOLIDS["gate_front"][0], pp.SOLIDS["gate_body"][0], pp.SOLIDS["light_dock"][0]) == ("2", "2b", "3")
    drive = [n for n, g in groups.items() if g == "4 · Film drive"]
    assert drive == ["sprocket_supply", "sprocket_takeup", "gear_supply", "gear_takeup", "idler", "idler_axle", "deck"]
    assert [n for n, g in groups.items() if g == "5 · Spools"] == ["spool_supply", "spool_takeup", "cap_supply", "cap_takeup"]
    assert {group for _, _, group, _, _ in pp.REF_MESHES} == {"2 · Film gate", "5 · Spools"}      # the film; the rolls


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


def test_the_assembly_carries_the_drive_the_spools_and_the_rolls():
    a = pp.assembled(DEFAULT)
    names = [s["name"] for s in a["solids"]]
    for name in ("sprocket_supply", "sprocket_takeup", "gear_supply", "gear_takeup", "idler", "idler_axle", "deck",
                 "spool_supply", "spool_takeup", "cap_supply", "cap_takeup"):
        assert name in names and next(s for s in a["solids"] if s["name"] == name)["stl"], name
    assert [r["name"] for r in a["refs"]] == ["film", "film_frames", "rolls", "cs_lite"]
