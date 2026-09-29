import numpy as np
from nlb.heic import list_inputs, load_rgb, save_gray, to_u8


def test_list_inputs_filters(tmp_path):
    for name in ["b.heic", "a.HEIC", "c.HEIF", "d.jpg", "e.MOV", ".DS_Store", "._a.HEIC"]:
        (tmp_path / name).write_bytes(b"x")
    (tmp_path / "sub.heic").mkdir()
    assert [p.name for p in list_inputs(tmp_path)] == ["a.HEIC", "b.heic", "c.HEIF"]


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
