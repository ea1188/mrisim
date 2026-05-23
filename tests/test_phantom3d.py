import numpy as np
import pytest
from phantom3d import (
    generate_synthetic_3d_brain,
    get_slice,
    simulate_slice,
    TISSUE_PROPERTIES_3D,
)


@pytest.fixture(scope="module")
def small_brain():
    # Smaller than default to keep tests fast
    return generate_synthetic_3d_brain(nx=40, ny=48, nz=40)


class TestGenerateSyntheticBrain:
    def test_default_shape(self, small_brain):
        assert small_brain.shape == (40, 48, 40)

    def test_dtype_uint8(self, small_brain):
        assert small_brain.dtype == np.uint8

    def test_labels_in_range(self, small_brain):
        assert small_brain.min() >= 0
        assert small_brain.max() <= 5

    def test_has_multiple_tissues(self, small_brain):
        unique = set(np.unique(small_brain).tolist())
        assert len(unique) >= 3

    def test_wm_inside_gm(self, small_brain):
        # WM voxels should exist inside the brain
        assert 3 in np.unique(small_brain)

    def test_background_on_edges(self, small_brain):
        assert small_brain[0, 0, 0] == 0


class TestGetSlice:
    def test_axial_shape(self, small_brain):
        sl = get_slice(small_brain, "axial", 20)
        assert sl.shape == (48, 40)  # rows=Y(ny), cols=X(nz)

    def test_coronal_shape(self, small_brain):
        sl = get_slice(small_brain, "coronal", 24)
        assert sl.shape == (40, 40)  # rows=Z(nx), cols=X(nz)

    def test_sagittal_shape(self, small_brain):
        sl = get_slice(small_brain, "sagittal", 20)
        assert sl.shape == (40, 48)  # rows=Z(nx), cols=Y(ny)

    def test_default_index_is_middle(self, small_brain):
        sl_default = get_slice(small_brain, "axial")
        sl_mid = get_slice(small_brain, "axial", 20)
        np.testing.assert_array_equal(sl_default, sl_mid)

    def test_clamping_out_of_bounds(self, small_brain):
        # Indices beyond volume should clamp, not raise
        sl = get_slice(small_brain, "axial", 9999)
        assert sl is not None

    def test_returns_2d(self, small_brain):
        for orient in ["axial", "coronal", "sagittal"]:
            sl = get_slice(small_brain, orient, 10)
            assert sl.ndim == 2


class TestSimulateSlice:
    def test_se_output_shape(self, small_brain):
        sl = get_slice(small_brain, "axial", 20)
        img = simulate_slice(sl, TR=500, TE=15, sequence="SE")
        assert img.shape == sl.shape

    def test_gre_output_shape(self, small_brain):
        sl = get_slice(small_brain, "axial", 20)
        img = simulate_slice(sl, TR=250, TE=5, sequence="GRE", flip_angle=70)
        assert img.shape == sl.shape

    def test_ir_output_shape(self, small_brain):
        sl = get_slice(small_brain, "axial", 20)
        img = simulate_slice(sl, TR=9000, TE=90, sequence="IR", TI=2500)
        assert img.shape == sl.shape

    def test_se_nonnegative(self, small_brain):
        sl = get_slice(small_brain, "axial", 20)
        img = simulate_slice(sl, TR=500, TE=15, sequence="SE")
        assert np.all(img >= 0)

    def test_background_zero(self, small_brain):
        sl = get_slice(small_brain, "axial", 20)
        img = simulate_slice(sl, TR=500, TE=15, sequence="SE")
        bg_mask = sl == 0
        assert np.all(img[bg_mask] == 0)

    def test_t2_weighted_csf_brighter_than_wm(self, small_brain):
        sl = get_slice(small_brain, "axial", 20)
        img = simulate_slice(sl, TR=4000, TE=100, sequence="SE")
        if np.any(sl == 1) and np.any(sl == 3):
            assert img[sl == 1].mean() > img[sl == 3].mean()


class TestTissueProperties3D:
    def test_required_keys(self):
        for lab, props in TISSUE_PROPERTIES_3D.items():
            for key in ("T1", "T2", "PD", "T2star", "name"):
                assert key in props

    def test_background_pd_zero(self):
        assert TISSUE_PROPERTIES_3D[0]["PD"] == 0.0

    def test_all_values_positive(self):
        for lab, props in TISSUE_PROPERTIES_3D.items():
            assert props["T1"] > 0
            assert props["T2"] > 0
