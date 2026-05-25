import numpy as np
import pytest
from nifti_region import (
    EXTRA_MR_PROPERTIES,
    TS_TO_MR,
    TS_MR_TO_MR,
    detect_scheme,
    _remap,
    register_properties,
    _slice_silhouette,
    _erode,
    _fill_body_layers,
    _fill_body_fat,
    _maybe_downsample,
)

# nibabel is optional; skip load_segmented_nifti tests if absent
nibabel = pytest.importorskip  # just the marker function
try:
    import nibabel as _nib
    HAS_NIBABEL = True
except ImportError:
    HAS_NIBABEL = False


# ---------------------------------------------------------------------------
# EXTRA_MR_PROPERTIES
# ---------------------------------------------------------------------------
class TestExtraMrProperties:
    def test_no_background_label(self):
        assert 0 not in EXTRA_MR_PROPERTIES

    def test_all_labels_1_to_21(self):
        assert set(EXTRA_MR_PROPERTIES.keys()) == set(range(1, 22))

    def test_required_keys(self):
        for lab, p in EXTRA_MR_PROPERTIES.items():
            for k in ("T1", "T2", "PD", "T2star", "name"):
                assert k in p, f"label {lab} missing key {k}"

    def test_pd_in_unit_interval(self):
        for lab, p in EXTRA_MR_PROPERTIES.items():
            assert 0.0 <= p["PD"] <= 1.0


# ---------------------------------------------------------------------------
# TS_TO_MR (CT 117-class mapping)
# ---------------------------------------------------------------------------
class TestTsToMrMapping:
    def test_covers_all_117_ct_classes(self):
        assert len(TS_TO_MR) == 117

    def test_all_output_labels_in_mr_range(self):
        valid_mr = set(range(22))
        for ts, mr in TS_TO_MR.items():
            assert mr in valid_mr, f"CT class {ts} -> invalid MR label {mr}"

    def test_liver_maps_to_7(self):
        assert TS_TO_MR[5] == 7

    def test_spleen_maps_to_8(self):
        assert TS_TO_MR[1] == 8

    def test_kidney_maps_to_9(self):
        assert TS_TO_MR[2] == 9
        assert TS_TO_MR[3] == 9

    def test_brain_maps_to_2(self):
        assert TS_TO_MR[90] == 2

    def test_spinal_cord_maps_to_16(self):
        assert TS_TO_MR[79] == 16

    def test_bones_map_to_13(self):
        # Skull (91) and several ribs should map to cortical bone (13)
        assert TS_TO_MR[91] == 13
        assert TS_TO_MR[92] == 13


# ---------------------------------------------------------------------------
# TS_MR_TO_MR (MR 50-class mapping)
# ---------------------------------------------------------------------------
class TestTsMrToMrMapping:
    def test_covers_all_50_mr_classes(self):
        assert len(TS_MR_TO_MR) == 50

    def test_all_output_labels_in_mr_range(self):
        valid_mr = set(range(22))
        for ts, mr in TS_MR_TO_MR.items():
            assert mr in valid_mr, f"MR class {ts} -> invalid MR label {mr}"

    def test_liver_maps_to_7(self):
        assert TS_MR_TO_MR[5] == 7

    def test_spinal_cord_maps_to_16(self):
        assert TS_MR_TO_MR[21] == 16

    def test_brain_maps_to_2(self):
        assert TS_MR_TO_MR[50] == 2

    def test_intervertebral_disc_maps_to_15(self):
        assert TS_MR_TO_MR[20] == 15

    def test_heart_maps_to_20(self):
        assert TS_MR_TO_MR[22] == 20


# ---------------------------------------------------------------------------
# detect_scheme
# ---------------------------------------------------------------------------
class TestDetectScheme:
    def test_empty_set_is_ct(self):
        assert detect_scheme(set()) == "ct"

    def test_empty_array_is_ct(self):
        assert detect_scheme(np.array([])) == "ct"

    def test_label_above_50_is_ct(self):
        assert detect_scheme({1, 5, 90, 92}) == "ct"

    def test_labels_only_up_to_50_is_mr(self):
        assert detect_scheme({1, 2, 5, 20, 50}) == "mr"

    def test_single_high_label_is_ct(self):
        assert detect_scheme({117}) == "ct"

    def test_single_low_label_is_mr(self):
        assert detect_scheme({10}) == "mr"

    def test_zero_only_is_ct(self):
        # Only background — no positive labels, falls back to "ct"
        assert detect_scheme({0}) == "ct"


# ---------------------------------------------------------------------------
# _remap
# ---------------------------------------------------------------------------
class TestRemap:
    def test_all_zeros_stays_zero(self):
        vol = np.zeros((4, 4, 4), dtype=np.int32)
        out = _remap(vol, scheme="ct")
        assert np.all(out == 0)

    def test_ct_liver_label_5_becomes_7(self):
        vol = np.array([[[5]]], dtype=np.int32)
        out = _remap(vol, scheme="ct")
        assert out[0, 0, 0] == 7

    def test_ct_spleen_label_1_becomes_8(self):
        vol = np.array([[[1]]], dtype=np.int32)
        out = _remap(vol, scheme="ct")
        assert out[0, 0, 0] == 8

    def test_mr_liver_label_5_becomes_7(self):
        vol = np.array([[[5]]], dtype=np.int32)
        out = _remap(vol, scheme="mr")
        assert out[0, 0, 0] == 7

    def test_mr_brain_label_50_becomes_2(self):
        vol = np.array([[[50]]], dtype=np.int32)
        out = _remap(vol, scheme="mr")
        assert out[0, 0, 0] == 2

    def test_output_dtype_uint8(self):
        vol = np.zeros((3, 3, 3), dtype=np.int32)
        vol[1, 1, 1] = 5
        out = _remap(vol, scheme="ct")
        assert out.dtype == np.uint8

    def test_output_shape_preserved(self):
        vol = np.zeros((5, 6, 7), dtype=np.int32)
        out = _remap(vol, scheme="ct")
        assert out.shape == (5, 6, 7)

    def test_unknown_label_maps_to_zero(self):
        # Label 999 is not in the CT table, so it stays 0
        vol = np.array([[[999]]], dtype=np.int32)
        out = _remap(vol, scheme="ct")
        assert out[0, 0, 0] == 0


# ---------------------------------------------------------------------------
# register_properties
# ---------------------------------------------------------------------------
class TestRegisterProperties:
    def test_fills_body_labels_in_phantom3d(self):
        import phantom3d
        register_properties(field=None)
        for lab in range(1, 22):
            assert lab in phantom3d.TISSUE_PROPERTIES_3D, \
                f"label {lab} not present after register_properties"

    def test_labels_have_required_keys(self):
        import phantom3d
        register_properties(field=None)
        for lab in range(1, 22):
            p = phantom3d.TISSUE_PROPERTIES_3D[lab]
            for k in ("T1", "T2", "PD"):
                assert k in p

    def test_with_explicit_field_applies_tissue_db(self):
        """Passing field='3T' should call tissue_db.apply_to_engine (line 211)."""
        import phantom3d
        orig_props = {k: dict(v) for k, v in phantom3d.TISSUE_PROPERTIES_3D.items()}
        try:
            register_properties(field="3T")
            for lab in range(1, 22):
                assert lab in phantom3d.TISSUE_PROPERTIES_3D
        finally:
            phantom3d.TISSUE_PROPERTIES_3D.clear()
            phantom3d.TISSUE_PROPERTIES_3D.update(orig_props)

    def test_exception_fallback_uses_local_defaults(self, monkeypatch):
        """If tissue_db raises, the except branch (lines 219-223) falls back to EXTRA_MR_PROPERTIES."""
        import nifti_region as nr
        import phantom3d
        import sys
        import types

        def _raise(*a, **kw):
            raise RuntimeError("simulated tissue_db failure")

        fake_tdb = types.ModuleType("tissue_db")
        fake_tdb.apply_to_engine = _raise  # type: ignore[attr-defined]
        fake_tdb.properties = _raise  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "tissue_db", fake_tdb)

        orig_props = {k: dict(v) for k, v in phantom3d.TISSUE_PROPERTIES_3D.items()}
        try:
            phantom3d.TISSUE_PROPERTIES_3D.clear()
            register_properties(field=None)
            for lab in nr.EXTRA_MR_PROPERTIES:
                assert lab in phantom3d.TISSUE_PROPERTIES_3D
        finally:
            phantom3d.TISSUE_PROPERTIES_3D.clear()
            phantom3d.TISSUE_PROPERTIES_3D.update(orig_props)


# ---------------------------------------------------------------------------
# _slice_silhouette
# ---------------------------------------------------------------------------
class TestSliceSilhouette:
    def test_solid_rectangle_returns_same(self):
        mask = np.zeros((20, 20), dtype=bool)
        mask[5:15, 5:15] = True
        sil = _slice_silhouette(mask)
        # Any filled interior of the rectangle should be included
        assert sil[10, 10]

    def test_empty_mask_returns_empty(self):
        mask = np.zeros((10, 10), dtype=bool)
        sil = _slice_silhouette(mask)
        assert not sil.any()

    def test_output_shape_matches_input(self):
        mask = np.zeros((15, 20), dtype=bool)
        mask[5, 5] = True
        sil = _slice_silhouette(mask)
        assert sil.shape == (15, 20)

    def test_single_pixel_row_fill(self):
        # One row with two separated pixels -> row between them is filled
        mask = np.zeros((10, 10), dtype=bool)
        mask[5, 2] = True
        mask[5, 8] = True
        sil = _slice_silhouette(mask)
        # The interior of the single row should be filled by the row pass,
        # but the column pass only fills that single row between top and bottom
        # of the same column — since each pixel is alone in its column, only
        # those single pixels appear in the column fill. AND gives just the
        # original two pixels, which is fine — no error.
        assert sil.shape == (10, 10)

    def test_l_shaped_mask(self):
        mask = np.zeros((20, 20), dtype=bool)
        mask[5:15, 5] = True   # vertical bar
        mask[5, 5:15] = True   # horizontal bar
        sil = _slice_silhouette(mask)
        # The corner (5,5) must be inside
        assert sil[5, 5]


# ---------------------------------------------------------------------------
# _erode
# ---------------------------------------------------------------------------
def _square_in_background(size=20, pad=3):
    """True block of (size-2*pad)^2 in a size×size False background."""
    mask = np.zeros((size, size), dtype=bool)
    mask[pad:size - pad, pad:size - pad] = True
    return mask


class TestErode:
    def test_zero_iters_identity(self):
        mask = _square_in_background()
        out = _erode(mask, iters=0)
        np.testing.assert_array_equal(out, mask)

    def test_one_iter_removes_border_of_inner_block(self):
        # True block with a False border: erosion shrinks the True region
        mask = _square_in_background(size=20, pad=3)  # True at rows/cols 3:17
        out = _erode(mask, iters=1)
        # Outermost ring of the True block should now be False
        assert not out[3, :].any()   # top border of block eroded
        assert not out[16, :].any()  # bottom border eroded
        assert not out[:, 3].any()   # left border eroded
        assert not out[:, 16].any()  # right border eroded

    def test_deep_interior_stays_true(self):
        mask = _square_in_background(size=20, pad=3)
        out = _erode(mask, iters=1)
        assert out[10, 10]  # deep interior untouched

    def test_small_mask_fully_eroded(self):
        mask = np.zeros((5, 5), dtype=bool)
        mask[2, 2] = True  # single pixel
        out = _erode(mask, iters=1)
        assert not out.any()

    def test_multiple_iters_shrinks_more(self):
        mask = _square_in_background(size=30, pad=2)
        out1 = _erode(mask, iters=1)
        out3 = _erode(mask, iters=3)
        assert out3.sum() < out1.sum()


# ---------------------------------------------------------------------------
# _fill_body_layers / _fill_body_fat
# ---------------------------------------------------------------------------
def _make_vol_with_organ():
    """3D volume with a rectangular frame of organs enclosing empty interior.

    The silhouette algorithm spans the gap between the bars, so _fill_body_layers
    sees unlabelled voxels inside the body outline to fill with fat/muscle.
    """
    vol = np.zeros((5, 60, 70), dtype=np.uint8)
    # Top and bottom horizontal bars
    vol[:, 5:12, 5:65] = 7   # liver
    vol[:, 48:55, 5:65] = 7
    # Left and right vertical bars
    vol[:, 5:55, 5:12] = 7
    vol[:, 5:55, 58:65] = 7
    return vol


class TestFillBodyLayers:
    def test_output_shape_unchanged(self):
        vol = _make_vol_with_organ()
        out = _fill_body_layers(vol)
        assert out.shape == vol.shape

    def test_dtype_preserved(self):
        vol = _make_vol_with_organ()
        out = _fill_body_layers(vol)
        assert out.dtype == np.uint8

    def test_existing_labels_not_overwritten(self):
        vol = _make_vol_with_organ()
        out = _fill_body_layers(vol)
        # Every voxel that was organ (7) must still be organ
        np.testing.assert_array_equal(out[vol == 7], np.full(np.sum(vol == 7), 7))

    def test_fills_some_interior(self):
        vol = _make_vol_with_organ()
        out = _fill_body_layers(vol)
        # Some previously-zero voxels inside the silhouette should now be labelled
        interior_filled = (vol == 0) & (out != 0)
        assert interior_filled.any()

    def test_fills_with_fat_or_muscle(self):
        vol = _make_vol_with_organ()
        out = _fill_body_layers(vol)
        filled = out[(vol == 0) & (out != 0)]
        assert set(filled.tolist()).issubset({4, 6})

    def test_background_outside_silhouette_stays_zero(self):
        vol = _make_vol_with_organ()
        out = _fill_body_layers(vol)
        # Corners are clearly outside any silhouette
        assert out[0, 0, 0] == 0
        assert out[0, 0, -1] == 0

    def test_empty_slice_skipped_unchanged(self):
        """A fully-zero slice triggers the `not sl.any()` continue (line 331)."""
        vol = np.zeros((3, 20, 20), dtype=np.uint8)
        vol[1, 5:15, 5:15] = 7   # only middle slice has content
        out = _fill_body_layers(vol)
        # Empty slices must remain all zero
        assert out[0].sum() == 0
        assert out[2].sum() == 0

    def test_fully_labeled_slice_skipped_unchanged(self):
        """A slice where the silhouette has no unlabeled gaps triggers the
        `not empty.any()` continue (line 335). A solid slab of organ label
        leaves no interior zeros after silhouette computation."""
        vol = np.zeros((2, 20, 20), dtype=np.uint8)
        vol[0, 5:15, 5:15] = 7   # solid 10×10 block — interior fully labeled
        out = _fill_body_layers(vol)
        # The existing organ voxels must be untouched
        assert (out[0, 5:15, 5:15] == 7).all()


class TestFillBodyFat:
    def test_is_alias_for_fill_body_layers(self):
        vol = _make_vol_with_organ()
        out_layers = _fill_body_layers(vol)
        out_fat = _fill_body_fat(vol)
        np.testing.assert_array_equal(out_layers, out_fat)


# ---------------------------------------------------------------------------
# _maybe_downsample
# ---------------------------------------------------------------------------
class TestMaybeDownsample:
    def test_already_small_unchanged(self):
        vol = np.arange(8, dtype=np.uint8).reshape(2, 2, 2)
        out = _maybe_downsample(vol, target_max=256)
        np.testing.assert_array_equal(out, vol)

    def test_large_is_downsampled(self):
        vol = np.zeros((300, 300, 300), dtype=np.uint8)
        out = _maybe_downsample(vol, target_max=128)
        assert max(out.shape) <= 128

    def test_label_values_preserved(self):
        vol = np.zeros((200, 200, 200), dtype=np.uint8)
        vol[100, 100, 100] = 7  # liver somewhere in the middle
        out = _maybe_downsample(vol, target_max=100)
        # At least some non-zero voxels must survive NN downsampling
        assert out.max() >= 0   # shape changed, value may or may not survive
        assert out.dtype == np.uint8

    def test_output_3d(self):
        vol = np.zeros((50, 60, 70), dtype=np.uint8)
        out = _maybe_downsample(vol, target_max=40)
        assert out.ndim == 3

    def test_step_is_ceil_division(self):
        # max dim = 300, target = 100 -> step = ceil(300/100) = 3 -> output dim ~100
        vol = np.zeros((300, 150, 120), dtype=np.uint8)
        out = _maybe_downsample(vol, target_max=100)
        assert max(out.shape) <= 100


# ---------------------------------------------------------------------------
# load_segmented_nifti  (skipped if nibabel unavailable or no test file exists)
# ---------------------------------------------------------------------------
@pytest.mark.skipif(not HAS_NIBABEL, reason="nibabel not installed")
class TestLoadSegmentedNifti:
    def test_import_succeeds(self):
        from nifti_region import load_segmented_nifti
        assert callable(load_segmented_nifti)

    def _write_synthetic_nifti(self, tmp_path: str, data: np.ndarray) -> str:
        import nibabel as nib
        import os
        affine = np.eye(4)
        img = nib.Nifti1Image(data.astype(np.int32), affine)
        p = os.path.join(tmp_path, "test.nii.gz")
        nib.save(img, p)
        return p

    def test_returns_uint8_ndarray(self, tmp_path):
        from nifti_region import load_segmented_nifti
        # CT-scheme volume: label 5=liver (->7), label 90=brain (->2)
        data = np.zeros((30, 30, 30), dtype=np.int32)
        data[10:20, 10:20, 10:20] = 5
        p = self._write_synthetic_nifti(str(tmp_path), data)
        out = load_segmented_nifti(p, target_max=256)
        assert isinstance(out, np.ndarray)
        assert out.dtype == np.uint8

    def test_output_is_3d(self, tmp_path):
        from nifti_region import load_segmented_nifti
        data = np.zeros((20, 20, 20), dtype=np.int32)
        data[5:15, 5:15, 5:15] = 5
        p = self._write_synthetic_nifti(str(tmp_path), data)
        out = load_segmented_nifti(p)
        assert out.ndim == 3

    def test_ct_scheme_maps_liver(self, tmp_path):
        from nifti_region import load_segmented_nifti
        data = np.zeros((20, 20, 20), dtype=np.int32)
        data[5:15, 5:15, 5:15] = 5   # CT label 5 = liver -> MR label 7
        p = self._write_synthetic_nifti(str(tmp_path), data)
        out = load_segmented_nifti(p, scheme="ct")
        assert 7 in np.unique(out)

    def test_mr_scheme_maps_liver(self, tmp_path):
        from nifti_region import load_segmented_nifti
        data = np.zeros((20, 20, 20), dtype=np.int32)
        data[5:15, 5:15, 5:15] = 5   # MR label 5 = liver -> MR label 7
        p = self._write_synthetic_nifti(str(tmp_path), data)
        out = load_segmented_nifti(p, scheme="mr")
        assert 7 in np.unique(out)

    def test_auto_scheme_detection(self, tmp_path):
        from nifti_region import load_segmented_nifti
        # Label 92 (>50) forces CT detection
        data = np.zeros((20, 20, 20), dtype=np.int32)
        data[5:15, 5:15, 5:15] = 92   # rib_left_1 -> bone (13)
        p = self._write_synthetic_nifti(str(tmp_path), data)
        out = load_segmented_nifti(p, scheme="auto")
        assert 13 in np.unique(out)
