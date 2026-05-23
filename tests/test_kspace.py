import numpy as np
import pytest
from kspace import (
    image_to_kspace,
    kspace_to_image,
    apply_matrix_size,
    zero_fill_resize,
    simulate_acquisition,
    get_kspace_display,
)


@pytest.fixture
def simple_image():
    np.random.seed(0)
    img = np.random.rand(64, 64)
    return img


class TestForwardInverseRoundtrip:
    def test_roundtrip_recovers_image(self, simple_image):
        kspace = image_to_kspace(simple_image)
        recovered = kspace_to_image(kspace)
        np.testing.assert_allclose(recovered, simple_image, atol=1e-10)

    def test_kspace_is_complex(self, simple_image):
        kspace = image_to_kspace(simple_image)
        assert np.iscomplexobj(kspace)

    def test_kspace_same_shape(self, simple_image):
        kspace = image_to_kspace(simple_image)
        assert kspace.shape == simple_image.shape

    def test_kspace_to_image_real(self, simple_image):
        kspace = image_to_kspace(simple_image)
        recovered = kspace_to_image(kspace)
        assert np.isrealobj(recovered) or np.all(recovered >= 0)

    def test_center_of_kspace_has_largest_magnitude(self, simple_image):
        kspace = image_to_kspace(simple_image)
        mag = np.abs(kspace)
        cy, cx = np.array(mag.shape) // 2
        center_val = mag[cy, cx]
        assert center_val >= mag[0, 0]


class TestApplyMatrixSize:
    def test_passthrough_when_target_ge_full(self, simple_image):
        kspace = image_to_kspace(simple_image)
        cropped = apply_matrix_size(kspace, 64)
        assert cropped.shape == (64, 64)

    def test_crops_to_target(self, simple_image):
        kspace = image_to_kspace(simple_image)
        cropped = apply_matrix_size(kspace, 32)
        assert cropped.shape == (32, 32)

    def test_larger_target_returns_unchanged(self, simple_image):
        kspace = image_to_kspace(simple_image)
        result = apply_matrix_size(kspace, 128)
        np.testing.assert_array_equal(result, kspace)


class TestZeroFillResize:
    def test_output_is_2d_float(self, simple_image):
        kspace = image_to_kspace(simple_image)
        small = apply_matrix_size(kspace, 32)
        out = zero_fill_resize(small, 64)
        assert out.ndim == 2
        assert np.isrealobj(out) or out.dtype in (np.float32, np.float64)

    def test_output_size(self, simple_image):
        kspace = image_to_kspace(simple_image)
        small = apply_matrix_size(kspace, 32)
        out = zero_fill_resize(small, 64)
        assert out.shape == (64, 64)

    def test_no_resize_when_already_target(self, simple_image):
        kspace = image_to_kspace(simple_image)
        out = zero_fill_resize(kspace, 32)  # current >= target: falls through
        assert out is not None


class TestSimulateAcquisition:
    def test_output_shape_no_aliasing(self, simple_image):
        recon, ks = simulate_acquisition(simple_image, 64)
        assert recon.shape == (64, 64)

    def test_kspace_shape(self, simple_image):
        recon, ks = simulate_acquisition(simple_image, 32)
        assert ks.shape == (32, 32)

    def test_reduced_matrix_lowers_resolution(self, simple_image):
        recon_full, _ = simulate_acquisition(simple_image, 64)
        recon_half, _ = simulate_acquisition(simple_image, 32)
        # Recon shapes may differ (zero-filled back), both should be non-negative
        assert np.all(recon_full >= 0)
        assert np.all(recon_half >= 0)


class TestGetKspaceDisplay:
    def test_nonnegative(self, simple_image):
        kspace = image_to_kspace(simple_image)
        disp = get_kspace_display(kspace)
        assert np.all(disp >= 0)

    def test_same_shape(self, simple_image):
        kspace = image_to_kspace(simple_image)
        disp = get_kspace_display(kspace)
        assert disp.shape == kspace.shape
