import numpy as np
import pytest
from scan_geometry import (
    cfg_for,
    depth_index,
    scout_slice,
    prescribed_indices,
    box_rect,
    update_from_drag,
    fov_crop,
    SCOUT,
)
from phantom3d import generate_synthetic_3d_brain


@pytest.fixture(scope="module")
def small_vol():
    return generate_synthetic_3d_brain(nx=30, ny=36, nz=30)


class TestCfgFor:
    def test_axial(self):
        cfg = cfg_for("axial")
        assert cfg["scout"] == "coronal"
        assert cfg["through_axis"] == 0

    def test_coronal(self):
        cfg = cfg_for("coronal")
        assert cfg["scout"] == "axial"
        assert cfg["through_axis"] == 1

    def test_sagittal(self):
        cfg = cfg_for("sagittal")
        assert cfg["scout"] == "coronal"
        assert cfg["through_axis"] == 2

    def test_all_orientations_in_scout(self):
        for acq in ["axial", "coronal", "sagittal"]:
            cfg = cfg_for(acq)
            assert "scout" in cfg
            assert "through_axis" in cfg
            assert "inplane_axis" in cfg
            assert "depth_axis" in cfg


class TestDepthIndex:
    def test_axial_depth_midpoint(self, small_vol):
        d = depth_index("axial", small_vol.shape)
        assert d == small_vol.shape[1] // 2  # depth_axis=1 for axial

    def test_coronal_depth_midpoint(self, small_vol):
        d = depth_index("coronal", small_vol.shape)
        assert d == small_vol.shape[0] // 2  # depth_axis=0 for coronal

    def test_sagittal_depth_midpoint(self, small_vol):
        d = depth_index("sagittal", small_vol.shape)
        assert d == small_vol.shape[1] // 2  # depth_axis=1 for sagittal


class TestScoutSlice:
    def test_returns_tuple(self, small_vol):
        result = scout_slice(small_vol, "axial")
        assert len(result) == 3

    def test_slice_is_2d(self, small_vol):
        sl, cfg, d = scout_slice(small_vol, "axial")
        assert sl.ndim == 2

    def test_cfg_is_dict(self, small_vol):
        _, cfg, _ = scout_slice(small_vol, "axial")
        assert isinstance(cfg, dict)

    def test_depth_in_volume(self, small_vol):
        for acq in ["axial", "coronal", "sagittal"]:
            _, cfg, d = scout_slice(small_vol, acq)
            max_d = small_vol.shape[cfg["depth_axis"]]
            assert 0 <= d < max_d


class TestPrescribedIndices:
    def test_single_slice(self, small_vol):
        idxs = prescribed_indices("axial", small_vol.shape, 15, 1, 1, 0)
        assert len(idxs) == 1

    def test_multiple_slices(self, small_vol):
        idxs = prescribed_indices("axial", small_vol.shape, 15, 5, 1, 0)
        assert len(idxs) == 5

    def test_indices_within_volume(self, small_vol):
        through_len = small_vol.shape[0]
        idxs = prescribed_indices("axial", small_vol.shape, 15, 10, 2, 1)
        assert all(0 <= i < through_len for i in idxs)

    def test_indices_sorted(self, small_vol):
        idxs = prescribed_indices("axial", small_vol.shape, 15, 7, 2, 0)
        assert idxs == sorted(idxs)


class TestBoxRect:
    def test_returns_dict_with_required_keys(self, small_vol):
        info = box_rect("axial", small_vol.shape, 15, 5, 2, 0, 1.0, 0)
        for key in ("x0", "y0", "w", "h", "lines"):
            assert key in info

    def test_width_positive(self, small_vol):
        info = box_rect("axial", small_vol.shape, 15, 5, 2, 0, 1.0, 0)
        assert info["w"] > 0

    def test_height_positive(self, small_vol):
        info = box_rect("axial", small_vol.shape, 15, 5, 2, 0, 1.0, 0)
        assert info["h"] > 0

    def test_lines_count(self, small_vol):
        info = box_rect("axial", small_vol.shape, 15, 5, 2, 0, 1.0, 0)
        assert len(info["lines"]) == 5


class TestUpdateFromDrag:
    def test_move_updates_slice_idx(self, small_vol):
        si, io, ff, ns = update_from_drag("axial", small_vol.shape, "move",
                                          dx_through=3, d_inplane=0,
                                          slice_idx=15, n_slices=5,
                                          thickness=2, gap=0,
                                          inplane_fov_frac=1.0, inplane_off=0)
        assert si == pytest.approx(18)

    def test_move_clamps_to_volume(self, small_vol):
        si, _, _, _ = update_from_drag("axial", small_vol.shape, "move",
                                       dx_through=9999, d_inplane=0,
                                       slice_idx=15, n_slices=1,
                                       thickness=1, gap=0,
                                       inplane_fov_frac=1.0, inplane_off=0)
        through_len = small_vol.shape[0]
        assert 0 <= si <= through_len - 1

    def test_resize_cov_changes_nslices(self, small_vol):
        _, _, _, ns = update_from_drag("axial", small_vol.shape, "resize_cov",
                                       dx_through=5, d_inplane=0,
                                       slice_idx=15, n_slices=5,
                                       thickness=2, gap=0,
                                       inplane_fov_frac=1.0, inplane_off=0)
        assert ns >= 1

    def test_resize_fov_changes_frac(self, small_vol):
        _, _, ff, _ = update_from_drag("axial", small_vol.shape, "resize_fov",
                                       dx_through=0, d_inplane=5,
                                       slice_idx=15, n_slices=5,
                                       thickness=2, gap=0,
                                       inplane_fov_frac=0.8, inplane_off=0)
        assert 0.1 <= ff <= 1.0


class TestFovCrop:
    def test_output_is_2d(self, small_vol):
        from phantom3d import get_slice
        sl = get_slice(small_vol, "axial", 15)
        cropped = fov_crop("axial", sl, 0.8, 0)
        assert cropped.ndim == 2

    def test_full_fov_same_or_smaller(self, small_vol):
        from phantom3d import get_slice
        sl = get_slice(small_vol, "axial", 15)
        cropped = fov_crop("axial", sl, 1.0, 0)
        assert cropped.shape[0] <= sl.shape[0]
        assert cropped.shape[1] <= sl.shape[1]

    def test_half_fov_smaller(self, small_vol):
        from phantom3d import get_slice
        sl = get_slice(small_vol, "axial", 15)
        cropped = fov_crop("axial", sl, 0.5, 0)
        assert cropped.size < sl.size

    def test_never_empty(self, small_vol):
        from phantom3d import get_slice
        for acq in ["axial", "coronal", "sagittal"]:
            sl = get_slice(small_vol, acq, 15)
            cropped = fov_crop(acq, sl, 0.1, 0)
            assert cropped.size > 0
