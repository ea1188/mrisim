"""Tests for src/epi.py — EPI k-space trajectory and artifacts."""

import numpy as np
import pytest
from epi import (
    epi_trajectory,
    epi_phase_correction,
    add_nyquist_ghost,
    ghost_ratio,
    epi_b0_phase_error,
    epi_distortion_map,
    apply_epi_distortion,
    simulate_epi,
    epi_t2star_decay,
)


# ---------------------------------------------------------------------------
# TestEpiTrajectory
# ---------------------------------------------------------------------------
class TestEpiTrajectory:
    def test_output_shapes(self):
        kx, ky, t = epi_trajectory(64, 32)
        assert kx.shape == (32, 64)
        assert ky.shape == (32, 64)
        assert t.shape  == (32, 64)

    def test_even_lines_left_to_right(self):
        kx, _, _ = epi_trajectory(16, 8)
        assert kx[0, 0] < kx[0, -1]   # line 0: ascending
        assert kx[2, 0] < kx[2, -1]   # line 2: ascending

    def test_odd_lines_right_to_left(self):
        kx, _, _ = epi_trajectory(16, 8)
        assert kx[1, 0] > kx[1, -1]   # line 1: descending
        assert kx[3, 0] > kx[3, -1]   # line 3: descending

    def test_ky_monotonically_increasing(self):
        _, ky, _ = epi_trajectory(16, 8)
        # First sample of each line should increase monotonically
        ky_first = ky[:, 0]
        assert np.all(np.diff(ky_first) > 0)

    def test_time_increases(self):
        _, _, t = epi_trajectory(16, 8, esp_ms=1.0)
        assert t[-1, -1] > t[0, 0]

    def test_time_step_equals_esp(self):
        esp = 0.5
        _, _, t = epi_trajectory(16, 8, esp_ms=esp)
        # First sample of consecutive lines is separated by esp
        np.testing.assert_allclose(t[1, 0] - t[0, 0], esp, rtol=1e-6)

    def test_kx_range(self):
        n_freq = 64
        kx, _, _ = epi_trajectory(n_freq, 32)
        assert kx.min() == pytest.approx(-n_freq / 2)
        assert kx.max() == pytest.approx(n_freq / 2 - 1)

    def test_ky_range(self):
        n_phase = 32
        _, ky, _ = epi_trajectory(64, n_phase)
        assert ky.min() == pytest.approx(-n_phase / 2)
        assert ky.max() == pytest.approx(n_phase / 2 - 1)


# ---------------------------------------------------------------------------
# TestAddNyquistGhost
# ---------------------------------------------------------------------------
class TestAddNyquistGhost:
    def _make_kspace(self, shape=(32, 32)):
        rng = np.random.default_rng(0)
        return (rng.standard_normal(shape) + 1j * rng.standard_normal(shape))

    def test_even_lines_unchanged(self):
        ks = self._make_kspace()
        ghosted = add_nyquist_ghost(ks, phase_offset_rad=0.5)
        np.testing.assert_array_equal(ghosted[0], ks[0])
        np.testing.assert_array_equal(ghosted[2], ks[2])

    def test_odd_lines_modified(self):
        ks = self._make_kspace()
        ghosted = add_nyquist_ghost(ks, phase_offset_rad=0.5)
        assert not np.allclose(ghosted[1], ks[1])

    def test_zero_offset_identity(self):
        ks = self._make_kspace()
        ghosted = add_nyquist_ghost(ks, phase_offset_rad=0.0,
                                     linear_phase_rad_per_sample=0.0)
        np.testing.assert_array_equal(ghosted, ks)

    def test_magnitude_preserved(self):
        ks = self._make_kspace()
        ghosted = add_nyquist_ghost(ks, phase_offset_rad=1.0)
        np.testing.assert_allclose(np.abs(ghosted), np.abs(ks), rtol=1e-10)

    def test_output_shape(self):
        ks = self._make_kspace((20, 24))
        ghosted = add_nyquist_ghost(ks, phase_offset_rad=0.2)
        assert ghosted.shape == (20, 24)


# ---------------------------------------------------------------------------
# TestGhostRatio
# ---------------------------------------------------------------------------
class TestGhostRatio:
    def test_no_ghost_gives_low_ratio(self):
        # Signal only in top half, nothing in bottom → low GSR
        img = np.zeros((32, 32))
        img[:16, :] = 1.0
        gsr = ghost_ratio(img)
        assert gsr < 0.1

    def test_equal_halves_gives_ratio_one(self):
        img = np.ones((32, 32))
        gsr = ghost_ratio(img)
        assert gsr == pytest.approx(1.0, abs=1e-6)

    def test_zero_image_gives_zero(self):
        assert ghost_ratio(np.zeros((16, 16))) == pytest.approx(0.0)

    def test_output_scalar(self):
        assert isinstance(ghost_ratio(np.ones((8, 8))), float)

    def test_ratio_in_unit_interval(self):
        rng = np.random.default_rng(1)
        img = np.abs(rng.standard_normal((32, 32)))
        gsr = ghost_ratio(img)
        assert 0.0 <= gsr


# ---------------------------------------------------------------------------
# TestEpiB0PhaseError
# ---------------------------------------------------------------------------
class TestEpiB0PhaseError:
    def test_zero_time_gives_zero_phase(self):
        b0 = np.full((10, 10), 100.)
        phase = epi_b0_phase_error(b0, t_pe_ms=0.0)
        assert np.all(phase == 0.0)

    def test_phase_proportional_to_b0(self):
        b0a = np.full((5, 5), 50.)
        b0b = np.full((5, 5), 100.)
        pa = epi_b0_phase_error(b0a, 1.0)
        pb = epi_b0_phase_error(b0b, 1.0)
        np.testing.assert_allclose(pb, 2 * pa, rtol=1e-10)

    def test_phase_proportional_to_time(self):
        b0 = np.full((5, 5), 100.)
        p1 = epi_b0_phase_error(b0, 1.0)
        p2 = epi_b0_phase_error(b0, 2.0)
        np.testing.assert_allclose(p2, 2 * p1, rtol=1e-10)

    def test_output_shape(self):
        b0 = np.zeros((8, 12))
        assert epi_b0_phase_error(b0, 1.0).shape == (8, 12)


# ---------------------------------------------------------------------------
# TestEpiDistortionMap
# ---------------------------------------------------------------------------
class TestEpiDistortionMap:
    def test_zero_b0_gives_zero_shift(self):
        b0 = np.zeros((10, 10))
        shift = epi_distortion_map(b0, esp_ms=0.5, n_phase=64)
        assert np.all(shift == 0.)

    def test_shift_proportional_to_b0(self):
        b0 = np.full((5, 5), 100.)
        s1 = epi_distortion_map(b0, esp_ms=0.5, n_phase=64)
        s2 = epi_distortion_map(b0 * 2, esp_ms=0.5, n_phase=64)
        np.testing.assert_allclose(s2, 2 * s1, rtol=1e-10)

    def test_larger_n_phase_larger_shift(self):
        b0 = np.full((5, 5), 100.)
        s_small = epi_distortion_map(b0, esp_ms=0.5, n_phase=32)
        s_large = epi_distortion_map(b0, esp_ms=0.5, n_phase=128)
        assert s_large.mean() > s_small.mean()

    def test_larger_esp_larger_shift(self):
        b0 = np.full((5, 5), 100.)
        s_short = epi_distortion_map(b0, esp_ms=0.5, n_phase=64)
        s_long  = epi_distortion_map(b0, esp_ms=1.0, n_phase=64)
        assert s_long.mean() > s_short.mean()

    def test_output_shape(self):
        b0 = np.zeros((7, 9))
        assert epi_distortion_map(b0, 0.5, 64).shape == (7, 9)

    def test_custom_bw_overrides_default(self):
        b0 = np.full((5, 5), 200.)
        shift = epi_distortion_map(b0, esp_ms=0.5, n_phase=64,
                                    bw_hz_per_pixel=100.)
        np.testing.assert_allclose(shift, 2.0)


# ---------------------------------------------------------------------------
# TestApplyEpiDistortion
# ---------------------------------------------------------------------------
class TestApplyEpiDistortion:
    def test_zero_b0_identity(self):
        img = np.arange(100., dtype=float).reshape(10, 10)
        b0 = np.zeros((10, 10))
        out = apply_epi_distortion(img, b0, esp_ms=0.5, n_phase=64)
        np.testing.assert_allclose(out, img, atol=1e-5)

    def test_output_shape(self):
        img = np.ones((12, 14))
        b0 = np.zeros((12, 14))
        out = apply_epi_distortion(img, b0, 0.5, 64)
        assert out.shape == (12, 14)

    def test_nonzero_b0_changes_image(self):
        img = np.zeros((20, 20))
        img[5, :] = 1.0
        b0 = np.full((20, 20), 500.)
        out = apply_epi_distortion(img, b0, esp_ms=0.5, n_phase=32)
        assert not np.allclose(out, img)

    def test_phase_encode_axis_1(self):
        img = np.zeros((20, 20))
        img[:, 5] = 1.0
        b0 = np.full((20, 20), 500.)
        out = apply_epi_distortion(img, b0, esp_ms=0.5, n_phase=32,
                                    phase_encode_axis=1)
        assert not np.allclose(out, img)


# ---------------------------------------------------------------------------
# TestSimulateEpi
# ---------------------------------------------------------------------------
class TestSimulateEpi:
    def _phantom(self, size=32):
        img = np.zeros((size, size))
        img[size // 4: 3 * size // 4, size // 4: 3 * size // 4] = 1.0
        return img

    def test_output_shapes(self):
        img = self._phantom()
        recon, ks = simulate_epi(img)
        assert recon.shape == img.shape
        assert ks.shape == img.shape

    def test_no_error_perfect_recon(self):
        img = self._phantom()
        recon, _ = simulate_epi(img)
        np.testing.assert_allclose(np.abs(recon), img, atol=1e-8)

    def test_phase_error_creates_ghost(self):
        img = self._phantom(32)
        recon_clean, _ = simulate_epi(img)
        recon_ghost, _ = simulate_epi(img, phase_offset_rad=np.pi / 4)
        # Ghosted image has higher ghost-to-signal ratio
        gsr_clean = ghost_ratio(np.abs(recon_clean))
        gsr_ghost = ghost_ratio(np.abs(recon_ghost))
        assert gsr_ghost > gsr_clean

    def test_correction_reduces_ghost(self):
        img = self._phantom(32)
        _, ks_ghost = simulate_epi(img, phase_offset_rad=0.3)
        recon_uncorr, _ = simulate_epi(img, phase_offset_rad=0.3, correct_ghost=False)
        recon_corr, _   = simulate_epi(img, phase_offset_rad=0.3, correct_ghost=True)
        gsr_uncorr = ghost_ratio(np.abs(recon_uncorr))
        gsr_corr   = ghost_ratio(np.abs(recon_corr))
        assert gsr_corr <= gsr_uncorr + 0.05

    def test_kspace_is_complex(self):
        img = self._phantom()
        _, ks = simulate_epi(img)
        assert np.iscomplexobj(ks)


# ---------------------------------------------------------------------------
# TestEpiT2starDecay
# ---------------------------------------------------------------------------
class TestEpiT2starDecay:
    def test_output_shape(self):
        img = np.ones((32, 32))
        T2s = np.full((32, 32), 50.)
        out = epi_t2star_decay(img, T2s, esp_ms=0.5, n_phase=32)
        assert out.shape == (32, 32)

    def test_output_nonneg(self):
        img = np.ones((20, 20))
        T2s = np.full((20, 20), 30.)
        out = epi_t2star_decay(img, T2s, esp_ms=0.5, n_phase=20)
        assert out.min() >= 0.

    def test_blurring_reduces_peak_signal(self):
        img = np.zeros((32, 32))
        img[16, 16] = 1.0   # single bright voxel
        T2s = np.full((32, 32), 20.)
        out = epi_t2star_decay(img, T2s, esp_ms=0.5, n_phase=32)
        # T2* decay smears energy away from peak
        assert out.max() < 1.0

    def test_infinite_t2star_no_blur(self):
        img = np.ones((16, 16))
        T2s = np.full((16, 16), 1e9)   # effectively infinite
        out = epi_t2star_decay(img, T2s, esp_ms=0.5, n_phase=16)
        np.testing.assert_allclose(out, img, rtol=1e-3)

    def test_shorter_t2star_more_blurring(self):
        img = np.zeros((32, 32))
        img[16, 16] = 1.0
        T2s_long  = np.full((32, 32), 200.)
        T2s_short = np.full((32, 32), 20.)
        out_long  = epi_t2star_decay(img, T2s_long,  esp_ms=0.5, n_phase=32)
        out_short = epi_t2star_decay(img, T2s_short, esp_ms=0.5, n_phase=32)
        assert out_short.max() < out_long.max()
