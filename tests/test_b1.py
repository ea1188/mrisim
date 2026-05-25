"""Tests for src/b1.py — B1+ transmit field inhomogeneity."""

import numpy as np
import pytest
from b1 import (
    gaussian_b1_map,
    sinusoidal_b1_map,
    uniform_b1_map,
    effective_flip_angle,
    apply_b1_to_gre,
    apply_b1_to_se,
    double_angle_b1_map,
    actual_flip_angle_b1_map,
    b1_uniformity,
)


# ---------------------------------------------------------------------------
# TestGaussianB1Map
# ---------------------------------------------------------------------------
class TestGaussianB1Map:
    def test_output_shape(self):
        b1 = gaussian_b1_map((20, 24))
        assert b1.shape == (20, 24)

    def test_peak_at_centre(self):
        b1 = gaussian_b1_map((21, 21), voxel_size=(1., 1.),
                              nominal=1.0, variation=0.2, fwhm_mm=50.)
        assert b1[10, 10] == b1.max()

    def test_centre_value_is_nominal(self):
        # With variation=0, map should be flat at nominal
        b1 = gaussian_b1_map((10, 10), variation=0.0, nominal=0.9)
        np.testing.assert_allclose(b1, 0.9, atol=1e-10)

    def test_periphery_less_than_centre(self):
        b1 = gaussian_b1_map((41, 41), voxel_size=(1., 1.),
                              nominal=1.0, variation=0.3, fwhm_mm=30.)
        assert b1[0, 0] < b1[20, 20]

    def test_output_dtype_float64(self):
        assert gaussian_b1_map((8, 8)).dtype == np.float64

    def test_all_values_positive(self):
        b1 = gaussian_b1_map((20, 20), nominal=1.0, variation=0.3)
        assert b1.min() > 0.


# ---------------------------------------------------------------------------
# TestSinusoidalB1Map
# ---------------------------------------------------------------------------
class TestSinusoidalB1Map:
    def test_output_shape(self):
        b1 = sinusoidal_b1_map((16, 24))
        assert b1.shape == (16, 24)

    def test_mean_equals_nominal(self):
        # Over an integer number of periods the mean should equal nominal
        b1 = sinusoidal_b1_map((10, 200), voxel_size=(1., 1.),
                                period_mm=100., nominal=1.0, amplitude=0.2)
        np.testing.assert_allclose(b1.mean(), 1.0, atol=0.02)

    def test_amplitude_controls_range(self):
        b1 = sinusoidal_b1_map((10, 100), voxel_size=(1., 1.),
                                period_mm=100., nominal=1.0, amplitude=0.3)
        assert b1.max() == pytest.approx(1.3, abs=0.02)
        assert b1.min() == pytest.approx(0.7, abs=0.02)

    def test_axis_0_varies_in_rows(self):
        b1 = sinusoidal_b1_map((100, 5), voxel_size=(1., 1.),
                                period_mm=50., axis=0, amplitude=0.2)
        assert b1[:, 0].std() > 0.
        np.testing.assert_allclose(b1[:, 0], b1[:, 4])

    def test_axis_1_varies_in_cols(self):
        b1 = sinusoidal_b1_map((5, 100), voxel_size=(1., 1.),
                                period_mm=50., axis=1, amplitude=0.2)
        assert b1[0, :].std() > 0.
        np.testing.assert_allclose(b1[0, :], b1[4, :])

    def test_output_dtype_float64(self):
        assert sinusoidal_b1_map((8, 8)).dtype == np.float64


# ---------------------------------------------------------------------------
# TestUniformB1Map
# ---------------------------------------------------------------------------
class TestUniformB1Map:
    def test_all_equal_to_value(self):
        b1 = uniform_b1_map((10, 10), value=0.85)
        np.testing.assert_allclose(b1, 0.85)

    def test_default_value_one(self):
        b1 = uniform_b1_map((5, 5))
        np.testing.assert_allclose(b1, 1.0)

    def test_output_shape(self):
        assert uniform_b1_map((7, 9)).shape == (7, 9)

    def test_output_dtype_float64(self):
        assert uniform_b1_map((4, 4)).dtype == np.float64


# ---------------------------------------------------------------------------
# TestEffectiveFlipAngle
# ---------------------------------------------------------------------------
class TestEffectiveFlipAngle:
    def test_uniform_b1_returns_nominal(self):
        b1 = uniform_b1_map((8, 8), value=1.0)
        efa = effective_flip_angle(90., b1)
        np.testing.assert_allclose(efa, 90.)

    def test_scales_linearly_with_b1(self):
        b1 = uniform_b1_map((5, 5), value=0.8)
        efa = effective_flip_angle(90., b1)
        np.testing.assert_allclose(efa, 72.)

    def test_output_shape_matches_b1_map(self):
        b1 = np.ones((10, 12))
        assert effective_flip_angle(30., b1).shape == (10, 12)

    def test_zero_b1_gives_zero_flip(self):
        b1 = np.zeros((4, 4))
        np.testing.assert_allclose(effective_flip_angle(90., b1), 0.)


# ---------------------------------------------------------------------------
# TestApplyB1ToGre
# ---------------------------------------------------------------------------
class TestApplyB1ToGre:
    _shape = (8, 8)
    _T1   = np.full(_shape, 1000.)
    _T2s  = np.full(_shape, 50.)
    _PD   = np.full(_shape, 0.8)

    def test_uniform_b1_matches_nominal_signal(self):
        from signal_engine import gradient_echo_signal
        b1  = uniform_b1_map(self._shape, 1.0)
        img = apply_b1_to_gre(None, b1, 30., self._T1, self._T2s, self._PD, 100., 5.)
        expected = gradient_echo_signal(1000., 50., 0.8, 100., 5., 30.)
        np.testing.assert_allclose(img, expected, rtol=1e-6)

    def test_b1_below_one_reduces_signal(self):
        b1_full = uniform_b1_map(self._shape, 1.0)
        b1_low  = uniform_b1_map(self._shape, 0.7)
        img_full = apply_b1_to_gre(None, b1_full, 30., self._T1, self._T2s, self._PD, 100., 5.)
        img_low  = apply_b1_to_gre(None, b1_low,  30., self._T1, self._T2s, self._PD, 100., 5.)
        assert img_low.mean() != img_full.mean()

    def test_background_zero(self):
        T1_bg = np.zeros(self._shape)
        b1 = uniform_b1_map(self._shape)
        img = apply_b1_to_gre(None, b1, 30., T1_bg, self._T2s, self._PD, 100., 5.)
        assert np.all(img == 0.)

    def test_output_shape(self):
        b1 = uniform_b1_map(self._shape)
        img = apply_b1_to_gre(None, b1, 30., self._T1, self._T2s, self._PD, 100., 5.)
        assert img.shape == self._shape

    def test_output_nonneg(self):
        b1 = gaussian_b1_map(self._shape)
        img = apply_b1_to_gre(None, b1, 30., self._T1, self._T2s, self._PD, 100., 5.)
        assert img.min() >= 0.


# ---------------------------------------------------------------------------
# TestApplyB1ToSe
# ---------------------------------------------------------------------------
class TestApplyB1ToSe:
    def test_uniform_b1_one_identity(self):
        signal = np.ones((8, 8)) * 0.5
        b1 = uniform_b1_map((8, 8), 1.0)
        out = apply_b1_to_se(signal, b1, 90.)
        np.testing.assert_allclose(out, signal, rtol=1e-6)

    def test_reduced_b1_reduces_signal(self):
        signal = np.ones((8, 8))
        b1 = uniform_b1_map((8, 8), 0.8)
        out = apply_b1_to_se(signal, b1, 90.)
        assert out.mean() < signal.mean()

    def test_output_shape(self):
        signal = np.ones((6, 7))
        b1 = uniform_b1_map((6, 7))
        assert apply_b1_to_se(signal, b1, 90.).shape == (6, 7)

    def test_output_nonneg(self):
        signal = np.abs(np.random.default_rng(0).standard_normal((10, 10)))
        b1 = gaussian_b1_map((10, 10))
        out = apply_b1_to_se(signal, b1, 90.)
        assert out.min() >= 0.


# ---------------------------------------------------------------------------
# TestDoubleAngleB1Map
# ---------------------------------------------------------------------------
class TestDoubleAngleB1Map:
    def _signals(self, b1_true, alpha_deg=60., T1=1000., T2s=50., PD=0.8,
                 TR=5000.):
        """Generate DA signals for a given true B1+ map."""
        from signal_engine import gradient_echo_signal
        alpha_eff  = b1_true * alpha_deg
        alpha2_eff = b1_true * 2. * alpha_deg
        s1 = np.vectorize(lambda a: gradient_echo_signal(T1, T2s, PD, TR, 5., a))(alpha_eff)
        s2 = np.vectorize(lambda a: gradient_echo_signal(T1, T2s, PD, TR, 5., a))(alpha2_eff)
        return s1, s2

    def test_uniform_b1_returns_one(self):
        b1_true = np.ones((5, 5))
        s1, s2 = self._signals(b1_true)
        b1_est = double_angle_b1_map(s1, s2)
        np.testing.assert_allclose(b1_est, 1.0, atol=0.02)

    def test_output_shape(self):
        s1 = np.ones((6, 7))
        s2 = np.ones((6, 7))
        assert double_angle_b1_map(s1, s2).shape == (6, 7)

    def test_reduced_b1_gives_value_below_one(self):
        b1_true = np.full((5, 5), 0.8)
        s1, s2 = self._signals(b1_true)
        b1_est = double_angle_b1_map(s1, s2)
        assert b1_est.mean() < 1.0


# ---------------------------------------------------------------------------
# TestActualFlipAngleB1Map
# ---------------------------------------------------------------------------
class TestActualFlipAngleB1Map:
    def test_output_shape(self):
        s1 = np.ones((6, 7))
        s2 = np.ones((6, 7))
        assert actual_flip_angle_b1_map(s1, s2, 20., 100.).shape == (6, 7)

    def test_uniform_inputs_finite_output(self):
        s1 = np.full((5, 5), 0.5)
        s2 = np.full((5, 5), 0.4)
        out = actual_flip_angle_b1_map(s1, s2, 20., 100.)
        assert np.all(np.isfinite(out))


# ---------------------------------------------------------------------------
# TestB1Uniformity
# ---------------------------------------------------------------------------
class TestB1Uniformity:
    def test_uniform_map_gives_zero(self):
        b1 = uniform_b1_map((10, 10), 1.0)
        assert b1_uniformity(b1) == pytest.approx(0., abs=1e-10)

    def test_variable_map_nonzero(self):
        b1 = gaussian_b1_map((20, 20), variation=0.3)
        assert b1_uniformity(b1) > 0.

    def test_mask_restricts_region(self):
        b1 = gaussian_b1_map((20, 20), variation=0.3)
        mask_centre = np.zeros((20, 20), dtype=bool)
        mask_centre[9:11, 9:11] = True
        cv_centre = b1_uniformity(b1, mask_centre)
        cv_full   = b1_uniformity(b1)
        # Centre patch is more uniform than whole image
        assert cv_centre <= cv_full

    def test_returns_scalar(self):
        b1 = uniform_b1_map((5, 5))
        assert isinstance(b1_uniformity(b1), float)


# ---------------------------------------------------------------------------
# Branch coverage additions
# ---------------------------------------------------------------------------
class TestGaussianB1MapWithCenter:
    def test_explicit_center_shifts_peak(self):
        """Providing center=(cy, cx) hits the cy, cx = center branch (line 48)."""
        b1_default = gaussian_b1_map((20, 20), variation=0.3)
        b1_shifted = gaussian_b1_map((20, 20), variation=0.3, center=(5., 5.))
        # Peak location should differ
        assert np.unravel_index(b1_default.argmax(), b1_default.shape) != \
               np.unravel_index(b1_shifted.argmax(), b1_shifted.shape)

    def test_center_tuple_output_shape(self):
        b1 = gaussian_b1_map((16, 16), center=(-3., 2.))
        assert b1.shape == (16, 16)


class TestB1UniformityNearZeroMean:
    def test_near_zero_mean_returns_zero(self):
        """A map with effectively zero mean hits the `return 0.` guard (line 269)."""
        b1 = np.zeros((10, 10))
        result = b1_uniformity(b1)
        assert result == pytest.approx(0., abs=1e-12)
