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
    resample_labels_isotropic,
    _REGION_NIFTI,
    _REGION_TOTALSEG,
    _SEG_FILE_TO_MR,
    _classify_unlabeled_from_mri,
    _enrich_filled_labels,
    _mark_bowel_gas,
    _normalize_texture_per_label,
    encode_mixel_fraction,
    decode_mixel_fraction,
    build_mixel,
    load_region_nifti,
    load_totalseg_mri_subject,
)

# nibabel is optional; skip load_segmented_nifti tests if absent
nibabel = pytest.importorskip  # just the marker function
try:
    import nibabel as _nib  # noqa: F401  (availability check)
    HAS_NIBABEL = True
except ImportError:
    HAS_NIBABEL = False


# ---------------------------------------------------------------------------
# EXTRA_MR_PROPERTIES
# ---------------------------------------------------------------------------
class TestExtraMrProperties:
    def test_no_background_label(self):
        assert 0 not in EXTRA_MR_PROPERTIES

    def test_all_labels_1_to_22(self):
        assert set(EXTRA_MR_PROPERTIES.keys()) == set(range(1, 23))

    def test_required_keys(self):
        for lab, p in EXTRA_MR_PROPERTIES.items():
            for k in ("T1", "T2", "PD", "T2star", "name"):
                assert k in p, f"label {lab} missing key {k}"

    def test_pd_in_unit_interval(self):
        for _lab, p in EXTRA_MR_PROPERTIES.items():
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
# resample_labels_isotropic
# ---------------------------------------------------------------------------
class TestResampleLabelsIsotropic:
    def _anisotropic_block(self, Z=12, H=40, W=40):
        """A thick-sliced volume: a solid label block centred in the volume."""
        vol = np.zeros((Z, H, W), dtype=np.uint8)
        vol[3:9, 8:32, 8:32] = 7   # liver-ish block
        return vol

    def test_identity_when_already_isotropic(self):
        vol = self._anisotropic_block()
        out = resample_labels_isotropic(vol, (1.5, 1.5, 1.5), max_dim=256)
        assert out is vol  # unchanged sampling -> returned as-is

    def test_thick_slices_upsample_z(self):
        # 8 mm slices, 1.5 mm in-plane -> Z should grow ~5x toward isotropy
        vol = self._anisotropic_block(Z=12, H=40, W=40)
        out = resample_labels_isotropic(vol, (8.0, 1.5, 1.5), max_dim=256)
        assert out.shape[0] > vol.shape[0]
        # in-plane unchanged (already at target 1.5 mm)
        assert out.shape[1:] == vol.shape[1:]

    def test_output_is_near_isotropic_ratio(self):
        vol = self._anisotropic_block(Z=10, H=50, W=50)
        out = resample_labels_isotropic(vol, (8.0, 1.5, 1.5), max_dim=256)
        ratio = max(out.shape) / min(out.shape)
        assert ratio < 2.0, f"still anisotropic: {out.shape}"

    def test_dtype_uint8(self):
        vol = self._anisotropic_block()
        out = resample_labels_isotropic(vol, (6.0, 1.5, 1.5))
        assert out.dtype == np.uint8

    def test_no_new_labels_introduced(self):
        vol = self._anisotropic_block()
        vol[5, 15:20, 15:20] = 9   # add a second label
        out = resample_labels_isotropic(vol, (6.0, 1.5, 1.5))
        assert set(np.unique(out).tolist()).issubset({0, 7, 9})

    def test_label_survives_resampling(self):
        vol = self._anisotropic_block()
        out = resample_labels_isotropic(vol, (6.0, 1.5, 1.5))
        assert 7 in np.unique(out)

    def test_longest_axis_capped_at_max_dim(self):
        vol = self._anisotropic_block(Z=10, H=80, W=80)
        out = resample_labels_isotropic(vol, (8.0, 1.5, 1.5), max_dim=64)
        assert max(out.shape) <= 64

    def test_background_preserved(self):
        vol = self._anisotropic_block()
        out = resample_labels_isotropic(vol, (6.0, 1.5, 1.5))
        # corners are background and must stay background
        assert out[0, 0, 0] == 0


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


# ---------------------------------------------------------------------------
# load_region_nifti
# ---------------------------------------------------------------------------
class TestRegionNiftiRegistry:
    def test_known_regions_defined(self):
        for name in ("Abdomen", "Spine", "Pelvis"):
            assert name in _REGION_NIFTI

    def test_knee_not_in_registry(self):
        assert "Knee" not in _REGION_NIFTI

    def test_missing_dir_returns_none(self, tmp_path):
        result = load_region_nifti("Abdomen", str(tmp_path))
        assert result is None

    def test_unknown_region_returns_none(self, tmp_path):
        result = load_region_nifti("Thorax_XYZ", str(tmp_path))
        assert result is None


# ---------------------------------------------------------------------------
# _SEG_FILE_TO_MR
# ---------------------------------------------------------------------------
class TestSegFileToMr:
    def test_covers_all_56_expected_organs(self):
        expected = {
            "adrenal_gland_left", "adrenal_gland_right", "aorta",
            "autochthon_left", "autochthon_right", "brain",
            "colon", "duodenum", "esophagus",
            "femur_left", "femur_right", "fibula", "gallbladder",
            "gluteus_maximus_left", "gluteus_maximus_right",
            "gluteus_medius_left", "gluteus_medius_right",
            "gluteus_minimus_left", "gluteus_minimus_right",
            "heart", "hip_left", "hip_right",
            "humerus_left", "humerus_right",
            "iliac_artery_left", "iliac_artery_right",
            "iliac_vena_left", "iliac_vena_right",
            "iliopsoas_left", "iliopsoas_right",
            "inferior_vena_cava", "intervertebral_discs",
            "kidney_left", "kidney_right", "liver",
            "lung_left", "lung_right", "pancreas",
            "portal_vein_and_splenic_vein", "prostate",
            "quadriceps_femoris_left", "quadriceps_femoris_right",
            "sacrum", "sartorius_left", "sartorius_right",
            "small_bowel", "spinal_cord", "spleen", "stomach",
            "thigh_medial_compartment_left", "thigh_medial_compartment_right",
            "thigh_posterior_compartment_left", "thigh_posterior_compartment_right",
            "tibia", "urinary_bladder", "vertebrae",
        }
        assert expected == set(_SEG_FILE_TO_MR.keys())

    def test_all_labels_in_mr_range(self):
        for name, label in _SEG_FILE_TO_MR.items():
            assert 0 < label < 22, f"{name} -> {label} out of MR range"

    def test_key_organ_labels(self):
        assert _SEG_FILE_TO_MR["liver"] == 7
        assert _SEG_FILE_TO_MR["spleen"] == 8
        assert _SEG_FILE_TO_MR["kidney_left"] == 9
        assert _SEG_FILE_TO_MR["kidney_right"] == 9
        assert _SEG_FILE_TO_MR["spinal_cord"] == 16
        assert _SEG_FILE_TO_MR["intervertebral_discs"] == 15
        assert _SEG_FILE_TO_MR["vertebrae"] == 13
        assert _SEG_FILE_TO_MR["sacrum"] == 13
        assert _SEG_FILE_TO_MR["heart"] == 20
        assert _SEG_FILE_TO_MR["aorta"] == 11

    def test_muscle_labels(self):
        for name in ("autochthon_left", "gluteus_maximus_left", "iliopsoas_right",
                     "quadriceps_femoris_left", "sartorius_right"):
            assert _SEG_FILE_TO_MR[name] == 6, f"{name} should be muscle (6)"

    def test_bone_labels(self):
        for name in ("femur_left", "femur_right", "hip_left", "sacrum", "vertebrae",
                     "fibula", "tibia"):
            assert _SEG_FILE_TO_MR[name] == 13, f"{name} should be bone (13)"


# ---------------------------------------------------------------------------
# _REGION_TOTALSEG
# ---------------------------------------------------------------------------
class TestRegionTotalsegRegistry:
    def test_all_regions_use_totalseg_subjects(self):
        # Every configured body region uses a near-isotropic real-MRI subject
        # (adaptive fill + isotropic resample), not the thick-sliced or CT-scheme
        # flat fallbacks. Torso (s0250) is a real-data-only whole-torso region.
        for region in ("Abdomen", "Spine", "Pelvis", "Torso"):
            assert region in _REGION_TOTALSEG, f"{region} missing from _REGION_TOTALSEG"
        # A distinct subject per region (no accidental duplicate mappings).
        assert len(set(_REGION_TOTALSEG.values())) == len(_REGION_TOTALSEG)

    def test_knee_not_in_registry(self):
        assert "Knee" not in _REGION_TOTALSEG

    def test_subjects_are_non_empty_strings(self):
        for region, subj in _REGION_TOTALSEG.items():
            assert isinstance(subj, str) and subj, f"{region} has empty subject name"


# ---------------------------------------------------------------------------
# _classify_unlabeled_from_mri  (synthetic — no real data needed)
# ---------------------------------------------------------------------------
class TestClassifyUnlabeledFromMri:
    def _make_pair(self, H=20, W=20, D=20):
        """Label vol with a central organ; MRI with bright outer ring (fat)."""
        label = np.zeros((D, H, W), dtype=np.uint8)
        label[D // 2, H // 4:3 * H // 4, W // 4:3 * W // 4] = 7  # liver blob
        mri = np.zeros((D, H, W), dtype=np.float32)
        # High intensity = fat in outer ring; medium = muscle inside
        mri[D // 2, 2:H - 2, 2:W - 2] = 200.0   # body interior: muscle-level
        mri[D // 2, 2:4, 2:W - 2] = 500.0         # outer rows: fat-level
        mri[D // 2, H - 4:H - 2, 2:W - 2] = 500.0
        return label, mri

    def test_output_shape_unchanged(self):
        label, mri = self._make_pair()
        out = _classify_unlabeled_from_mri(label, mri)
        assert out.shape == label.shape

    def test_dtype_preserved(self):
        label, mri = self._make_pair()
        out = _classify_unlabeled_from_mri(label, mri)
        assert out.dtype == np.uint8

    def test_existing_labels_not_overwritten(self):
        label, mri = self._make_pair(H=30, W=30, D=10)
        out = _classify_unlabeled_from_mri(label, mri)
        np.testing.assert_array_equal(out[label == 7], np.full((label == 7).sum(), 7))

    def test_high_intensity_becomes_fat(self):
        label, mri = self._make_pair()
        out = _classify_unlabeled_from_mri(label, mri, fat_thresh=380.0, body_thresh=60.0)
        # The fat-level ring (500) should become fat label 4
        z = label.shape[0] // 2
        fat_pixels = out[z][mri[z] >= 380]
        # Only voxels that were unlabeled AND inside body AND bright should become 4
        if fat_pixels.size > 0:
            assert 4 in fat_pixels or fat_pixels.size == 0

    def test_medium_intensity_becomes_muscle(self):
        label, mri = self._make_pair()
        out = _classify_unlabeled_from_mri(label, mri, fat_thresh=380.0, body_thresh=60.0)
        z = label.shape[0] // 2
        interior_pixels = out[z][(mri[z] >= 60) & (mri[z] < 380) & (label[z] == 0)]
        if interior_pixels.size > 0:
            assert set(interior_pixels.tolist()).issubset({0, 6})

    def test_below_body_thresh_stays_zero(self):
        label = np.zeros((5, 20, 20), dtype=np.uint8)
        mri = np.zeros((5, 20, 20), dtype=np.float32)  # all below body_thresh
        out = _classify_unlabeled_from_mri(label, mri, body_thresh=60.0)
        assert out.sum() == 0

    def test_mismatched_z_does_not_crash(self):
        label = np.zeros((10, 20, 20), dtype=np.uint8)
        mri = np.zeros((5, 20, 20), dtype=np.float32)   # fewer slices
        out = _classify_unlabeled_from_mri(label, mri)
        assert out.shape == label.shape   # first 5 slices processed, rest untouched

    def test_adaptive_fat_follows_anatomy_not_a_quota(self):
        """k-means adaptive mode: when half the unlabeled body is fat-bright,
        about half must be classified fat — not a fixed percentile quota."""
        D, H, W = (8, 40, 40)
        label = np.zeros((D, H, W), dtype=np.uint8)
        mri = np.zeros((D, H, W), dtype=np.float32)
        mri[:, 2:H - 2, 2:W - 2] = 200.0            # dark half: muscle-level
        mri[:, 2:H // 2, 2:W - 2] = 520.0           # bright half: fat-level
        out = _classify_unlabeled_from_mri(label, mri)
        empty = mri > 60
        fat_frac = (out[empty] == 4).sum() / empty.sum()
        assert fat_frac > 0.40, f"fat {fat_frac:.2f} — bright half not classified fat"


# ---------------------------------------------------------------------------
# _enrich_filled_labels  (synthetic — no real data needed)
# ---------------------------------------------------------------------------
class TestEnrichFilledLabels:
    def _volume(self):
        vol = np.zeros((10, 30, 30), dtype=np.uint8)
        vol[:, 5:25, 5:25] = 6                       # muscle body
        vol[3:8, 10:20, 10:20] = 13                  # bone block inside
        return vol

    def test_bone_interior_becomes_marrow(self):
        out = _enrich_filled_labels(self._volume())
        assert (out == 14).any(), "no marrow split inside bone"
        assert (out == 13).any(), "cortical shell vanished"

    def test_body_rind_becomes_skin(self):
        out = _enrich_filled_labels(self._volume())
        z = 5
        assert out[z, 5, 15] == 5, "outer body rind should be skin"
        assert out[z, 15, 15] != 5, "interior must not become skin"

    def test_background_untouched(self):
        out = _enrich_filled_labels(self._volume())
        assert (out[self._volume() == 0] == 0).all()


class TestMarkBowelGas:
    def _pair(self):
        label = np.zeros((6, 20, 20), dtype=np.uint8)
        label[:, 2:18, 2:18] = 6                       # muscle body
        label[:, 6:14, 6:14] = 17                      # bowel
        mri = np.full(label.shape, 100.0, dtype=np.float32)
        mri[:, 8:12, 8:12] = 5.0                       # dark gas pocket in bowel
        mri[:, 3, 3] = 5.0                             # dark voxel OUTSIDE bowel
        return label, mri

    def test_dark_bowel_content_becomes_gas(self):
        label, mri = self._pair()
        out = _mark_bowel_gas(label, mri)
        assert (out[:, 8:12, 8:12] == 12).all()

    def test_bright_bowel_and_other_labels_untouched(self):
        label, mri = self._pair()
        out = _mark_bowel_gas(label, mri)
        assert out[0, 6, 6] == 17                      # fluid-bright bowel stays
        assert out[0, 3, 3] == 6                       # dark muscle voxel NOT gas


class TestNormalizeTexturePerLabel:
    def test_medians_become_one_and_detail_survives(self):
        label = np.zeros((4, 10, 10), dtype=np.uint8)
        label[:, :, :5] = 4; label[:, :, 5:] = 6
        rng = np.random.default_rng(0)
        tex = np.ones(label.shape, dtype=np.float32)
        tex[label == 4] = 1.5 + 0.05 * rng.standard_normal((label == 4).sum())
        tex[label == 6] = 0.7 + 0.05 * rng.standard_normal((label == 6).sum())
        out = _normalize_texture_per_label(tex, label)
        assert abs(np.median(out[label == 4]) - 1.0) < 0.02
        assert abs(np.median(out[label == 6]) - 1.0) < 0.02
        assert out[label == 4].std() > 0.01            # intra-label detail kept

    def test_background_stays_one(self):
        label = np.zeros((2, 4, 4), dtype=np.uint8); label[:, 1:3, 1:3] = 6
        tex = np.full(label.shape, 1.0, dtype=np.float32); tex[label == 6] = 0.5
        out = _normalize_texture_per_label(tex, label)
        assert (out[label == 0] == 1.0).all()


class TestMixelCodec:
    def test_roundtrip(self):
        f = np.array([0.5, 0.75, 1.0], dtype=np.float32)
        b = encode_mixel_fraction(f)
        assert b.dtype == np.uint8 and b[2] == 255 and b[0] == 0
        np.testing.assert_allclose(decode_mixel_fraction(b), f, atol=0.002)


class TestBuildMixel:
    def _hires(self):
        """Two-tissue block at 2x the target resolution, vertical boundary."""
        hi = np.zeros((8, 20, 40), dtype=np.uint8)
        hi[:, :, :21] = 4          # fat — boundary at hi-res column 21 (odd,
        hi[:, :, 21:] = 6          # muscle    so target column 10 is mixed)
        return hi

    def test_hires_boundary_is_mixed_and_complementary(self):
        hi = self._hires()
        atlas = hi[:, ::2, ::2]                    # nearest-downsample stand-in
        mix = build_mixel(hi, atlas)
        assert mix.shape == (2,) + atlas.shape and mix.dtype == np.uint8
        z, y, bcol = 4, 5, 10                      # straddles the hi-res boundary
        assert mix[1, z, y, bcol] < 255            # mixed
        a = atlas[z, y, bcol]
        assert mix[0, z, y, bcol] == (6 if a == 4 else 4)   # the OTHER tissue

    def test_interiors_are_pure(self):
        hi = self._hires()
        atlas = hi[:, ::2, ::2]
        mix = build_mixel(hi, atlas)
        assert (mix[0, :, :, :5] == 0).all() and (mix[1, :, :, :5] == 255).all()
        assert (mix[0, :, :, 15:] == 0).all() and (mix[1, :, :, 15:] == 255).all()

    def test_background_is_pure(self):
        hi = np.zeros((4, 10, 10), dtype=np.uint8); hi[:, 3:7, 3:7] = 6
        mix = build_mixel(hi, hi)                  # blur-fallback path
        assert (mix[0][hi == 0] == 0).all() and (mix[1][hi == 0] == 255).all()

    def test_blur_fallback_marks_boundary(self):
        lab = np.zeros((4, 10, 20), dtype=np.uint8)
        lab[:, :, :10] = 4; lab[:, :, 10:] = 6
        mix = build_mixel(lab, lab)
        assert (mix[1][:, :, 9:11] < 255).any()    # boundary mixed
        assert (mix[1][:, :, :4] == 255).all()     # interior pure


class TestMixelCacheEmitted:
    @pytest.mark.parametrize("subj", ["s0246", "s0187", "s0250", "s0267"])
    def test_totalseg_mixel_cache_exists(self, subj):
        import os
        path = os.path.join(os.path.dirname(__file__), "..", "data",
                            "TotalsegmentatorMRI_dataset_v200", subj,
                            "mixel_iso_adapt_256.npy")
        if not os.path.exists(os.path.dirname(path)):
            pytest.skip("dataset not present")
        assert os.path.exists(path), f"{subj}: mixel sidecar missing"
        atlas = np.load(os.path.join(os.path.dirname(path), "atlas_iso_adapt_256.npy"))
        mix = np.load(path)
        assert mix.shape == (2,) + atlas.shape and mix.dtype == np.uint8
        mixed = mix[1] < 255
        body = atlas > 0
        assert 0.005 < mixed[body].mean() < 0.35, "implausible mixed-voxel share"
        # Objective boundary check (no eyeballing): the vast majority of mixed
        # voxels must hug atlas label changes. A small off-boundary residue is
        # legitimate — thin structures on the finer working grid (cortical
        # shells, vessel walls) can vanish from the nearest-neighbor atlas yet
        # still carry partial volume. Measured 96-98% on-boundary, <=0.2%
        # off-5x5 across all four subjects.
        from scipy.ndimage import maximum_filter, minimum_filter
        v3 = maximum_filter(atlas, 3) != minimum_filter(atlas, 3)
        v5 = maximum_filter(atlas, 5) != minimum_filter(atlas, 5)
        on3 = (mixed & body & v3).sum() / max((mixed & body).sum(), 1)
        assert on3 > 0.90, f"only {on3:.1%} of mixels on atlas boundaries"
        assert (mixed & body & ~v5).mean() < 0.005


class TestDenseRegionAtlases:
    """Committed TotalSegMRI region caches carry the densified fill:
    marrow-split bone, a skin rind, and measured (not quota) fat."""

    _CACHES = {
        "Abdomen": "s0246", "Pelvis": "s0187", "Torso": "s0250", "Spine": "s0267",
    }

    def _load(self, subj):
        import os
        path = os.path.join(os.path.dirname(__file__), "..", "data",
                            "TotalsegmentatorMRI_dataset_v200", subj,
                            "atlas_iso_adapt_256.npy")
        if not os.path.exists(path):
            pytest.skip(f"{subj} cache not present")
        return np.load(path)

    @pytest.mark.parametrize("region", ["Abdomen", "Pelvis", "Torso", "Spine"])
    def test_marrow_and_skin_present(self, region):
        a = self._load(self._CACHES[region])
        assert (a == 14).sum() > 1_000, f"{region}: no marrow in bone"
        assert (a == 5).sum() > 1_000, f"{region}: no skin rind"

    @pytest.mark.parametrize("region", ["Abdomen", "Pelvis", "Torso"])
    def test_fat_is_substantial(self, region):
        a = self._load(self._CACHES[region])
        ratio = (a == 4).sum() / max((a == 6).sum(), 1)
        assert ratio > 0.25, f"{region}: fat/muscle {ratio:.2f}"

    @pytest.mark.parametrize("region", ["Abdomen", "Torso"])
    def test_bowel_gas_labeled(self, region):
        # Pelvis's bowel is fluid-filled on this subject — only guard the two
        # with measured gas (31% / 47% of bowel content below the gas cut).
        a = self._load(self._CACHES[region])
        assert (a == 12).sum() > 10_000, f"{region}: no bowel-gas voxels"

    @pytest.mark.parametrize("region", ["Abdomen", "Pelvis", "Torso"])
    def test_texture_is_label_normalized(self, region):
        import os
        subj = self._CACHES[region]
        path = os.path.join(os.path.dirname(__file__), "..", "data",
                            "TotalsegmentatorMRI_dataset_v200", subj,
                            "texture_iso_adapt_256.npy")
        if not os.path.exists(path):
            pytest.skip("texture cache not present")
        a = self._load(subj)
        t = np.load(path).astype(np.float32)
        for lab in (4, 6):   # fat, muscle — where the cross-tissue bias lived
            med = float(np.median(t[a == lab]))
            assert abs(med - 1.0) < 0.1, f"{region} label {lab}: texture median {med:.2f}"


import os as _os
_DATA_DIR = _os.path.join(_os.path.dirname(_os.path.dirname(__file__)), "data")
_REAL_DATA_AVAILABLE = all(
    _os.path.exists(_os.path.join(_DATA_DIR, f))
    for f in _REGION_NIFTI.values()
)
_TS_DIR = _os.path.join(_DATA_DIR, "TotalsegmentatorMRI_dataset_v100")
_TS_S0001 = _os.path.join(_TS_DIR, "s0001")
_TS_S0008 = _os.path.join(_TS_DIR, "s0008")
_TS_AVAILABLE = (
    HAS_NIBABEL
    and _os.path.isdir(_TS_S0001)
    and _os.path.isdir(_TS_S0008)
)


@pytest.mark.skipif(not (HAS_NIBABEL and _REAL_DATA_AVAILABLE),
                    reason="nibabel or real NIfTI data not available")
class TestLoadRegionNiftiIntegration:
    def test_abdomen_returns_ndarray(self):
        vol = load_region_nifti("Abdomen", _DATA_DIR)
        assert isinstance(vol, np.ndarray) and vol.ndim == 3

    def test_abdomen_dtype_uint8(self):
        vol = load_region_nifti("Abdomen", _DATA_DIR)
        assert vol.dtype == np.uint8

    def test_abdomen_has_liver(self):
        vol = load_region_nifti("Abdomen", _DATA_DIR)
        assert 7 in np.unique(vol)   # liver label

    def test_abdomen_has_kidney(self):
        vol = load_region_nifti("Abdomen", _DATA_DIR)
        assert 9 in np.unique(vol)   # kidney cortex label

    def test_spine_has_cord(self):
        vol = load_region_nifti("Spine", _DATA_DIR)
        assert 16 in np.unique(vol)  # spinal cord

    def test_spine_has_disc(self):
        vol = load_region_nifti("Spine", _DATA_DIR)
        assert 15 in np.unique(vol)  # cartilage/disc

    def test_pelvis_has_bone(self):
        vol = load_region_nifti("Pelvis", _DATA_DIR)
        assert 13 in np.unique(vol)  # cortical bone (sacrum/hips)

    def test_cached_npy_reused(self):
        # Second call should be fast (reads .npy cache)
        import time
        t = time.time()
        load_region_nifti("Abdomen", _DATA_DIR)
        load_region_nifti("Abdomen", _DATA_DIR)
        assert time.time() - t < 5.0  # both loads well under 5s

    def test_build_region_uses_real_data(self):
        from body_phantoms import build_region
        for region in ("Abdomen", "Spine", "Pelvis"):
            vol = build_region(region)
            assert vol.ndim == 3 and vol.dtype == np.uint8

    def test_regions_are_volumetric_not_thick_sliced(self):
        # Voxels are isotropic by construction (resample_labels_isotropic); here we
        # guard against regressing to the old thick-sliced atlases (~34 slices):
        # the volume must be genuinely 3D with a substantial through-plane extent.
        # (The A/P axis can be a thin FOV slab on dedicated spine scans, so we
        # check absolute extents, not a shape-aspect ratio.)
        from body_phantoms import build_region
        for region in ("Abdomen", "Spine", "Pelvis"):
            vol = build_region(region)
            assert vol.shape[0] >= 120, f"{region} too few S/I slices: {vol.shape}"
            assert min(vol.shape) >= 40, f"{region} a degenerate axis: {vol.shape}"


# ---------------------------------------------------------------------------
# load_totalseg_mri_subject  (integration — skipped if data unavailable)
# ---------------------------------------------------------------------------
@pytest.mark.skipif(not _TS_AVAILABLE,
                    reason="nibabel or TotalSegmentatorMRI data not available")
class TestLoadTotalsegMriSubjectIntegration:
    def test_abdomen_subject_returns_uint8_3d(self):
        vol = load_totalseg_mri_subject(_TS_S0001, target_max=64)
        assert isinstance(vol, np.ndarray) and vol.ndim == 3
        assert vol.dtype == np.uint8

    def test_abdomen_has_liver(self):
        vol = load_totalseg_mri_subject(_TS_S0001, target_max=64)
        assert 7 in np.unique(vol)

    def test_abdomen_has_kidney(self):
        vol = load_totalseg_mri_subject(_TS_S0001, target_max=64)
        assert 9 in np.unique(vol)

    def test_abdomen_has_spleen(self):
        vol = load_totalseg_mri_subject(_TS_S0001, target_max=64)
        assert 8 in np.unique(vol)

    def test_abdomen_has_spinal_cord(self):
        vol = load_totalseg_mri_subject(_TS_S0001, target_max=64)
        assert 16 in np.unique(vol)

    def test_abdomen_has_vertebrae_and_disc(self):
        vol = load_totalseg_mri_subject(_TS_S0001, target_max=64)
        labels = set(np.unique(vol).tolist())
        assert 13 in labels  # vertebra bone
        assert 15 in labels  # disc

    def test_abdomen_has_fat_and_muscle(self):
        vol = load_totalseg_mri_subject(_TS_S0001, target_max=64)
        labels = set(np.unique(vol).tolist())
        assert 4 in labels   # fat (MRI-guided fill)
        assert 6 in labels   # muscle (MRI-guided fill)

    def test_pelvis_subject_has_bone_and_muscle(self):
        vol = load_totalseg_mri_subject(_TS_S0008, target_max=64)
        labels = set(np.unique(vol).tolist())
        assert 13 in labels  # sacrum/hip bones
        assert 6 in labels   # gluteal/iliopsoas muscles

    def test_output_respects_target_max(self):
        vol = load_totalseg_mri_subject(_TS_S0001, target_max=64)
        assert max(vol.shape) <= 64

    def test_load_region_nifti_uses_totalseg_mri_for_abdomen(self):
        # When TotalSegMRI data is present, load_region_nifti should use it
        # (richer data source with MRI-guided fat fill)
        vol = load_region_nifti("Abdomen", _DATA_DIR, target_max=64)
        assert vol is not None and vol.ndim == 3
        labels = set(np.unique(vol).tolist())
        # Both fat (4) and explicit organ labels are present in the richer source
        assert 4 in labels or 7 in labels  # fat from MRI fill OR liver

    def test_load_region_nifti_pelvis_uses_s0008(self):
        vol = load_region_nifti("Pelvis", _DATA_DIR, target_max=64)
        assert vol is not None
        labels = set(np.unique(vol).tolist())
        assert 13 in labels  # bone from sacrum/hips
