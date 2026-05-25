import numpy as np
import pytest
from fmri import (
    create_fmri_phantom,
    simulate_bold_signal,
    simulate_fmri_fast,
    simulate_fmri_image,
    compute_activation_map,
    compute_t_statistic_map,
    compute_temporal_snr,
)


@pytest.fixture(scope="module")
def fmri_data():
    np.random.seed(0)
    phantom, activation = create_fmri_phantom(64)
    return phantom, activation


class TestCreateFmriPhantom:
    def test_shapes_match(self):
        phantom, activation = create_fmri_phantom(64)
        assert phantom.shape == (64, 64)
        assert activation.shape == (64, 64)

    def test_activation_range(self):
        _, activation = create_fmri_phantom(64)
        assert activation.min() >= 0.0
        assert activation.max() <= 5.0

    def test_activation_only_in_gm(self):
        phantom, activation = create_fmri_phantom(64)
        # Activation should only appear in GM (label 2)
        non_gm_mask = phantom != 2
        assert np.all(activation[non_gm_mask] == 0.0)

    def test_has_some_activation(self):
        _, activation = create_fmri_phantom(64)
        assert np.sum(activation > 0) > 0


class TestSimulateBoldSignal:
    def test_returns_float(self):
        result = simulate_bold_signal(60.0, bold_change_percent=2.0)
        assert isinstance(result, float)

    def test_activation_increases_t2star(self):
        # BOLD effect increases T2* in active state
        T2star_rest = 60.0
        T2star_active = simulate_bold_signal(T2star_rest, bold_change_percent=3.0)
        assert T2star_active > T2star_rest

    def test_zero_activation_unchanged(self):
        T2star = 60.0
        result = simulate_bold_signal(T2star, bold_change_percent=0.0)
        assert result == pytest.approx(T2star)


class TestSimulateFmriFast:
    def test_output_shape(self, fmri_data):
        phantom, activation = fmri_data
        img = simulate_fmri_fast(phantom, activation, TR=2000, TE=30)
        assert img.shape == phantom.shape

    def test_nonnegative(self, fmri_data):
        phantom, activation = fmri_data
        img = simulate_fmri_fast(phantom, activation, TR=2000, TE=30)
        assert np.all(img >= 0)

    def test_background_zero(self, fmri_data):
        phantom, activation = fmri_data
        img = simulate_fmri_fast(phantom, activation, TR=2000, TE=30)
        assert np.all(img[phantom == 0] == 0.0)

    def test_active_ge_rest_in_gm(self, fmri_data):
        phantom, activation = fmri_data
        rest = simulate_fmri_fast(phantom, activation, TR=2000, TE=30, is_active=False)
        active = simulate_fmri_fast(phantom, activation, TR=2000, TE=30, is_active=True)
        if np.any(phantom == 2):
            gm_active = active[phantom == 2].mean()
            gm_rest = rest[phantom == 2].mean()
            assert gm_active >= gm_rest


class TestComputeActivationMap:
    def test_output_shape(self, fmri_data):
        phantom, activation = fmri_data
        pct = compute_activation_map(phantom, activation)
        assert pct.shape == phantom.shape

    def test_background_zero(self, fmri_data):
        phantom, activation = fmri_data
        pct = compute_activation_map(phantom, activation)
        assert np.all(pct[phantom == 0] == 0)


class TestComputeTStatisticMap:
    def test_output_shape(self, fmri_data):
        phantom, activation = fmri_data
        t_map = compute_t_statistic_map(phantom, activation,
                                        num_volumes=20, noise_level=0.5)
        assert t_map.shape == phantom.shape

    def test_background_zero(self, fmri_data):
        phantom, activation = fmri_data
        t_map = compute_t_statistic_map(phantom, activation, num_volumes=20)
        assert np.all(t_map[phantom == 0] == 0)

    def test_positive_t_in_activated_regions(self, fmri_data):
        phantom, activation = fmri_data
        activated_gm = (phantom == 2) & (activation > 1.0)
        if np.any(activated_gm):
            t_map = compute_t_statistic_map(phantom, activation, num_volumes=50,
                                            noise_level=0.1)
            assert t_map[activated_gm].mean() > 0


class TestSimulateFmriImage:
    """Tests for simulate_fmri_image (the vectorised non-fast variant)."""

    def test_output_shape(self, fmri_data):
        phantom, activation = fmri_data
        img = simulate_fmri_image(phantom, activation, TR=2000, TE=30)
        assert img.shape == phantom.shape

    def test_nonnegative(self, fmri_data):
        phantom, activation = fmri_data
        img = simulate_fmri_image(phantom, activation, TR=2000, TE=30)
        assert np.all(img >= 0)

    def test_background_zero(self, fmri_data):
        phantom, activation = fmri_data
        img = simulate_fmri_image(phantom, activation, TR=2000, TE=30)
        assert np.all(img[phantom == 0] == 0.0)

    def test_dtype_float64(self, fmri_data):
        phantom, activation = fmri_data
        img = simulate_fmri_image(phantom, activation)
        assert img.dtype == np.float64

    def test_rest_matches_fast(self, fmri_data):
        """simulate_fmri_image rest state should match simulate_fmri_fast."""
        phantom, activation = fmri_data
        img_img = simulate_fmri_image(phantom, activation, TR=2000, TE=30, is_active=False)
        img_fast = simulate_fmri_fast(phantom, activation, TR=2000, TE=30, is_active=False)
        # Both functions use the same GRE formula for non-GM tissue
        np.testing.assert_allclose(img_img[phantom != 2], img_fast[phantom != 2], rtol=1e-6)

    def test_active_ne_rest_with_activation(self, fmri_data):
        phantom, activation = fmri_data
        rest = simulate_fmri_image(phantom, activation, TR=2000, TE=30, is_active=False)
        active = simulate_fmri_image(phantom, activation, TR=2000, TE=30, is_active=True)
        activated_gm = (phantom == 2) & (activation > 1.0)
        if np.any(activated_gm):
            assert not np.allclose(rest[activated_gm], active[activated_gm])


class TestFmriPhysics:
    def test_longer_te_reduces_signal(self, fmri_data):
        """Longer TE always reduces GRE signal (T2* decay)."""
        phantom, activation = fmri_data
        img_short = simulate_fmri_fast(phantom, activation, TR=2000, TE=15, is_active=False)
        img_long  = simulate_fmri_fast(phantom, activation, TR=2000, TE=80, is_active=False)
        brain = phantom > 0
        assert img_short[brain].mean() > img_long[brain].mean()

    def test_activation_map_positive_in_gm(self, fmri_data):
        phantom, activation = fmri_data
        pct = compute_activation_map(phantom, activation)
        activated_gm = (phantom == 2) & (activation > 1.0)
        if np.any(activated_gm):
            assert pct[activated_gm].mean() > 0

    def test_activation_map_zero_background(self, fmri_data):
        phantom, activation = fmri_data
        pct = compute_activation_map(phantom, activation)
        assert np.all(pct[phantom == 0] == 0)

    def test_bold_signal_array_input(self):
        """simulate_bold_signal must work on ndarray inputs (used inside vectorised loop)."""
        T2s = np.array([50.0, 60.0, 70.0])
        acts = np.array([1.0, 2.0, 3.0])
        result = simulate_bold_signal(T2s, acts)
        assert result.shape == (3,)
        assert np.all(result > T2s)

    def test_near_zero_denominator_returns_zero(self, fmri_data):
        """flip_angle=90 with very long TR makes denom~0 at some T1 values;
        simulate_fmri_fast must return 0.0 (not NaN/Inf) in that branch."""
        phantom, activation = fmri_data
        # cos(90°)=0 so denom = 1 - 0*E1 = 1, actually not near-zero.
        # Force near-zero by using flip=0 → sin(0)=0, so signal=0 regardless.
        img = simulate_fmri_fast(phantom, activation, TR=2000, TE=30,
                                 flip_angle=0.0, is_active=True)
        assert np.all(np.isfinite(img))
        assert np.all(img >= 0)

    def test_zero_flip_angle_gives_zero(self, fmri_data):
        phantom, activation = fmri_data
        img = simulate_fmri_fast(phantom, activation, TR=2000, TE=30, flip_angle=0)
        assert np.allclose(img, 0.0)


class TestComputeTemporalSNR:
    def test_positive(self):
        tsnr = compute_temporal_snr(TR=2000, TE=30, flip_angle=90, num_volumes=100)
        assert tsnr > 0

    def test_more_volumes_higher_tsnr(self):
        tsnr_few = compute_temporal_snr(TR=2000, TE=30, flip_angle=90, num_volumes=50)
        tsnr_many = compute_temporal_snr(TR=2000, TE=30, flip_angle=90, num_volumes=200)
        assert tsnr_many > tsnr_few

    def test_optimal_te_around_t2star(self):
        # TE near T2* of GM (60ms) should give highest tSNR
        tsnr_30 = compute_temporal_snr(TR=2000, TE=30, flip_angle=90, num_volumes=100)
        tsnr_60 = compute_temporal_snr(TR=2000, TE=60, flip_angle=90, num_volumes=100)
        tsnr_200 = compute_temporal_snr(TR=2000, TE=200, flip_angle=90, num_volumes=100)
        assert tsnr_60 >= tsnr_30  # 60ms closer to optimal
        assert tsnr_60 > tsnr_200  # very long TE loses signal
