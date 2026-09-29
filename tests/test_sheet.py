import numpy as np

from nlb.sheet import CELL_PAD, LABEL_H, contact_sheet


def test_grid_size():
    items = [(f"IMG_{i}", np.full((200, 300), 0.5, np.float32), []) for i in range(4)]
    sheet = contact_sheet(items, thumb=150, cols=3)
    cell_w, cell_h = 150 + 2 * CELL_PAD, 150 + LABEL_H + 2 * CELL_PAD
    assert sheet.size == (3 * cell_w, 2 * cell_h)
    assert sheet.mode == "RGB"


def test_flagged_label_is_red():
    items = [("ok", np.ones((100, 150), np.float32), []),
             ("bad", np.ones((100, 150), np.float32), ["partial_or_blank"])]
    arr = np.asarray(contact_sheet(items, thumb=150, cols=2)).astype(int)
    cell_w = 150 + 2 * CELL_PAD
    label_rows = arr[150 + CELL_PAD:]
    def red(a):
        return ((a[..., 0] > 150) & (a[..., 1] < 80) & (a[..., 2] < 80)).sum()
    assert red(label_rows[:, :cell_w]) == 0
    assert red(label_rows[:, cell_w:]) > 0


def test_empty_items_gives_small_blank_sheet():
    assert contact_sheet([]).size[0] > 0
