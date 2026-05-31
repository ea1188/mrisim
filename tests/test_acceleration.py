"""Tests for acceleration.py — parallel imaging and compressed sensing."""

import numpy as np
import pytest
from acceleration import (
    apply_compressed_sensing,
    apply_parallel_imaging,
    compute_acceleration_metrics,
    sense_reconstruction,
    vd_poisson_mask,
)
from coil import head_coil_array, g_factor_map


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def rng():
    return np.random.default_rng(42)


@pytest.fixture
def uniform_image():
    """64×64 image with a circular uniform-signal object."""
    img = np.zeros((64, 64), dtype=float)
    y, x = np.ogrid[:64, :64]
    img[(x - 32)**2 + (y - 32)**2 < 28**2] = 1.0
    return img


@pytest.fixture
def brain_image():
    """64×64 brain-like image with varying signal intensities."""
    rng_fix = np.random.default_rng(1)
    img = np.abs(rng_fix.standard_normal((64, 64))) * 0.1
    y, x = np.ogrid[:64, :64]
    img[(x - 32)**2 + (y - 32)**2 < 28**2] += 1.0
    img[(x - 32)**2 + (y - 32)**2 < 12**2] += 0.5
    return img


@pytest.fixture
def sensitivity_maps_8(uniform_image):
    """8-element head coil array for the 64×64 FOV."""
    return head_coil_array(shape=uniform_image.shape, n_coils=8)


# ---------------------------------------------------------------------------
# sense_reconstruction
# ---------------------------------------------------------------------------

class TestSenseReconstruction:
    def test_output_shape(self, uniform_image, sensitivity_maps_8):
        recon, g = sense_reconstruction(uniform_image, sensitivity_maps_8.astype(complex), 2)
        assert recon.shape == uniform_image.shape
        assert g.shape == uniform_image.shape

    def test_r1_returns_sos(self, uniform_image, sensitivity_maps_8):
        recon, g = sense_reconstruction(uniform_image, sensitivity_maps_8.astype(complex), 1)
        assert recon.shape == uniform_image.shape
        np.testing.assert_array_equal(g, np.ones_like(g))

    def test_gfactor_ge_one(self, uniform_image, sensitivity_maps_8):
        _, g = sense_reconstruction(uniform_image, sensitivity_maps_8.astype(complex), 2)
        assert np.all(g >= 1.0)

    def test_nonnegative_output(self, uniform_image, sensitivity_maps_8):
        recon, _ = sense_reconstruction(uniform_image, sensitivity_maps_8.astype(complex), 2)
        assert np.all(recon >= 0.0)

    def test_noise_free_recovers_signal(self, uniform_image, sensitivity_maps_8):
        # With no noise, SENSE should reconstruct within the object to ~signal level
        recon, _ = sense_reconstruction(uniform_image, sensitivity_maps_8.astype(complex), 2,
                                        noise_sigma=0.0)
        obj_mask = uniform_image > 0.5
        # Reconstructed signal inside object should be close to the expected SENSE combination
        # (not necessarily == 1.0 because SoS normalisation differs from SENSE)
        assert recon[obj_mask].mean() > 0.1

    def test_noise_free_background_near_zero(self, uniform_image, sensitivity_maps_8):
        # Background (outside object) should have very low signal when noise-free
        recon, _ = sense_reconstruction(uniform_image, sensitivity_maps_8.astype(complex), 2,
                                        noise_sigma=0.0)
        bg_mask = uniform_image < 0.01
        assert recon[bg_mask].mean() < 0.05

    def test_r4_output_shape(self, uniform_image, sensitivity_maps_8):
        recon, g = sense_reconstruction(uniform_image, sensitivity_maps_8.astype(complex), 4)
        assert recon.shape == uniform_image.shape

    def test_rows_not_divisible_raises(self, sensitivity_maps_8):
        img_odd = np.ones((65, 64))
        sm_odd  = np.ones((8, 65, 64), dtype=complex)
        with pytest.raises(ValueError, match="divisible"):
            sense_reconstruction(img_odd, sm_odd, 3)

    def test_acceleration_lt_1_raises(self, uniform_image, sensitivity_maps_8):
        with pytest.raises(ValueError, match="acceleration"):
            sense_reconstruction(uniform_image, sensitivity_maps_8.astype(complex), 0)

    def test_rng_reproducible(self, uniform_image, sensitivity_maps_8):
        r1, _ = sense_reconstruction(uniform_image, sensitivity_maps_8.astype(complex), 2,
                                     noise_sigma=0.05, rng=np.random.default_rng(7))
        r2, _ = sense_reconstruction(uniform_image, sensitivity_maps_8.astype(complex), 2,
                                     noise_sigma=0.05, rng=np.random.default_rng(7))
        np.testing.assert_array_equal(r1, r2)

    def test_rng_different_seeds_differ(self, uniform_image, sensitivity_maps_8):
        r1, _ = sense_reconstruction(uniform_image, sensitivity_maps_8.astype(complex), 2,
                                     noise_sigma=0.1, rng=np.random.default_rng(1))
        r2, _ = sense_reconstruction(uniform_image, sensitivity_maps_8.astype(complex), 2,
                                     noise_sigma=0.1, rng=np.random.default_rng(2))
        assert not np.array_equal(r1, r2)

    def test_higher_noise_higher_bg_signal(self, uniform_image, sensitivity_maps_8):
        rng_a = np.random.default_rng(10)
        rng_b = np.random.default_rng(10)
        r_low,  _ = sense_reconstruction(uniform_image, sensitivity_maps_8.astype(complex), 2,
                                          noise_sigma=0.0, rng=rng_a)
        r_high, _ = sense_reconstruction(uniform_image, sensitivity_maps_8.astype(complex), 2,
                                          noise_sigma=0.5, rng=rng_b)
        bg = uniform_image < 0.01
        assert r_high[bg].std() > r_low[bg].std()

    def test_gfactor_matches_standalone(self, uniform_image, sensitivity_maps_8):
        sm = sensitivity_maps_8.astype(complex)
        _, g_sense = sense_reconstruction(uniform_image, sm, 2)
        g_standalone = g_factor_map(sm, 2)
        np.testing.assert_allclose(g_sense, g_standalone)

    def test_noise_cov_identity_equals_default(self, uniform_image, sensitivity_maps_8):
        sm    = sensitivity_maps_8.astype(complex)
        n     = sm.shape[0]
        eye   = np.eye(n, dtype=complex)
        r_def, g_def = sense_reconstruction(uniform_image, sm, 2,
                                             rng=np.random.default_rng(0))
        r_eye, g_eye = sense_reconstruction(uniform_image, sm, 2, noise_cov=eye,
                                             rng=np.random.default_rng(0))
        np.testing.assert_allclose(r_def, r_eye)
        np.testing.assert_allclose(g_def, g_eye)


# ---------------------------------------------------------------------------
# apply_parallel_imaging
# ---------------------------------------------------------------------------

class TestApplyParallelImaging:
    def test_no_accel_returns_image_unchanged(self, brain_image):
        result, gfactor = apply_parallel_imaging(brain_image, acceleration_factor=1)
        np.testing.assert_array_equal(result, brain_image)
        np.testing.assert_array_equal(gfactor, np.ones_like(brain_image))

    def test_output_shape_r2(self, brain_image, rng):
        result, gfactor = apply_parallel_imaging(brain_image, acceleration_factor=2, rng=rng)
        assert result.shape == brain_image.shape
        assert gfactor.shape == brain_image.shape

    def test_gfactor_ge_one(self, brain_image, rng):
        _, gfactor = apply_parallel_imaging(brain_image, acceleration_factor=2, rng=rng)
        assert np.all(gfactor >= 1.0)

    def test_nonnegative_output(self, brain_image, rng):
        result, _ = apply_parallel_imaging(brain_image, acceleration_factor=2, rng=rng)
        assert np.all(result >= 0.0)

    def test_grappa_method(self, brain_image, rng):
        result, gfactor = apply_parallel_imaging(brain_image, acceleration_factor=2,
                                                  method="GRAPPA", rng=rng)
        assert result.shape == brain_image.shape
        assert gfactor.shape == brain_image.shape
        assert np.all(gfactor >= 1.0)

    def test_grappa_nonnegative(self, brain_image, rng):
        result, _ = apply_parallel_imaging(brain_image, acceleration_factor=2,
                                            method="GRAPPA", rng=rng)
        assert np.all(result >= 0.0)

    @pytest.mark.parametrize("R", [2, 3, 4])
    def test_grappa_rows_not_divisible_by_R(self, R, rng):
        """Regression: GRAPPA must not crash when rows aren't a multiple of R
        (e.g. the 217-row brain slice). The g-factor map needs padding."""
        img = np.abs(rng.standard_normal((217, 181)))   # 217 % 2/3/4 != 0
        result, gfactor = apply_parallel_imaging(img, acceleration_factor=R,
                                                 method="GRAPPA", rng=rng)
        assert result.shape == img.shape
        assert gfactor.shape == img.shape
        assert np.all(gfactor >= 1.0)

    def test_higher_accel_higher_gfactor(self, brain_image, rng):
        _, gf2 = apply_parallel_imaging(brain_image, acceleration_factor=2, rng=rng)
        _, gf4 = apply_parallel_imaging(brain_image, acceleration_factor=4, rng=rng)
        assert gf4.mean() > gf2.mean()

    def test_sense_gfactor_from_physics(self, brain_image):
        # SENSE g-factor must come from the actual coil geometry, not a heuristic —
        # verify it matches g_factor_map called on the same auto-generated array
        sm = head_coil_array(shape=brain_image.shape, n_coils=8)
        _, g = apply_parallel_imaging(brain_image, acceleration_factor=2,
                                       sensitivity_maps=sm,
                                       rng=np.random.default_rng(0))
        g_ref = g_factor_map(sm.astype(complex), 2)
        np.testing.assert_allclose(g, g_ref)

    def test_custom_sensitivity_maps(self, brain_image, sensitivity_maps_8, rng):
        result, g = apply_parallel_imaging(brain_image, acceleration_factor=2,
                                            sensitivity_maps=sensitivity_maps_8, rng=rng)
        assert result.shape == brain_image.shape
        assert np.all(g >= 1.0)

    def test_rng_reproducible_sense(self, brain_image, sensitivity_maps_8):
        r1, _ = apply_parallel_imaging(brain_image, acceleration_factor=2,
                                        sensitivity_maps=sensitivity_maps_8,
                                        rng=np.random.default_rng(5))
        r2, _ = apply_parallel_imaging(brain_image, acceleration_factor=2,
                                        sensitivity_maps=sensitivity_maps_8,
                                        rng=np.random.default_rng(5))
        np.testing.assert_array_equal(r1, r2)

    def test_r3_non_square_rows_padded(self, rng):
        # 66 rows is not divisible by 3 before padding — should work via auto-pad
        img = np.ones((66, 64))
        result, g = apply_parallel_imaging(img, acceleration_factor=3, rng=rng)
        assert result.shape == (66, 64)
        assert g.shape == (66, 64)


# ---------------------------------------------------------------------------
# compute_acceleration_metrics
# ---------------------------------------------------------------------------

class TestComputeAccelerationMetrics:
    def test_no_accel_metrics(self):
        m = compute_acceleration_metrics(1, 30, 128)
        assert m["snr_factor"]    == pytest.approx(1.0)
        assert m["adjusted_snr"]  == pytest.approx(30.0)
        assert m["adjusted_time"] == pytest.approx(128.0)
        assert m["g_factor_mean"] == pytest.approx(1.0)
        assert m["g_factor_max"]  == pytest.approx(1.0)

    def test_accel_2_halves_time(self):
        m = compute_acceleration_metrics(2, 30, 128)
        assert m["adjusted_time"] == pytest.approx(64.0)

    def test_snr_decreases_with_accel(self):
        m1 = compute_acceleration_metrics(1, 30, 128)
        m2 = compute_acceleration_metrics(4, 30, 128)
        assert m2["adjusted_snr"] < m1["adjusted_snr"]

    def test_snr_factor_sqrt_relationship(self):
        m = compute_acceleration_metrics(4, 30, 128)
        assert m["snr_factor"] == pytest.approx(0.5, rel=0.01)  # 1/sqrt(4)

    def test_with_gfactor_map_uniform(self):
        g = np.ones((64, 64)) * 1.5
        m = compute_acceleration_metrics(2, 40, 100, g_factor=g)
        # snr_factor = 1 / (sqrt(2) * 1.5)
        expected = 1.0 / (np.sqrt(2) * 1.5)
        assert m["snr_factor"]    == pytest.approx(expected, rel=1e-5)
        assert m["g_factor_mean"] == pytest.approx(1.5)
        assert m["g_factor_max"]  == pytest.approx(1.5)
        assert m["g_factor_p95"]  == pytest.approx(1.5)

    def test_with_gfactor_map_varying(self):
        g = np.array([[1.0, 1.2], [1.8, 2.0]])
        m = compute_acceleration_metrics(2, 30, 128, g_factor=g)
        assert m["g_factor_mean"] == pytest.approx(1.5)
        assert m["g_factor_max"]  == pytest.approx(2.0)
        assert m["g_factor_p95"]  > m["g_factor_mean"]

    def test_no_gfactor_key_present(self):
        m = compute_acceleration_metrics(2, 30, 128)
        for key in ("snr_factor", "adjusted_snr", "adjusted_time",
                    "g_factor_mean", "g_factor_max", "g_factor_p95"):
            assert key in m

    def test_gfactor_map_increases_snr_penalty(self):
        # Real g > 1 should make snr_factor worse than the g=1 baseline
        g_real = np.ones((32, 32)) * 1.5
        m_ideal = compute_acceleration_metrics(2, 30, 128)
        m_real  = compute_acceleration_metrics(2, 30, 128, g_factor=g_real)
        assert m_real["snr_factor"] < m_ideal["snr_factor"]


# ---------------------------------------------------------------------------
# vd_poisson_mask
# ---------------------------------------------------------------------------

class TestVdPoissonMask:
    def test_output_shape(self, rng):
        mask = vd_poisson_mask(64, 64, 4, rng=rng)
        assert mask.shape == (64, 64)
        assert mask.dtype == bool

    def test_center_fully_sampled(self, rng):
        rows, cols = 64, 64
        cf = 0.1
        mask = vd_poisson_mask(rows, cols, 4, center_fraction=cf, rng=rng)
        acs_half = max(1, int(rows * cf / 2))
        center_region = mask[rows // 2 - acs_half: rows // 2 + acs_half, :]
        assert center_region.all()

    def test_approximate_acceleration(self, rng):
        rows, cols, R = 64, 64, 4
        mask = vd_poisson_mask(rows, cols, R, rng=rng)
        # Actual sampling fraction should be within 30 % of target 1/R
        fraction = mask.sum() / (rows * cols)
        assert fraction == pytest.approx(1.0 / R, rel=0.3)

    def test_acceleration_1_fully_sampled(self, rng):
        mask = vd_poisson_mask(32, 32, 1, rng=rng)
        # Everything ends up sampled (target = all lines)
        assert mask.all()

    def test_higher_accel_fewer_samples(self, rng):
        m2 = vd_poisson_mask(64, 64, 2, rng=np.random.default_rng(0))
        m8 = vd_poisson_mask(64, 64, 8, rng=np.random.default_rng(0))
        assert m8.sum() < m2.sum()

    def test_reproducible(self):
        m1 = vd_poisson_mask(64, 64, 4, rng=np.random.default_rng(99))
        m2 = vd_poisson_mask(64, 64, 4, rng=np.random.default_rng(99))
        np.testing.assert_array_equal(m1, m2)

    def test_different_seeds_differ(self):
        m1 = vd_poisson_mask(64, 64, 4, rng=np.random.default_rng(1))
        m2 = vd_poisson_mask(64, 64, 4, rng=np.random.default_rng(2))
        assert not np.array_equal(m1, m2)

    def test_density_higher_at_centre(self, rng):
        mask = vd_poisson_mask(64, 64, 4, rng=rng)
        half = 64 // 2
        inner = mask[half - 8: half + 8, half - 8: half + 8].mean()
        outer = mask[:8, :8].mean()
        assert inner >= outer

    def test_rectangular_shape(self, rng):
        mask = vd_poisson_mask(64, 32, 4, rng=rng)
        assert mask.shape == (64, 32)


# ---------------------------------------------------------------------------
# apply_compressed_sensing
# ---------------------------------------------------------------------------

class TestApplyCompressedSensing:
    def test_no_accel_returns_same(self, brain_image):
        result = apply_compressed_sensing(brain_image, acceleration_factor=1)
        np.testing.assert_array_equal(result, brain_image)

    def test_output_shape(self, brain_image, rng):
        result = apply_compressed_sensing(brain_image, acceleration_factor=4, rng=rng)
        assert result.shape == brain_image.shape

    def test_nonnegative(self, brain_image, rng):
        result = apply_compressed_sensing(brain_image, acceleration_factor=4, rng=rng)
        assert np.all(result >= 0.0)

    def test_output_not_all_zero(self, brain_image, rng):
        result = apply_compressed_sensing(brain_image, acceleration_factor=4, rng=rng)
        assert result.max() > 0.0

    def test_centre_preserved(self, brain_image, rng):
        # ACS region always sampled → low-frequency content always present
        result = apply_compressed_sensing(brain_image, acceleration_factor=4, rng=rng)
        # Mean signal should be non-negligible compared to input
        assert result.mean() > 0.01 * brain_image.mean()

    def test_rng_reproducible(self, brain_image):
        r1 = apply_compressed_sensing(brain_image, 4, rng=np.random.default_rng(3))
        r2 = apply_compressed_sensing(brain_image, 4, rng=np.random.default_rng(3))
        np.testing.assert_array_equal(r1, r2)

    def test_rng_different_seeds_differ(self, brain_image):
        r1 = apply_compressed_sensing(brain_image, 4, rng=np.random.default_rng(1))
        r2 = apply_compressed_sensing(brain_image, 4, rng=np.random.default_rng(2))
        assert not np.array_equal(r1, r2)

    def test_higher_accel_more_artefact(self, brain_image):
        # Higher acceleration removes more k-space → larger deviation from original
        r2 = apply_compressed_sensing(brain_image, 2, rng=np.random.default_rng(0))
        r8 = apply_compressed_sensing(brain_image, 8, rng=np.random.default_rng(0))
        err2 = np.abs(r2 - brain_image).mean()
        err8 = np.abs(r8 - brain_image).mean()
        assert err8 >= err2

    def test_output_dtype_float64(self, brain_image, rng):
        result = apply_compressed_sensing(brain_image, acceleration_factor=4, rng=rng)
        assert result.dtype == np.float64

    def test_custom_center_fraction(self, brain_image, rng):
        r_small = apply_compressed_sensing(brain_image, 4, center_fraction=0.02, rng=rng)
        r_large = apply_compressed_sensing(brain_image, 4, center_fraction=0.20, rng=rng)
        assert r_small.shape == brain_image.shape
        assert r_large.shape == brain_image.shape

    def test_no_rng_arg_runs(self, brain_image):
        """Omitting rng triggers the default_rng() fallback inside the function."""
        result = apply_compressed_sensing(brain_image, acceleration_factor=2)
        assert result.shape == brain_image.shape
        assert np.all(result >= 0.0)


class TestDefaultRngFallbacks:
    """Verify that functions with optional rng kwargs work when rng is omitted."""

    def test_parallel_imaging_no_rng(self, brain_image):
        result, g = apply_parallel_imaging(brain_image, acceleration_factor=2)
        assert result.shape == brain_image.shape
        assert np.all(g >= 1.0)

    def test_vd_poisson_mask_no_rng(self):
        mask = vd_poisson_mask(32, 32, 4)
        assert mask.shape == (32, 32)
        assert mask.dtype == bool


# ---------------------------------------------------------------------------
# Branch coverage additions
# ---------------------------------------------------------------------------
class TestSensePaddingNonDivisibleRows:
    def test_sense_pads_non_divisible_rows(self, rng):
        """Image with rows not divisible by R triggers SENSE padding (lines 192-193)
        and the matching crop (lines 201-202) after reconstruction."""
        # 33 rows, R=4 → 33 % 4 = 1 → pad = 3
        img = np.ones((33, 32))
        result, g = apply_parallel_imaging(img, acceleration_factor=4, method="SENSE",
                                           rng=rng)
        assert result.shape == (33, 32)
        assert g.shape == (33, 32)
