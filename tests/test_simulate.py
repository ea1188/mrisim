import matplotlib
matplotlib.use('Agg')
import numpy as np
import pytest
from simulate import simulate_spin_echo, simulate_gradient_echo, add_noise, display_image
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
        noisy = add_noise(img, snr_level=30, rng=np.random.default_rng(42))
        assert np.all(noisy >= 0)

    def test_mean_close_to_original(self, phantom64):
        img = simulate_spin_echo(phantom64, TR=500, TE=15)
        brain = phantom64 > 0
        noisy = add_noise(img, snr_level=100, rng=np.random.default_rng(0))
        # Mean of noisy brain should be close to mean of original
        assert abs(noisy[brain].mean() - img[brain].mean()) < 0.05

    def test_lower_snr_more_noise(self, phantom64):
        img = simulate_spin_echo(phantom64, TR=500, TE=15)
        noisy_high = add_noise(img, snr_level=100, rng=np.random.default_rng(0))
        noisy_low  = add_noise(img, snr_level=5,   rng=np.random.default_rng(0))
        # STD of residual should be larger with low SNR
        assert np.std(noisy_low - img) > np.std(noisy_high - img)

    def test_noise_changes_image(self, phantom64):
        img = simulate_spin_echo(phantom64, TR=500, TE=15)
        noisy = add_noise(img, snr_level=10, rng=np.random.default_rng(1))
        assert not np.allclose(noisy, img)

    def test_dtype_float64(self, phantom64):
        img = simulate_spin_echo(phantom64, TR=500, TE=15)
        noisy = add_noise(img, snr_level=30)
        assert noisy.dtype == np.float64


class TestSimulatePhysics:
    """Cross-function contrast checks."""

    def test_longer_te_lower_se_signal(self, phantom64):
        """Longer TE always reduces SE signal (T2 decay)."""
        img_short = simulate_spin_echo(phantom64, TR=4000, TE=20)
        img_long  = simulate_spin_echo(phantom64, TR=4000, TE=120)
        brain = phantom64 > 0
        assert img_short[brain].mean() > img_long[brain].mean()

    def test_gre_dtype_float64(self, phantom64):
        img = simulate_gradient_echo(phantom64, TR=50, TE=5, flip_angle=15)
        assert img.dtype == np.float64

    def test_se_dtype_float64(self, phantom64):
        img = simulate_spin_echo(phantom64, TR=500, TE=15)
        assert img.dtype == np.float64

    def test_gre_short_tr_suppresses_long_t1(self, phantom64):
        """Short TR saturates long-T1 tissue (CSF) more than short-T1 tissue."""
        img = simulate_gradient_echo(phantom64, TR=50, TE=5, flip_angle=70)
        if np.any(phantom64 == 1) and np.any(phantom64 == 3):
            # WM (T1~830ms) less saturated than CSF (T1~4500ms)
            assert img[phantom64 == 3].mean() > img[phantom64 == 1].mean()

    def test_gre_long_tr_approaches_se(self, phantom64):
        """For very long TR, GRE signal pattern approaches SE ordering."""
        img_gre = simulate_gradient_echo(phantom64, TR=10000, TE=10, flip_angle=90)
        img_se  = simulate_spin_echo(phantom64, TR=10000, TE=10)
        brain = phantom64 > 0
        # Both should be mostly PD-weighted — same tissue ordering
        if np.any(phantom64 == 1) and np.any(phantom64 == 3):
            gre_csf_wm = img_gre[phantom64 == 1].mean() / (img_gre[phantom64 == 3].mean() + 1e-9)
            se_csf_wm  = img_se[phantom64 == 1].mean()  / (img_se[phantom64 == 3].mean()  + 1e-9)
            # Both ratios should be > 1 (CSF brighter in PD-weighted)
            assert gre_csf_wm > 1.0
            assert se_csf_wm  > 1.0


# ---------------------------------------------------------------------------
# Branch coverage additions
# ---------------------------------------------------------------------------
class TestDisplayImage:
    def test_display_without_save_path(self, monkeypatch, tmp_path, phantom64):
        """display_image with save_path=None covers lines 42-46, 50."""
        import matplotlib.pyplot as plt
        monkeypatch.setattr(plt, "show", lambda: None)
        img = simulate_spin_echo(phantom64, TR=500, TE=15)
        display_image(img, title="Test")  # no exception → lines 42-46, 50 covered

    def test_display_with_save_path(self, monkeypatch, tmp_path, phantom64):
        """display_image with a save_path covers the if-branch (lines 47-49)."""
        import matplotlib.pyplot as plt
        monkeypatch.setattr(plt, "show", lambda: None)
        img = simulate_spin_echo(phantom64, TR=500, TE=15)
        out = str(tmp_path / "mri_out.png")
        display_image(img, title="Saved", save_path=out)
        import os
        assert os.path.exists(out)
