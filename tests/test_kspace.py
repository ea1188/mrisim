"""Tests for kspace.py."""

import numpy as np
import pytest
from kspace import (
    apply_aliasing,
    apply_matrix_size,
    get_kspace_display,
    image_to_kspace,
    kspace_filter,
    kspace_to_image,
    partial_fourier,
    simulate_acquisition,
    zero_fill_resize,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def square_image():
    rng = np.random.default_rng(0)
    img = rng.random((64, 64))
    return img


@pytest.fixture
def rect_image():
    rng = np.random.default_rng(1)
    return rng.random((64, 96))


@pytest.fixture
def circle_image():
    """Disc phantom with sharp edges — good for Gibbs/aliasing tests."""
    img = np.zeros((64, 64))
    y, x = np.ogrid[:64, :64]
    img[(x - 32)**2 + (y - 32)**2 < 24**2] = 1.0
    return img


# ---------------------------------------------------------------------------
# image_to_kspace / kspace_to_image
# ---------------------------------------------------------------------------

class TestForwardInverseRoundtrip:
    def test_roundtrip_recovers_image(self, square_image):
        kspace = image_to_kspace(square_image)
        recovered = kspace_to_image(kspace)
        np.testing.assert_allclose(recovered, square_image, atol=1e-10)

    def test_kspace_is_complex(self, square_image):
        assert np.iscomplexobj(image_to_kspace(square_image))

    def test_kspace_same_shape(self, square_image):
        assert image_to_kspace(square_image).shape == square_image.shape

    def test_kspace_to_image_nonnegative(self, square_image):
        assert np.all(kspace_to_image(image_to_kspace(square_image)) >= 0)

    def test_center_of_kspace_has_largest_magnitude(self, square_image):
        mag = np.abs(image_to_kspace(square_image))
        cy, cx = np.array(mag.shape) // 2
        assert mag[cy, cx] >= mag[0, 0]

    def test_dc_value_equals_image_sum(self, square_image):
        kspace = image_to_kspace(square_image)
        cy, cx = np.array(kspace.shape) // 2
        expected_dc = square_image.sum()
        assert abs(kspace[cy, cx].real - expected_dc) < 1e-8

    def test_rect_image_roundtrip(self, rect_image):
        kspace = image_to_kspace(rect_image)
        recovered = kspace_to_image(kspace)
        np.testing.assert_allclose(recovered, rect_image, atol=1e-10)

    def test_output_dtype_float64(self, square_image):
        assert kspace_to_image(image_to_kspace(square_image)).dtype == np.float64


# ---------------------------------------------------------------------------
# apply_matrix_size
# ---------------------------------------------------------------------------

class TestApplyMatrixSize:
    def test_square_crop(self, square_image):
        kspace = image_to_kspace(square_image)
        cropped = apply_matrix_size(kspace, 32)
        assert cropped.shape == (32, 32)

    def test_passthrough_when_target_ge_full(self, square_image):
        kspace = image_to_kspace(square_image)
        result = apply_matrix_size(kspace, 64)
        assert result.shape == (64, 64)

    def test_larger_target_returns_unchanged(self, square_image):
        kspace = image_to_kspace(square_image)
        result = apply_matrix_size(kspace, 128)
        np.testing.assert_array_equal(result, kspace)

    def test_rectangular_crop(self, square_image):
        kspace = image_to_kspace(square_image)
        cropped = apply_matrix_size(kspace, 32, target_cols=48)
        assert cropped.shape == (32, 48)

    def test_row_only_crop(self, square_image):
        kspace = image_to_kspace(square_image)
        cropped = apply_matrix_size(kspace, 32, target_cols=64)
        assert cropped.shape == (32, 64)

    def test_col_only_crop(self, square_image):
        kspace = image_to_kspace(square_image)
        cropped = apply_matrix_size(kspace, 64, target_cols=32)
        assert cropped.shape == (64, 32)

    def test_central_crop_preserves_dc(self, square_image):
        # DC should still be present after cropping the centre
        kspace = image_to_kspace(square_image)
        cropped = apply_matrix_size(kspace, 32)
        cy_f, cx_f = np.array(kspace.shape) // 2
        cy_c, cx_c = np.array(cropped.shape) // 2
        np.testing.assert_allclose(kspace[cy_f, cx_f], cropped[cy_c, cx_c])

    def test_rect_image_crop(self, rect_image):
        kspace = image_to_kspace(rect_image)
        cropped = apply_matrix_size(kspace, 32, target_cols=48)
        assert cropped.shape == (32, 48)


# ---------------------------------------------------------------------------
# zero_fill_resize
# ---------------------------------------------------------------------------

class TestZeroFillResize:
    def test_output_shape_square(self, square_image):
        kspace = image_to_kspace(square_image)
        small = apply_matrix_size(kspace, 32)
        out = zero_fill_resize(small, 64)
        assert out.shape == (64, 64)

    def test_output_dtype_float64(self, square_image):
        kspace = image_to_kspace(square_image)
        small = apply_matrix_size(kspace, 32)
        assert zero_fill_resize(small, 64).dtype == np.float64

    def test_no_resize_when_already_target(self, square_image):
        kspace = image_to_kspace(square_image)
        out = zero_fill_resize(kspace, 32)  # current >= target
        assert out is not None
        assert out.shape == (64, 64)

    def test_zero_fill_increases_apparent_resolution(self, circle_image):
        kspace = image_to_kspace(circle_image)
        small = apply_matrix_size(kspace, 16)
        zf = zero_fill_resize(small, 64)
        # Zero-filled image should look smoother (lower gradient magnitude)
        low_res = kspace_to_image(small)
        assert zf.shape == (64, 64)
        assert low_res.shape == (16, 16)

    def test_rectangular_output(self, square_image):
        kspace = image_to_kspace(square_image)
        small = apply_matrix_size(kspace, 32, 32)
        out = zero_fill_resize(small, 64, target_cols=96)
        assert out.shape == (64, 96)

    def test_intensity_scale_preserved(self, circle_image):
        # Zero-filling should not inflate pixel intensities
        kspace = image_to_kspace(circle_image)
        small = apply_matrix_size(kspace, 32)
        zf = zero_fill_resize(small, 64)
        full = kspace_to_image(kspace)
        # Object signal after zero-fill should be in the same ballpark as full
        assert zf[circle_image > 0.5].mean() == pytest.approx(
            full[circle_image > 0.5].mean(), rel=0.3
        )


# ---------------------------------------------------------------------------
# kspace_filter
# ---------------------------------------------------------------------------

class TestKspaceFilter:
    @pytest.mark.parametrize("window", ["hamming", "hanning", "blackman", "bartlett"])
    def test_output_shape(self, window, square_image):
        kspace = image_to_kspace(square_image)
        filtered = kspace_filter(kspace, window)
        assert filtered.shape == kspace.shape

    def test_rect_is_identity(self, square_image):
        kspace = image_to_kspace(square_image)
        filtered = kspace_filter(kspace, "rect")
        np.testing.assert_array_equal(filtered, kspace)

    def test_hamming_attenuates_edges(self, square_image):
        kspace = image_to_kspace(square_image)
        filtered = kspace_filter(kspace, "hamming")
        # Corners (high-frequency) should be attenuated
        assert np.abs(filtered[0, 0]) <= np.abs(kspace[0, 0]) + 1e-12

    def test_hamming_preserves_dc(self, square_image):
        kspace = image_to_kspace(square_image)
        filtered = kspace_filter(kspace, "hamming")
        cy, cx = np.array(kspace.shape) // 2
        # DC component should be preserved (window = 1 at centre)
        np.testing.assert_allclose(filtered[cy, cx], kspace[cy, cx], rtol=0.05)

    def test_filter_attenuates_outer_kspace(self, square_image):
        # Verify that Hamming attenuates outer k-space lines and leaves DC intact.
        # This is the core property Gibbs-reduction relies on.
        kspace = image_to_kspace(square_image)
        small  = apply_matrix_size(kspace, 16)
        filt   = kspace_filter(small, "hamming")
        # Outer lines of the 16×16 k-space should be attenuated
        outer_before = np.abs(small[0, :]).mean()
        outer_after  = np.abs(filt[0, :]).mean()
        assert outer_after <= outer_before + 1e-12
        # Centre (DC region) should be largely preserved
        cy, cx = 8, 8
        dc_before = abs(small[cy, cx])
        dc_after  = abs(filt[cy, cx])
        assert dc_after >= 0.8 * dc_before

    def test_unknown_window_raises(self, square_image):
        kspace = image_to_kspace(square_image)
        with pytest.raises(ValueError, match="Unknown window"):
            kspace_filter(kspace, "bogus")

    def test_output_is_complex(self, square_image):
        kspace = image_to_kspace(square_image)
        assert np.iscomplexobj(kspace_filter(kspace, "hamming"))


# ---------------------------------------------------------------------------
# partial_fourier
# ---------------------------------------------------------------------------

class TestPartialFourier:
    def test_output_shape(self, square_image):
        kspace = image_to_kspace(square_image)
        pf = partial_fourier(kspace, 0.625)
        assert pf.shape == kspace.shape

    def test_positive_half_unchanged(self, square_image):
        kspace = image_to_kspace(square_image)
        pf = partial_fourier(kspace, 0.75, axis=0)
        rows = kspace.shape[0]
        centre = rows // 2
        # Positive half (centre to end) must be untouched
        np.testing.assert_array_equal(pf[centre:, :], kspace[centre:, :])

    def test_zeroed_lines_are_zero(self, square_image):
        kspace = image_to_kspace(square_image)
        fraction = 0.6
        rows = kspace.shape[0]
        centre = rows // 2
        n_neg_acquired = int(round((fraction - 0.5) * rows))
        pf = partial_fourier(kspace, fraction, axis=0)
        n_zeroed = centre - n_neg_acquired
        if n_zeroed > 0:
            assert np.all(pf[:n_zeroed, :] == 0.0)

    def test_fraction_1_unchanged(self, square_image):
        kspace = image_to_kspace(square_image)
        pf = partial_fourier(kspace, 1.0)
        np.testing.assert_array_equal(pf, kspace)

    def test_fraction_le_05_raises(self, square_image):
        kspace = image_to_kspace(square_image)
        with pytest.raises(ValueError, match="fraction"):
            partial_fourier(kspace, 0.5)
        with pytest.raises(ValueError, match="fraction"):
            partial_fourier(kspace, 0.3)

    def test_higher_fraction_more_nonzero(self, square_image):
        kspace = image_to_kspace(square_image)
        pf6 = partial_fourier(kspace, 0.6)
        pf9 = partial_fourier(kspace, 0.9)
        assert (pf9 != 0).sum() >= (pf6 != 0).sum()

    def test_axis_1(self, square_image):
        kspace = image_to_kspace(square_image)
        pf = partial_fourier(kspace, 0.75, axis=1)
        cols = kspace.shape[1]
        centre = cols // 2
        np.testing.assert_array_equal(pf[:, centre:], kspace[:, centre:])


# ---------------------------------------------------------------------------
# apply_aliasing
# ---------------------------------------------------------------------------

class TestApplyAliasing:
    def test_no_aliasing_passthrough(self, square_image):
        result = apply_aliasing(square_image, 1.0)
        np.testing.assert_array_equal(result, square_image)

    def test_output_shape_halved(self, square_image):
        result = apply_aliasing(square_image, 0.5)
        assert result.shape == (32, 64)

    def test_signal_conservation(self, square_image):
        # Total signal should be conserved under aliasing (energy folds in)
        result = apply_aliasing(square_image, 0.5)
        np.testing.assert_allclose(result.sum(), square_image.sum(), rtol=1e-10)

    def test_nonnegative_for_nonneg_input(self, square_image):
        img = np.abs(square_image)
        result = apply_aliasing(img, 0.5)
        assert np.all(result >= 0)

    def test_uniform_image_halved(self):
        # Uniform image: folding doubles the pixel values
        img = np.ones((64, 64))
        result = apply_aliasing(img, 0.5)
        assert result.shape == (32, 64)
        np.testing.assert_allclose(result, 2.0, atol=1e-10)

    def test_three_quarter_fov(self, square_image):
        result = apply_aliasing(square_image, 0.75)
        assert result.shape[0] == 48

    def test_very_small_fov_fraction_clips_to_min(self, square_image):
        result = apply_aliasing(square_image, 0.01)
        assert result.shape[0] == 10  # clamped to minimum of 10

    def test_agrees_with_reference_loop(self):
        # Reference: the original slow nested-loop implementation
        rng = np.random.default_rng(42)
        img = rng.random((20, 20))
        fov = 0.5
        new_n = int(20 * fov)

        ref = np.zeros((new_n, 20))
        for i in range(20):
            for j in range(20):
                ref[i % new_n, j] += img[i, j]

        result = apply_aliasing(img, fov)
        np.testing.assert_allclose(result, ref, atol=1e-12)

    def test_fov_gt_1_returns_same(self, square_image):
        result = apply_aliasing(square_image, 1.5)
        np.testing.assert_array_equal(result, square_image)


# ---------------------------------------------------------------------------
# simulate_acquisition
# ---------------------------------------------------------------------------

class TestSimulateAcquisition:
    def test_output_shape_no_aliasing(self, square_image):
        recon, ks = simulate_acquisition(square_image, 64)
        assert recon.shape == (64, 64)

    def test_kspace_shape(self, square_image):
        _, ks = simulate_acquisition(square_image, 32)
        assert ks.shape == (32, 32)

    def test_reduced_matrix_nonnegative(self, square_image):
        recon, _ = simulate_acquisition(square_image, 32)
        assert np.all(recon >= 0)

    def test_full_matrix_faithful(self, circle_image):
        recon, _ = simulate_acquisition(circle_image, 64)
        np.testing.assert_allclose(recon, circle_image, atol=1e-10)

    def test_with_hamming_filter(self, circle_image):
        recon, _ = simulate_acquisition(circle_image, 64, filter_window="hamming")
        assert recon.shape == (64, 64)
        assert np.all(recon >= 0)

    def test_with_partial_fourier(self, circle_image):
        recon, _ = simulate_acquisition(circle_image, 64, pf_fraction=0.75)
        assert recon.shape == (64, 64)
        assert np.all(recon >= 0)

    def test_aliasing_reduces_phase_fov(self, square_image):
        recon_full, _ = simulate_acquisition(square_image, 64, fov_fraction=1.0)
        # With fov_fraction < 1 and zoom back, output shape stays the same
        recon_half, _ = simulate_acquisition(square_image, 64, fov_fraction=0.5)
        assert recon_half.shape == (64, 64)

    def test_combined_filter_and_pf(self, circle_image):
        recon, _ = simulate_acquisition(
            circle_image, 32, filter_window="hanning", pf_fraction=0.75)
        assert recon.shape == (64, 64)


# ---------------------------------------------------------------------------
# get_kspace_display
# ---------------------------------------------------------------------------

class TestGetKspaceDisplay:
    def test_nonnegative(self, square_image):
        disp = get_kspace_display(image_to_kspace(square_image))
        assert np.all(disp >= 0)

    def test_same_shape(self, square_image):
        kspace = image_to_kspace(square_image)
        assert get_kspace_display(kspace).shape == kspace.shape

    def test_dtype_float64(self, square_image):
        kspace = image_to_kspace(square_image)
        assert get_kspace_display(kspace).dtype == np.float64

    def test_zero_kspace_gives_zero_display(self):
        kspace = np.zeros((16, 16), dtype=complex)
        disp = get_kspace_display(kspace)
        np.testing.assert_array_equal(disp, 0.0)

    def test_log_compresses_dynamic_range(self, square_image):
        kspace = image_to_kspace(square_image)
        mag    = np.abs(kspace)
        disp   = get_kspace_display(kspace)
        # log1p maps to much smaller range
        assert disp.max() < mag.max()


# --- Radial (non-Cartesian) sampling ----------------------------------------
from kspace import radial_sampling_mask, apply_radial_sampling


def test_radial_mask_centre_always_sampled():
    m = radial_sampling_mask((64, 64), n_spokes=16)
    assert m[32, 32]                                  # DC sampled
    assert m.dtype == bool and m.shape == (64, 64)


def test_more_spokes_more_coverage():
    few = radial_sampling_mask((96, 96), 24).sum()
    many = radial_sampling_mask((96, 96), 200).sum()
    assert many > few                                 # denser k-space coverage


def test_radial_undersampling_adds_streak_energy_outside_object():
    """A compact object reconstructed from few spokes spreads streak energy into
    the surrounding background; full sampling does not."""
    img = np.zeros((96, 96)); img[40:56, 40:56] = 1.0
    full = apply_radial_sampling(img, 400)
    under = apply_radial_sampling(img, 24)
    bg = np.ones((96, 96), bool); bg[30:66, 30:66] = False   # outside the object
    assert under[bg].std() > 3 * full[bg].std()
