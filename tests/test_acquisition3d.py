"""Tests for the true 3-D (slab) acquisition library (acquisition3d.py)."""
import numpy as np
import pytest

from acquisition3d import (volume_to_kspace, kspace_to_volume, acquire_3d,
                           slab_excitation_profile, snr_3d_gain)


def _blob_slab(Nz=16, H=32, W=32):
    """A smooth non-negative 3-D blob (band-limited so FFT round-trips cleanly)."""
    z, y, x = np.ogrid[:Nz, :H, :W]
    g = np.exp(-(((z - Nz / 2) / (Nz / 4.0)) ** 2
                 + ((y - H / 2) / (H / 4.0)) ** 2
                 + ((x - W / 2) / (W / 4.0)) ** 2))
    return g.astype(float)


def _zsharp_slab(Nz=16, H=24, W=24):
    """Slab with a sharp through-plane (z) edge — for resolution tests."""
    s = np.zeros((Nz, H, W))
    s[: Nz // 2] = 1.0
    s[:, 6:18, 6:18] += 0.5
    return s


# --------------------------------------------------------------------------- #
#  3-D transform round-trip / energy
# --------------------------------------------------------------------------- #
def test_fft_roundtrip_identity():
    slab = _blob_slab()
    back = kspace_to_volume(volume_to_kspace(slab))
    assert np.allclose(back, slab, atol=1e-9)


def test_parseval_energy():
    slab = _blob_slab()
    ks = volume_to_kspace(slab)
    img_energy = np.sum(slab ** 2)
    k_energy = np.sum(np.abs(ks) ** 2) / slab.size
    assert k_energy == pytest.approx(img_energy, rel=1e-6)


# --------------------------------------------------------------------------- #
#  acquire_3d — shapes, losslessness, resolution
# --------------------------------------------------------------------------- #
def test_acquire_shapes():
    slab = _blob_slab(16, 32, 32)
    recon, ks = acquire_3d(slab, matrix_xy=32, n_kz=16)
    assert recon.shape == slab.shape
    assert ks.shape == (16, 32, 32)


def test_full_acquisition_is_lossless():
    slab = _blob_slab(16, 32, 32)
    recon, _ = acquire_3d(slab, matrix_xy=32, n_kz=16)
    assert np.allclose(recon, slab, atol=1e-9)


def test_recon_finite_and_nonnegative():
    slab = _blob_slab()
    recon, _ = acquire_3d(slab, matrix_xy=16, n_kz=8, pf_kz=0.75,
                          pf_ky=0.75, filter_window="hamming")
    assert np.all(np.isfinite(recon))
    assert float(recon.min()) >= 0.0


def _z_sharpness(vol):
    """Peak through-plane gradient of the slab's z-profile (higher = sharper)."""
    zp = vol.mean(axis=(1, 2))
    return float(np.abs(np.diff(zp)).max())


def test_fewer_kz_encodes_blur_through_plane():
    slab = _zsharp_slab(Nz=16)
    hi, _ = acquire_3d(slab, matrix_xy=24, n_kz=16)
    lo, _ = acquire_3d(slab, matrix_xy=24, n_kz=4)
    assert _z_sharpness(hi) > _z_sharpness(lo), "fewer kz encodes must blur z"


def _xy_sharpness(vol):
    mid = vol[vol.shape[0] // 2]
    return float(np.abs(np.diff(mid, axis=1)).max())


def test_smaller_matrix_blurs_in_plane():
    slab = _zsharp_slab(Nz=8, H=32, W=32)
    hi, _ = acquire_3d(slab, matrix_xy=32, n_kz=8)
    lo, _ = acquire_3d(slab, matrix_xy=8, n_kz=8)
    assert _xy_sharpness(hi) > _xy_sharpness(lo)


def test_kz_partial_fourier_changes_recon():
    slab = _blob_slab()
    full, _ = acquire_3d(slab, matrix_xy=32, n_kz=16)
    pf, _ = acquire_3d(slab, matrix_xy=32, n_kz=16, pf_kz=0.625)
    assert not np.allclose(full, pf)


# --------------------------------------------------------------------------- #
#  Slab excitation profile
# --------------------------------------------------------------------------- #
def test_profile_length_and_peak():
    p = slab_excitation_profile(20)
    assert p.shape == (20,)
    assert p.max() == pytest.approx(1.0)
    assert np.all((p > 0) & (p <= 1.0 + 1e-9))


def test_profile_edges_attenuated():
    p = slab_excitation_profile(24, sharpness=0.85)
    assert p[0] < p[len(p) // 2] and p[-1] < p[len(p) // 2]


def test_profile_sharpness_flattens_top():
    flat = slab_excitation_profile(40, sharpness=1.0)
    round_ = slab_excitation_profile(40, sharpness=0.1)
    # a flatter (sharper) profile keeps more partitions near full excitation
    assert np.sum(flat > 0.9) > np.sum(round_ > 0.9)


def test_profile_single_partition():
    assert np.allclose(slab_excitation_profile(1), [1.0])


def test_profile_applied_dims_edge_partitions():
    slab = np.ones((20, 16, 16))
    prof = slab_excitation_profile(20, sharpness=0.6)
    recon, _ = acquire_3d(slab, matrix_xy=16, n_kz=20, profile=prof)
    edge = 0.5 * (recon[0].mean() + recon[-1].mean())
    centre = recon[10].mean()
    assert edge < centre, "slab edges should be dimmer than the centre"


# --------------------------------------------------------------------------- #
#  3-D SNR gain
# --------------------------------------------------------------------------- #
def test_snr_gain_formula():
    assert snr_3d_gain(64) == pytest.approx(8.0)
    assert snr_3d_gain(64, nex=4) == pytest.approx(16.0)


def test_snr_gain_unity_for_single_partition():
    assert snr_3d_gain(1) == pytest.approx(1.0)


def test_snr_gain_monotonic():
    assert snr_3d_gain(128) > snr_3d_gain(32) > snr_3d_gain(8)


def test_acquire_rejects_non_3d():
    with pytest.raises(ValueError):
        acquire_3d(np.zeros((16, 16)), matrix_xy=16, n_kz=4)
