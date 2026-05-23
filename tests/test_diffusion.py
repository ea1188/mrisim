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


class TestDiffusionSignal:
    def test_b0_equals_s0(self):
        sig = diffusion_signal(1.0, b_value=0, ADC=0.8)
        assert sig == pytest.approx(1.0)

    def test_higher_b_lower_signal(self):
        sig_low = diffusion_signal(1.0, b_value=500, ADC=0.8)
        sig_high = diffusion_signal(1.0, b_value=1000, ADC=0.8)
        assert sig_low > sig_high

    def test_zero_adc_no_decay(self):
        sig = diffusion_signal(0.5, b_value=1000, ADC=0.0)
        assert sig == pytest.approx(0.5)

    def test_high_adc_more_decay(self):
        sig_low_adc = diffusion_signal(1.0, b_value=1000, ADC=0.7)
        sig_high_adc = diffusion_signal(1.0, b_value=1000, ADC=3.0)
        assert sig_high_adc < sig_low_adc

    def test_nonnegative(self):
        assert diffusion_signal(0.5, 1000, 0.8) >= 0


class TestCreateDiffusionTensor:
    def test_isotropic_when_fa_zero(self):
        tensor = create_diffusion_tensor(ADC=0.8, FA=0, orientation=[1, 0])
        expected = np.eye(2) * 0.8e-3
        np.testing.assert_allclose(tensor, expected)

    def test_symmetric(self):
        tensor = create_diffusion_tensor(ADC=0.7, FA=0.45, orientation=[1, 0])
        np.testing.assert_allclose(tensor, tensor.T, atol=1e-15)

    def test_trace_preserved(self):
        ADC = 0.7
        tensor = create_diffusion_tensor(ADC=ADC, FA=0.45, orientation=[1, 0])
        expected_trace = 2 * ADC * 1e-3
        np.testing.assert_allclose(np.trace(tensor), expected_trace, rtol=1e-5)

    def test_shape_2x2(self):
        tensor = create_diffusion_tensor(ADC=0.8, FA=0.3, orientation=[1, 0])
        assert tensor.shape == (2, 2)


class TestDiffusionTensorSignal:
    def test_returns_scalar(self):
        tensor = np.eye(2) * 0.8e-3
        sig = diffusion_tensor_signal(1.0, 1000, tensor, [1, 0])
        assert np.isscalar(sig) or sig.ndim == 0

    def test_b0_equals_s0(self):
        tensor = np.eye(2) * 0.8e-3
        sig = diffusion_tensor_signal(1.0, 0, tensor, [1, 0])
        assert sig == pytest.approx(1.0)

    def test_anisotropic_direction_dependence(self):
        tensor = create_diffusion_tensor(ADC=0.7, FA=0.6, orientation=[1, 0])
        sig_parallel = diffusion_tensor_signal(1.0, 1000, tensor, [1, 0])
        sig_perp = diffusion_tensor_signal(1.0, 1000, tensor, [0, 1])
        assert sig_parallel != sig_perp


class TestSimulateDiffusionImage:
    def test_output_shape(self, phantom64):
        img = simulate_diffusion_image(phantom64, TISSUE_PROPERTIES, b_value=1000)
        assert img.shape == phantom64.shape

    def test_nonnegative(self, phantom64):
        img = simulate_diffusion_image(phantom64, TISSUE_PROPERTIES, b_value=1000)
        assert np.all(img >= 0)

    def test_higher_b_lower_signal(self, phantom64):
        img_b0 = simulate_diffusion_image(phantom64, TISSUE_PROPERTIES, b_value=0)
        img_b1000 = simulate_diffusion_image(phantom64, TISSUE_PROPERTIES, b_value=1000)
        brain_mask = phantom64 > 0
        assert img_b0[brain_mask].mean() > img_b1000[brain_mask].mean()

    def test_csf_loses_more_signal_than_wm(self, phantom64):
        img_b0 = simulate_diffusion_image(phantom64, TISSUE_PROPERTIES, b_value=0)
        img_b1000 = simulate_diffusion_image(phantom64, TISSUE_PROPERTIES, b_value=1000)
        if np.any(phantom64 == 1) and np.any(phantom64 == 3):
            csf_ratio = img_b1000[phantom64 == 1].mean() / (img_b0[phantom64 == 1].mean() + 1e-9)
            wm_ratio = img_b1000[phantom64 == 3].mean() / (img_b0[phantom64 == 3].mean() + 1e-9)
            # CSF has higher ADC -> more signal loss at high b
            assert csf_ratio < wm_ratio


class TestComputeAdcMap:
    def test_output_shape(self, phantom64):
        adc = compute_adc_map(phantom64, TISSUE_PROPERTIES, b_value=1000)
        assert adc.shape == phantom64.shape

    def test_nonnegative(self, phantom64):
        adc = compute_adc_map(phantom64, TISSUE_PROPERTIES, b_value=1000)
        assert np.all(adc >= 0)

    def test_background_zero(self, phantom64):
        adc = compute_adc_map(phantom64, TISSUE_PROPERTIES, b_value=1000)
        assert np.all(adc[phantom64 == 0] == 0)

    def test_csf_high_adc(self, phantom64):
        adc = compute_adc_map(phantom64, TISSUE_PROPERTIES, b_value=1000)
        if np.any(phantom64 == 1) and np.any(phantom64 == 3):
            assert adc[phantom64 == 1].mean() > adc[phantom64 == 3].mean()


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
