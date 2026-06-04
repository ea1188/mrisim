"""Tests for the SWI processing library (swi.py) and b0.field_from_chi."""
import numpy as np
import pytest

import b0
import swi


# --------------------------------------------------------------------------- #
#  Phase mask
# --------------------------------------------------------------------------- #
def test_phase_mask_range_and_endpoints():
    phase = np.linspace(-np.pi, np.pi, 101)
    m = swi.phase_mask(phase, power=1)
    assert m.min() >= 0.0 and m.max() <= 1.0
    assert m[0] == pytest.approx(0.0, abs=1e-6)       # φ = −π → 0
    assert swi.phase_mask(np.array([0.0]))[0] == pytest.approx(1.0)


def test_phase_mask_is_one_for_positive_phase():
    pos = np.array([0.1, 1.0, np.pi])
    assert np.allclose(swi.phase_mask(pos, power=4), 1.0)


def test_phase_mask_monotonic_on_negative_phase():
    phase = np.linspace(-np.pi, 0, 50)
    m = swi.phase_mask(phase, power=1)
    assert np.all(np.diff(m) >= -1e-9)                 # increases from 0 → 1


def test_higher_power_darkens_more():
    phase = np.full(10, -np.pi / 2)
    assert swi.phase_mask(phase, 4).mean() < swi.phase_mask(phase, 1).mean()


# --------------------------------------------------------------------------- #
#  Combine — paramagnetic (negative phase) darkens, rest preserved
# --------------------------------------------------------------------------- #
def test_swi_darkens_negative_phase_only():
    mag = np.ones((16, 16))
    phase = np.zeros((16, 16))
    phase[6:10, 6:10] = -np.pi * 0.9            # a paramagnetic blob
    out = swi.swi_combine(mag, phase, power=4, hp_sigma=0.0)
    assert out[8, 8] < 0.3                       # darkened
    assert out[0, 0] == pytest.approx(1.0, abs=1e-6)  # untouched


def test_swi_preserves_magnitude_where_no_phase():
    rng = np.random.default_rng(0)
    mag = rng.random((20, 20)) + 0.1
    out = swi.swi_combine(mag, np.zeros((20, 20)), hp_sigma=0.0)
    assert np.allclose(out, mag)


# --------------------------------------------------------------------------- #
#  Field → phase
# --------------------------------------------------------------------------- #
def test_field_to_phase_scales_with_te_and_wraps():
    f = np.array([10.0])
    assert swi.field_to_phase(f, 10)[0] == pytest.approx(2 * np.pi * 10 * 0.01)
    # large field × TE wraps into (−π, π]
    big = swi.field_to_phase(np.array([200.0]), 50)[0]
    assert -np.pi < big <= np.pi


# --------------------------------------------------------------------------- #
#  Homodyne high-pass removes a smooth background ramp
# --------------------------------------------------------------------------- #
def test_homodyne_removes_smooth_background():
    y, x = np.mgrid[0:48, 0:48]
    background = 0.05 * (x - 24)                  # smooth linear field ramp (rad)
    local = np.zeros((48, 48)); local[22:26, 22:26] = -1.2
    hp = swi.homodyne_highpass(background + local, sigma=6.0)
    # background is largely removed (small away from the local source)…
    assert abs(hp[4, 4]) < 0.3
    # …while the local negative source survives
    assert hp[24, 24] < -0.3


# --------------------------------------------------------------------------- #
#  Minimum-intensity projection
# --------------------------------------------------------------------------- #
def test_min_ip_takes_local_minimum():
    vol = np.ones((10, 4, 4))
    vol[5] = 0.2                                  # a dark vessel on one partition
    mip = swi.min_ip(vol, axis=0, slab=5)
    assert mip[5].max() == pytest.approx(0.2)
    assert mip[3, 0, 0] == pytest.approx(0.2)     # pulled into neighbours within the slab
    assert mip[0, 0, 0] == pytest.approx(1.0)     # outside the slab reach


# --------------------------------------------------------------------------- #
#  b0.field_from_chi — custom susceptibility (e.g. a venous source)
# --------------------------------------------------------------------------- #
def test_field_from_chi_matches_label_path():
    vol = np.zeros((16, 16, 16), dtype=int)
    vol[6:10, 6:10, 6:10] = 17                    # an air cavity (paramagnetic vs tissue)
    from_label = b0.susceptibility_b0_map(vol, field_strength_T=3.0)
    from_chi = b0.field_from_chi(b0._chi_vol(vol), field_strength_T=3.0)
    assert np.allclose(from_label, from_chi)


def test_paramagnetic_source_produces_nonzero_field():
    chi = np.zeros((16, 16, 16))
    chi[8, 8, 8] = 0.45                            # a venous voxel (+0.45 ppm)
    field = b0.field_from_chi(chi, field_strength_T=3.0)
    assert np.abs(field).max() > 0.0
    assert np.isfinite(field).all()
