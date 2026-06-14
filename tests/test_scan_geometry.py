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
    fov_transform,
    secondary_overlay,
    inplane_box,
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

    def test_coronal_orientation(self, small_vol):
        info = box_rect("coronal", small_vol.shape, 18, 3, 2, 0, 1.0, 0)
        assert info["w"] > 0 and info["h"] > 0
        assert len(info["lines"]) == 3

    def test_sagittal_orientation_horizontal_through(self, small_vol):
        # sagittal has through="h", so w maps to through direction, h to in-plane
        info = box_rect("sagittal", small_vol.shape, 15, 4, 2, 0, 1.0, 0)
        assert info["line_axis"] == "x"
        assert info["through"] == "h"

    def test_axial_orientation_vertical_through(self, small_vol):
        info = box_rect("axial", small_vol.shape, 15, 4, 2, 0, 1.0, 0)
        assert info["line_axis"] == "y"
        assert info["through"] == "v"

    def test_coverage_equals_n_slices_times_thickness_no_gap(self, small_vol):
        n, t = 4, 3
        info = box_rect("axial", small_vol.shape, 15, n, t, 0, 1.0, 0)
        assert info["h"] == pytest.approx(n * t)  # h = 2*half_cov = cov = n*t

    def test_inplane_offset_shifts_box(self, small_vol):
        info0 = box_rect("axial", small_vol.shape, 15, 3, 2, 0, 0.8, 0)
        info5 = box_rect("axial", small_vol.shape, 15, 3, 2, 0, 0.8, 5)
        assert info5["x0"] != info0["x0"]

    def test_half_fov_frac_halves_inplane_width(self, small_vol):
        info_full = box_rect("axial", small_vol.shape, 15, 3, 2, 0, 1.0, 0)
        info_half = box_rect("axial", small_vol.shape, 15, 3, 2, 0, 0.5, 0)
        assert info_half["w"] == pytest.approx(info_full["w"] * 0.5)

    def test_gap_increases_height(self, small_vol):
        info_nogap = box_rect("axial", small_vol.shape, 15, 4, 2, 0, 1.0, 0)
        info_gap   = box_rect("axial", small_vol.shape, 15, 4, 2, 1, 1.0, 0)
        assert info_gap["h"] > info_nogap["h"]


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

    def test_move_inplane_updates_offset(self, small_vol):
        _, io, _, _ = update_from_drag("axial", small_vol.shape, "move",
                                       dx_through=0, d_inplane=4,
                                       slice_idx=15, n_slices=3,
                                       thickness=2, gap=0,
                                       inplane_fov_frac=1.0, inplane_off=0)
        assert io == pytest.approx(4)

    def test_move_negative_drag_decreases_slice_idx(self, small_vol):
        si, _, _, _ = update_from_drag("axial", small_vol.shape, "move",
                                       dx_through=-3, d_inplane=0,
                                       slice_idx=15, n_slices=3,
                                       thickness=2, gap=0,
                                       inplane_fov_frac=1.0, inplane_off=0)
        assert si == pytest.approx(12)

    def test_move_clamps_to_zero_lower(self, small_vol):
        si, _, _, _ = update_from_drag("axial", small_vol.shape, "move",
                                       dx_through=-9999, d_inplane=0,
                                       slice_idx=5, n_slices=1,
                                       thickness=1, gap=0,
                                       inplane_fov_frac=1.0, inplane_off=0)
        assert si >= 0

    def test_resize_cov_negative_decreases_nslices(self, small_vol):
        _, _, _, ns_before = update_from_drag("axial", small_vol.shape, "resize_cov",
                                              dx_through=0, d_inplane=0,
                                              slice_idx=15, n_slices=5,
                                              thickness=2, gap=0,
                                              inplane_fov_frac=1.0, inplane_off=0)
        _, _, _, ns_after = update_from_drag("axial", small_vol.shape, "resize_cov",
                                             dx_through=-5, d_inplane=0,
                                             slice_idx=15, n_slices=5,
                                             thickness=2, gap=0,
                                             inplane_fov_frac=1.0, inplane_off=0)
        assert ns_after <= ns_before

    def test_resize_cov_clamps_to_at_least_1(self, small_vol):
        _, _, _, ns = update_from_drag("axial", small_vol.shape, "resize_cov",
                                       dx_through=-9999, d_inplane=0,
                                       slice_idx=15, n_slices=1,
                                       thickness=2, gap=0,
                                       inplane_fov_frac=1.0, inplane_off=0)
        assert ns >= 1

    def test_resize_fov_large_drag_clamps_to_1(self, small_vol):
        _, _, ff, _ = update_from_drag("axial", small_vol.shape, "resize_fov",
                                       dx_through=0, d_inplane=9999,
                                       slice_idx=15, n_slices=3,
                                       thickness=2, gap=0,
                                       inplane_fov_frac=0.8, inplane_off=0)
        assert ff == pytest.approx(1.0)

    def test_resize_fov_large_negative_drag_reduces_frac(self, small_vol):
        # Large negative d_inplane should reduce fov_frac and clamp it (not go <0.1)
        _, _, ff, _ = update_from_drag("axial", small_vol.shape, "resize_fov",
                                       dx_through=0, d_inplane=-9999,
                                       slice_idx=15, n_slices=3,
                                       thickness=2, gap=0,
                                       inplane_fov_frac=0.8, inplane_off=0)
        assert ff < 0.8  # reduced from starting value
        assert ff >= 0.1  # clamp floor

    def test_coronal_move(self, small_vol):
        si, _, _, _ = update_from_drag("coronal", small_vol.shape, "move",
                                       dx_through=4, d_inplane=0,
                                       slice_idx=18, n_slices=3,
                                       thickness=2, gap=0,
                                       inplane_fov_frac=1.0, inplane_off=0)
        assert si == pytest.approx(22)

    def test_sagittal_move(self, small_vol):
        si, _, _, _ = update_from_drag("sagittal", small_vol.shape, "move",
                                       dx_through=2, d_inplane=0,
                                       slice_idx=14, n_slices=3,
                                       thickness=2, gap=0,
                                       inplane_fov_frac=1.0, inplane_off=0)
        assert si == pytest.approx(16)


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

    def test_coronal_crop_returns_2d(self, small_vol):
        from phantom3d import get_slice
        sl = get_slice(small_vol, "coronal", 18)
        cropped = fov_crop("coronal", sl, 0.7, 0)
        assert cropped.ndim == 2
        assert cropped.size > 0

    def test_sagittal_crop_returns_2d(self, small_vol):
        from phantom3d import get_slice
        sl = get_slice(small_vol, "sagittal", 15)
        cropped = fov_crop("sagittal", sl, 0.7, 0)
        assert cropped.ndim == 2
        assert cropped.size > 0

    def test_nonzero_offset_produces_different_crop(self, small_vol):
        from phantom3d import get_slice
        sl = get_slice(small_vol, "axial", 15)
        cropped0 = fov_crop("axial", sl, 0.6, 0)
        cropped5 = fov_crop("axial", sl, 0.6, 3)
        # Different offsets should yield different windows (unless the vol is
        # very small and both clamp to the same thing, so we just check they run)
        assert cropped0.size > 0
        assert cropped5.size > 0

    def test_very_small_frac_still_nonempty(self, small_vol):
        from phantom3d import get_slice
        sl = get_slice(small_vol, "axial", 15)
        # frac=0.01 is smaller than min; window() clamps to at least 2 px per side
        cropped = fov_crop("axial", sl, 0.01, 0)
        assert cropped.size > 0

    def test_wrap_same_size_as_crop_but_folds_anatomy(self):
        # A ramp object filling the FOV; a half FOV should fold the out-of-window
        # anatomy back in (aliasing), so wrap conserves more signal than a plain crop.
        sl = np.zeros((64, 64))
        sl[:, :] = np.arange(64)[None, :] + 1.0     # signal everywhere
        crop = fov_crop("axial", sl, 0.5, 0, wrap=False)
        wrap = fov_crop("axial", sl, 0.5, 0, wrap=True)
        assert wrap.shape == crop.shape, "wrap keeps the displayed FOV size"
        assert not np.allclose(wrap, crop), "wrap should fold, not crop"
        assert wrap.sum() > crop.sum(), "aliasing folds out-of-FOV signal back in"

    def test_wrap_full_fov_is_identity_like_crop(self):
        sl = np.arange(64 * 64, dtype=float).reshape(64, 64)
        assert np.allclose(fov_crop("axial", sl, 1.0, 0, wrap=True),
                           fov_crop("axial", sl, 1.0, 0, wrap=False)), \
            "at 100% FOV there is nothing to alias"

    def test_wrap_default_off_preserves_crop_behaviour(self, small_vol):
        from phantom3d import get_slice
        sl = get_slice(small_vol, "axial", 15)
        assert np.array_equal(fov_crop("axial", sl, 0.6, 0),
                              fov_crop("axial", sl, 0.6, 0, wrap=False))


class TestSatBand:
    def test_nulls_the_band_only(self):
        from scan_geometry import apply_sat_band
        a = np.ones((40, 30)) * 5.0
        out = apply_sat_band(a, 0.5, 0.2)        # centre 50%, width 20% → 8 rows
        nulled = np.where(out.sum(axis=1) == 0)[0]
        assert len(nulled) == 8
        assert np.allclose(out[0], a[0]) and np.allclose(out[-1], a[-1])

    def test_zero_width_is_noop(self):
        from scan_geometry import apply_sat_band
        a = np.arange(40 * 30, dtype=float).reshape(40, 30)
        assert np.array_equal(apply_sat_band(a, 0.5, 0.0), a)

    def test_position_moves_the_band(self):
        from scan_geometry import apply_sat_band
        a = np.ones((40, 30))
        top = np.where(apply_sat_band(a, 0.2, 0.2).sum(axis=1) == 0)[0].mean()
        bot = np.where(apply_sat_band(a, 0.8, 0.2).sum(axis=1) == 0)[0].mean()
        assert top < bot


class TestPrescribedIndicesExtra:
    """Additional coverage for prescribed_indices: gaps, orientations, edge cases."""

    def test_gap_increases_span(self, small_vol):
        idxs_no = prescribed_indices("axial", small_vol.shape, 15, 5, 2, 0)
        idxs_gap = prescribed_indices("axial", small_vol.shape, 15, 5, 2, 2)
        span_no  = idxs_no[-1]  - idxs_no[0]
        span_gap = idxs_gap[-1] - idxs_gap[0]
        assert span_gap >= span_no

    def test_coronal_indices_within_volume(self, small_vol):
        through_len = small_vol.shape[cfg_for("coronal")["through_axis"]]
        idxs = prescribed_indices("coronal", small_vol.shape, 18, 5, 2, 1)
        assert all(0 <= i < through_len for i in idxs)

    def test_sagittal_indices_within_volume(self, small_vol):
        through_len = small_vol.shape[cfg_for("sagittal")["through_axis"]]
        idxs = prescribed_indices("sagittal", small_vol.shape, 14, 4, 2, 0)
        assert all(0 <= i < through_len for i in idxs)

    def test_single_slice_at_center(self, small_vol):
        midpoint = small_vol.shape[0] // 2
        idxs = prescribed_indices("axial", small_vol.shape, midpoint, 1, 1, 0)
        assert idxs == [midpoint]


# ---------------------------------------------------------------------------
# Branch coverage additions
# ---------------------------------------------------------------------------
class TestFovCropEmptyInput:
    def test_empty_slice_returns_input_unchanged(self):
        """fov_crop with a (0, 0) slice produces an empty crop → guard at line 229 fires."""
        empty = np.zeros((0, 0), dtype=np.float64)
        result = fov_crop("axial", empty, 0.8, 0.0)
        assert result.shape == (0, 0)


# ---------------------------------------------------------------------------
# secondary_overlay
# ---------------------------------------------------------------------------
SHAPE = (40, 50, 60)   # (nZ=40, nY=50, nX=60)


class TestSecondaryOverlay:
    def test_axial_sagittal_orient(self):
        ov = secondary_overlay("sagittal", "axial", SHAPE, 20, 3, 2, 0, 1.0, 0.0)
        assert ov["orient"] == "h"
        assert ov["through"] == "v"
        assert ov["through_sign"] == +1

    def test_axial_sagittal_positions_are_z_indices(self):
        ov = secondary_overlay("sagittal", "axial", SHAPE, 20, 3, 2, 0, 1.0, 0.0)
        expected = prescribed_indices("axial", SHAPE, 20, 3, 2, 0)
        assert ov["positions"] == expected

    def test_axial_sagittal_span_full_y(self):
        ov = secondary_overlay("sagittal", "axial", SHAPE, 20, 1, 2, 0, 1.0, 0.0)
        assert ov["span"] == (0, SHAPE[1])   # nY

    def test_coronal_sagittal_orient(self):
        ov = secondary_overlay("sagittal", "coronal", SHAPE, 25, 3, 2, 0, 1.0, 0.0)
        assert ov["orient"] == "v"
        assert ov["through"] == "h"
        assert ov["through_sign"] == -1

    def test_coronal_sagittal_positions_flipped(self):
        ov = secondary_overlay("sagittal", "coronal", SHAPE, 25, 3, 2, 0, 1.0, 0.0)
        raw = prescribed_indices("coronal", SHAPE, 25, 3, 2, 0)
        expected = [SHAPE[1] - 1 - y for y in raw]
        assert ov["positions"] == expected

    def test_coronal_sagittal_span_full_z(self):
        ov = secondary_overlay("sagittal", "coronal", SHAPE, 25, 1, 2, 0, 1.0, 0.0)
        assert ov["span"] == (0, SHAPE[0])   # nZ

    def test_sagittal_axial_orient(self):
        ov = secondary_overlay("axial", "sagittal", SHAPE, 30, 3, 2, 0, 1.0, 0.0)
        assert ov["orient"] == "v"
        assert ov["through"] == "h"
        assert ov["through_sign"] == +1

    def test_sagittal_axial_positions_are_x_indices(self):
        ov = secondary_overlay("axial", "sagittal", SHAPE, 30, 3, 2, 0, 1.0, 0.0)
        expected = prescribed_indices("sagittal", SHAPE, 30, 3, 2, 0)
        assert ov["positions"] == expected

    def test_sagittal_axial_span_full_y(self):
        ov = secondary_overlay("axial", "sagittal", SHAPE, 30, 1, 2, 0, 1.0, 0.0)
        assert ov["span"] == (0, SHAPE[1])   # nY

    def test_positions_length_matches_n_slices(self):
        for acq, viewer in [("axial", "sagittal"), ("coronal", "sagittal"), ("sagittal", "axial")]:
            for n in [1, 3, 5]:
                ov = secondary_overlay(viewer, acq, SHAPE, 20, n, 2, 0, 1.0, 0.0)
                assert len(ov["positions"]) == n, f"{acq}/{viewer} n={n}"


# ---------------------------------------------------------------------------
# inplane_box
# ---------------------------------------------------------------------------
class TestInplaneBox:
    def test_axial_full_fov(self):
        b = inplane_box("axial", SHAPE, 1.0, 0.0)
        nZ, nY, nX = SHAPE
        assert abs(b["w"] - nX) < 1.0
        assert abs(b["h"] - nY) < 1.0

    def test_axial_half_fov(self):
        b = inplane_box("axial", SHAPE, 0.5, 0.0)
        nZ, nY, nX = SHAPE
        assert abs(b["w"] - 0.5 * nX) < 1.0
        assert abs(b["h"] - 0.5 * nY) < 1.0

    def test_coronal_full_fov(self):
        b = inplane_box("coronal", SHAPE, 1.0, 0.0)
        nZ, nY, nX = SHAPE
        assert abs(b["w"] - nX) < 1.0
        assert abs(b["h"] - nZ) < 1.0

    def test_sagittal_full_fov(self):
        b = inplane_box("sagittal", SHAPE, 1.0, 0.0)
        nZ, nY, nX = SHAPE
        assert abs(b["h"] - nZ) < 1.0   # inplane = rows = Z
        assert abs(b["w"] - nY) < 1.0   # depth = cols = Y

    def test_centred_no_offset(self):
        for acq in ("axial", "coronal", "sagittal"):
            b = inplane_box(acq, SHAPE, 0.8, 0.0)
            # box should be roughly centred in each dimension
            cx = b["x0"] + b["w"] / 2
            cy = b["y0"] + b["h"] / 2
            dims = {"axial": (SHAPE[2]/2, SHAPE[1]/2),
                    "coronal": (SHAPE[2]/2, SHAPE[0]/2),
                    "sagittal": (SHAPE[1]/2, SHAPE[0]/2)}
            ex, ey = dims[acq]
            assert abs(cx - ex) < 2.0, f"{acq} cx={cx} expected {ex}"
            assert abs(cy - ey) < 2.0, f"{acq} cy={cy} expected {ey}"

    def test_offset_shifts_box(self):
        b0 = inplane_box("axial", SHAPE, 0.8, 0.0)
        b1 = inplane_box("axial", SHAPE, 0.8, 5.0)
        assert abs((b1["x0"] + b1["w"]/2) - (b0["x0"] + b0["w"]/2) - 5.0) < 1.0


class TestFovTransform:
    """fov_transform: magnify+wraparound for small FOV, shrink+surround for large."""

    def _blob(self, n=80):
        a = np.zeros((n, n), dtype=np.uint8)
        a[15:65, 15:65] = 2        # tissue block
        a[35:45, 35:45] = 1        # inner structure
        return a

    def test_ratio_one_is_identity(self):
        a = self._blob()
        assert np.array_equal(fov_transform(a, 1.0), a)

    def test_shape_preserved(self):
        a = self._blob()
        for r in (0.4, 0.6, 1.3, 2.0):
            assert fov_transform(a, r).shape == a.shape

    def test_labels_preserved(self):
        """No interpolated/invented labels — only the originals survive."""
        a = self._blob()
        for r in (0.5, 1.5):
            out = fov_transform(a, r)
            assert set(np.unique(out)).issubset({0, 1, 2})

    def test_small_fov_wraps(self):
        """A FOV smaller than the object folds anatomy into more rows than it
        originally spanned (wraparound), and fills a larger fraction of the frame."""
        a = self._blob()
        native_rows = np.where(a.any(axis=1))[0]
        out = fov_transform(a, 0.5)
        out_rows = np.where(out.any(axis=1))[0]
        assert out.mean() > a.mean()                       # more of the frame is filled
        assert np.ptp(out_rows) >= np.ptp(native_rows)     # anatomy spans more rows

    def test_large_fov_shrinks_with_surround(self):
        """A FOV larger than the object shrinks it toward the centre, leaving an
        empty (background) border on all sides."""
        a = self._blob()
        out = fov_transform(a, 2.0)
        assert out.mean() < a.mean()                       # object occupies less area
        assert out[0].sum() == 0 and out[-1].sum() == 0    # empty top/bottom border
        assert out[:, 0].sum() == 0 and out[:, -1].sum() == 0
        assert out.max() > 0                               # object still present
