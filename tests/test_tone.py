import numpy as np

from nlb.tone import to_positive


def _rgb(gray):
    return np.repeat(np.asarray(gray, np.float32)[..., None], 3, axis=2)


def test_inverts_and_stretches_to_full_range():
    neg = _rgb(np.tile(np.linspace(0.3, 0.7, 1000), (10, 1)))
    pos = to_positive(neg)
    assert pos.shape == (10, 1000) and pos.dtype == np.float32
    assert pos[:, 0].mean() > 0.99      # thin negative -> white
    assert pos[:, -1].mean() < 0.01     # dense negative -> black
    assert pos.min() >= 0 and pos.max() <= 1


def test_gamma_above_one_brightens_midtones():
    neg = _rgb(np.tile(np.linspace(0.3, 0.7, 1000), (10, 1)))
    assert to_positive(neg, gamma=2.0)[:, 500].mean() > to_positive(neg)[:, 500].mean() + 0.1


def test_flat_input_returns_black_not_nan():
    pos = to_positive(_rgb(np.full((5, 5), 0.5)))
    assert np.isfinite(pos).all() and pos.max() == 0


def test_uses_luma_not_single_channel():
    neg = np.zeros((4, 4, 3), np.float32)
    neg[:2, :, 1] = 1.0                   # green-bright top half
    pos = to_positive(neg)
    assert pos[:2].mean() < pos[2:].mean()
