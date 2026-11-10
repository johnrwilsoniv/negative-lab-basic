"""print_preview.py: the "Dimensions to confirm" checklist, the STL sizes it reads, and the guard on stale exports."""

import dataclasses
import re

import cadquery as cq
import pytest

import build
import cadutil
import print_preview as pp
from params import DEFAULT, Params

FIELDS = {f.name for f in dataclasses.fields(Params)}
FIGURES = ("side", "lens", "cslite", "slot", "bed", "film", "screw")      # the drawings the template knows


def sizes_at(p: Params) -> dict[str, list[float]]:
    """Plausible print-pose sizes: the tube wd - 13 tall, the gate front gh tall on the bed, the rest as built."""
    sizes = {name: [50.0, 50.0, 10.0] for name in pp.ORDER}
    sizes["tube"] = [72.0, 72.0, p.tube_len]
    sizes["gate_front"] = [110.0, p.gh, 13.7]
    sizes["light_dock"] = [69.7, 181.0, 62.0]
    return sizes


def write_stls(folder, sizes):
    for name, (dx, dy, dz) in sizes.items():
        box = cq.Workplane("XY").box(dx, dy, dz, centered=False)
        cadutil.export(box, folder / "step" / f"{name}.step", folder / "stl" / f"{name}.stl")
    return folder / "stl"


# ---- the checklist ---------------------------------------------------------------------


def test_every_item_has_what_the_page_shows():
    c = pp.checks(DEFAULT, sizes_at(DEFAULT))
    groups = [g["id"] for g in c["groups"]]
    ids = [it["id"] for it in c["items"]]
    assert len(ids) == len(set(ids))
    for it in c["items"]:
        assert it["group"] in groups, it["id"]
        assert it["title"] and it["what"] and it["how"] and it["wrong"] and it["fix"], it["id"]
        assert it["method"] in ("ruler", "calipers", "coupon", "spec", "test print"), it["id"]
        assert set(it["parts"]) <= set(pp.ORDER) and set(it.get("watch", [])) <= set(pp.ORDER), it["id"]
        assert set(it["figs"]) <= set(FIGURES), it["id"]
        for q in it["params"]:
            assert q["value"] == pytest.approx(getattr(DEFAULT, q["name"]), abs=1e-4), (it["id"], q["name"])
            assert q["tag"] in ("", "measured", "guess", "assumed", "derived", "fixed")


def test_the_plans_known_dimensions_are_all_on_the_list():
    named = {q["name"] for it in pp.checks(DEFAULT, sizes_at(DEFAULT))["items"] for q in it["params"]}
    assert {"wd", "axis", "thread_major", "thread_pitch", "thread_clear", "lens_r", "lens_len", "csl_l", "csl_h",
            "csl_t", "csl_lit_w", "csl_lit_h", "bed_x", "bed_y", "tube_max_len", "film_slot_clear", "pilot_d"} <= named


def test_must_check_first_leads_with_axis_and_wd():
    items = pp.checks(DEFAULT, sizes_at(DEFAULT))["items"]
    first = [it["id"] for it in items if it["group"] == "first"]
    assert first[:2] == ["axis", "wd"]
    assert {"cslite", "bed", "thread"} <= set(first)
    order = [g for g, *_ in pp.CHECK_GROUPS]
    assert [order.index(it["group"]) for it in items] == sorted(order.index(it["group"]) for it in items)


def test_values_and_wording_follow_the_params():
    p = Params(wd=150, axis=45)
    c = pp.checks(p, sizes_at(p))
    assert (c["p"]["wd"], c["p"]["axis"], c["p"]["tube_len"], c["p"]["gh"]) == (150, 45, 137, 81)
    wd = next(it for it in c["items"] if it["id"] == "wd")
    assert [q["value"] for q in wd["params"]] == [150, 137]
    assert "137" in wd["wrong"]


def test_the_drawings_get_every_value_they_are_dimensioned_from():
    c = pp.checks(DEFAULT, sizes_at(DEFAULT))
    assert set(c["p"]) == set(pp.FIG_PARAMS)
    assert c["p"]["x_film"] == DEFAULT.x_film and c["p"]["fit_r"] == DEFAULT.fit_r
    assert c["sizes"]["light_dock"] == [69.7, 181, 62]
    template = pp.TEMPLATE.read_text()
    for fig in FIGURES:
        assert f"id: '{fig}'" in template, fig


def _snapshot(p: Params) -> dict[str, tuple]:
    out = {}
    for model in build.discover().values():
        solids = dict(model.build(p))
        if hasattr(model, "extras"):
            solids.update(model.extras(p))
        for name, wp in solids.items():
            out[name] = (cadutil.volume(wp), cadutil.size(wp))
    return out


def _changed(a, b) -> set[str]:
    return {
        name for name in a
        if a[name][0] != pytest.approx(b[name][0], rel=1e-5) or a[name][1] != pytest.approx(b[name][1], abs=1e-3)
    }


def _nudged(v: float) -> float:
    return v + (0.05 if v < 1 else 0.5 if v < 100 else 2)


def test_each_items_parts_are_the_solids_its_params_change():
    """Rebuilds every part once per item, with each of its params nudged: the slowest test here."""
    base = _snapshot(DEFAULT)
    for it in pp.checks(DEFAULT, sizes_at(DEFAULT))["items"]:
        measured = [q["name"] for q in it["params"] if q["tag"] not in ("derived", "fixed")]
        assert set(measured) <= FIELDS, it["id"]
        nudge = {name: _nudged(getattr(DEFAULT, name)) for name in measured}
        assert nudge, it["id"]
        assert _changed(base, _snapshot(Params(**nudge))) == set(it["parts"]), it["id"]


# ---- STL sizes and stale exports -------------------------------------------------------


def test_stl_size_is_the_bounding_box_of_the_exported_mesh(tmp_path):
    stl = write_stls(tmp_path, {"slab": [30, 20, 7.5]})
    assert pp.stl_size(stl / "slab.stl") == pytest.approx([30, 20, 7.5], abs=1e-4)


def test_data_carries_the_checklist_for_the_stls_on_disk(tmp_path, monkeypatch):
    monkeypatch.setattr(pp, "assembled", lambda p: {"solids": [], "refs": []})
    stl = write_stls(tmp_path, sizes_at(DEFAULT))
    d = pp.data(DEFAULT, stl)
    assert [part["name"] for part in d["parts"]] == pp.ORDER
    assert d["check"]["sizes"]["tube"] == pytest.approx([72, 72, 98], abs=1e-3)
    assert [it["id"] for it in d["check"]["items"]] == [it["id"] for it in pp.checks(DEFAULT, sizes_at(DEFAULT))["items"]]


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


def test_the_plan_numbers_the_checks_as_the_page_does():
    plan = (pp.ROOT / "PLAN.md").read_text()
    section = plan[plan.index("## Check before printing"):plan.index("## Tuning and print notes")]
    items = pp.checks(DEFAULT, sizes_at(DEFAULT))["items"]
    assert [it["num"] for it in items] == [f"C{i}" for i in range(1, len(items) + 1)]
    entries = re.split(r"^- \*\*(?=C\d+ · )", section, flags=re.M)[1:]
    assert len(entries) == len(items)
    for it, entry in zip(items, entries):
        assert entry.startswith(it["num"] + " · "), it["num"]
        measured = [q["name"] for q in it["params"] if q["tag"] not in ("derived", "fixed")]
        if it["id"] not in ("thread",):             # the thread's params read "M67 × 0.75" in the plan
            assert all(f"`{name}`" in entry for name in measured), (it["num"], measured)
