import numpy as np
import pytest

from flow import apply_flow, BLOOD_LABEL
import tissue_db

PROPS = tissue_db.properties("3T")
BLOOD = PROPS[BLOOD_LABEL]


def _slice():
    sl = np.zeros((20, 20), dtype=np.uint8)
    sl[4:16, 4:16] = 6              # muscle
    sl[8:12, 8:12] = BLOOD_LABEL    # a vessel
    img = np.ones((20, 20)) * 0.5
    return sl, img


def test_spin_echo_makes_blood_dark():
    sl, img = _slice()
    out = apply_flow(img, sl, "Spin Echo", BLOOD, TE=15, flip_angle=90, velocity=0.8)
    assert out[sl == BLOOD_LABEL].mean() < 0.5 * img[sl == BLOOD_LABEL].mean()


def test_gradient_echo_makes_blood_bright():
    sl, img = _slice()
    out = apply_flow(img, sl, "Gradient Echo", BLOOD, TE=4, flip_angle=70, velocity=0.8)
    assert out[sl == BLOOD_LABEL].mean() > img[sl == BLOOD_LABEL].mean()


def test_non_blood_unchanged():
    sl, img = _slice()
    out = apply_flow(img, sl, "Spin Echo", BLOOD, TE=15, flip_angle=90, velocity=0.8)
    np.testing.assert_allclose(out[sl == 6], img[sl == 6])


def test_zero_velocity_is_noop():
    sl, img = _slice()
    for seq in ("Spin Echo", "Gradient Echo"):
        out = apply_flow(img, sl, seq, BLOOD, TE=10, flip_angle=70, velocity=0.0)
        np.testing.assert_array_equal(out, img)


def test_no_blood_returns_input():
    sl = np.full((10, 10), 6, dtype=np.uint8)   # no blood label
    img = np.ones((10, 10))
    out = apply_flow(img, sl, "Spin Echo", BLOOD, TE=15, flip_angle=90, velocity=1.0)
    np.testing.assert_array_equal(out, img)


def test_faster_flow_deeper_void():
    sl, img = _slice()
    slow = apply_flow(img, sl, "Spin Echo", BLOOD, TE=15, flip_angle=90, velocity=0.3)
    fast = apply_flow(img, sl, "Spin Echo", BLOOD, TE=15, flip_angle=90, velocity=0.9)
    assert fast[sl == BLOOD_LABEL].mean() < slow[sl == BLOOD_LABEL].mean()
