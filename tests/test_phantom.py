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
