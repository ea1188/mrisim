"""Tests for diffusion.py — DWI signal, DTI tensors, parametric maps."""

import numpy as np
import pytest
from diffusion import (
    diffusion_signal,
    diffusion_tensor_signal,
    create_diffusion_tensor,
    simulate_diffusion_image,
    compute_adc_map,
    compute_fa_map,
    compute_direction_map,
    DIFFUSION_PROPERTIES,
)
from phantom import create_brain_phantom, TISSUE_PROPERTIES


@pytest.fixture(scope="module")
def phantom64():
    return create_brain_phantom(64)


@pytest.fixture
def fixed_rng():
    return np.random.default_rng(0)


# ---------------------------------------------------------------------------
# diffusion_signal
# ---------------------------------------------------------------------------

class TestDiffusionSignal:
    def test_b0_equals_s0(self):
        assert diffusion_signal(1.0, b_value=0, ADC=0.8) == pytest.approx(1.0)

    def test_higher_b_lower_signal(self):
        sig_low  = diffusion_signal(1.0, b_value=500,  ADC=0.8)
        sig_high = diffusion_signal(1.0, b_value=1000, ADC=0.8)
        assert sig_low > sig_high

    def test_zero_adc_no_decay(self):
        assert diffusion_signal(0.5, b_value=1000, ADC=0.0) == pytest.approx(0.5)

    def test_high_adc_more_decay(self):
        sig_low_adc  = diffusion_signal(1.0, b_value=1000, ADC=0.7)
        sig_high_adc = diffusion_signal(1.0, b_value=1000, ADC=3.0)
        assert sig_high_adc < sig_low_adc

    def test_nonnegative(self):
        assert diffusion_signal(0.5, 1000, 0.8) >= 0

    def test_returns_float(self):
        assert isinstance(diffusion_signal(1.0, 1000, 0.8), float)

    def test_formula(self):
        """S = S0 * exp(-b * ADC * 1e-3)."""
        S0, b, ADC = 0.8, 1000.0, 0.7
        expected = S0 * np.exp(-b * ADC * 1e-3)
        assert diffusion_signal(S0, b, ADC) == pytest.approx(expected)


# ---------------------------------------------------------------------------
# create_diffusion_tensor
# ---------------------------------------------------------------------------

class TestCreateDiffusionTensor:
    def test_isotropic_when_fa_zero(self):
        tensor = create_diffusion_tensor(ADC=0.8, FA=0, orientation=[1, 0])
        np.testing.assert_allclose(tensor, np.eye(2) * 0.8e-3)

    def test_symmetric(self):
        tensor = create_diffusion_tensor(ADC=0.7, FA=0.45, orientation=[1, 0])
        np.testing.assert_allclose(tensor, tensor.T, atol=1e-15)

    def test_trace_preserved(self):
        ADC = 0.7
        tensor = create_diffusion_tensor(ADC=ADC, FA=0.45, orientation=[1, 0])
        np.testing.assert_allclose(np.trace(tensor), 2 * ADC * 1e-3, rtol=1e-5)

    def test_shape_2x2(self):
        tensor = create_diffusion_tensor(ADC=0.8, FA=0.3, orientation=[1, 0])
        assert tensor.shape == (2, 2)

    def test_positive_definite(self):
        """All eigenvalues must be positive."""
        tensor = create_diffusion_tensor(ADC=0.7, FA=0.8, orientation=[1, 1])
        eigenvalues = np.linalg.eigvalsh(tensor)
        assert np.all(eigenvalues > 0)

    def test_orientation_matters(self):
        t0 = create_diffusion_tensor(0.7, 0.5, [1, 0])
        t45 = create_diffusion_tensor(0.7, 0.5, [1, 1])
        assert not np.allclose(t0, t45)

    def test_higher_fa_more_anisotropic(self):
        """Higher FA → larger λ₁/λ₂ ratio."""
        t_low  = create_diffusion_tensor(0.7, 0.2, [1, 0])
        t_high = create_diffusion_tensor(0.7, 0.8, [1, 0])
        ev_low  = sorted(np.linalg.eigvalsh(t_low))
        ev_high = sorted(np.linalg.eigvalsh(t_high))
        ratio_low  = ev_low[-1]  / ev_low[0]
        ratio_high = ev_high[-1] / ev_high[0]
        assert ratio_high > ratio_low


# ---------------------------------------------------------------------------
# diffusion_tensor_signal
# ---------------------------------------------------------------------------

class TestDiffusionTensorSignal:
    def test_returns_float(self):
        tensor = np.eye(2) * 0.8e-3
        sig = diffusion_tensor_signal(1.0, 1000, tensor, [1, 0])
        assert isinstance(sig, float)

    def test_b0_equals_s0(self):
        tensor = np.eye(2) * 0.8e-3
        assert diffusion_tensor_signal(1.0, 0, tensor, [1, 0]) == pytest.approx(1.0)

    def test_anisotropic_direction_dependence(self):
        tensor = create_diffusion_tensor(ADC=0.7, FA=0.6, orientation=[1, 0])
        sig_parallel = diffusion_tensor_signal(1.0, 1000, tensor, [1, 0])
        sig_perp     = diffusion_tensor_signal(1.0, 1000, tensor, [0, 1])
        assert sig_parallel != sig_perp

    def test_parallel_higher_diffusion(self):
        """Signal is lower along the principal diffusion direction (high D)."""
        tensor = create_diffusion_tensor(ADC=0.7, FA=0.6, orientation=[1, 0])
        sig_parallel = diffusion_tensor_signal(1.0, 1000, tensor, [1, 0])
        sig_perp     = diffusion_tensor_signal(1.0, 1000, tensor, [0, 1])
        # Higher D along [1,0] → more attenuation → lower signal
        assert sig_parallel < sig_perp

    def test_isotropic_tensor_matches_scalar(self):
        ADC = 0.8
        tensor = create_diffusion_tensor(ADC, 0.0, [1, 0])
        sig_tensor = diffusion_tensor_signal(1.0, 1000, tensor, [1, 0])
        sig_scalar = diffusion_signal(1.0, 1000, ADC)
        assert sig_tensor == pytest.approx(sig_scalar, rel=1e-5)

    def test_gradient_normalised_internally(self):
        """Gradient direction is normalised inside, so scale does not matter."""
        tensor = np.eye(2) * 0.8e-3
        sig1 = diffusion_tensor_signal(1.0, 1000, tensor, [1, 0])
        sig2 = diffusion_tensor_signal(1.0, 1000, tensor, [5, 0])
        assert sig1 == pytest.approx(sig2)


# ---------------------------------------------------------------------------
# simulate_diffusion_image
# ---------------------------------------------------------------------------

class TestSimulateDiffusionImage:
    def test_output_shape(self, phantom64):
        img = simulate_diffusion_image(phantom64, TISSUE_PROPERTIES, b_value=1000)
        assert img.shape == phantom64.shape

    def test_nonnegative(self, phantom64):
        img = simulate_diffusion_image(phantom64, TISSUE_PROPERTIES, b_value=1000)
        assert np.all(img >= 0)

    def test_higher_b_lower_signal(self, phantom64):
        img_b0    = simulate_diffusion_image(phantom64, TISSUE_PROPERTIES, b_value=0)
        img_b1000 = simulate_diffusion_image(phantom64, TISSUE_PROPERTIES, b_value=1000)
        brain_mask = phantom64 > 0
        assert img_b0[brain_mask].mean() > img_b1000[brain_mask].mean()

    def test_csf_loses_more_signal_than_wm(self, phantom64):
        img_b0    = simulate_diffusion_image(phantom64, TISSUE_PROPERTIES, b_value=0)
        img_b1000 = simulate_diffusion_image(phantom64, TISSUE_PROPERTIES, b_value=1000)
        if np.any(phantom64 == 1) and np.any(phantom64 == 3):
            csf_ratio = img_b1000[phantom64 == 1].mean() / (img_b0[phantom64 == 1].mean() + 1e-9)
            wm_ratio  = img_b1000[phantom64 == 3].mean() / (img_b0[phantom64 == 3].mean() + 1e-9)
            assert csf_ratio < wm_ratio

    def test_default_gradient_direction(self, phantom64):
        """Calling without gradient_direction should not raise."""
        img = simulate_diffusion_image(phantom64, TISSUE_PROPERTIES, b_value=500)
        assert img.shape == phantom64.shape

    def test_dtype_float64(self, phantom64):
        img = simulate_diffusion_image(phantom64, TISSUE_PROPERTIES, b_value=1000)
        assert img.dtype == np.float64

    def test_direction_dependence_wm(self, phantom64):
        """White-matter signal differs between perpendicular gradient directions."""
        img_x = simulate_diffusion_image(phantom64, TISSUE_PROPERTIES, 1000, [1, 0])
        img_y = simulate_diffusion_image(phantom64, TISSUE_PROPERTIES, 1000, [0, 1])
        if np.any(phantom64 == 3):
            assert not np.allclose(img_x[phantom64 == 3], img_y[phantom64 == 3])


# ---------------------------------------------------------------------------
# compute_adc_map
# ---------------------------------------------------------------------------

class TestComputeAdcMap:
    def test_output_shape(self, phantom64):
        adc = compute_adc_map(phantom64)
        assert adc.shape == phantom64.shape

    def test_nonnegative(self, phantom64):
        adc = compute_adc_map(phantom64)
        assert np.all(adc >= 0)

    def test_background_zero(self, phantom64):
        adc = compute_adc_map(phantom64)
        assert np.all(adc[phantom64 == 0] == 0)

    def test_csf_high_adc(self, phantom64):
        adc = compute_adc_map(phantom64)
        if np.any(phantom64 == 1) and np.any(phantom64 == 3):
            assert adc[phantom64 == 1].mean() > adc[phantom64 == 3].mean()

    def test_reproducible_with_rng(self, phantom64):
        adc1 = compute_adc_map(phantom64, rng=np.random.default_rng(42))
        adc2 = compute_adc_map(phantom64, rng=np.random.default_rng(42))
        np.testing.assert_array_equal(adc1, adc2)

    def test_different_seeds_differ(self, phantom64):
        adc1 = compute_adc_map(phantom64, rng=np.random.default_rng(1))
        adc2 = compute_adc_map(phantom64, rng=np.random.default_rng(2))
        brain_mask = phantom64 > 0
        assert not np.allclose(adc1[brain_mask], adc2[brain_mask])

    def test_within_reasonable_bounds(self, phantom64):
        """ADC values should stay within ±50 % of their tissue base values."""
        adc = compute_adc_map(phantom64, rng=np.random.default_rng(0))
        for label, props in DIFFUSION_PROPERTIES.items():
            mask = phantom64 == label
            if not np.any(mask) or props["ADC"] == 0:
                continue
            assert adc[mask].min() >= props["ADC"] * 0.5 - 1e-9
            assert adc[mask].max() <= props["ADC"] * 1.5 + 1e-9


# ---------------------------------------------------------------------------
# compute_fa_map
# ---------------------------------------------------------------------------

class TestComputeFaMap:
    def test_output_shape(self, phantom64):
        fa = compute_fa_map(phantom64)
        assert fa.shape == phantom64.shape

    def test_values_in_unit_interval(self, phantom64):
        fa = compute_fa_map(phantom64)
        assert fa.min() >= 0.0
        assert fa.max() <= 1.0

    def test_background_zero(self, phantom64):
        fa = compute_fa_map(phantom64)
        assert np.all(fa[phantom64 == 0] == 0)

    def test_wm_has_higher_fa_than_csf(self, phantom64):
        fa = compute_fa_map(phantom64)
        if np.any(phantom64 == 3) and np.any(phantom64 == 1):
            assert fa[phantom64 == 3].mean() > fa[phantom64 == 1].mean()

    def test_reproducible_with_rng(self, phantom64):
        fa1 = compute_fa_map(phantom64, rng=np.random.default_rng(7))
        fa2 = compute_fa_map(phantom64, rng=np.random.default_rng(7))
        np.testing.assert_array_equal(fa1, fa2)

    def test_different_seeds_differ(self, phantom64):
        fa1 = compute_fa_map(phantom64, rng=np.random.default_rng(1))
        fa2 = compute_fa_map(phantom64, rng=np.random.default_rng(2))
        if np.any(phantom64 == 3):
            assert not np.allclose(fa1[phantom64 == 3], fa2[phantom64 == 3])

    def test_dtype_float64(self, phantom64):
        fa = compute_fa_map(phantom64)
        assert fa.dtype == np.float64


# ---------------------------------------------------------------------------
# compute_direction_map
# ---------------------------------------------------------------------------

class TestComputeDirectionMap:
    def test_output_shape(self, phantom64):
        dm = compute_direction_map(phantom64)
        assert dm.shape == (64, 64, 3)

    def test_values_in_unit_interval(self, phantom64):
        dm = compute_direction_map(phantom64)
        assert dm.min() >= 0.0
        assert dm.max() <= 1.0

    def test_background_zero(self, phantom64):
        dm = compute_direction_map(phantom64)
        assert np.all(dm[phantom64 == 0] == 0)

    def test_reproducible_with_rng(self, phantom64):
        dm1 = compute_direction_map(phantom64, rng=np.random.default_rng(3))
        dm2 = compute_direction_map(phantom64, rng=np.random.default_rng(3))
        np.testing.assert_array_equal(dm1, dm2)

    def test_dtype_float64(self, phantom64):
        dm = compute_direction_map(phantom64)
        assert dm.dtype == np.float64


# ---------------------------------------------------------------------------
# Branch coverage additions
# ---------------------------------------------------------------------------
class TestCreateDiffusionTensorExtremeFa:
    def test_fa_above_sqrt2_denom_guard(self):
        """FA > √2 makes denom ≤ 0, triggering the denom=1e-9 guard (line 111).
        The result must still be a valid 2×2 positive-semidefinite matrix."""
        tensor = create_diffusion_tensor(ADC=0.7, FA=1.5, orientation=[1., 0.])
        assert tensor.shape == (2, 2)
        eigenvalues = np.linalg.eigvalsh(tensor)
        assert np.all(eigenvalues >= -1e-10)  # PSD up to floating-point noise

    def test_fa_above_one_lambda2_guard(self):
        """FA slightly > 1 (unphysical but defensively handled) produces lambda2 < 0,
        triggering the lambda2 = 0.01e-3 clamp (lines 117-118)."""
        tensor = create_diffusion_tensor(ADC=0.7, FA=1.1, orientation=[1., 0.])
        assert tensor.shape == (2, 2)
        # trace should be positive
        assert np.trace(tensor) > 0


class TestSimulateDiffusionImageSparsePhantom:
    def test_continue_for_absent_label(self):
        """Phantom with a gap in labels forces the `continue` branch (line 168)."""
        # Labels 0,2,3 are present; label 1 is missing → the label-1 loop iteration
        # hits `not np.any(mask)` → continue
        ph = np.zeros((10, 10), dtype=int)
        ph[3:7, 3:7] = 2  # gray matter only
        ph[0, 0] = 3      # white matter corner
        img = simulate_diffusion_image(ph, TISSUE_PROPERTIES, b_value=1000, TR=8000, TE=80)
        assert img.shape == (10, 10)
        assert np.all(img >= 0)
