import numpy as np
import pytest
from simulate import simulate_spin_echo, simulate_gradient_echo, add_noise
from phantom import create_brain_phantom, TISSUE_PROPERTIES


@pytest.fixture(scope="module")
def phantom64():
    return create_brain_phantom(64)


class TestSimulateSpinEcho:
    def test_output_shape(self, phantom64):
        img = simulate_spin_echo(phantom64, TR=500, TE=15)
        assert img.shape == phantom64.shape

    def test_nonnegative(self, phantom64):
        img = simulate_spin_echo(phantom64, TR=500, TE=15)
        assert np.all(img >= 0)

    def test_background_zero(self, phantom64):
        img = simulate_spin_echo(phantom64, TR=500, TE=15)
        bg = phantom64 == 0
        assert np.all(img[bg] == 0.0)

    def test_t1_contrast_wm_brighter_than_csf(self, phantom64):
        # Short TR, TE: WM has shorter T1 -> brighter (T1-weighted)
        img = simulate_spin_echo(phantom64, TR=500, TE=15)
        if np.any(phantom64 == 3) and np.any(phantom64 == 1):
            assert img[phantom64 == 3].mean() > img[phantom64 == 1].mean()

    def test_t2_contrast_csf_brighter_than_wm(self, phantom64):
        # Long TR and TE: CSF has very long T2 -> stays bright
        img = simulate_spin_echo(phantom64, TR=4000, TE=100)
        if np.any(phantom64 == 1) and np.any(phantom64 == 3):
            assert img[phantom64 == 1].mean() > img[phantom64 == 3].mean()

    def test_pd_weighted_csf_bright(self, phantom64):
        # True PD-weighting requires TR >> T1 for all tissues.  CSF T1=4500ms,
        # so we need TR >> 4500ms; use 50000ms to virtually eliminate T1 weighting.
        img = simulate_spin_echo(phantom64, TR=50000, TE=1)
        if np.any(phantom64 == 1) and np.any(phantom64 == 3):
            assert img[phantom64 == 1].mean() > img[phantom64 == 3].mean()


class TestSimulateGradientEcho:
    def test_output_shape(self, phantom64):
        img = simulate_gradient_echo(phantom64, TR=250, TE=5, flip_angle=70)
        assert img.shape == phantom64.shape

    def test_nonnegative(self, phantom64):
        img = simulate_gradient_echo(phantom64, TR=250, TE=5, flip_angle=70)
        assert np.all(img >= 0)

    def test_background_zero(self, phantom64):
        img = simulate_gradient_echo(phantom64, TR=250, TE=5, flip_angle=70)
        bg = phantom64 == 0
        assert np.all(img[bg] == 0.0)

    def test_zero_flip_all_zero(self, phantom64):
        img = simulate_gradient_echo(phantom64, TR=250, TE=5, flip_angle=0)
        assert np.allclose(img, 0.0)


class TestAddNoise:
    def test_output_shape(self, phantom64):
        img = simulate_spin_echo(phantom64, TR=500, TE=15)
        noisy = add_noise(img, snr_level=30)
        assert noisy.shape == img.shape

    def test_nonnegative(self, phantom64):
        img = simulate_spin_echo(phantom64, TR=500, TE=15)
        np.random.seed(42)
        noisy = add_noise(img, snr_level=30)
        assert np.all(noisy >= 0)

    def test_mean_close_to_original(self, phantom64):
        img = simulate_spin_echo(phantom64, TR=500, TE=15)
        brain = phantom64 > 0
        np.random.seed(0)
        noisy = add_noise(img, snr_level=100)  # high SNR
        # Mean of noisy brain should be close to mean of original
        assert abs(noisy[brain].mean() - img[brain].mean()) < 0.05

    def test_lower_snr_more_noise(self, phantom64):
        img = simulate_spin_echo(phantom64, TR=500, TE=15)
        np.random.seed(0)
        noisy_high = add_noise(img, snr_level=100)
        np.random.seed(0)
        noisy_low = add_noise(img, snr_level=5)
        # STD of residual should be larger with low SNR
        assert np.std(noisy_low - img) > np.std(noisy_high - img)
