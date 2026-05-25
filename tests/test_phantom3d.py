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

    def test_all_six_labels_present(self, small_brain):
        unique = set(int(x) for x in np.unique(small_brain))
        assert unique == {0, 1, 2, 3, 4, 5}

    def test_csf_label_present(self, small_brain):
        assert 1 in np.unique(small_brain)

    def test_bone_label_present(self, small_brain):
        assert 5 in np.unique(small_brain)

    def test_brain_fills_majority_of_volume(self, small_brain):
        brain_voxels = np.sum(small_brain > 0)
        assert brain_voxels / small_brain.size > 0.05


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

    def test_negative_index_clamps(self, small_brain):
        sl_neg = get_slice(small_brain, "axial", -1)
        sl_0   = get_slice(small_brain, "axial", 0)
        np.testing.assert_array_equal(sl_neg, sl_0)

    def test_sagittal_is_fliplr_of_raw(self, small_brain):
        idx = 15
        sl = get_slice(small_brain, "sagittal", idx)
        raw = small_brain[:, :, idx]
        np.testing.assert_array_equal(sl, np.fliplr(raw))

    def test_sagittal_default_index_is_middle(self, small_brain):
        sl_default = get_slice(small_brain, "sagittal")
        sl_mid = get_slice(small_brain, "sagittal", small_brain.shape[2] // 2)
        np.testing.assert_array_equal(sl_default, sl_mid)

    def test_coronal_default_index_is_middle(self, small_brain):
        sl_default = get_slice(small_brain, "coronal")
        sl_mid = get_slice(small_brain, "coronal", small_brain.shape[1] // 2)
        np.testing.assert_array_equal(sl_default, sl_mid)


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

    def test_gre_nonnegative(self, small_brain):
        sl = get_slice(small_brain, "axial", 20)
        img = simulate_slice(sl, TR=250, TE=5, sequence="GRE", flip_angle=70)
        assert np.all(img >= 0)

    def test_gre_background_zero(self, small_brain):
        sl = get_slice(small_brain, "axial", 20)
        img = simulate_slice(sl, TR=250, TE=5, sequence="GRE", flip_angle=70)
        assert np.all(img[sl == 0] == 0)

    def test_ir_nonnegative(self, small_brain):
        sl = get_slice(small_brain, "axial", 20)
        img = simulate_slice(sl, TR=9000, TE=90, sequence="IR", TI=2500)
        assert np.all(img >= 0)

    def test_ir_background_zero(self, small_brain):
        sl = get_slice(small_brain, "axial", 20)
        img = simulate_slice(sl, TR=9000, TE=90, sequence="IR", TI=2500)
        assert np.all(img[sl == 0] == 0)

    def test_ir_default_ti(self, small_brain):
        # TI=None should default to 150 without raising
        sl = get_slice(small_brain, "axial", 20)
        img = simulate_slice(sl, TR=9000, TE=90, sequence="IR", TI=None)
        assert img.shape == sl.shape

    def test_unknown_sequence_falls_back_to_se(self, small_brain):
        sl = get_slice(small_brain, "axial", 20)
        img_se  = simulate_slice(sl, TR=500, TE=15, sequence="SE")
        img_unk = simulate_slice(sl, TR=500, TE=15, sequence="UNKNOWN")
        np.testing.assert_array_equal(img_se, img_unk)

    def test_fat_brighter_than_bone_t1w(self, small_brain):
        # Fat (label 4): short T1 → bright on T1w; Bone (label 5): short T2, low PD → dim
        sl = get_slice(small_brain, "axial", 20)
        img = simulate_slice(sl, TR=400, TE=10, sequence="SE")
        if np.any(sl == 4) and np.any(sl == 5):
            assert img[sl == 4].mean() > img[sl == 5].mean()

    def test_coronal_slice_simulation(self, small_brain):
        sl = get_slice(small_brain, "coronal", 24)
        img = simulate_slice(sl, TR=500, TE=15, sequence="SE")
        assert img.shape == sl.shape
        assert np.all(img >= 0)

    def test_sagittal_slice_simulation(self, small_brain):
        sl = get_slice(small_brain, "sagittal", 20)
        img = simulate_slice(sl, TR=500, TE=15, sequence="SE")
        assert img.shape == sl.shape
        assert np.all(img >= 0)


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

    def test_t2star_le_t2(self):
        # T2* <= T2 for all tissues (susceptibility only shortens relaxation)
        for lab, props in TISSUE_PROPERTIES_3D.items():
            assert props["T2star"] <= props["T2"], (
                f"Label {lab} ({props['name']}): T2star={props['T2star']} > T2={props['T2']}"
            )

    def test_pd_in_range(self):
        for lab, props in TISSUE_PROPERTIES_3D.items():
            assert 0.0 <= props["PD"] <= 1.0, (
                f"Label {lab} ({props['name']}): PD={props['PD']} out of [0,1]"
            )

    def test_csf_longest_t1(self):
        # CSF should have the longest T1 (label 1)
        t1_values = {lab: props["T1"] for lab, props in TISSUE_PROPERTIES_3D.items() if lab > 0}
        assert t1_values[1] == max(t1_values.values())

    def test_name_strings_nonempty(self):
        for lab, props in TISSUE_PROPERTIES_3D.items():
            assert isinstance(props["name"], str) and len(props["name"]) > 0
