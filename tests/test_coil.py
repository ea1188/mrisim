"""Tests for receive coil sensitivity maps (src/coil.py)."""

import numpy as np
import pytest

from coil import (
    biot_savart_sensitivity,
    gaussian_sensitivity,
    cylindrical_array,
    head_coil_array,
    apply_coil_sensitivities,
    combine_sos,
    combine_sense,
    coil_snr_weights,
    snr_map,
    g_factor_map,
    coil_uniformity,
    estimate_sensitivity,
)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

SHAPE = (32, 32)


@pytest.fixture
def single_map():
    return biot_savart_sensitivity(SHAPE, coil_center=(16, 0), coil_radius_mm=10.)


@pytest.fixture
def four_coil_maps():
    return cylindrical_array(SHAPE, n_coils=4, radius_mm=20.)


@pytest.fixture
def uniform_image():
    return np.ones(SHAPE, dtype=np.float64)


# ---------------------------------------------------------------------------
# biot_savart_sensitivity
# ---------------------------------------------------------------------------

class TestBiotSavartSensitivity:

    def test_shape(self):
        s = biot_savart_sensitivity(SHAPE, (16, 0), 10.)
        assert s.shape == SHAPE

    def test_dtype(self):
        s = biot_savart_sensitivity(SHAPE, (16, 0), 10.)
        assert s.dtype == np.float64

    def test_peak_is_one_by_default(self):
        s = biot_savart_sensitivity(SHAPE, (16, 0), 10.)
        np.testing.assert_allclose(s.max(), 1.0, atol=1e-10)

    def test_custom_peak(self):
        s = biot_savart_sensitivity(SHAPE, (16, 0), 10., peak=0.5)
        np.testing.assert_allclose(s.max(), 0.5, atol=1e-10)

    def test_nonnegative(self):
        s = biot_savart_sensitivity(SHAPE, (16, 0), 10.)
        assert np.all(s >= 0)

    def test_falls_off_with_distance(self):
        center = (16, 0)
        s = biot_savart_sensitivity(SHAPE, center, 10.)
        near = s[16, 2]
        far  = s[16, 20]
        assert near > far

    def test_sensitivity_at_infinity_approaches_zero(self):
        s = biot_savart_sensitivity((100, 100), (50, 50), 5.)
        # Far corner from centre
        assert s[0, 0] < 0.05

    def test_voxel_size_affects_falloff(self):
        # Larger voxels → faster mm-distance → steeper falloff
        s1 = biot_savart_sensitivity(SHAPE, (16, 0), 10., voxel_size_mm=(1., 1.))
        s2 = biot_savart_sensitivity(SHAPE, (16, 0), 10., voxel_size_mm=(2., 2.))
        # At the same pixel position, s2 puts more mm between pixels → lower
        assert s2[16, 10] < s1[16, 10]


# ---------------------------------------------------------------------------
# gaussian_sensitivity
# ---------------------------------------------------------------------------

class TestGaussianSensitivity:

    def test_shape(self):
        s = gaussian_sensitivity(SHAPE, (16, 16), 20.)
        assert s.shape == SHAPE

    def test_dtype(self):
        s = gaussian_sensitivity(SHAPE, (16, 16), 20.)
        assert s.dtype == np.float64

    def test_peak_at_center(self):
        s = gaussian_sensitivity(SHAPE, (16, 16), 20., peak=2.)
        assert s[16, 16] == pytest.approx(2.0)

    def test_symmetry(self):
        s = gaussian_sensitivity(SHAPE, (16, 16), 10.)
        np.testing.assert_allclose(s[14, 16], s[18, 16], rtol=1e-6)
        np.testing.assert_allclose(s[16, 14], s[16, 18], rtol=1e-6)

    def test_nonnegative(self):
        s = gaussian_sensitivity(SHAPE, (16, 16), 10.)
        assert np.all(s >= 0)

    def test_wider_sigma_more_uniform(self):
        s_narrow = gaussian_sensitivity(SHAPE, (16, 16), 3.)
        s_wide   = gaussian_sensitivity(SHAPE, (16, 16), 30.)
        # Wide profile has higher CV (more uniform) — less std/mean variation
        assert s_wide.std() < s_narrow.std()


# ---------------------------------------------------------------------------
# cylindrical_array
# ---------------------------------------------------------------------------

class TestCylindricalArray:

    def test_shape(self, four_coil_maps):
        assert four_coil_maps.shape == (4, *SHAPE)

    def test_dtype(self, four_coil_maps):
        assert four_coil_maps.dtype == np.float64

    def test_nonnegative(self, four_coil_maps):
        assert np.all(four_coil_maps >= 0)

    def test_n_coils_parameter(self):
        maps = cylindrical_array(SHAPE, n_coils=8, radius_mm=20.)
        assert maps.shape[0] == 8

    def test_each_coil_peaks_at_one(self, four_coil_maps):
        for i in range(four_coil_maps.shape[0]):
            assert four_coil_maps[i].max() == pytest.approx(1.0, abs=1e-10)

    def test_coils_are_not_identical(self, four_coil_maps):
        assert not np.allclose(four_coil_maps[0], four_coil_maps[1])

    def test_rotational_symmetry(self):
        """For 4 coils, coil 0 and coil 2 should be mirror-symmetric."""
        maps = cylindrical_array(SHAPE, n_coils=4, radius_mm=20.)
        # Coil 2 is opposite coil 0 — their sum should be symmetric
        combined = maps[0] + maps[2]
        np.testing.assert_allclose(combined, combined[::-1, ::-1], atol=0.05)


# ---------------------------------------------------------------------------
# head_coil_array
# ---------------------------------------------------------------------------

class TestHeadCoilArray:

    def test_shape(self):
        maps = head_coil_array(SHAPE, n_coils=8)
        assert maps.shape == (8, *SHAPE)

    def test_dtype(self):
        maps = head_coil_array(SHAPE, n_coils=8)
        assert maps.dtype == np.float64

    def test_nonnegative(self):
        maps = head_coil_array(SHAPE, n_coils=8)
        assert np.all(maps >= 0)

    def test_configurable_n_coils(self):
        for n in (4, 8, 16):
            maps = head_coil_array(SHAPE, n_coils=n)
            assert maps.shape[0] == n


# ---------------------------------------------------------------------------
# apply_coil_sensitivities
# ---------------------------------------------------------------------------

class TestApplyCoilSensitivities:

    def test_shape(self, four_coil_maps, uniform_image):
        ci = apply_coil_sensitivities(uniform_image, four_coil_maps)
        assert ci.shape == (4, *SHAPE)

    def test_dtype(self, four_coil_maps, uniform_image):
        ci = apply_coil_sensitivities(uniform_image, four_coil_maps)
        assert ci.dtype == np.float64

    def test_uniform_image_equals_sensitivity(self, four_coil_maps, uniform_image):
        ci = apply_coil_sensitivities(uniform_image, four_coil_maps)
        np.testing.assert_allclose(ci, four_coil_maps)

    def test_scaled_image(self, four_coil_maps):
        img = np.full(SHAPE, 3.0)
        ci  = apply_coil_sensitivities(img, four_coil_maps)
        np.testing.assert_allclose(ci, four_coil_maps * 3.0)

    def test_shape_mismatch_raises(self, four_coil_maps):
        wrong = np.ones((16, 16))
        with pytest.raises(ValueError, match="shape"):
            apply_coil_sensitivities(wrong, four_coil_maps)

    def test_zero_image_gives_zero_coil_images(self, four_coil_maps):
        ci = apply_coil_sensitivities(np.zeros(SHAPE), four_coil_maps)
        assert np.all(ci == 0)


# ---------------------------------------------------------------------------
# combine_sos
# ---------------------------------------------------------------------------

class TestCombineSos:

    def test_shape(self, four_coil_maps, uniform_image):
        ci  = apply_coil_sensitivities(uniform_image, four_coil_maps)
        sos = combine_sos(ci)
        assert sos.shape == SHAPE

    def test_dtype(self, four_coil_maps, uniform_image):
        ci  = apply_coil_sensitivities(uniform_image, four_coil_maps)
        sos = combine_sos(ci)
        assert sos.dtype == np.float64

    def test_nonnegative(self, four_coil_maps, uniform_image):
        ci  = apply_coil_sensitivities(uniform_image, four_coil_maps)
        sos = combine_sos(ci)
        assert np.all(sos >= 0)

    def test_single_coil_equals_magnitude(self):
        img = np.random.default_rng(0).random(SHAPE)
        ci  = img[np.newaxis, :, :]
        np.testing.assert_allclose(combine_sos(ci), img)

    def test_orthogonal_coils_pythagorean(self):
        ci = np.zeros((2, 4, 4))
        ci[0, :, :] = 3.0
        ci[1, :, :] = 4.0
        np.testing.assert_allclose(combine_sos(ci), 5.0)

    def test_complex_input(self):
        ci = np.ones((2, 4, 4), dtype=complex) * (1 + 1j)
        sos = combine_sos(ci)
        # |1+i|² = 2, so SoS = sqrt(2+2) = 2
        np.testing.assert_allclose(sos, 2.0, atol=1e-10)


# ---------------------------------------------------------------------------
# combine_sense
# ---------------------------------------------------------------------------

class TestCombineSense:

    def test_shape(self, four_coil_maps, uniform_image):
        ci  = apply_coil_sensitivities(uniform_image, four_coil_maps)
        out = combine_sense(ci, four_coil_maps)
        assert out.shape == SHAPE

    def test_dtype(self, four_coil_maps, uniform_image):
        ci  = apply_coil_sensitivities(uniform_image, four_coil_maps)
        out = combine_sense(ci, four_coil_maps)
        assert out.dtype == np.float64

    def test_uniform_image_reconstructed(self, four_coil_maps):
        """SENSE combination of C_i = S_i × 1 should recover ~1 everywhere."""
        ci  = apply_coil_sensitivities(np.ones(SHAPE), four_coil_maps)
        out = combine_sense(ci, four_coil_maps)
        # Where SoS > 0.1 the reconstruction should be close to 1
        sos = combine_sos(four_coil_maps)
        mask = sos > 0.1
        np.testing.assert_allclose(out[mask], 1.0, atol=1e-6)

    def test_scaled_image_reconstructed(self, four_coil_maps):
        img = np.full(SHAPE, 2.5)
        ci  = apply_coil_sensitivities(img, four_coil_maps)
        out = combine_sense(ci, four_coil_maps)
        sos = combine_sos(four_coil_maps)
        mask = sos > 0.1
        np.testing.assert_allclose(out[mask], 2.5, atol=1e-6)

    def test_with_noise_cov(self, four_coil_maps, uniform_image):
        ci  = apply_coil_sensitivities(uniform_image, four_coil_maps)
        psi = np.eye(4) * 2.0
        out = combine_sense(ci, four_coil_maps, noise_cov=psi)
        sos = combine_sos(four_coil_maps)
        mask = sos > 0.1
        np.testing.assert_allclose(out[mask], 1.0, atol=1e-6)

    def test_nonnegative(self, four_coil_maps, uniform_image):
        ci  = apply_coil_sensitivities(uniform_image, four_coil_maps)
        out = combine_sense(ci, four_coil_maps)
        assert np.all(out >= 0)


# ---------------------------------------------------------------------------
# coil_snr_weights
# ---------------------------------------------------------------------------

class TestCoilSnrWeights:

    def test_shape(self, four_coil_maps):
        w = coil_snr_weights(four_coil_maps)
        assert w.shape == (4, *SHAPE)

    def test_reconstruction_equals_combine_sense(self, four_coil_maps):
        """Applying SNR weights should reproduce combine_sense output."""
        img = np.random.default_rng(1).random(SHAPE)
        ci  = apply_coil_sensitivities(img, four_coil_maps)
        w   = coil_snr_weights(four_coil_maps)
        reconstructed = np.abs(np.sum(w * ci, axis=0))
        reference = combine_sense(ci, four_coil_maps)
        sos = combine_sos(four_coil_maps)
        mask = sos > 0.1
        np.testing.assert_allclose(reconstructed[mask], reference[mask], atol=1e-10)


# ---------------------------------------------------------------------------
# snr_map
# ---------------------------------------------------------------------------

class TestSnrMap:

    def test_shape(self, four_coil_maps):
        assert snr_map(four_coil_maps).shape == SHAPE

    def test_dtype(self, four_coil_maps):
        assert snr_map(four_coil_maps).dtype == np.float64

    def test_nonnegative(self, four_coil_maps):
        assert np.all(snr_map(four_coil_maps) >= 0)

    def test_scales_inversely_with_sigma(self, four_coil_maps):
        s1 = snr_map(four_coil_maps, noise_sigma=1.0)
        s2 = snr_map(four_coil_maps, noise_sigma=2.0)
        np.testing.assert_allclose(s1, s2 * 2.0, rtol=1e-10)

    def test_equals_sos_divided_by_sigma(self, four_coil_maps):
        sos = combine_sos(four_coil_maps)
        snr = snr_map(four_coil_maps, noise_sigma=1.0)
        np.testing.assert_allclose(snr, sos, rtol=1e-10)

    def test_more_coils_higher_snr(self):
        maps4 = cylindrical_array(SHAPE, n_coils=4, radius_mm=20.)
        maps8 = cylindrical_array(SHAPE, n_coils=8, radius_mm=20.)
        assert snr_map(maps8).mean() > snr_map(maps4).mean()


# ---------------------------------------------------------------------------
# g_factor_map
# ---------------------------------------------------------------------------

class TestGFactorMap:

    def test_shape(self, four_coil_maps):
        g = g_factor_map(four_coil_maps, acceleration=2)
        assert g.shape == SHAPE

    def test_dtype(self, four_coil_maps):
        g = g_factor_map(four_coil_maps, acceleration=2)
        assert g.dtype == np.float64

    def test_g_ge_one(self, four_coil_maps):
        g = g_factor_map(four_coil_maps, acceleration=2)
        assert np.all(g >= 1.0 - 1e-10)

    def test_acceleration_1_gives_g_one(self, four_coil_maps):
        g = g_factor_map(four_coil_maps, acceleration=1)
        np.testing.assert_allclose(g, 1.0, atol=1e-6)

    def test_invalid_acceleration_raises(self, four_coil_maps):
        with pytest.raises(ValueError, match="acceleration"):
            g_factor_map(four_coil_maps, acceleration=0)

    def test_rows_not_divisible_raises(self):
        maps = cylindrical_array((33, 32), n_coils=4, radius_mm=20.)
        with pytest.raises(ValueError, match="divisible"):
            g_factor_map(maps, acceleration=4)

    def test_higher_acceleration_higher_g(self, four_coil_maps):
        g2 = g_factor_map(four_coil_maps, acceleration=2)
        g4 = g_factor_map(four_coil_maps, acceleration=4)
        # Mean g should be higher for R=4 than R=2
        assert g4.mean() >= g2.mean()

    def test_with_noise_cov(self, four_coil_maps):
        psi = np.eye(4) * 2.0
        g = g_factor_map(four_coil_maps, acceleration=2, noise_cov=psi)
        assert g.shape == SHAPE
        assert np.all(g >= 1.0 - 1e-10)


# ---------------------------------------------------------------------------
# coil_uniformity
# ---------------------------------------------------------------------------

class TestCoilUniformity:

    def test_perfectly_uniform_array_low_cv(self):
        maps = np.ones((4, *SHAPE))
        cv = coil_uniformity(maps)
        assert cv == pytest.approx(0.0, abs=1e-10)

    def test_nonuniform_array_nonzero_cv(self, four_coil_maps):
        cv = coil_uniformity(four_coil_maps)
        assert cv > 0

    def test_mask_restricts_region(self, four_coil_maps):
        mask_all    = np.ones(SHAPE, dtype=bool)
        mask_centre = np.zeros(SHAPE, dtype=bool)
        mask_centre[12:20, 12:20] = True
        cv_all    = coil_uniformity(four_coil_maps, mask=mask_all)
        cv_centre = coil_uniformity(four_coil_maps, mask=mask_centre)
        # Centre is more uniform (closer to coil centres)
        assert cv_centre <= cv_all + 0.05

    def test_returns_float(self, four_coil_maps):
        assert isinstance(coil_uniformity(four_coil_maps), float)


# ---------------------------------------------------------------------------
# estimate_sensitivity
# ---------------------------------------------------------------------------

class TestEstimateSensitivity:

    def test_shape(self, four_coil_maps, uniform_image):
        ci   = apply_coil_sensitivities(uniform_image, four_coil_maps)
        est  = estimate_sensitivity(ci)
        assert est.shape == (4, *SHAPE)

    def test_dtype(self, four_coil_maps, uniform_image):
        ci  = apply_coil_sensitivities(uniform_image, four_coil_maps)
        est = estimate_sensitivity(ci)
        assert est.dtype == np.float64

    def test_nonnegative(self, four_coil_maps, uniform_image):
        ci  = apply_coil_sensitivities(uniform_image, four_coil_maps)
        est = estimate_sensitivity(ci)
        assert np.all(est >= 0)

    def test_rough_agreement_with_true_maps(self, four_coil_maps):
        """Estimated sensitivities should roughly match true maps."""
        img = np.ones(SHAPE) * 100.
        ci  = apply_coil_sensitivities(img, four_coil_maps)
        est = estimate_sensitivity(ci, smooth_sigma=3.0)
        # Sum-of-squares of estimated and true maps should be correlated
        sos_true = combine_sos(four_coil_maps)
        sos_est  = combine_sos(est)
        sos_est_norm = sos_est / (sos_est.max() + 1e-12)
        sos_true_norm = sos_true / (sos_true.max() + 1e-12)
        corr = np.corrcoef(sos_true_norm.ravel(), sos_est_norm.ravel())[0, 1]
        assert corr > 0.9

    def test_smoothing_sigma_zero_no_crash(self, four_coil_maps, uniform_image):
        ci  = apply_coil_sensitivities(uniform_image, four_coil_maps)
        est = estimate_sensitivity(ci, smooth_sigma=0.0)
        assert est.shape == (4, *SHAPE)


# ---------------------------------------------------------------------------
# Branch coverage additions
# ---------------------------------------------------------------------------
class TestCoilSnrWeightsWithNoiseCov:
    def test_noise_cov_argument_accepted(self):
        """Providing noise_cov triggers the linalg.inv branch (line 334)."""
        from coil import coil_snr_weights, gaussian_sensitivity
        sm = np.stack([gaussian_sensitivity((16, 16), (8., 8.), sigma_mm=6.)
                       for _ in range(3)])  # (3, 16, 16)
        n_coils = sm.shape[0]
        psi = np.eye(n_coils, dtype=complex) * 0.5
        w = coil_snr_weights(sm, noise_cov=psi)
        assert w.shape == sm.shape

    def test_noise_cov_weights_differ_from_default(self):
        from coil import coil_snr_weights, gaussian_sensitivity
        # Two coils at opposite sides — different sensitivity maps
        sm = np.stack([
            gaussian_sensitivity((12, 12), (2., 6.), sigma_mm=3.),
            gaussian_sensitivity((12, 12), (10., 6.), sigma_mm=3.),
        ])
        w_default = coil_snr_weights(sm)
        # Strong cross-correlation in noise cov changes the optimal combination
        psi = np.array([[1., 0.9], [0.9, 1.]], dtype=complex)
        w_corr = coil_snr_weights(sm, noise_cov=psi)
        assert not np.allclose(w_default, w_corr)


class TestCoilUniformityZeroReturn:
    def test_zero_sensitivity_returns_zero(self):
        """All-zero sensitivity maps → mean=0 → return 0.0 guard (line 464)."""
        from coil import coil_uniformity
        sm_zero = np.zeros((2, 8, 8))
        result = coil_uniformity(sm_zero)
        assert result == pytest.approx(0., abs=1e-12)
