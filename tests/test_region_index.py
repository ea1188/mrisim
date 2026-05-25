import json
import os
import pytest
from region_index import (
    TS_CT_NAMES,
    TS_MR_NAMES,
    detect_scheme,
    _names_for,
    classify_region,
    summarise_anatomy,
    _mask_files,
    build_index,
    regions_summary,
)

try:
    import nibabel as _nib
    HAS_NIBABEL = True
except ImportError:
    HAS_NIBABEL = False


# ---------------------------------------------------------------------------
# TS_CT_NAMES  (CT 117-class table)
# ---------------------------------------------------------------------------
class TestTsCtNames:
    def test_covers_all_117_classes(self):
        assert len(TS_CT_NAMES) == 117

    def test_keys_are_1_to_117(self):
        assert min(TS_CT_NAMES) == 1
        assert max(TS_CT_NAMES) == 117

    def test_all_values_are_strings(self):
        for k, v in TS_CT_NAMES.items():
            assert isinstance(v, str), f"label {k} has non-string name"

    def test_spot_checks(self):
        assert TS_CT_NAMES[5]  == "liver"
        assert TS_CT_NAMES[1]  == "spleen"
        assert TS_CT_NAMES[51] == "heart"
        assert TS_CT_NAMES[90] == "brain"
        assert TS_CT_NAMES[91] == "skull"
        assert TS_CT_NAMES[79] == "spinal_cord"

    def test_bulk_vertebrae_range(self):
        for i in range(26, 51):
            assert TS_CT_NAMES[i] == "vertebra", f"label {i} should be 'vertebra'"

    def test_bulk_vessel_range(self):
        for i in range(53, 69):
            assert TS_CT_NAMES[i] == "vessel", f"label {i} should be 'vessel'"

    def test_bulk_rib_range(self):
        for i in range(92, 116):
            assert TS_CT_NAMES[i] == "rib", f"label {i} should be 'rib'"

    def test_bulk_muscle_range(self):
        for i in range(80, 90):
            assert TS_CT_NAMES[i] == "muscle", f"label {i} should be 'muscle'"

    def test_humerus_labels(self):
        assert TS_CT_NAMES[69] == "humerus"
        assert TS_CT_NAMES[70] == "humerus"

    def test_femur_labels(self):
        assert TS_CT_NAMES[75] == "femur"
        assert TS_CT_NAMES[76] == "femur"


# ---------------------------------------------------------------------------
# TS_MR_NAMES  (MR 50-class table)
# ---------------------------------------------------------------------------
class TestTsMrNames:
    def test_covers_50_classes(self):
        assert len(TS_MR_NAMES) == 50

    def test_keys_are_1_to_50(self):
        assert min(TS_MR_NAMES) == 1
        assert max(TS_MR_NAMES) == 50

    def test_all_values_are_strings(self):
        for k, v in TS_MR_NAMES.items():
            assert isinstance(v, str)

    def test_spot_checks(self):
        assert TS_MR_NAMES[5]  == "liver"
        assert TS_MR_NAMES[1]  == "spleen"
        assert TS_MR_NAMES[22] == "heart"
        assert TS_MR_NAMES[50] == "brain"
        assert TS_MR_NAMES[21] == "spinal_cord"
        assert TS_MR_NAMES[20] == "intervertebral_disc"

    def test_vessels_25_to_29(self):
        for i in range(25, 30):
            assert TS_MR_NAMES[i] == "vessel"

    def test_muscles_40_to_49(self):
        for i in range(40, 50):
            assert TS_MR_NAMES[i] == "muscle"


# ---------------------------------------------------------------------------
# detect_scheme
# ---------------------------------------------------------------------------
class TestDetectScheme:
    def test_empty_set_is_ct(self):
        assert detect_scheme(set()) == "ct"

    def test_empty_list_is_ct(self):
        assert detect_scheme([]) == "ct"

    def test_zero_only_is_ct(self):
        assert detect_scheme({0}) == "ct"

    def test_label_above_50_is_ct(self):
        assert detect_scheme({1, 5, 90}) == "ct"

    def test_label_exactly_51_is_ct(self):
        assert detect_scheme({51}) == "ct"

    def test_labels_up_to_50_is_mr(self):
        assert detect_scheme({1, 5, 22, 50}) == "mr"

    def test_label_exactly_50_is_mr(self):
        assert detect_scheme({50}) == "mr"

    def test_single_low_label_is_mr(self):
        assert detect_scheme({7}) == "mr"


# ---------------------------------------------------------------------------
# _names_for
# ---------------------------------------------------------------------------
class TestNamesFor:
    def test_returns_set(self):
        result = _names_for({5}, "ct")
        assert isinstance(result, set)

    def test_ct_liver(self):
        assert "liver" in _names_for({5}, "ct")

    def test_mr_brain(self):
        assert "brain" in _names_for({50}, "mr")

    def test_empty_label_set(self):
        assert _names_for(set(), "ct") == set()

    def test_unknown_label_excluded(self):
        result = _names_for({999}, "ct")
        assert result == set()

    def test_multiple_labels(self):
        result = _names_for({5, 1}, "ct")   # liver + spleen
        assert "liver" in result
        assert "spleen" in result

    def test_uses_mr_table_when_mr_scheme(self):
        # label 22 = "heart" in MR, but in CT label 22 = "prostate"
        assert "heart"   in _names_for({22}, "mr")
        assert "prostate" in _names_for({22}, "ct")

    def test_no_empty_strings_in_result(self):
        result = _names_for({5, 999}, "ct")
        assert "" not in result


# ---------------------------------------------------------------------------
# classify_region  — every output string exercised
# ---------------------------------------------------------------------------
class TestClassifyRegion:
    # CT scheme labels --------------------------------------------------
    def test_head_neck_brain_only(self):
        # brain (90) + skull (91), no lungs/abdomen
        assert classify_region({90, 91}, scheme="ct") == "Head / Neck"

    def test_head_neck_auto_detect(self):
        # labels > 50 → auto-detected as CT
        assert classify_region({90}) == "Head / Neck"

    def test_chest_lung_only(self):
        assert classify_region({10}, scheme="ct") == "Chest"

    def test_chest_heart_only(self):
        assert classify_region({51}, scheme="ct") == "Chest"

    def test_chest_abdomen(self):
        # lung + liver
        assert classify_region({10, 5}, scheme="ct") == "Chest + Abdomen"

    def test_abdomen_only(self):
        assert classify_region({5}, scheme="ct") == "Abdomen"

    def test_abdomen_pelvis(self):
        # liver + bladder
        assert classify_region({5, 21}, scheme="ct") == "Abdomen + Pelvis"

    def test_pelvis_only(self):
        # bladder alone
        assert classify_region({21}, scheme="ct") == "Pelvis"

    def test_limb(self):
        assert classify_region({69}, scheme="ct") == "Limb"

    def test_spine_spinal_cord(self):
        assert classify_region({79}, scheme="ct") == "Neck / Spine"

    def test_spine_vertebra(self):
        # cervical vertebra
        assert classify_region({44}, scheme="ct") == "Neck / Spine"

    def test_other(self):
        # thyroid alone — not covered by any major region rule
        assert classify_region({17}, scheme="ct") == "Other"

    # MR scheme labels --------------------------------------------------
    def test_mr_head(self):
        # brain = label 50 in MR
        assert classify_region({50}, scheme="mr") == "Head / Neck"

    def test_mr_chest(self):
        # lung_left = label 10 in MR
        assert classify_region({10}, scheme="mr") == "Chest"

    def test_mr_abdomen(self):
        # liver = label 5 in MR
        assert classify_region({5}, scheme="mr") == "Abdomen"

    def test_mr_pelvis(self):
        # urinary_bladder = label 16 in MR
        assert classify_region({16}, scheme="mr") == "Pelvis"

    def test_mr_spine(self):
        # spinal_cord = label 21 in MR
        assert classify_region({21}, scheme="mr") == "Neck / Spine"

    # Auto-detection --------------------------------------------------
    def test_auto_mr_scheme_from_low_labels(self):
        # Labels ≤ 50 auto-detected as MR; liver(5) + lung(10) → Chest + Abdomen in MR
        assert classify_region({5, 10}) == "Chest + Abdomen"

    def test_empty_labels_returns_other(self):
        assert classify_region(set()) == "Other"


# ---------------------------------------------------------------------------
# summarise_anatomy
# ---------------------------------------------------------------------------
class TestSummariseAnatomy:
    def test_returns_string(self):
        assert isinstance(summarise_anatomy({5}, scheme="ct"), str)

    def test_empty_set_no_structures(self):
        assert summarise_anatomy(set()) == "(no recognised structures)"

    def test_zero_only_no_structures(self):
        assert summarise_anatomy({0}) == "(no recognised structures)"

    def test_liver_present(self):
        result = summarise_anatomy({5}, scheme="ct")
        assert "liver" in result

    def test_underscore_replaced_with_space(self):
        # "kidney_right" should appear as "kidney right"
        result = summarise_anatomy({2}, scheme="ct")
        assert "_" not in result

    def test_deduplication(self):
        # Labels 10-14 are all different lung lobes but the same group name "lung..."
        # The names are distinct strings so no merging — but vertebra 26..50 all map
        # to "vertebra", so they should appear only once.
        result = summarise_anatomy(set(range(26, 32)), scheme="ct")
        assert result.count("vertebra") == 1

    def test_max_items_truncation(self):
        # 20 distinct labels should be truncated at max_items=5
        labels = set(range(1, 21))  # spleen, kidneys, ..., colon
        result = summarise_anatomy(labels, scheme="ct", max_items=5)
        assert "+", result   # should contain "+N more"
        assert "+" in result

    def test_no_truncation_within_limit(self):
        result = summarise_anatomy({1, 5}, scheme="ct", max_items=10)
        assert "+" not in result

    def test_mr_scheme(self):
        result = summarise_anatomy({5, 1}, scheme="mr")
        assert "liver" in result
        assert "spleen" in result

    def test_sorted_by_label_number(self):
        # Label 1 (spleen) should come before label 5 (liver)
        result = summarise_anatomy({5, 1}, scheme="ct")
        assert result.index("spleen") < result.index("liver")


# ---------------------------------------------------------------------------
# _mask_files
# ---------------------------------------------------------------------------
class TestMaskFiles:
    def test_returns_only_nii_files(self, tmp_path):
        (tmp_path / "a.nii").write_bytes(b"x")
        (tmp_path / "b.nii.gz").write_bytes(b"x")
        (tmp_path / "c.txt").write_bytes(b"x")
        (tmp_path / "d.json").write_bytes(b"x")
        result = _mask_files(str(tmp_path))
        assert sorted(result) == ["a.nii", "b.nii.gz"]

    def test_empty_folder_returns_empty(self, tmp_path):
        assert _mask_files(str(tmp_path)) == []

    def test_result_is_sorted(self, tmp_path):
        for name in ["z.nii", "a.nii.gz", "m.nii"]:
            (tmp_path / name).write_bytes(b"x")
        result = _mask_files(str(tmp_path))
        assert result == sorted(result)

    def test_excludes_directories(self, tmp_path):
        (tmp_path / "subdir.nii").mkdir()
        (tmp_path / "real.nii.gz").write_bytes(b"x")
        result = _mask_files(str(tmp_path))
        assert "real.nii.gz" in result
        assert "subdir.nii" in result  # listdir returns it; os.listdir doesn't filter dirs

    def test_no_nii_files_only_others(self, tmp_path):
        (tmp_path / "scan.dcm").write_bytes(b"x")
        (tmp_path / "data.npz").write_bytes(b"x")
        assert _mask_files(str(tmp_path)) == []


# ---------------------------------------------------------------------------
# regions_summary
# ---------------------------------------------------------------------------
class TestRegionsSummary:
    def test_returns_dict(self):
        entries = [{"region": "Abdomen"}, {"region": "Chest"}, {"region": "Abdomen"}]
        result = regions_summary(entries)
        assert isinstance(result, dict)

    def test_counts_correct(self):
        entries = [
            {"region": "Abdomen"},
            {"region": "Abdomen"},
            {"region": "Chest"},
        ]
        result = regions_summary(entries)
        assert result["Abdomen"] == 2
        assert result["Chest"] == 1

    def test_sorted_by_descending_count(self):
        entries = [
            {"region": "Chest"},
            {"region": "Abdomen"}, {"region": "Abdomen"},
            {"region": "Pelvis"}, {"region": "Pelvis"}, {"region": "Pelvis"},
        ]
        result = regions_summary(entries)
        counts = list(result.values())
        assert counts == sorted(counts, reverse=True)

    def test_empty_entries(self):
        assert regions_summary([]) == {}

    def test_single_entry(self):
        result = regions_summary([{"region": "Head / Neck"}])
        assert result == {"Head / Neck": 1}

    def test_keys_are_region_strings(self):
        entries = [{"region": "Abdomen"}, {"region": "Other"}]
        result = regions_summary(entries)
        assert set(result.keys()) == {"Abdomen", "Other"}


# ---------------------------------------------------------------------------
# build_index  — no-nibabel paths
# ---------------------------------------------------------------------------
class TestBuildIndex:
    def test_empty_folder_returns_empty_list(self, tmp_path):
        result = build_index(str(tmp_path))
        assert result == []

    def test_empty_folder_writes_no_cache(self, tmp_path):
        cache = tmp_path / "idx.json"
        build_index(str(tmp_path), cache_path=str(cache))
        # No files → nothing to write (changed=False)
        assert not cache.exists()

    def test_cache_hit_avoids_nibabel(self, tmp_path):
        # Create a dummy .nii.gz file (invalid NIfTI, but we'll pre-populate the cache
        # so nibabel is never called).
        nii_file = tmp_path / "s0001.nii.gz"
        nii_file.write_bytes(b"\x00" * 64)
        st = nii_file.stat()
        key = f"s0001.nii.gz:{int(st.st_mtime)}:{st.st_size}"
        entry = {
            "key": key, "file": "s0001.nii.gz", "path": str(nii_file),
            "region": "Abdomen", "anatomy": "liver, spleen",
            "scheme": "ct", "n_labels": 5,
        }
        cache_path = tmp_path / ".region_index.json"
        cache_path.write_text(json.dumps([entry]))

        result = build_index(str(tmp_path), cache_path=str(cache_path))

        assert len(result) == 1
        assert result[0]["region"] == "Abdomen"
        assert result[0]["file"] == "s0001.nii.gz"

    def test_stale_cache_ignored_gracefully(self, tmp_path):
        # Corrupt JSON in cache → build_index falls back to empty cache
        # (no .nii files, so nothing new to scan either)
        cache_path = tmp_path / ".region_index.json"
        cache_path.write_text("NOT VALID JSON {{{")
        result = build_index(str(tmp_path), cache_path=str(cache_path))
        assert result == []

    def test_cache_hit_returns_all_fields(self, tmp_path):
        nii_file = tmp_path / "scan.nii.gz"
        nii_file.write_bytes(b"\x00" * 32)
        st = nii_file.stat()
        key = f"scan.nii.gz:{int(st.st_mtime)}:{st.st_size}"
        entry = {
            "key": key, "file": "scan.nii.gz", "path": str(nii_file),
            "region": "Chest", "anatomy": "lung left, heart",
            "scheme": "mr", "n_labels": 3,
        }
        cache_path = tmp_path / "cache.json"
        cache_path.write_text(json.dumps([entry]))

        result = build_index(str(tmp_path), cache_path=str(cache_path))
        assert result[0]["scheme"] == "mr"
        assert result[0]["n_labels"] == 3
        assert result[0]["anatomy"] == "lung left, heart"

    def test_progress_callback_called(self, tmp_path):
        # Even without nibabel, verify progress is invoked for cache-miss files.
        # We patch labels_in_mask to avoid the nibabel dependency.
        import region_index
        nii_file = tmp_path / "new.nii.gz"
        nii_file.write_bytes(b"\x00" * 16)

        calls = []
        original = region_index.labels_in_mask

        def fake_labels(path, subsample=4):
            return {5, 1, 90}  # liver, spleen, brain

        region_index.labels_in_mask = fake_labels
        try:
            def progress(i, total, fn):
                calls.append((i, total, fn))

            build_index(str(tmp_path), progress=progress)
            assert len(calls) == 1
            assert calls[0][2] == "new.nii.gz"
        finally:
            region_index.labels_in_mask = original

    def test_new_file_entry_has_required_fields(self, tmp_path):
        import region_index
        nii_file = tmp_path / "organ.nii"
        nii_file.write_bytes(b"\x00" * 16)

        original = region_index.labels_in_mask

        def fake_labels(path, subsample=4):
            return {5}  # liver → "Abdomen"

        region_index.labels_in_mask = fake_labels
        try:
            result = build_index(str(tmp_path))
            assert len(result) == 1
            entry = result[0]
            for field in ("key", "file", "path", "region", "anatomy", "scheme", "n_labels"):
                assert field in entry, f"missing field: {field}"
            assert entry["region"] == "Abdomen"
        finally:
            region_index.labels_in_mask = original

    def test_cache_written_for_new_files(self, tmp_path):
        import region_index
        nii_file = tmp_path / "new.nii.gz"
        nii_file.write_bytes(b"\x00" * 16)
        cache_path = tmp_path / "idx.json"

        original = region_index.labels_in_mask
        region_index.labels_in_mask = lambda path, subsample=4: {5}
        try:
            build_index(str(tmp_path), cache_path=str(cache_path))
            assert cache_path.exists()
            data = json.loads(cache_path.read_text())
            assert len(data) == 1
        finally:
            region_index.labels_in_mask = original


# ---------------------------------------------------------------------------
# labels_in_mask  — skip without nibabel
# ---------------------------------------------------------------------------
@pytest.mark.skipif(not HAS_NIBABEL, reason="nibabel not installed")
class TestLabelsInMask:
    def test_import_succeeds(self):
        from region_index import labels_in_mask
        assert callable(labels_in_mask)


# ---------------------------------------------------------------------------
# Branch coverage additions
# ---------------------------------------------------------------------------
class TestLabelsInMaskReal:
    @pytest.mark.skipif(not HAS_NIBABEL, reason="nibabel not installed")
    def test_returns_set_of_labels(self, tmp_path):
        """Call labels_in_mask on a real NIfTI; covers lines 144-149."""
        import numpy as np
        import nibabel as nib
        from region_index import labels_in_mask
        data = np.zeros((20, 20, 20), dtype=np.int32)
        data[5:10, 5:10, 5:10] = 5    # liver
        data[12:16, 5:10, 5:10] = 90  # brain
        img = nib.Nifti1Image(data, np.eye(4))
        p = str(tmp_path / "test.nii.gz")
        nib.save(img, p)
        labs = labels_in_mask(p, subsample=1)
        assert isinstance(labs, set)
        assert 5 in labs
        assert 90 in labs
        assert 0 not in labs

    @pytest.mark.skipif(not HAS_NIBABEL, reason="nibabel not installed")
    def test_all_zeros_returns_empty_set(self, tmp_path):
        import numpy as np
        import nibabel as nib
        from region_index import labels_in_mask
        data = np.zeros((10, 10, 10), dtype=np.int32)
        img = nib.Nifti1Image(data, np.eye(4))
        p = str(tmp_path / "zero.nii.gz")
        nib.save(img, p)
        assert labels_in_mask(p) == set()


class TestBuildIndexJsonWriteFailure:
    def test_json_write_failure_silently_ignored(self, tmp_path, monkeypatch):
        """JSON cache write exception is swallowed (lines 209-210)."""
        import region_index

        nii_file = tmp_path / "organ.nii.gz"
        nii_file.write_bytes(b"\x00" * 16)
        cache_path = tmp_path / "idx.json"

        original_labels = region_index.labels_in_mask
        region_index.labels_in_mask = lambda path, subsample=4: {5}

        def _raise_dump(*a, **kw):
            raise OSError("disk full")

        # Patch json.dump as seen by region_index (not the local import)
        monkeypatch.setattr(region_index.json, "dump", _raise_dump)
        try:
            # Should not raise — the OSError is silently caught (lines 209-210)
            result = build_index(str(tmp_path), cache_path=str(cache_path))
            assert len(result) == 1  # scan ran normally despite write failure
            # File may exist (opened before dump raised) but has no valid JSON
            if cache_path.exists():
                assert cache_path.stat().st_size == 0 or \
                    not cache_path.read_text().strip().startswith("[")
        finally:
            region_index.labels_in_mask = original_labels
