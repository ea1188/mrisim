import numpy as np
import pytest
from acceleration import (
    apply_parallel_imaging,
    compute_acceleration_metrics,
    apply_compressed_sensing,
)


@pytest.fixture
def test_image():
    np.random.seed(1)
    img = np.abs(np.random.rand(64, 64))
    # Make it brain-like: zero out corners
    y, x = np.ogrid[:64, :64]
    mask = ((x - 32)**2 + (y - 32)**2) < 30**2
    img[~mask] = 0
    return img


class TestApplyParallelImaging:
    def test_no_accel_returns_image_unchanged(self, test_image):
        result, gfactor = apply_parallel_imaging(test_image, acceleration_factor=1)
        np.testing.assert_array_equal(result, test_image)
        np.testing.assert_array_equal(gfactor, np.ones_like(test_image))

    def test_output_shape_r2(self, test_image):
        np.random.seed(0)
        result, gfactor = apply_parallel_imaging(test_image, acceleration_factor=2)
        assert result.shape == test_image.shape
        assert gfactor.shape == test_image.shape

    def test_gfactor_ge_one(self, test_image):
        np.random.seed(0)
        _, gfactor = apply_parallel_imaging(test_image, acceleration_factor=2)
        assert np.all(gfactor >= 1.0)

    def test_nonnegative_output(self, test_image):
        np.random.seed(0)
        result, _ = apply_parallel_imaging(test_image, acceleration_factor=2)
        assert np.all(result >= 0)

    def test_grappa_method(self, test_image):
        np.random.seed(0)
        result, gfactor = apply_parallel_imaging(test_image, acceleration_factor=2,
                                                  method="GRAPPA")
        assert result.shape == test_image.shape

    def test_higher_accel_higher_gfactor(self, test_image):
        np.random.seed(0)
        _, gf2 = apply_parallel_imaging(test_image, acceleration_factor=2)
        _, gf4 = apply_parallel_imaging(test_image, acceleration_factor=4)
        assert gf4.mean() > gf2.mean()


class TestComputeAccelerationMetrics:
    def test_no_accel_metrics(self):
        m = compute_acceleration_metrics(1, 30, 128)
        assert m["snr_factor"] == pytest.approx(1.0)
        assert m["adjusted_snr"] == pytest.approx(30.0)
        assert m["adjusted_time"] == pytest.approx(128.0)

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


class TestApplyCompressedSensing:
    def test_no_accel_returns_same(self, test_image):
        result = apply_compressed_sensing(test_image, acceleration_factor=1)
        np.testing.assert_array_equal(result, test_image)

    def test_output_shape(self, test_image):
        np.random.seed(0)
        result = apply_compressed_sensing(test_image, acceleration_factor=4)
        assert result.shape == test_image.shape

    def test_nonnegative(self, test_image):
        np.random.seed(0)
        result = apply_compressed_sensing(test_image, acceleration_factor=4)
        assert np.all(result >= 0)

    def test_output_not_all_zero(self, test_image):
        np.random.seed(0)
        result = apply_compressed_sensing(test_image, acceleration_factor=4)
        assert result.max() > 0
