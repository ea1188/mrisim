import numpy as np
import pytest
from brainweb_loader import get_brainweb_or_synthetic, load_brainweb_phantom


class TestGetBrainwebOrSynthetic:
    def test_returns_tuple(self):
        result = get_brainweb_or_synthetic()
        assert isinstance(result, tuple) and len(result) == 2

    def test_returns_ndarray(self):
        phantom, _ = get_brainweb_or_synthetic()
        assert isinstance(phantom, np.ndarray)

    def test_returns_source_string(self):
        _, source = get_brainweb_or_synthetic()
        assert isinstance(source, str)
        assert source in ("BrainWeb", "Synthetic")

    def test_phantom_is_3d(self):
        phantom, _ = get_brainweb_or_synthetic()
        assert phantom.ndim == 3

    def test_labels_in_range(self):
        phantom, _ = get_brainweb_or_synthetic()
        assert phantom.min() >= 0
        assert phantom.max() <= 5

    def test_has_brain_voxels(self):
        phantom, _ = get_brainweb_or_synthetic()
        assert np.sum(phantom > 0) > 10000

    def test_dtype_uint8(self):
        phantom, _ = get_brainweb_or_synthetic()
        assert phantom.dtype == np.uint8


class TestLoadBrainwebPhantom:
    def test_returns_ndarray(self):
        phantom = load_brainweb_phantom(subject_num=4)
        assert isinstance(phantom, np.ndarray)

    def test_is_3d(self):
        phantom = load_brainweb_phantom(subject_num=4)
        assert phantom.ndim == 3

    def test_labels_in_range(self):
        phantom = load_brainweb_phantom(subject_num=4)
        assert set(int(x) for x in np.unique(phantom)).issubset({0, 1, 2, 3, 4, 5})

    def test_has_multiple_tissues(self):
        phantom = load_brainweb_phantom(subject_num=4)
        assert len(np.unique(phantom)) >= 4

    def test_gm_and_wm_present(self):
        phantom = load_brainweb_phantom(subject_num=4)
        unique = set(int(x) for x in np.unique(phantom))
        assert 2 in unique  # gray matter
        assert 3 in unique  # white matter
