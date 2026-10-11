import numpy as np
import pytest
from synth import make_raw_negative, neutral_wedge_scene

from nlb import develop
from nlb.studio import feedback as fb

C41 = {"film": "c41", "flip": False, "base": None, "levels": None}
CONFIG = {
    "iso": {"value": "400", "choices": ["100", "200", "400"]},
    "shutterspeed": {"value": "1/60", "choices": ["1/125", "1/60", "1/30", "1/15", "1/8", "1/4", "0.5", "1"]},
}


def metrics(**kw):
    lin, _ = make_raw_negative(neutral_wedge_scene(), **kw)
    return develop.capture_metrics(lin, C41, detail=lin)


def statuses(report):
    return {c["key"]: c["status"] for c in report["checks"]}


def test_shutter_parsing():
    assert fb.shutter_seconds("1/250") == pytest.approx(0.004)
    assert fb.shutter_seconds('1"3') == pytest.approx(1.3)
    assert fb.shutter_seconds('30"') == 30
    assert fb.shutter_seconds("Bulb") is None
    assert fb.iso_value("Auto ISO") == "auto" and fb.iso_value("100") == 100
    assert fb.f_number("f/5.6") == 5.6


def test_suggest_exposure_uses_camera_choices():
    cfg = {"iso": {"value": "100"}, "shutterspeed": CONFIG["shutterspeed"]}
    assert fb.suggest_exposure(2.0, cfg) == "Set the shutter to 1/15 (now 1/60)."
    assert fb.suggest_exposure(-1.0, cfg) == "Set the shutter to 1/125 (now 1/60)."
    assert fb.suggest_exposure(0.05, cfg) == ""
    # ISO 400 -> 100 is two more stops on the shutter
    assert fb.suggest_exposure(1.0, CONFIG) == "Set ISO 100 and the shutter to 1/8 (now ISO 400, 1/60)."
    assert "longest shutter" in fb.suggest_exposure(8.0, cfg)
    assert fb.suggest_exposure(1.5, {}) == "Lengthen the exposure by 1.5 stops."


def test_underexposed_capture_says_how_much_longer():
    m = metrics()  # the synthetic light puts the base near 15%, like the sample captures
    r = fb.assess(m, CONFIG)
    exposure = next(c for c in r["checks"] if c["key"] == "exposure")
    assert exposure["status"] == "bad" and "stops under" in exposure["advice"]
    assert "Set ISO 100 and the shutter to" in exposure["advice"]
    assert r["verdict"] == "bad" and r["checks"][0]["key"] == "exposure"
    assert statuses(r)["settings"] == "warn"


def test_good_capture():
    m = metrics(exposure=5.0)
    assert 0.6 <= m["base_headroom"] <= 0.85
    assert m["angle"] is not None and m["picture"] is not None and m["edge_px"]
    s = statuses(fb.assess(m, {"iso": {"value": "100"}}))
    assert s["exposure"] == "ok" and s["refs"] == "ok" and s["tilt"] == "ok" and s["light"] == "ok"
    assert s["settings"] == "ok"


def test_clipping_and_falloff():
    s = statuses(fb.assess(metrics(exposure=8.0), {}))
    assert s["exposure"] == "bad"
    r = fb.assess(metrics(exposure=5.0, falloff=0.4), {})
    light = next(c for c in r["checks"] if c["key"] == "light")
    assert light["status"] == "warn" and "left" in light["value"]


def test_not_film_and_black_frame():
    noise = np.random.default_rng(0).uniform(0.2, 0.4, (400, 600, 3)).astype(np.float32)
    r = fb.assess(develop.capture_metrics(noise, C41), {})
    assert r["verdict"] == "bad" and r["checks"][0]["key"] == "film"
    r = fb.assess(develop.capture_metrics(noise * 0.01, C41), {})
    assert r["checks"][0]["key"] == "dark"


def test_framing_off_center_and_cut_off():
    base = {"size": [1600, 1067]}
    s = fb.framing_check({**base, "picture": [0.3, 0.2, 0.6, 0.6]})
    assert s["status"] == "warn" and "right by 10%" in s["advice"]
    s = fb.framing_check({**base, "picture": [0.0, 0.2, 0.6, 0.6]})
    assert s["status"] == "bad" and "left edge" in s["advice"]
    assert fb.framing_check({**base, "picture": [0.3, 0.3, 0.4, 0.4]})["status"] == "warn"  # small
    assert fb.framing_check({**base, "picture": [0.15, 0.15, 0.7, 0.7]})["status"] == "ok"


def test_focus_and_roll_match():
    m = {"edge_px": 3.0, "base": [0.5, 0.75, 0.3]}
    assert fb.focus_check(m, None, 2.0)["status"] == "ok"
    assert fb.focus_check(m, {"id": 1, "edge_px": 2.0}, 2.0)["status"] == "warn"
    assert fb.focus_check({"edge_px": 6.0}, None, 2.0)["status"] == "warn"  # 12 px: soft anyway
    assert fb.match_check(m, {"label": "frame-003", "base": [0.5, 0.74, 0.3]})["status"] == "ok"
    c = fb.match_check(m, {"label": "frame-003", "base": [0.25, 0.375, 0.15]})
    assert c["status"] == "warn" and c["value"] == "1.0 stops brighter than frame-003"


def test_tilt_direction():
    assert "counter-clockwise" in fb.tilt_check({"angle": 2.0})["advice"]
    assert " clockwise" in fb.tilt_check({"angle": -2.0})["advice"]
    assert fb.tilt_check({"angle": 0.5})["status"] == "ok"
