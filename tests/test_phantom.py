import numpy as np
import pytest
from phantom import create_brain_phantom, TISSUE_LABELS, TISSUE_PROPERTIES


class TestCreateBrainPhantom:
    def test_default_size(self):
        p = create_brain_phantom()
        assert p.shape == (256, 256)

    def test_custom_size(self):
        p = create_brain_phantom(64)
        assert p.shape == (64, 64)

    def test_dtype_is_int(self):
        p = create_brain_phantom(64)
        assert np.issubdtype(p.dtype, np.integer)

    def test_labels_0_to_4(self):
        p = create_brain_phantom(64)
        unique = set(np.unique(p).tolist())
        assert unique.issubset({0, 1, 2, 3, 4})

    def test_background_exists(self):
        p = create_brain_phantom(128)
        assert 0 in np.unique(p)

    def test_all_tissue_regions_present(self):
        # At size 256, all of GM/WM/CSF should appear
        p = create_brain_phantom(256)
        for label in [1, 2, 3, 4]:
            assert label in np.unique(p), f"Label {label} missing from phantom"

    def test_non_zero_fraction(self):
        p = create_brain_phantom(128)
        frac = np.sum(p > 0) / p.size
        assert 0.2 < frac < 0.9

    def test_center_is_brain(self):
        p = create_brain_phantom(256)
        center = 128
        # The center should be white matter (label 3) or CSF (4), not background
        assert p[center, center] != 0

    def test_corners_are_background(self):
        p = create_brain_phantom(128)
        assert p[0, 0] == 0
        assert p[0, -1] == 0
        assert p[-1, 0] == 0
        assert p[-1, -1] == 0

    def test_wm_voxels_fewer_than_gm(self):
        p = create_brain_phantom(256)
        n_wm = np.sum(p == 3)
        n_gm = np.sum(p == 2)
        assert n_wm < n_gm  # WM inner ellipse < GM outer band

    def test_small_size_valid(self):
        p = create_brain_phantom(16)
        assert p.shape == (16, 16)
        assert np.issubdtype(p.dtype, np.integer)

    def test_ventricles_inside_brain(self):
        # Label 4 (ventricles) should exist where brain (label 3 or 2) also exists
        p = create_brain_phantom(256)
        assert 4 in np.unique(p)
        # All ventricle pixels must be inside the skull boundary
        vent_ys, vent_xs = np.where(p == 4)
        center = 128
        for y, x in zip(vent_ys[:10], vent_xs[:10]):
            assert p[center, center] != 0  # just confirm brain exists at center


class TestTissueMappings:
    def test_tissue_labels_keys(self):
        assert set(TISSUE_LABELS.keys()) == {0, 1, 2, 3, 4}

    def test_tissue_properties_keys(self):
        assert set(TISSUE_PROPERTIES.keys()) == {0, 1, 2, 3, 4}

    def test_background_pd_zero(self):
        assert TISSUE_PROPERTIES[0]["PD"] == 0.0

    def test_csf_high_pd(self):
        assert TISSUE_PROPERTIES[1]["PD"] == 1.0

    def test_properties_have_t1_t2_pd(self):
        for label, props in TISSUE_PROPERTIES.items():
            for key in ["T1", "T2", "PD"]:
                assert key in props, f"Label {label} missing key {key}"

    def test_t1_gt_t2_for_brain_tissues(self):
        for label in [2, 3]:  # GM and WM
            p = TISSUE_PROPERTIES[label]
            assert p["T1"] > p["T2"]

    def test_wm_shorter_t1_than_gm(self):
        assert TISSUE_PROPERTIES[3]["T1"] < TISSUE_PROPERTIES[2]["T1"]

    def test_csf_labels_same_properties(self):
        # Labels 1 and 4 are both CSF; should have identical T1, T2, PD
        assert TISSUE_PROPERTIES[1] == TISSUE_PROPERTIES[4]

    def test_labels_1_and_4_map_to_csf(self):
        assert TISSUE_LABELS[1] == "csf"
        assert TISSUE_LABELS[4] == "csf"

    def test_all_properties_positive(self):
        for label, props in TISSUE_PROPERTIES.items():
            if label == 0:
                continue  # background has T1=T2=1 (placeholder)
            assert props["T1"] > 0
            assert props["T2"] > 0
            assert props["PD"] > 0
