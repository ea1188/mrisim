"""Tests for src/rician.py — Rician noise model."""

import numpy as np
import pytest
from rician import (
    rician_pdf,
    rician_mean,
    rician_variance,
    rician_snr_bias,
    add_rician_noise,
    add_rician_noise_seeded,
    estimate_snr_background,
    noise_sigma_from_snr,
    rician_bias_correction,
)


# ---------------------------------------------------------------------------
# TestRicianPdf
# ---------------------------------------------------------------------------
class TestRicianPdf:
    def test_nonneg_x_gives_nonneg_pdf(self):
        x = np.linspace(0., 5., 100)
        assert rician_pdf(x, nu=2., sigma=1.).min() >= 0.

    def test_negative_x_gives_zero(self):
        assert rician_pdf(-1., nu=2., sigma=1.) == pytest.approx(0.)

    def test_integrates_to_one(self):
        x = np.linspace(0., 20., 10000)
        pdf = rician_pdf(x, nu=3., sigma=1.)
        integral = np.trapezoid(pdf, x)
        assert integral == pytest.approx(1.0, abs=0.01)

    def test_mode_near_nu_for_high_snr(self):
        # For high SNR, the mode ≈ nu
        x = np.linspace(0., 10., 1000)
        pdf = rician_pdf(x, nu=5., sigma=0.5)
        mode_x = x[np.argmax(pdf)]
        assert abs(mode_x - 5.) < 0.2

    def test_rayleigh_at_nu_zero(self):
        # nu=0: Rician → Rayleigh; pdf = (x/σ²)*exp(-x²/(2σ²))
        sigma = 1.0
        x = np.array([0.5, 1.0, 1.5, 2.0])
        pdf_rician  = rician_pdf(x, nu=0., sigma=sigma)
        pdf_rayleigh = (x / sigma**2) * np.exp(-x**2 / (2 * sigma**2))
        np.testing.assert_allclose(pdf_rician, pdf_rayleigh, rtol=1e-5)

    def test_output_shape(self):
        x = np.ones((4, 5))
        assert rician_pdf(x, 2., 1.).shape == (4, 5)


# ---------------------------------------------------------------------------
# TestRicianMean
# ---------------------------------------------------------------------------
class TestRicianMean:
    def test_high_snr_approximation(self):
        # E[M] ≈ sqrt(ν² + σ²)
        nu, sigma = 10., 1.
        m = rician_mean(nu, sigma)
        assert m == pytest.approx(np.sqrt(nu**2 + sigma**2), rel=1e-6)

    def test_mean_ge_nu(self):
        # Rician mean is always ≥ nu (noise floor bias)
        nu = np.array([0., 1., 5., 10.])
        m = rician_mean(nu, sigma=1.)
        assert np.all(m >= nu)

    def test_zero_sigma_returns_nu(self):
        nu = np.array([0., 2., 5.])
        np.testing.assert_allclose(rician_mean(nu, sigma=0.), nu)

    def test_mean_increases_with_sigma(self):
        nu = 3.
        m1 = rician_mean(nu, 0.5)
        m2 = rician_mean(nu, 2.0)
        assert m2 > m1

    def test_output_scalar_for_scalar_inputs(self):
        assert np.isscalar(float(rician_mean(2., 1.)))


# ---------------------------------------------------------------------------
# TestRicianVariance
# ---------------------------------------------------------------------------
class TestRicianVariance:
    def test_nonneg(self):
        assert rician_variance(3., 1.) >= 0.

    def test_zero_at_zero_sigma(self):
        # No noise → no variance
        assert rician_variance(5., 0.) == pytest.approx(0., abs=1e-10)

    def test_increases_with_sigma(self):
        v1 = rician_variance(3., 0.5)
        v2 = rician_variance(3., 2.0)
        assert v2 > v1


# ---------------------------------------------------------------------------
# TestRicianSnrBias
# ---------------------------------------------------------------------------
class TestRicianSnrBias:
    def test_positive_bias(self):
        # Always positive (noise floor adds to signal)
        bias = rician_snr_bias(nu=5., sigma=1.)
        assert float(bias) > 0.

    def test_bias_decreases_at_high_snr(self):
        b_low  = float(rician_snr_bias(nu=2.,  sigma=1.))
        b_high = float(rician_snr_bias(nu=10., sigma=1.))
        assert b_high < b_low

    def test_zero_nu_gives_inf_bias(self):
        b = rician_snr_bias(nu=0., sigma=1.)
        assert not np.isfinite(b)

    def test_small_sigma_small_bias(self):
        b = float(rician_snr_bias(nu=10., sigma=0.01))
        assert b < 0.001


# ---------------------------------------------------------------------------
# TestAddRicianNoise
# ---------------------------------------------------------------------------
class TestAddRicianNoise:
    def test_output_shape(self):
        img = np.ones((10, 12))
        out = add_rician_noise(img, sigma=0.1)
        assert out.shape == (10, 12)

    def test_output_nonneg(self):
        img = np.ones((20, 20))
        out = add_rician_noise(img, sigma=0.5)
        assert out.min() >= 0.

    def test_zero_image_has_rayleigh_distribution(self):
        # Nu=0 → magnitude follows Rayleigh distribution; mean ≈ σ*sqrt(π/2)
        sigma = 1.0
        img = np.zeros((10000,))
        out = add_rician_noise_seeded(img, sigma=sigma, seed=42)
        expected_mean = sigma * np.sqrt(np.pi / 2.)
        assert out.mean() == pytest.approx(expected_mean, rel=0.05)

    def test_high_snr_mean_near_signal(self):
        signal = 10.0
        sigma = 0.1
        img = np.full((5000,), signal)
        out = add_rician_noise_seeded(img, sigma=sigma, seed=0)
        assert out.mean() == pytest.approx(signal, rel=0.02)

    def test_noisier_image_higher_std(self):
        img = np.ones((1000,)) * 5.
        out_low  = add_rician_noise_seeded(img, sigma=0.1, seed=1)
        out_high = add_rician_noise_seeded(img, sigma=2.0, seed=1)
        assert out_high.std() > out_low.std()


# ---------------------------------------------------------------------------
# TestAddRicianNoiseSeeded
# ---------------------------------------------------------------------------
class TestAddRicianNoiseSeeded:
    def test_reproducible(self):
        img = np.ones((10, 10))
        a = add_rician_noise_seeded(img, sigma=0.5, seed=7)
        b = add_rician_noise_seeded(img, sigma=0.5, seed=7)
        np.testing.assert_array_equal(a, b)

    def test_different_seeds_different_result(self):
        img = np.ones((10, 10))
        a = add_rician_noise_seeded(img, sigma=0.5, seed=1)
        b = add_rician_noise_seeded(img, sigma=0.5, seed=2)
        assert not np.allclose(a, b)

    def test_output_shape(self):
        img = np.zeros((5, 7))
        out = add_rician_noise_seeded(img, sigma=0.3, seed=0)
        assert out.shape == (5, 7)


# ---------------------------------------------------------------------------
# TestEstimateSnrBackground
# ---------------------------------------------------------------------------
class TestEstimateSnrBackground:
    def test_high_snr_image(self):
        img = np.ones((30, 30)) * 100.
        # Add tiny noise in corner
        img[:10, :10] = 1.0
        mask = np.ones((30, 30), dtype=bool)
        mask[:10, :10] = False
        bg = np.zeros((30, 30), dtype=bool)
        bg[:10, :10] = True
        snr = estimate_snr_background(img, mask, bg)
        assert snr > 10.

    def test_zero_background_gives_inf(self):
        img = np.ones((20, 20))
        signal_mask = np.ones((20, 20), dtype=bool)
        bg_mask = np.zeros((20, 20), dtype=bool)
        bg_mask[0, 0] = True
        img[0, 0] = 1.0   # same value → zero std
        snr = estimate_snr_background(img, signal_mask, bg_mask)
        assert not np.isfinite(snr)

    def test_default_background_corner(self):
        img = np.zeros((30, 30))
        img[15:, 15:] = 5.0
        signal_mask = np.zeros((30, 30), dtype=bool)
        signal_mask[15:, 15:] = True
        snr = estimate_snr_background(img, signal_mask)
        assert snr >= 0.


# ---------------------------------------------------------------------------
# TestNoiseSigmaFromSnr
# ---------------------------------------------------------------------------
class TestNoiseSigmaFromSnr:
    def test_basic_formula(self):
        sigma = noise_sigma_from_snr(signal_level=100., target_snr=10.)
        assert sigma == pytest.approx(10., rel=1e-6)

    def test_higher_snr_lower_sigma(self):
        s10 = noise_sigma_from_snr(100., 10.)
        s50 = noise_sigma_from_snr(100., 50.)
        assert s10 > s50

    def test_proportional_to_signal(self):
        s1 = noise_sigma_from_snr(50., 10.)
        s2 = noise_sigma_from_snr(100., 10.)
        assert s2 == pytest.approx(2 * s1, rel=1e-6)


# ---------------------------------------------------------------------------
# TestRicianBiasCorrection
# ---------------------------------------------------------------------------
class TestRicianBiasCorrection:
    def test_zero_signal_zero_output(self):
        img = np.zeros((5, 5))
        out = rician_bias_correction(img, sigma=1.)
        assert np.all(out == 0.)

    def test_large_signal_near_identity(self):
        signal = 100.
        sigma = 0.1
        img = np.full((5, 5), signal)
        out = rician_bias_correction(img, sigma)
        np.testing.assert_allclose(out, np.sqrt(signal**2 - sigma**2), rtol=1e-6)

    def test_output_nonneg(self):
        img = np.array([0.5, 1.0, 2.0, 5.0])
        out = rician_bias_correction(img, sigma=1.)
        assert out.min() >= 0.

    def test_removes_noise_floor_bias(self):
        # Background: magnitude mean ≈ σ√(π/2).  After correction:
        # sqrt((σ√(π/2))² − σ²) = σ√(π/2 − 1) ≈ 0.755σ < σ√(π/2) ≈ 1.253σ
        sigma = 1.0
        background = np.full((100,), sigma * np.sqrt(np.pi / 2.))
        corrected = rician_bias_correction(background, sigma)
        assert corrected.mean() < background.mean()

    def test_output_shape(self):
        img = np.ones((6, 7))
        assert rician_bias_correction(img, 0.1).shape == (6, 7)

    def test_correction_reduces_overestimation(self):
        # Rician mean > nu → correction brings it closer to nu
        nu = 3.
        sigma = 1.
        img = np.full((100,), rician_mean(nu, sigma))
        corrected = rician_bias_correction(img, sigma)
        assert abs(corrected.mean() - nu) < abs(img.mean() - nu)
