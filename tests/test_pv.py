"""Tests for partial volume effects simulation (src/pv.py)."""

import numpy as np
import pytest

from pv import (
    tissue_fraction_maps,
    pv_signal_linear,
    simulate_pv_slice,
    simulate_thick_slice,
    boundary_mask,
    fraction_at_boundary,
    pv_correction,
    mean_signal_in_roi,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def two_tissue_map():
    """50x50 label map: left half label 2 (GM), right half label 3 (WM)."""
    m = np.zeros((50, 50), dtype=int)
    m[:, :25] = 2
    m[:, 25:] = 3
    return m


@pytest.fixture
def three_tissue_map():
    """60x60 label map: three horizontal bands — labels 1, 2, 3."""
    m = np.zeros((60, 60), dtype=int)
    m[:20, :] = 1
    m[20:40, :] = 2
    m[40:, :] = 3
    return m


@pytest.fixture
def vol_3d(two_tissue_map):
    """10-slice 3-D volume from the 2-tissue map."""
    return np.stack([two_tissue_map] * 10, axis=0)


SIMPLE_PROPS = {
    2: {"T1": 1330., "T2": 100., "PD": 0.8, "T2star": 60.},
    3: {"T1": 830.,  "T2": 80.,  "PD": 0.65, "T2star": 48.},
}

SINGLE_LABEL_PROPS = {
    5: {"T1": 500., "T2": 50., "PD": 0.7, "T2star": 40.},
}


# ---------------------------------------------------------------------------
# tissue_fraction_maps
# ---------------------------------------------------------------------------

class TestTissueFractionMaps:

    def test_fractions_sum_to_one_sigma0(self, two_tissue_map):
        fracs = tissue_fraction_maps(two_tissue_map, smooth_sigma_vox=0)
        total = sum(fracs.values())
        np.testing.assert_allclose(total, 1.0)

    def test_fractions_sum_to_one_smooth(self, two_tissue_map):
        fracs = tissue_fraction_maps(two_tissue_map, smooth_sigma_vox=1.0)
        total = sum(fracs.values())
        np.testing.assert_allclose(total, 1.0, atol=1e-10)

    def test_sigma0_hard_labels(self, two_tissue_map):
        fracs = tissue_fraction_maps(two_tissue_map, smooth_sigma_vox=0)
        np.testing.assert_array_equal(fracs[2], (two_tissue_map == 2).astype(float))
        np.testing.assert_array_equal(fracs[3], (two_tissue_map == 3).astype(float))

    def test_interior_pure_tissue(self, two_tissue_map):
        fracs = tissue_fraction_maps(two_tissue_map, smooth_sigma_vox=1.0)
        # Centre of label-2 region (col 5) should be almost purely label 2
        assert fracs[2][25, 5] > 0.99

    def test_boundary_mixing(self, two_tissue_map):
        fracs = tissue_fraction_maps(two_tissue_map, smooth_sigma_vox=2.0)
        # Column 24 is at the boundary — neither tissue should dominate fully
        assert fracs[2][25, 24] < 0.95
        assert fracs[3][25, 24] > 0.0

    def test_output_dtype_float64(self, two_tissue_map):
        fracs = tissue_fraction_maps(two_tissue_map, smooth_sigma_vox=1.0)
        for v in fracs.values():
            assert v.dtype == np.float64

    def test_output_shape_preserved(self, two_tissue_map):
        fracs = tissue_fraction_maps(two_tissue_map, smooth_sigma_vox=1.0)
        for v in fracs.values():
            assert v.shape == two_tissue_map.shape

    def test_all_labels_present(self, two_tissue_map):
        fracs = tissue_fraction_maps(two_tissue_map, smooth_sigma_vox=1.0)
        assert set(fracs.keys()) == {2, 3}

    def test_single_tissue(self):
        m = np.full((10, 10), 5, dtype=int)
        fracs = tissue_fraction_maps(m, smooth_sigma_vox=1.0)
        np.testing.assert_allclose(fracs[5], 1.0)

    def test_three_tissue_sum(self, three_tissue_map):
        fracs = tissue_fraction_maps(three_tissue_map, smooth_sigma_vox=1.5)
        total = sum(fracs.values())
        np.testing.assert_allclose(total, 1.0, atol=1e-10)

    def test_fractions_nonnegative(self, two_tissue_map):
        fracs = tissue_fraction_maps(two_tissue_map, smooth_sigma_vox=2.0)
        for v in fracs.values():
            assert np.all(v >= -1e-12)

    def test_fractions_le_one(self, two_tissue_map):
        fracs = tissue_fraction_maps(two_tissue_map, smooth_sigma_vox=2.0)
        for v in fracs.values():
            assert np.all(v <= 1.0 + 1e-12)

    def test_3d_label_map(self):
        m = np.zeros((5, 10, 10), dtype=int)
        m[:, :5, :] = 2
        m[:, 5:, :] = 3
        fracs = tissue_fraction_maps(m, smooth_sigma_vox=1.0)
        total = sum(fracs.values())
        np.testing.assert_allclose(total, 1.0, atol=1e-10)


# ---------------------------------------------------------------------------
# pv_signal_linear
# ---------------------------------------------------------------------------

class TestPvSignalLinear:

    def test_pure_label_2(self):
        fracs = {2: np.ones((5, 5)), 3: np.zeros((5, 5))}
        sig   = {2: 0.8, 3: 0.5}
        out = pv_signal_linear(fracs, sig)
        np.testing.assert_allclose(out, 0.8)

    def test_pure_label_3(self):
        fracs = {2: np.zeros((5, 5)), 3: np.ones((5, 5))}
        sig   = {2: 0.8, 3: 0.5}
        out = pv_signal_linear(fracs, sig)
        np.testing.assert_allclose(out, 0.5)

    def test_equal_mixture(self):
        fracs = {2: np.full((5, 5), 0.5), 3: np.full((5, 5), 0.5)}
        sig   = {2: 0.8, 3: 0.4}
        out = pv_signal_linear(fracs, sig)
        np.testing.assert_allclose(out, 0.6)

    def test_output_dtype(self):
        fracs = {2: np.full((4, 4), 0.5), 3: np.full((4, 4), 0.5)}
        sig   = {2: 0.8, 3: 0.4}
        out = pv_signal_linear(fracs, sig)
        assert out.dtype == np.float64

    def test_output_shape(self):
        fracs = {2: np.full((6, 7), 0.5), 3: np.full((6, 7), 0.5)}
        sig   = {2: 0.8, 3: 0.4}
        out = pv_signal_linear(fracs, sig)
        assert out.shape == (6, 7)

    def test_missing_label_treated_as_zero(self):
        # Label 99 not in signal_per_label → contributes 0
        fracs = {2: np.full((4, 4), 0.5), 99: np.full((4, 4), 0.5)}
        sig   = {2: 0.8}
        out = pv_signal_linear(fracs, sig)
        np.testing.assert_allclose(out, 0.4)

    def test_linearity(self):
        fracs = {2: np.full((4, 4), 0.3), 3: np.full((4, 4), 0.7)}
        sig   = {2: 1.0, 3: 2.0}
        out = pv_signal_linear(fracs, sig)
        np.testing.assert_allclose(out, 0.3 * 1.0 + 0.7 * 2.0)


# ---------------------------------------------------------------------------
# simulate_pv_slice
# ---------------------------------------------------------------------------

class TestSimulatePvSlice:

    def test_output_shape(self, two_tissue_map):
        img = simulate_pv_slice(two_tissue_map, tissue_props=SIMPLE_PROPS)
        assert img.shape == two_tissue_map.shape

    def test_output_dtype(self, two_tissue_map):
        img = simulate_pv_slice(two_tissue_map, tissue_props=SIMPLE_PROPS)
        assert img.dtype == np.float64

    def test_sigma0_matches_hard_signal(self, two_tissue_map):
        from signal_engine import spin_echo_signal
        img = simulate_pv_slice(two_tissue_map, TR_ms=500., TE_ms=15.,
                                sequence="SE", smooth_sigma_vox=0,
                                tissue_props=SIMPLE_PROPS)
        s2 = spin_echo_signal(1330., 100., 0.8, 500., 15.)
        s3 = spin_echo_signal(830.,  80.,  0.65, 500., 15.)
        np.testing.assert_allclose(img[25, 5],  s2, rtol=1e-6)
        np.testing.assert_allclose(img[25, 45], s3, rtol=1e-6)

    def test_blurring_reduces_interior_signal_jump(self, two_tissue_map):
        img0 = simulate_pv_slice(two_tissue_map, smooth_sigma_vox=0,
                                 tissue_props=SIMPLE_PROPS)
        img1 = simulate_pv_slice(two_tissue_map, smooth_sigma_vox=2.0,
                                 tissue_props=SIMPLE_PROPS)
        # At boundary column, the two images should differ
        diff0 = abs(img0[25, 24] - img0[25, 25])
        diff1 = abs(img1[25, 24] - img1[25, 25])
        assert diff1 < diff0

    def test_nonnegative(self, two_tissue_map):
        img = simulate_pv_slice(two_tissue_map, tissue_props=SIMPLE_PROPS)
        assert np.all(img >= 0)

    def test_gre_sequence(self, two_tissue_map):
        img = simulate_pv_slice(two_tissue_map, TR_ms=200., TE_ms=5.,
                                sequence="GRE", flip_angle_deg=30.,
                                smooth_sigma_vox=0, tissue_props=SIMPLE_PROPS)
        from signal_engine import gradient_echo_signal
        s2 = gradient_echo_signal(1330., 60., 0.8, 200., 5., 30.)
        np.testing.assert_allclose(img[25, 5], s2, rtol=1e-6)

    def test_ir_sequence(self, two_tissue_map):
        img = simulate_pv_slice(two_tissue_map, TR_ms=3000., TE_ms=10.,
                                sequence="IR", TI_ms=400.,
                                smooth_sigma_vox=0, tissue_props=SIMPLE_PROPS)
        from signal_engine import inversion_recovery_signal
        s2 = inversion_recovery_signal(1330., 100., 0.8, 3000., 10., 400.)
        np.testing.assert_allclose(img[25, 5], s2, rtol=1e-6)

    def test_unknown_sequence_raises(self, two_tissue_map):
        with pytest.raises(ValueError, match="Unknown sequence"):
            simulate_pv_slice(two_tissue_map, sequence="INVALID",
                              tissue_props=SIMPLE_PROPS)

    def test_interior_pure_tissue_unchanged_by_smoothing(self, two_tissue_map):
        """Deep interior pixels should be essentially unaffected by mild PSF."""
        img0 = simulate_pv_slice(two_tissue_map, smooth_sigma_vox=0,
                                 tissue_props=SIMPLE_PROPS)
        img1 = simulate_pv_slice(two_tissue_map, smooth_sigma_vox=1.0,
                                 tissue_props=SIMPLE_PROPS)
        # Column 5 is 20 voxels from the boundary — should be stable
        np.testing.assert_allclose(img1[25, 5], img0[25, 5], rtol=0.01)


# ---------------------------------------------------------------------------
# simulate_thick_slice
# ---------------------------------------------------------------------------

class TestSimulateThickSlice:

    def test_output_shape(self, vol_3d):
        img = simulate_thick_slice(vol_3d, center_z=5,
                                   tissue_props=SIMPLE_PROPS)
        assert img.shape == vol_3d.shape[1:]

    def test_output_dtype(self, vol_3d):
        img = simulate_thick_slice(vol_3d, center_z=5,
                                   tissue_props=SIMPLE_PROPS)
        assert img.dtype == np.float64

    def test_single_plane_matches_2d(self, two_tissue_map):
        vol = np.stack([two_tissue_map] * 5, axis=0)
        thick = simulate_thick_slice(vol, center_z=2, slice_thickness_vox=1,
                                     tissue_props=SIMPLE_PROPS)
        thin  = simulate_pv_slice(two_tissue_map, smooth_sigma_vox=0,
                                  tissue_props=SIMPLE_PROPS)
        np.testing.assert_allclose(thick, thin, rtol=1e-6)

    def test_uniform_volume_unchanged_by_averaging(self):
        """If all slices are identical, averaging should return same signal."""
        m = np.full((10, 30, 30), 2, dtype=int)
        img5 = simulate_thick_slice(m, center_z=5, slice_thickness_vox=5,
                                    tissue_props=SIMPLE_PROPS)
        img1 = simulate_thick_slice(m, center_z=5, slice_thickness_vox=1,
                                    tissue_props=SIMPLE_PROPS)
        np.testing.assert_allclose(img5, img1, rtol=1e-6)

    def test_rect_vs_gauss_differ_at_boundary(self):
        """Rect and Gauss profiles should produce different results when slices differ."""
        nz = 20
        vol = np.zeros((nz, 20, 20), dtype=int)
        # Abrupt transition at z=10
        vol[:10, :, :] = 2
        vol[10:, :, :] = 3
        img_rect  = simulate_thick_slice(vol, center_z=10, slice_thickness_vox=6,
                                         slice_profile="rect",
                                         tissue_props=SIMPLE_PROPS)
        img_gauss = simulate_thick_slice(vol, center_z=10, slice_thickness_vox=6,
                                          slice_profile="gauss",
                                          tissue_props=SIMPLE_PROPS)
        assert not np.allclose(img_rect, img_gauss)

    def test_z_clipping_no_crash(self, vol_3d):
        # center at boundary — should not raise
        img = simulate_thick_slice(vol_3d, center_z=0, slice_thickness_vox=5,
                                   tissue_props=SIMPLE_PROPS)
        assert img.shape == vol_3d.shape[1:]

    def test_nonnegative(self, vol_3d):
        img = simulate_thick_slice(vol_3d, center_z=5,
                                   tissue_props=SIMPLE_PROPS)
        assert np.all(img >= 0)

    def test_weights_sum_to_one_gauss(self):
        """Gauss profile weights must be normalised (uniform volume → same signal)."""
        m = np.full((20, 10, 10), 3, dtype=int)
        img_g = simulate_thick_slice(m, center_z=10, slice_thickness_vox=7,
                                     slice_profile="gauss",
                                     tissue_props=SIMPLE_PROPS)
        img_r = simulate_thick_slice(m, center_z=10, slice_thickness_vox=7,
                                     slice_profile="rect",
                                     tissue_props=SIMPLE_PROPS)
        np.testing.assert_allclose(img_g, img_r, rtol=1e-6)


# ---------------------------------------------------------------------------
# boundary_mask
# ---------------------------------------------------------------------------

def _gapped_map():
    """30x30 map: label 2 on left, background gap, label 3 on right.

    boundary_mask finds voxels near BOTH labels but not assigned to either.
    For directly adjacent tissues every voxel belongs to one label, so a
    background gap is required to produce a non-empty result.

    Gap width (cols 10-15, 6 cols) < 2 × dilation_vox=4 → the two dilated
    regions overlap inside the gap.
    """
    m = np.zeros((30, 30), dtype=int)
    m[:, :10] = 2    # cols  0-9
    m[:, 16:] = 3    # cols 16-29
    # cols 10-15 are background (label 0) — the boundary zone
    return m


class TestBoundaryMask:

    def test_contains_interface_voxels(self):
        m = _gapped_map()
        mask = boundary_mask(m, 2, 3, dilation_vox=4)
        # The background zone (cols 10-15) should contain boundary voxels
        assert mask[:, 10:16].any()

    def test_not_pure_tissue(self):
        m = _gapped_map()
        mask = boundary_mask(m, 2, 3, dilation_vox=4)
        # Deep interior of either tissue should NOT be in the mask
        assert not mask[:, :5].any()
        assert not mask[:, 25:].any()

    def test_no_overlap_with_pure_a(self):
        m = _gapped_map()
        mask = boundary_mask(m, 2, 3, dilation_vox=4)
        assert not np.any(mask & (m == 2))

    def test_no_overlap_with_pure_b(self):
        m = _gapped_map()
        mask = boundary_mask(m, 2, 3, dilation_vox=4)
        assert not np.any(mask & (m == 3))

    def test_non_adjacent_labels_empty(self):
        m = np.zeros((20, 20), dtype=int)
        m[:10, :] = 1
        m[10:, :] = 5
        # Labels 2 and 3 are not present → empty mask
        mask = boundary_mask(m, 2, 3, dilation_vox=1)
        assert not mask.any()

    def test_boolean_output(self):
        m = _gapped_map()
        mask = boundary_mask(m, 2, 3, dilation_vox=4)
        assert mask.dtype == bool

    def test_larger_dilation_expands_mask(self):
        m = _gapped_map()
        mask1 = boundary_mask(m, 2, 3, dilation_vox=3)
        mask2 = boundary_mask(m, 2, 3, dilation_vox=4)
        assert mask2.sum() >= mask1.sum()

    def test_3d_label_map(self):
        # Gap cols 8-13 (width 6) < 2 × dilation_vox=4 → overlap exists
        m = np.zeros((10, 20, 30), dtype=int)
        m[:, :, :8]  = 2    # cols  0-7
        m[:, :, 14:] = 3    # cols 14-29
        # cols 8-13 are background — within reach of dilation_vox=4 from both sides
        mask = boundary_mask(m, 2, 3, dilation_vox=4)
        assert mask.shape == (10, 20, 30)
        assert mask.any()


# ---------------------------------------------------------------------------
# fraction_at_boundary
# ---------------------------------------------------------------------------

class TestFractionAtBoundary:

    def test_return_shapes(self, two_tissue_map):
        f_a, f_b, bnd = fraction_at_boundary(two_tissue_map, 2, 3)
        assert f_a.shape == two_tissue_map.shape
        assert f_b.shape == two_tissue_map.shape
        assert bnd.shape == two_tissue_map.shape

    def test_bnd_mask_boolean(self, two_tissue_map):
        _, _, bnd = fraction_at_boundary(two_tissue_map, 2, 3)
        assert bnd.dtype == bool

    def test_fractions_at_boundary_sum_near_one(self, two_tissue_map):
        f_a, f_b, bnd = fraction_at_boundary(two_tissue_map, 2, 3,
                                              smooth_sigma_vox=1.0)
        # At the boundary voxels, f_a + f_b should approach 1
        if bnd.any():
            total = f_a[bnd] + f_b[bnd]
            assert np.all(total > 0.5)

    def test_deep_interior_f_a_near_one(self, two_tissue_map):
        f_a, _, _ = fraction_at_boundary(two_tissue_map, 2, 3,
                                          smooth_sigma_vox=1.0)
        assert f_a[25, 5] > 0.99

    def test_missing_label_returns_zeros(self):
        m = np.full((10, 10), 2, dtype=int)
        # Label 99 absent → f_b = zeros
        _, f_b, _ = fraction_at_boundary(m, 2, 99)
        np.testing.assert_array_equal(f_b, 0.0)


# ---------------------------------------------------------------------------
# pv_correction
# ---------------------------------------------------------------------------

class TestPvCorrection:

    def test_pure_target_unchanged(self):
        """Where f_target=1, corrected = measured (no contamination)."""
        fracs = {2: np.ones((5, 5)), 3: np.zeros((5, 5))}
        meas  = np.full((5, 5), 0.8)
        sig   = {2: 0.8, 3: 0.4}
        corr  = pv_correction(meas, fracs, sig, target_label=2)
        np.testing.assert_allclose(corr, meas, rtol=1e-6)

    def test_roundtrip_recovers_pure_signal(self):
        """Simulate mixed signal then correct back to pure."""
        fracs = {2: np.full((5, 5), 0.6), 3: np.full((5, 5), 0.4)}
        sig   = {2: 0.8, 3: 0.4}
        # Forward: mixed signal
        mixed = 0.6 * 0.8 + 0.4 * 0.4   # = 0.64
        meas  = np.full((5, 5), mixed)
        corr  = pv_correction(meas, fracs, sig, target_label=2)
        np.testing.assert_allclose(corr, 0.8, atol=1e-6)

    def test_zero_target_fraction_returns_measured(self):
        """Where f_target=0, output = measured (no valid correction possible)."""
        fracs = {2: np.zeros((5, 5)), 3: np.ones((5, 5))}
        meas  = np.full((5, 5), 0.4)
        sig   = {2: 0.8, 3: 0.4}
        corr  = pv_correction(meas, fracs, sig, target_label=2)
        np.testing.assert_allclose(corr, meas, rtol=1e-6)

    def test_output_dtype(self):
        fracs = {2: np.full((4, 4), 0.7), 3: np.full((4, 4), 0.3)}
        meas  = np.full((4, 4), 0.6)
        sig   = {2: 0.8, 3: 0.4}
        corr  = pv_correction(meas, fracs, sig, target_label=2)
        assert corr.dtype == np.float64

    def test_output_shape(self):
        fracs = {2: np.full((3, 4), 0.7), 3: np.full((3, 4), 0.3)}
        meas  = np.full((3, 4), 0.6)
        sig   = {2: 0.8, 3: 0.4}
        corr  = pv_correction(meas, fracs, sig, target_label=2)
        assert corr.shape == (3, 4)

    def test_correction_moves_toward_pure_signal(self):
        """Corrected signal should be closer to pure target than measured."""
        fracs = {2: np.full((5, 5), 0.7), 3: np.full((5, 5), 0.3)}
        sig   = {2: 1.0, 3: 0.0}
        mixed = np.full((5, 5), 0.7)
        corr  = pv_correction(mixed, fracs, sig, target_label=2)
        assert abs(float(corr[0, 0]) - 1.0) < abs(float(mixed[0, 0]) - 1.0)

    def test_missing_target_label_uses_zero_fraction(self):
        """Target label absent from fracs → treated as f=0, returns measured."""
        fracs = {3: np.ones((4, 4))}
        meas  = np.full((4, 4), 0.5)
        sig   = {2: 0.8, 3: 0.4}
        corr  = pv_correction(meas, fracs, sig, target_label=2)
        np.testing.assert_allclose(corr, meas, rtol=1e-6)


# ---------------------------------------------------------------------------
# mean_signal_in_roi
# ---------------------------------------------------------------------------

class TestMeanSignalInRoi:

    def test_matches_hard_mask_mean(self, two_tissue_map):
        img = simulate_pv_slice(two_tissue_map, smooth_sigma_vox=0,
                                tissue_props=SIMPLE_PROPS)
        expected = float(img[two_tissue_map == 2].mean())
        result   = mean_signal_in_roi(img, two_tissue_map, label=2)
        np.testing.assert_allclose(result, expected, rtol=1e-6)

    def test_purity_filter_excludes_boundary(self, two_tissue_map):
        img   = simulate_pv_slice(two_tissue_map, smooth_sigma_vox=1.0,
                                  tissue_props=SIMPLE_PROPS)
        fracs = tissue_fraction_maps(two_tissue_map, smooth_sigma_vox=1.0)
        # Without purity filter — includes boundary voxels
        mean_all    = mean_signal_in_roi(img, two_tissue_map, label=2)
        # With high purity filter — only deep interior
        mean_pure   = mean_signal_in_roi(img, two_tissue_map, label=2,
                                         fractions=fracs, min_fraction=0.99)
        # Pure signal should be closer to the no-PVE signal
        img0 = simulate_pv_slice(two_tissue_map, smooth_sigma_vox=0,
                                 tissue_props=SIMPLE_PROPS)
        ref  = float(img0[two_tissue_map == 2].mean())
        assert abs(mean_pure - ref) <= abs(mean_all - ref) + 1e-6

    def test_empty_roi_returns_zero(self, two_tissue_map):
        img = simulate_pv_slice(two_tissue_map, tissue_props=SIMPLE_PROPS)
        result = mean_signal_in_roi(img, two_tissue_map, label=99)
        assert result == 0.

    def test_output_is_float(self, two_tissue_map):
        img = simulate_pv_slice(two_tissue_map, tissue_props=SIMPLE_PROPS)
        result = mean_signal_in_roi(img, two_tissue_map, label=2)
        assert isinstance(result, float)

    def test_purity_empty_roi_returns_zero(self, two_tissue_map):
        img   = simulate_pv_slice(two_tissue_map, tissue_props=SIMPLE_PROPS)
        fracs = {2: np.zeros_like(img), 3: np.ones_like(img)}
        result = mean_signal_in_roi(img, two_tissue_map, label=2,
                                    fractions=fracs, min_fraction=0.9)
        assert result == 0.

    def test_3d_signal_and_labels(self):
        m = np.zeros((5, 10, 10), dtype=int)
        m[:, :5, :] = 2
        m[:, 5:, :] = 3
        img = np.random.default_rng(0).random((5, 10, 10))
        result = mean_signal_in_roi(img, m, label=2)
        expected = float(img[m == 2].mean())
        np.testing.assert_allclose(result, expected, rtol=1e-6)
