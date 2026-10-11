import json

import numpy as np
import pytest
from synth import make_negative, write_dng

from nlb.cli import default_out, main, parse_rotations
from nlb.heic import load_rgb, save_gray
from nlb.tone import luma


@pytest.fixture
def roll(tmp_path):
    folder = tmp_path / "roll"
    folder.mkdir()
    save_gray(folder / "IMG_0001.HEIC", luma(make_negative()))
    save_gray(folder / "IMG_0002.HEIC", luma(make_negative(seed=5)))
    return folder


@pytest.fixture
def dng_roll(tmp_path):
    folder = tmp_path / "dng"
    folder.mkdir()
    write_dng(folder / "IMG_0003.DNG", make_negative())
    return folder


def test_parse_rotations():
    assert parse_rotations(["IMG_1=90cw", "IMG_2.HEIC=180"]) == {"IMG_1": "90cw", "IMG_2": "180"}
    for bad in ["IMG_1", "IMG_1=45", "=90cw"]:
        with pytest.raises(ValueError):
            parse_rotations([bad])


def test_default_out(tmp_path):
    assert default_out(tmp_path / "roll") == tmp_path / "roll-positive"


def test_preview_writes_previews_sheet_manifest(roll):
    assert main(["preview", str(roll)]) == 0
    work = default_out(roll) / ".nlb-work"
    manifest = json.loads((work / "manifest.json").read_text())
    assert [f["name"] for f in manifest["frames"]] == ["IMG_0001", "IMG_0002"]
    frame = manifest["frames"][0]
    assert frame["preview"] == "IMG_0001.jpg" and (work / "IMG_0001.jpg").exists()
    assert len(frame["crop"]) == 4 and frame["flags"] == []
    assert (work / "contact.jpg").exists()
    assert sorted(p.name for p in roll.iterdir()) == ["IMG_0001.HEIC", "IMG_0002.HEIC"]


def test_render_writes_rotated_heic(roll):
    assert main(["render", str(roll), "--rotate", "IMG_0002=90ccw"]) == 0
    out = default_out(roll)
    a = load_rgb(out / "IMG_0001.HEIC")
    b = load_rgb(out / "IMG_0002.HEIC")
    assert a.shape[1] * 2 == a.shape[0] * 3          # landscape 3:2
    assert b.shape[0] * 2 == b.shape[1] * 3          # rotated to portrait
    assert (out / "contact.jpg").exists()


def test_render_refuses_input_dir_as_output(roll):
    before = (roll / "IMG_0001.HEIC").read_bytes()
    assert main(["render", str(roll), "--out", str(roll)]) == 2
    assert (roll / "IMG_0001.HEIC").read_bytes() == before


def test_render_rejects_bad_rotation(roll):
    assert main(["render", str(roll), "--rotate", "IMG_9999=90cw"]) == 2
    assert main(["render", str(roll), "--rotate", "IMG_0001=sideways"]) == 2
    assert not default_out(roll).exists()


def test_render_preserves_other_files(roll):
    out = default_out(roll)
    out.mkdir()
    (out / "keep.txt").write_text("mine")
    assert main(["render", str(roll)]) == 0
    assert (out / "keep.txt").read_text() == "mine"


def test_preview_continues_past_bad_file(roll):
    (roll / "IMG_0000.HEIC").write_bytes(b"not an image")
    assert main(["preview", str(roll)]) == 1
    manifest = json.loads((default_out(roll) / ".nlb-work" / "manifest.json").read_text())
    assert [f["name"] for f in manifest["frames"]] == ["IMG_0001", "IMG_0002"]


def test_render_continues_past_bad_file(roll):
    (roll / "IMG_0000.HEIC").write_bytes(b"not an image")
    assert main(["render", str(roll)]) == 1
    assert (default_out(roll) / "IMG_0002.HEIC").exists()


def test_missing_dir_and_empty_dir(tmp_path):
    assert main(["preview", str(tmp_path / "nope")]) == 2
    assert main(["preview", str(tmp_path)]) == 2


def test_bad_gamma(roll):
    assert main(["preview", str(roll), "--gamma", "0"]) == 2


def test_render_refuses_case_variant_of_input_dir(roll):
    variant = roll.parent / roll.name.upper()
    if not variant.exists():
        pytest.skip("case-sensitive filesystem")
    before = (roll / "IMG_0001.HEIC").read_bytes()
    assert main(["render", str(roll), "--out", str(variant)]) == 2
    assert (roll / "IMG_0001.HEIC").read_bytes() == before


def test_preview_refuses_input_dir_as_work(roll):
    assert main(["preview", str(roll), "--work", str(roll)]) == 2
    assert sorted(p.name for p in roll.iterdir()) == ["IMG_0001.HEIC", "IMG_0002.HEIC"]


def _process_failing_on_first(monkeypatch):
    import nlb.cli
    real, calls = nlb.cli.process, []

    def flaky(rgb, **kw):
        calls.append(1)
        if len(calls) == 1:
            raise IndexError("boom")
        return real(rgb, **kw)
    monkeypatch.setattr(nlb.cli, "process", flaky)


def test_render_continues_past_processing_error(roll, monkeypatch):
    _process_failing_on_first(monkeypatch)
    assert main(["render", str(roll)]) == 1
    out = default_out(roll)
    assert (out / "IMG_0002.HEIC").exists() and (out / "contact.jpg").exists()


def test_preview_continues_past_processing_error(roll, monkeypatch):
    _process_failing_on_first(monkeypatch)
    assert main(["preview", str(roll)]) == 1
    manifest = json.loads((default_out(roll) / ".nlb-work" / "manifest.json").read_text())
    assert [f["name"] for f in manifest["frames"]] == ["IMG_0002"]


def test_preview_reads_dng(dng_roll):
    assert main(["preview", str(dng_roll)]) == 0
    manifest = json.loads((default_out(dng_roll) / ".nlb-work" / "manifest.json").read_text())
    frame = manifest["frames"][0]
    assert frame["file"] == "IMG_0003.DNG" and frame["flags"] == []


def test_render_dng_writes_heic(dng_roll):
    assert main(["render", str(dng_roll), "--rotate", "IMG_0003=180"]) == 0
    out = default_out(dng_roll)
    img = load_rgb(out / "IMG_0003.HEIC")
    assert img.shape[1] * 2 == img.shape[0] * 3
    assert not (out / "IMG_0003.DNG").exists()


def test_refuses_heic_and_dng_with_same_name(roll):
    write_dng(roll / "IMG_0001.DNG", make_negative())
    assert main(["preview", str(roll)]) == 2
    assert main(["render", str(roll)]) == 2
    assert not default_out(roll).exists()


def test_render_arw_writes_heic(tmp_path):
    folder = tmp_path / "arw"
    folder.mkdir()
    write_dng(folder / "DSC01.ARW", make_negative())  # LibRaw reads by content, not suffix
    assert main(["render", str(folder)]) == 0
    out = default_out(folder)
    assert load_rgb(out / "DSC01.HEIC").shape[2] == 3
    assert not (out / "DSC01.ARW").exists()


def test_refuses_heic_and_arw_with_same_name(roll):
    write_dng(roll / "IMG_0001.ARW", make_negative())
    assert main(["preview", str(roll)]) == 2
    assert not default_out(roll).exists()


def _raw_roll(tmp_path, roll_json=None):
    from synth import make_raw_negative, neutral_wedge_scene

    folder = tmp_path / "raw"
    folder.mkdir()
    lin, _ = make_raw_negative(neutral_wedge_scene())
    srgb = np.where(lin <= 0.0031308, 12.92 * lin, 1.055 * lin ** (1 / 2.4) - 0.055)
    for name in ("F1", "F2"):
        write_dng(folder / f"{name}.DNG", srgb)
    if roll_json is not None:
        (folder / "roll.json").write_text(json.dumps(roll_json))
    return folder


def test_develop_renders_kept_frames_from_roll_json(tmp_path):
    import tifffile

    folder = _raw_roll(tmp_path, {"version": 1, "settings": {"film": "c41", "flip": False},
                                  "frames": {"F1": {"file": "F1.DNG", "crop": [0.2, 0.3, 0.5, 0.4],
                                                    "rotation": 90, "params": {"exposure": 0.2}},
                                             "F2": {"file": "F2.DNG", "rejected": True}}})
    out = tmp_path / "out"
    assert main(["develop", str(folder), "--out", str(out)]) == 0
    assert sorted(p.name for p in out.iterdir()) == ["F1.tif"]
    img = tifffile.imread(out / "F1.tif")
    assert img.dtype == np.uint16 and img.shape == (300, 160, 3)  # 0.5 x 600 wide, 0.4 x 400 tall, turned


def test_develop_without_roll_json_needs_frames_or_arw(tmp_path):
    folder = _raw_roll(tmp_path)  # DNGs only: develop looks for ARW without a roll.json
    assert main(["develop", str(folder)]) == 2


def test_develop_auto_frames_missing_crop_and_rejects_unknown_frame(tmp_path):
    folder = _raw_roll(tmp_path, {"settings": {}, "frames": {"F1": {"file": "F1.DNG"}}})
    out = tmp_path / "out"
    assert main(["develop", str(folder), "--out", str(out), "--frames", "nope"]) == 2
    assert main(["develop", str(folder), "--out", str(out), "--film", "bw"]) == 0
    assert (out / "F1.tif").is_file()


def test_develop_check_reports_exposure(tmp_path, capsys):
    folder = _raw_roll(tmp_path, {"settings": {}, "frames": {"F1": {"file": "F1.DNG"}}})
    assert main(["develop", str(folder), "--check"]) == 0
    assert "F1: base at" in capsys.readouterr().out
    assert not (tmp_path / "raw-positive").exists()
