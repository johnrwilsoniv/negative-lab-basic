import sqlite3
import struct

import numpy as np
import pytest

from nlb import darktable, develop


def coords(h, w):
    """H x W x 3 image whose pixels name their own (x, y)."""
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    return np.dstack([x, y, np.zeros_like(x)])


def test_fit_trims_darktables_extra_margin_at_the_right():
    img = coords(10, 14)  # darktable keeps a few more columns than LibRaw's 10 x 12
    out = darktable.fit(img, (10, 12))
    assert out.shape == (10, 12, 3)
    assert np.array_equal(out, img[:, :12])


def test_fit_scales_a_preview_to_the_decode_size():
    out = darktable.fit(coords(20, 28), (10, 12))
    assert out.shape == (10, 12, 3)
    assert out[0, 0, 0] < 1 and out[0, -1, 0] < 24  # trimmed to 24 columns, then halved


@pytest.mark.parametrize("flip,shape", [(0, (4, 6)), (3, (4, 6)), (5, (6, 4)), (6, (6, 4))])
def test_to_sensor_undoes_exif_orientation(flip, shape):
    sensor = coords(4, 6)
    shown = {0: sensor, 3: np.rot90(sensor, 2), 5: np.rot90(sensor, 1), 6: np.rot90(sensor, -1)}[flip]
    assert shown.shape[:2] == shape
    assert np.array_equal(darktable.to_sensor(shown, flip), sensor)


def test_place_crops_flips_and_rotates_like_develop():
    img = coords(100, 150)
    frame = {"crop": [0.1, 0.2, 0.4, 0.5], "rotation": 90, "angle": 0.0}
    out = develop.place(img, {"flip": False}, frame)
    assert out.shape == (60, 50, 3)                       # 60 x 50 crop, turned clockwise
    assert tuple(out[0, -1, :2]) == (15, 20)              # crop's top-left lands top-right
    mirrored = develop.place(img, {"flip": True}, frame, view="full")
    assert tuple(mirrored[0, 0, :2]) == (149, 0)


def test_put_style_writes_items(tmp_path):
    db = tmp_path / "data.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE styles (id INTEGER PRIMARY KEY, name VARCHAR, description VARCHAR, iop_list VARCHAR)")
    con.execute("CREATE TABLE style_items (styleid INTEGER, num INTEGER, module INTEGER, operation VARCHAR(256),"
                " op_params BLOB, enabled INTEGER, blendop_params BLOB, blendop_version INTEGER,"
                " multi_priority INTEGER, multi_name VARCHAR(256), multi_name_hand_edited INTEGER)")
    con.commit()
    items = darktable.style_items("c41")
    darktable.put_style(db, "run", "", items)
    darktable.put_style(db, "run", "", items)  # rewriting replaces, never duplicates
    assert [r[0] for r in con.execute("SELECT name FROM styles")] == ["run"]
    ops = [r[0] for r in con.execute("SELECT operation FROM style_items ORDER BY num")]
    assert ops[-1] == "negadoctor" and "temperature" in ops
    neg = con.execute("SELECT op_params, blendop_params FROM style_items WHERE operation = 'negadoctor'").fetchone()
    assert len(neg[0]) == 76 and len(neg[1]) > 100  # raw struct bytes, blend params un-gzipped


def test_style_items_patch_negadoctor_dmin():
    def negadoctor(items):
        return next(i for i in items if i[2] == "negadoctor")
    stock = negadoctor(darktable.style_items("c41"))
    patched = negadoctor(darktable.style_items("c41", dmin=[0.4, 0.2, 0.1]))
    assert struct.unpack("<3f", patched[3][4:16]) == pytest.approx((0.4, 0.2, 0.1))
    assert patched[3][:4] == stock[3][:4] and patched[3][20:] == stock[3][20:]  # film stock, rest untouched
    assert struct.unpack("<3f", stock[3][4:16]) == pytest.approx((0.367, 0.177, 0.0855))
    assert negadoctor(darktable.style_items("c41", negadoctor=False))[4] == 0
    bw = negadoctor(darktable.style_items("bw", dmin=[0.5, 0.5, 0.5]))
    assert struct.unpack("<3f", bw[3][4:16]) == pytest.approx((0.5, 0.5, 0.5))


def test_fit_affine_recovers_the_map():
    rng = np.random.default_rng(0)
    src = rng.uniform(0.01, 0.8, (60, 80, 3)).astype(np.float32)
    src = np.repeat(np.repeat(src, 4, axis=0), 4, axis=1)  # flat patches survive the blur
    m = np.array([[4.5, 0.4, -0.7, -0.005], [0.0, 2.4, -1.2, -0.005], [0.0, -0.3, 3.8, -0.005]])
    dst = src @ m[:, :3].T.astype(np.float32) + m[:, 3].astype(np.float32)
    assert darktable.fit_affine(src, dst) == pytest.approx(m, abs=1e-3)


def test_film_base_dmin_maps_and_clamps(monkeypatch):
    m = np.array([[4.0, 0, 0, -0.01], [0, 2.0, 0, 0], [0, 0, 3.0, 0]])
    monkeypatch.setattr(darktable, "input_transform", lambda raw, film: m)
    assert darktable.film_base_dmin("x.ARW", "c41", [0.1, 0.09, 0.0]) == pytest.approx([0.39, 0.18, 1e-4])


def test_status_reports_missing_cli(monkeypatch):
    monkeypatch.setenv("NLB_DARKTABLE_CLI", "no-such-darktable-cli")
    st = darktable.status()
    assert st["available"] is False and "darktable-cli" in st["error"]
