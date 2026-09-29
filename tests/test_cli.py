import json

import pytest
from synth import make_negative

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
