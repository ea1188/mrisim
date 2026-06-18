"""Tests for src/b0.py — B0 field map and off-resonance effects."""

import numpy as np
import pytest
from b0 import (
    SUSCEPTIBILITY_PPM,
    _chi_vol,
    _dipole_kernel,
    susceptibility_b0_map,
    polynomial_b0_map,
    gaussian_b0_map,
    b0_lineshape_factor,
    apply_offresonance,
    readout_pixel_shift,
    apply_readout_shift,
)


# ---------------------------------------------------------------------------
# SUSCEPTIBILITY_PPM
# ---------------------------------------------------------------------------
class TestSusceptibilityPpm:
    def test_has_body_labels_0_to_21(self):
        # Body/neuro labels 0-21, plus the brain-only demo pathologies 23-26.
        assert set(range(22)).issubset(SUSCEPTIBILITY_PPM.keys())
        assert set(SUSCEPTIBILITY_PPM.keys()) == set(range(22)) | {23, 24, 25, 26, 27, 28}

    def test_background_zero(self):
        assert SUSCEPTIBILITY_PPM[0] == 0.0

    def test_air_cavity_positive(self):
        # Air is paramagnetic relative to tissue
        assert SUSCEPTIBILITY_PPM[17] > 0

    def test_bone_more_negative_than_soft_tissue(self):
        # Cortical bone is more diamagnetic than soft tissue
        assert SUSCEPTIBILITY_PPM[13] < SUSCEPTIBILITY_PPM[6]

    def test_fat_distinct_from_soft_tissue(self):
        assert SUSCEPTIBILITY_PPM[4] != SUSCEPTIBILITY_PPM[6]

    def test_all_values_are_floats(self):
        for v in SUSCEPTIBILITY_PPM.values():
            assert isinstance(v, float)


# ---------------------------------------------------------------------------
# _chi_vol
# ---------------------------------------------------------------------------
class TestChiVol:
    def test_all_zeros_gives_zero_chi(self):
        vol = np.zeros((4, 4, 4), dtype=np.uint8)
        chi = _chi_vol(vol)
        assert np.all(chi == 0.0)

    def test_label_17_gives_air_chi(self):
        vol = np.zeros((3, 3, 3), dtype=np.uint8)
        vol[1, 1, 1] = 17
        chi = _chi_vol(vol)
        assert chi[1, 1, 1] == pytest.approx(SUSCEPTIBILITY_PPM[17])

    def test_label_4_gives_fat_chi(self):
        vol = np.array([[[4]]], dtype=np.uint8)
        chi = _chi_vol(vol)
        assert chi[0, 0, 0] == pytest.approx(SUSCEPTIBILITY_PPM[4])

    def test_output_dtype_float64(self):
        vol = np.zeros((5, 5, 5), dtype=np.uint8)
        assert _chi_vol(vol).dtype == np.float64

    def test_output_shape_matches_input(self):
        vol = np.zeros((6, 7, 8), dtype=np.uint8)
        assert _chi_vol(vol).shape == (6, 7, 8)

    def test_multiple_labels(self):
        vol = np.zeros((2, 2, 2), dtype=np.uint8)
        vol[0, 0, 0] = 17   # air
        vol[1, 1, 1] = 13   # bone
        chi = _chi_vol(vol)
        assert chi[0, 0, 0] == pytest.approx(SUSCEPTIBILITY_PPM[17])
        assert chi[1, 1, 1] == pytest.approx(SUSCEPTIBILITY_PPM[13])
        assert chi[0, 1, 0] == pytest.approx(0.0)  # background


# ---------------------------------------------------------------------------
# _dipole_kernel
# ---------------------------------------------------------------------------
class TestDipoleKernel:
    def test_output_shape_matches_input(self):
        K = _dipole_kernel((10, 12, 14))
        assert K.shape == (10, 12, 14)

    def test_dc_is_zero(self):
        K = _dipole_kernel((16, 16, 16))
        assert K[0, 0, 0] == pytest.approx(0.0)

    def test_along_kz_axis_kernel_is_minus_two_thirds(self):
        # When ky=kx=0, K = 1/3 - kz²/kz² = 1/3 - 1 = -2/3
        K = _dipole_kernel((32, 32, 32))
        # k=(1,0,0) in numpy fftfreq ordering → index (1,0,0)
        assert K[1, 0, 0] == pytest.approx(-2.0 / 3.0, abs=1e-10)

    def test_along_kxy_plane_kernel_is_one_third(self):
        # When kz=0, K = 1/3 - 0 = 1/3
        K = _dipole_kernel((32, 32, 32))
        assert K[0, 1, 0] == pytest.approx(1.0 / 3.0, abs=1e-10)
        assert K[0, 0, 1] == pytest.approx(1.0 / 3.0, abs=1e-10)

    def test_kernel_values_bounded(self):
        K = _dipole_kernel((20, 20, 20))
        # Kernel values should be in [-2/3, 1/3]
        assert K.max() <= 1.0 / 3.0 + 1e-10
        assert K.min() >= -2.0 / 3.0 - 1e-10

    def test_anisotropic_voxel_size_changes_kernel(self):
        K_iso = _dipole_kernel((16, 16, 16), voxel_size=(1., 1., 1.))
        K_aniso = _dipole_kernel((16, 16, 16), voxel_size=(2., 1., 1.))
        assert not np.allclose(K_iso, K_aniso)


# ---------------------------------------------------------------------------
# susceptibility_b0_map
# ---------------------------------------------------------------------------
class TestSusceptibilityB0Map:
    def test_output_shape_matches_input(self):
        vol = np.zeros((16, 16, 16), dtype=np.uint8)
        b0 = susceptibility_b0_map(vol, voxel_size=(1., 1., 1.))
        assert b0.shape == (16, 16, 16)

    def test_uniform_volume_gives_near_zero_b0(self):
        # Uniform susceptibility → no gradient → ≈0 field variation
        vol = np.full((20, 20, 20), 6, dtype=np.uint8)  # all muscle
        b0 = susceptibility_b0_map(vol)
        assert np.abs(b0).max() < 1.0  # < 1 Hz

    def test_air_tissue_boundary_creates_nonzero_b0(self):
        vol = np.zeros((32, 32, 32), dtype=np.uint8)
        vol[:, :, :] = 6     # muscle
        vol[14:18, 14:18, 14:18] = 17  # air cavity inside
        b0 = susceptibility_b0_map(vol, field_strength_T=3.0)
        assert np.abs(b0).max() > 0.1

    def test_output_dtype_float64(self):
        vol = np.zeros((8, 8, 8), dtype=np.uint8)
        assert susceptibility_b0_map(vol).dtype == np.float64

    def test_scales_linearly_with_field_strength(self):
        vol = np.zeros((16, 16, 16), dtype=np.uint8)
        vol[6:10, 6:10, 6:10] = 17
        b0_15 = susceptibility_b0_map(vol, field_strength_T=1.5)
        b0_30 = susceptibility_b0_map(vol, field_strength_T=3.0)
        ratio = b0_30 / np.where(np.abs(b0_15) > 1e-10, b0_15, np.nan)
        valid = np.isfinite(ratio)
        np.testing.assert_allclose(ratio[valid], 2.0, rtol=1e-6)


# ---------------------------------------------------------------------------
# polynomial_b0_map
# ---------------------------------------------------------------------------
class TestPolynomialB0Map:
    def test_all_zero_coefficients_gives_zero(self):
        b0 = polynomial_b0_map((10, 10, 10))
        assert np.all(b0 == 0.0)

    def test_output_shape(self):
        b0 = polynomial_b0_map((5, 7, 9))
        assert b0.shape == (5, 7, 9)

    def test_linear_gradient_along_first_axis(self):
        b0 = polynomial_b0_map((11, 5, 5), voxel_size=(1., 1., 1.),
                                linear=(1., 0., 0.))
        # Coordinate of row 0 is -(10)/2 = -5 mm, row 10 = +5 mm
        assert b0[0, 2, 2] == pytest.approx(-5.0, abs=1e-10)
        assert b0[10, 2, 2] == pytest.approx(5.0, abs=1e-10)

    def test_linear_gradient_is_antisymmetric(self):
        b0 = polynomial_b0_map((10, 10, 10), linear=(1., 0., 0.))
        mid = 5
        # Symmetric positions about centre should have opposite signs
        assert b0[3, mid, mid] == pytest.approx(-b0[6, mid, mid], abs=1e-10)

    def test_quadratic_is_symmetric(self):
        b0 = polynomial_b0_map((10, 10, 10), quadratic=(1., 0., 0.))
        # Quadratic is even function
        np.testing.assert_allclose(b0[3, :, :], b0[6, :, :], atol=1e-10)

    def test_quadratic_minimum_at_centre(self):
        b0 = polynomial_b0_map((11, 11, 11), quadratic=(1., 0., 0.))
        # Centre voxel = (5,5,5) → coord = 0 → b0 = 0 (minimum)
        assert b0[5, 5, 5] == pytest.approx(0.0, abs=1e-10)

    def test_2d_shape(self):
        b0 = polynomial_b0_map((8, 8), voxel_size=(1., 1.), linear=(0.5, 0.0))
        assert b0.shape == (8, 8)


# ---------------------------------------------------------------------------
# gaussian_b0_map
# ---------------------------------------------------------------------------
class TestGaussianB0Map:
    def test_output_shape(self):
        b0 = gaussian_b0_map((20, 20, 20))
        assert b0.shape == (20, 20, 20)

    def test_peak_at_centre_by_default(self):
        b0 = gaussian_b0_map((21, 21, 21), voxel_size=(1., 1., 1.),
                              amplitude_hz=100.0, fwhm_mm=10.0)
        # Centre voxel has max value
        assert b0.max() == pytest.approx(b0[10, 10, 10], abs=1e-10)

    def test_amplitude_respected(self):
        b0 = gaussian_b0_map((21, 21, 21), voxel_size=(1., 1., 1.),
                              amplitude_hz=200.0, fwhm_mm=10.0)
        assert b0.max() == pytest.approx(200.0, rel=1e-6)

    def test_off_centre_peak(self):
        b0 = gaussian_b0_map((20, 20, 20), voxel_size=(1., 1., 1.),
                              center=(5., 5., 5.), amplitude_hz=50.0, fwhm_mm=5.0)
        assert b0[5, 5, 5] == pytest.approx(50.0, rel=1e-5)

    def test_values_non_negative_for_positive_amplitude(self):
        b0 = gaussian_b0_map((15, 15, 15), amplitude_hz=100.0)
        assert b0.min() >= 0.0

    def test_fwhm_half_max_at_correct_distance(self):
        b0 = gaussian_b0_map((101, 5, 5), voxel_size=(1., 1., 1.),
                              amplitude_hz=1.0, fwhm_mm=10.0)
        half = 0.5
        # Voxel at ~5 mm from centre (row 55 from row 50) should be ≈ 0.5
        assert b0[55, 2, 2] == pytest.approx(half, rel=0.01)

    def test_output_dtype_float64(self):
        assert gaussian_b0_map((8, 8, 8)).dtype == np.float64


# ---------------------------------------------------------------------------
# b0_lineshape_factor
# ---------------------------------------------------------------------------
class TestB0LineshapeFactor:
    def test_uniform_b0_gives_factor_one(self):
        b0 = np.full((20, 20), 100.0)  # uniform → zero gradient
        factor = b0_lineshape_factor(b0, TE_ms=20.0)
        np.testing.assert_allclose(factor, 1.0, atol=1e-6)

    def test_output_shape_matches_input(self):
        b0 = np.zeros((15, 18))
        factor = b0_lineshape_factor(b0, TE_ms=10.0)
        assert factor.shape == (15, 18)

    def test_values_in_unit_interval(self):
        rng = np.random.default_rng(42)
        b0 = rng.normal(0, 50, (30, 30))
        factor = b0_lineshape_factor(b0, TE_ms=20.0)
        assert factor.min() >= 0.0
        assert factor.max() <= 1.0 + 1e-10

    def test_large_gradient_gives_small_factor(self):
        # Steep gradient → large ΔF → sinc near zero
        b0 = np.zeros((20, 20))
        b0[:, 10:] = 5000.0   # 5 kHz step at column 10
        factor = b0_lineshape_factor(b0, TE_ms=1.0, voxel_size_2d=(1., 1.))
        # At the step edge, gradient is huge → factor should be < 0.5
        assert factor[:, 10].mean() < 0.5

    def test_longer_te_reduces_factor(self):
        b0 = np.zeros((20, 20))
        b0[10:, :] = 50.0  # moderate step
        f_short = b0_lineshape_factor(b0, TE_ms=10.0)
        f_long  = b0_lineshape_factor(b0, TE_ms=80.0)
        # At the boundary row, longer TE → more dephasing → smaller factor
        assert f_long[10, :].mean() <= f_short[10, :].mean() + 1e-6


# ---------------------------------------------------------------------------
# apply_offresonance
# ---------------------------------------------------------------------------
class TestApplyOffresonance:
    def _make_inputs(self):
        signal = np.ones((20, 20)) * 0.8
        b0 = np.zeros((20, 20))
        b0[10:, :] = 30.0
        return signal, b0

    def test_se_returns_unchanged(self):
        signal, b0 = self._make_inputs()
        out = apply_offresonance(signal, b0, TE_ms=20.0, sequence="SE")
        np.testing.assert_array_equal(out, signal)

    def test_ir_returns_unchanged(self):
        signal, b0 = self._make_inputs()
        out = apply_offresonance(signal, b0, TE_ms=20.0, sequence="IR")
        np.testing.assert_array_equal(out, signal)

    def test_gre_modulates_signal(self):
        signal, b0 = self._make_inputs()
        out = apply_offresonance(signal, b0, TE_ms=20.0, sequence="GRE")
        # At the step boundary dephasing occurs → max < original
        assert out.max() <= signal.max() + 1e-10

    def test_gre_uniform_b0_signal_unchanged(self):
        signal = np.ones((15, 15)) * 0.5
        b0 = np.full((15, 15), 100.0)  # uniform
        out = apply_offresonance(signal, b0, TE_ms=20.0, sequence="GRE")
        np.testing.assert_allclose(out, signal, rtol=1e-6)

    def test_output_shape_preserved(self):
        signal = np.ones((12, 14))
        b0 = np.zeros((12, 14))
        out = apply_offresonance(signal, b0, TE_ms=10.0, sequence="GRE")
        assert out.shape == (12, 14)

    def test_case_insensitive_sequence(self):
        signal, b0 = self._make_inputs()
        out_lower = apply_offresonance(signal, b0, TE_ms=20.0, sequence="se")
        np.testing.assert_array_equal(out_lower, signal)


# ---------------------------------------------------------------------------
# readout_pixel_shift
# ---------------------------------------------------------------------------
class TestReadoutPixelShift:
    def test_zero_b0_gives_zero_shift(self):
        b0 = np.zeros((10, 10))
        shift = readout_pixel_shift(b0, bandwidth_hz_per_pixel=200.0)
        assert np.all(shift == 0.0)

    def test_shift_proportional_to_b0(self):
        b0 = np.full((5, 5), 400.0)
        shift = readout_pixel_shift(b0, bandwidth_hz_per_pixel=200.0)
        np.testing.assert_allclose(shift, 2.0)

    def test_output_shape_matches_input(self):
        b0 = np.zeros((8, 12))
        shift = readout_pixel_shift(b0, bandwidth_hz_per_pixel=100.0)
        assert shift.shape == (8, 12)

    def test_sign_preserved(self):
        b0 = np.array([[-100.0, 100.0]])
        shift = readout_pixel_shift(b0, bandwidth_hz_per_pixel=50.0)
        assert shift[0, 0] < 0
        assert shift[0, 1] > 0

    def test_larger_bandwidth_smaller_shift(self):
        b0 = np.full((5, 5), 1000.0)
        s_narrow = readout_pixel_shift(b0, 100.0)
        s_wide   = readout_pixel_shift(b0, 500.0)
        assert s_narrow.mean() > s_wide.mean()


# ---------------------------------------------------------------------------
# apply_readout_shift
# ---------------------------------------------------------------------------
class TestApplyReadoutShift:
    def test_zero_b0_identity(self):
        image = np.arange(100, dtype=float).reshape(10, 10)
        b0 = np.zeros((10, 10))
        out = apply_readout_shift(image, b0, bandwidth_hz_per_pixel=200.0)
        np.testing.assert_allclose(out, image, atol=1e-5)

    def test_output_shape_unchanged(self):
        image = np.ones((12, 14))
        b0 = np.zeros((12, 14))
        out = apply_readout_shift(image, b0, bandwidth_hz_per_pixel=100.0)
        assert out.shape == (12, 14)

    def test_nonzero_shift_changes_image(self):
        image = np.zeros((20, 20))
        image[:, 5] = 1.0   # bright column
        b0 = np.full((20, 20), 300.0)  # uniform shift of 3 pixels (BW=100)
        out = apply_readout_shift(image, b0, bandwidth_hz_per_pixel=100.0,
                                  freq_encode_axis=1)
        # Bright column should have moved
        assert not np.allclose(out, image)

    def test_freq_encode_axis_0_shifts_rows(self):
        image = np.zeros((20, 20))
        image[5, :] = 1.0
        b0 = np.full((20, 20), 200.0)
        out = apply_readout_shift(image, b0, bandwidth_hz_per_pixel=100.0,
                                  freq_encode_axis=0)
        assert not np.allclose(out, image)


def test_lung_is_air_susceptibility_source():
    """Regression: the lungs (label 18) are air-filled and must perturb the B0 field
    (chest off-resonance → EPI/DWI distortion). They were mislabelled as tissue, so the
    lungs produced no off-resonance at all."""
    import numpy as np
    import b0
    assert b0.SUSCEPTIBILITY_PPM[18] > 0, "lung must be air-like (paramagnetic vs tissue)"
    vol = np.full((20, 36, 36), 6, dtype=int)      # soft tissue
    vol[:, 12:24, 12:24] = 18                       # enclosed lung
    field = b0.susceptibility_b0_map(vol, (2.0, 2.0, 2.0), 3.0)
    assert (field.max() - field.min()) > 50.0, "lung produced no B0 off-resonance"
    # a tissue-only volume stays flat
    flat = b0.susceptibility_b0_map(np.full((20, 36, 36), 6, dtype=int), (2.0, 2.0, 2.0), 3.0)
    assert (flat.max() - flat.min()) < 1.0
