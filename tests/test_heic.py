from pathlib import Path

import numpy as np
from synth import make_negative, write_dng

from nlb.heic import list_inputs, load_rgb, output_name, save_gray, to_u8


def test_list_inputs_filters(tmp_path):
    for name in ["b.heic", "a.HEIC", "c.HEIF", "d.jpg", "e.MOV", "f.DNG", "g.dng", "h.CR3",
                 "i.ARW", "j.arw", ".DS_Store", "._a.HEIC", "._f.DNG", "._i.ARW"]:
        (tmp_path / name).write_bytes(b"x")
    (tmp_path / "sub.heic").mkdir()
    assert [p.name for p in list_inputs(tmp_path)] == [
        "a.HEIC", "b.heic", "c.HEIF", "f.DNG", "g.dng", "i.ARW", "j.arw"]


def test_output_name():
    assert output_name(Path("IMG_1.HEIC")) == "IMG_1.HEIC"
    assert output_name(Path("IMG_1.heif")) == "IMG_1.heif"
    assert output_name(Path("IMG_1.DNG")) == "IMG_1.HEIC"
    assert output_name(Path("DSC01.ARW")) == "DSC01.HEIC"


def test_to_u8_clips_and_rounds():
    out = to_u8(np.array([-0.5, 0.0, 0.5, 1.0, 2.0]))
    assert out.dtype == np.uint8
    assert out.tolist() == [0, 0, 128, 255, 255]


def test_gray_heic_roundtrip(tmp_path):
    gray = np.tile(np.linspace(0, 1, 300, dtype=np.float32), (200, 1))
    path = tmp_path / "x.HEIC"
    save_gray(path, gray)
    rgb = load_rgb(path)
    assert rgb.shape == (200, 300, 3)
    assert rgb.dtype == np.float32
    assert np.abs(rgb[..., 0] - gray).mean() < 0.02
    assert np.allclose(rgb[..., 0], rgb[..., 1], atol=0.02)


def test_save_gray_jpeg(tmp_path):
    path = tmp_path / "p.jpg"
    save_gray(path, np.full((10, 15), 0.5, np.float32))
    assert load_rgb(path).shape == (10, 15, 3)


def test_dng_load_matches_source(tmp_path):
    srgb = make_negative()
    path = tmp_path / "x.DNG"
    write_dng(path, srgb)
    rgb = load_rgb(path)
    assert rgb.shape == srgb.shape
    assert rgb.dtype == np.float32
    assert np.abs(rgb - srgb).max() < 0.002


def test_arw_decodes_via_libraw(tmp_path):
    """LibRaw sniffs the format from content, so a DNG named .ARW checks the routing."""
    srgb = make_negative()
    path = tmp_path / "DSC01.ARW"
    write_dng(path, srgb)
    assert np.abs(load_rgb(path) - srgb).max() < 0.002
