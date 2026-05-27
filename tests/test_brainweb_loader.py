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

    # Rich multi-class mapping: BrainWeb classes map to these tissue_db labels
    # (CSF/GM/WM/fat/bone + muscle/blood/marrow/dura). Synthetic fallback ⊆ this.
    VALID_LABELS = {0, 1, 2, 3, 4, 5, 6, 11, 14, 15}

    def test_labels_in_range(self):
        phantom, _ = get_brainweb_or_synthetic()
        assert phantom.min() >= 0
        assert set(int(x) for x in np.unique(phantom)).issubset(self.VALID_LABELS)

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
        assert set(int(x) for x in np.unique(phantom)).issubset(
            {0, 1, 2, 3, 4, 5, 6, 11, 14, 15})

    def test_has_multiple_tissues(self):
        phantom = load_brainweb_phantom(subject_num=4)
        assert len(np.unique(phantom)) >= 4

    def test_gm_and_wm_present(self):
        phantom = load_brainweb_phantom(subject_num=4)
        unique = set(int(x) for x in np.unique(phantom))
        assert 2 in unique  # gray matter
        assert 3 in unique  # white matter


# ---------------------------------------------------------------------------
# Branch coverage additions
# ---------------------------------------------------------------------------
class TestLoadBrainwebPhantomCacheMiss:
    """Cover the brainweb download/processing path (lines 15-56) via mocks."""

    def test_processing_path_when_cache_missing(self, monkeypatch):
        """When the cached .npy doesn't exist, the brainweb library is called
        and the full label-remap + save path executes (lines 15-56)."""
        import sys
        import types
        import brainweb_loader as bwl

        # Fake brainweb volume with several BrainWeb-encoded labels
        fake_vol = np.zeros((10, 10, 10), dtype=np.uint8)
        fake_vol[1, :, :] = 16   # CSF
        fake_vol[2, :, :] = 32   # Gray Matter
        fake_vol[3, :, :] = 48   # White Matter
        fake_vol[4, :, :] = 64   # Fat
        fake_vol[5, :, :] = 80   # Muscle
        fake_vol[6, :, :] = 96   # Muscle/Skin
        fake_vol[7, :, :] = 112  # Skull
        fake_vol[8, :, :] = 128  # Vessels
        fake_vol[9, :, :] = 145  # Around fat
        fake_vol[0, :, :] = 177  # Bone marrow

        fake_bw = types.ModuleType("brainweb")
        fake_bw.get_files = lambda: None
        fake_bw.load_file = lambda path: fake_vol
        monkeypatch.setitem(sys.modules, "brainweb", fake_bw)

        # Patch os.path.exists: cache miss, subject file also absent (covers download branch)
        def _exists(path):
            return False  # neither cache nor subject file present

        monkeypatch.setattr(bwl.os.path, "exists", _exists)
        monkeypatch.setattr(bwl.os, "makedirs", lambda *a, **kw: None)
        monkeypatch.setattr(bwl.np, "save", lambda *a, **kw: None)

        phantom = bwl.load_brainweb_phantom(subject_num=99)
        assert phantom.ndim == 3
        assert set(int(x) for x in np.unique(phantom)).issubset(
            {0, 1, 2, 3, 4, 5, 6, 11, 14, 15})


class TestGetBrainwebOrSyntheticFallback:
    def test_falls_back_to_synthetic_on_exception(self, monkeypatch):
        """If load_brainweb_phantom raises, get_brainweb_or_synthetic returns Synthetic."""
        import brainweb_loader as bwl

        def _raise(*a, **kw):
            raise RuntimeError("simulated download failure")

        monkeypatch.setattr(bwl, "load_brainweb_phantom", _raise)
        phantom, source = bwl.get_brainweb_or_synthetic()
        assert source == "Synthetic"
        assert isinstance(phantom, np.ndarray)
        assert phantom.ndim == 3

    def test_fallback_phantom_has_brain_voxels(self, monkeypatch):
        import brainweb_loader as bwl

        monkeypatch.setattr(bwl, "load_brainweb_phantom",
                            lambda *a, **kw: (_ for _ in ()).throw(RuntimeError()))
        phantom, source = bwl.get_brainweb_or_synthetic()
        assert np.sum(phantom > 0) > 10000
