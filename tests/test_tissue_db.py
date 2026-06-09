from tissue_db import properties, apply_to_engine, FIELD_STRENGTHS, _RAW


class TestProperties:
    def test_all_labels_present_3t(self):
        props = properties("3T")
        assert set(props.keys()) == set(_RAW.keys())

    def test_all_labels_present_15t(self):
        props = properties("1.5T")
        assert set(props.keys()) == set(_RAW.keys())

    def test_required_keys_per_label(self):
        for field in ["1.5T", "3T"]:
            for lab, p in properties(field).items():
                assert "T1" in p, f"label {lab} missing T1 at {field}"
                assert "T2" in p, f"label {lab} missing T2 at {field}"
                assert "PD" in p, f"label {lab} missing PD at {field}"
                assert "T2star" in p, f"label {lab} missing T2star at {field}"
                assert "name" in p, f"label {lab} missing name at {field}"

    def test_pd_in_unit_interval(self):
        for field in ["1.5T", "3T"]:
            for lab, p in properties(field).items():
                assert 0.0 <= p["PD"] <= 1.0, f"PD out of range for label {lab} at {field}"

    def test_t1_positive(self):
        for field in ["1.5T", "3T"]:
            for _lab, p in properties(field).items():
                assert p["T1"] > 0

    def test_t2_positive(self):
        for field in ["1.5T", "3T"]:
            for _lab, p in properties(field).items():
                assert p["T2"] > 0

    def test_t1_3t_generally_longer_than_15t(self):
        # T1 lengthens at higher field strength for most tissue (known MR physics)
        p15 = properties("1.5T")
        p3 = properties("3T")
        tissue_labels = [2, 3, 1, 6, 7, 8, 9, 11]  # non-trivial tissues
        for lab in tissue_labels:
            assert p3[lab]["T1"] >= p15[lab]["T1"], (
                f"Label {lab}: expected T1 3T >= T1 1.5T"
            )

    def test_field_strengths_constant(self):
        assert "1.5T" in FIELD_STRENGTHS
        assert "3T" in FIELD_STRENGTHS

    def test_background_pd_zero(self):
        assert properties("3T")[0]["PD"] == 0.0

    def test_csf_high_t1_t2(self):
        p = properties("3T")[1]
        assert p["T1"] > 3000
        assert p["T2"] > 1000

    def test_wm_shorter_t1_than_gm(self):
        p = properties("3T")
        assert p[3]["T1"] < p[2]["T1"]  # WM T1 < GM T1 at 3T

    def test_unknown_field_behaves_like_3t(self):
        # Any value other than "3T" falls back to 1.5T values
        p_other = properties("1.0T")
        p_15 = properties("1.5T")
        for lab in _RAW:
            assert p_other[lab]["T1"] == p_15[lab]["T1"]

    def test_t2star_le_t2_all_labels(self):
        for field in ["1.5T", "3T"]:
            for lab, p in properties(field).items():
                assert p["T2star"] <= p["T2"], (
                    f"Label {lab} at {field}: T2star={p['T2star']} > T2={p['T2']}"
                )

    def test_label_count(self):
        assert len(_RAW) == 27  # labels 0-26 (22 = ligament, 23-26 = demo pathologies)

    def test_bone_short_t2(self):
        p = properties("3T")[5]
        assert p["T2"] < 10  # cortical bone / skull bone has very short T2

    def test_3t_t1_differs_from_15t(self):
        p15 = properties("1.5T")
        p3  = properties("3T")
        # At least most tissue labels should have different T1 values
        diffs = sum(1 for lab in _RAW if p3[lab]["T1"] != p15[lab]["T1"])
        assert diffs > 10


class TestApplyToEngine:
    def test_returns_dict(self):
        result = apply_to_engine("3T")
        assert isinstance(result, dict)

    def test_modifies_phantom3d(self):
        import phantom3d
        apply_to_engine("3T")
        # After applying, phantom3d should have at least the brain labels
        for lab in range(6):
            assert lab in phantom3d.TISSUE_PROPERTIES_3D

    def test_apply_15t_sets_shorter_t1(self):
        import phantom3d
        apply_to_engine("3T")
        t1_3t = phantom3d.TISSUE_PROPERTIES_3D[2]["T1"]
        apply_to_engine("1.5T")
        t1_15t = phantom3d.TISSUE_PROPERTIES_3D[2]["T1"]
        assert t1_15t < t1_3t  # 1.5T T1 < 3T T1 for gray matter

    def test_apply_includes_body_labels(self):
        result = apply_to_engine("3T")
        # All 22 labels (0-21) should be present
        for lab in range(22):
            assert lab in result

    def test_apply_3t_restores_default(self):
        import phantom3d
        apply_to_engine("1.5T")
        apply_to_engine("3T")
        assert phantom3d.TISSUE_PROPERTIES_3D[2]["T1"] == properties("3T")[2]["T1"]
