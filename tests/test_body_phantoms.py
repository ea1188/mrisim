import numpy as np
import pytest
from body_phantoms import (
    BODY_TISSUES,
    _BODY_ONLY,
    _ellipse,
    _win,
    _abdomen_slice,
    generate_abdomen_3d,
    generate_knee_3d,
    generate_spine_3d,
    generate_pelvis_3d,
    generate_abdomen_axial,
    REGION_NAMES,
    REGION_SEQUENCES,
    build_region,
    merge_into_engine,
    render_slice,
)

# Small grid shared by several tests
H, W = 60, 80
_gy, _gx = np.ogrid[:H, :W]


# ---------------------------------------------------------------------------
# BODY_TISSUES table
# ---------------------------------------------------------------------------
class TestBodyTissues:
    def test_all_labels_present(self):
        assert set(BODY_TISSUES.keys()) == set(range(24))

    def test_required_keys_per_label(self):
        for lab, p in BODY_TISSUES.items():
            for k in ("T1", "T2", "PD", "T2star", "name"):
                assert k in p, f"label {lab} missing key {k}"

    def test_pd_in_unit_interval(self):
        for lab, p in BODY_TISSUES.items():
            assert 0.0 <= p["PD"] <= 1.0, f"label {lab} PD out of range"

    def test_t1_t2_positive(self):
        for _lab, p in BODY_TISSUES.items():
            assert p["T1"] > 0
            assert p["T2"] > 0

    def test_body_only_labels_are_subset(self):
        assert set(_BODY_ONLY).issubset(set(BODY_TISSUES.keys()))


# ---------------------------------------------------------------------------
# _win – raised-cosine window
# ---------------------------------------------------------------------------
class TestWinFunction:
    def test_zero_outside_range(self):
        assert _win(-0.1, 0.0, 1.0) == 0.0
        assert _win(1.1, 0.0, 1.0) == 0.0
        assert _win(0.0, 0.0, 1.0) == 0.0   # boundary is excluded (f <= lo)
        assert _win(1.0, 0.0, 1.0) == 0.0   # boundary is excluded (f >= hi)

    def test_one_in_flat_interior(self):
        # At center, well away from edges with default edge=0.10
        assert _win(0.5, 0.0, 1.0) == 1.0

    def test_soft_edge_between_zero_and_one(self):
        v = _win(0.05, 0.0, 1.0)  # inside the 0.10 soft-edge zone
        assert 0.0 < v < 1.0

    def test_monotone_rising_edge(self):
        vals = [_win(0.0 + i * 0.02, 0.0, 1.0) for i in range(6)]
        assert vals == sorted(vals)

    def test_custom_edge_width(self):
        # Wider edge: value at 0.1 should be less than with narrower edge
        v_wide = _win(0.1, 0.0, 1.0, edge=0.20)
        v_narrow = _win(0.1, 0.0, 1.0, edge=0.05)
        assert v_narrow == 1.0        # already past the narrow edge
        assert v_wide < 1.0           # still in the wide edge


# ---------------------------------------------------------------------------
# _ellipse – parametric mask
# ---------------------------------------------------------------------------
class TestEllipseFunction:
    def test_returns_bool_array(self):
        mask = _ellipse(_gy, _gx, H / 2, W / 2, H * 0.3, W * 0.3)
        assert mask.dtype == bool

    def test_same_shape_as_grid(self):
        mask = _ellipse(_gy, _gx, H / 2, W / 2, H * 0.3, W * 0.3)
        assert mask.shape == (H, W)

    def test_center_is_inside(self):
        cy, cx = H / 2, W / 2
        mask = _ellipse(_gy, _gx, cy, cx, H * 0.3, W * 0.3)
        assert mask[int(cy), int(cx)]

    def test_corner_is_outside(self):
        mask = _ellipse(_gy, _gx, H / 2, W / 2, H * 0.3, W * 0.3)
        assert not mask[0, 0]

    def test_some_true_some_false(self):
        mask = _ellipse(_gy, _gx, H / 2, W / 2, H * 0.3, W * 0.3)
        assert mask.any() and not mask.all()

    def test_pert_enlarges_ellipse(self):
        mask_no_pert = _ellipse(_gy, _gx, H / 2, W / 2, H * 0.3, W * 0.3, pert=None)
        mask_pert = _ellipse(_gy, _gx, H / 2, W / 2, H * 0.3, W * 0.3, pert=0.5)
        assert mask_pert.sum() >= mask_no_pert.sum()

    def test_angle_rotates_ellipse(self):
        mask_0 = _ellipse(_gy, _gx, H / 2, W / 2, H * 0.2, W * 0.4, angle=0)
        mask_90 = _ellipse(_gy, _gx, H / 2, W / 2, H * 0.2, W * 0.4, angle=90)
        # Different orientations should produce different (but equal-area) masks
        assert not np.array_equal(mask_0, mask_90)


# ---------------------------------------------------------------------------
# _abdomen_slice – one axial slice
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def abdomen_slice_mid():
    return _abdomen_slice(0.34, H, W, _gy, _gx, pert=None, disc=False)


class TestAbdomenSlice:
    def test_output_shape(self, abdomen_slice_mid):
        assert abdomen_slice_mid.shape == (H, W)

    def test_dtype_uint8(self, abdomen_slice_mid):
        assert abdomen_slice_mid.dtype == np.uint8

    def test_labels_within_known_range(self, abdomen_slice_mid):
        unique = set(np.unique(abdomen_slice_mid).tolist())
        valid = set(BODY_TISSUES.keys())
        assert unique.issubset(valid), f"unexpected labels: {unique - valid}"

    def test_has_background(self, abdomen_slice_mid):
        assert 0 in np.unique(abdomen_slice_mid)

    def test_has_fat_and_muscle(self, abdomen_slice_mid):
        unique = set(np.unique(abdomen_slice_mid).tolist())
        assert 4 in unique, "fat (label 4) missing"
        assert 6 in unique, "muscle (label 6) missing"

    def test_disc_flag_changes_spine_label(self):
        sl_bone = _abdomen_slice(0.34, H, W, _gy, _gx, pert=None, disc=False)
        sl_disc = _abdomen_slice(0.34, H, W, _gy, _gx, pert=None, disc=True)
        # disc slice should have label 15 (cartilage/disc) somewhere, bone should have 13
        assert 13 in np.unique(sl_bone)
        assert 15 in np.unique(sl_disc)

    def test_f0_is_valid(self):
        sl = _abdomen_slice(0.0, H, W, _gy, _gx, pert=None)
        assert sl.shape == (H, W)

    def test_f1_is_valid(self):
        sl = _abdomen_slice(1.0, H, W, _gy, _gx, pert=None)
        assert sl.shape == (H, W)

    def test_inferior_slice_has_bowel(self):
        # f > 0.40 triggers bowel loops
        sl = _abdomen_slice(0.70, H, W, _gy, _gx, pert=None)
        assert 17 in np.unique(sl), "bowel (label 17) expected at inferior level"


# ---------------------------------------------------------------------------
# generate_abdomen_3d
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def small_abdomen_3d():
    return generate_abdomen_3d(Z=8, H=H, W=W, seed=42)


class TestGenerateAbdomen3d:
    def test_shape(self, small_abdomen_3d):
        assert small_abdomen_3d.shape == (8, H, W)

    def test_dtype_uint8(self, small_abdomen_3d):
        assert small_abdomen_3d.dtype == np.uint8

    def test_labels_within_known_range(self, small_abdomen_3d):
        unique = set(np.unique(small_abdomen_3d).tolist())
        valid = set(BODY_TISSUES.keys())
        assert unique.issubset(valid)

    def test_multiple_tissues_present(self, small_abdomen_3d):
        assert len(np.unique(small_abdomen_3d)) >= 4

    def test_has_background(self, small_abdomen_3d):
        assert 0 in np.unique(small_abdomen_3d)

    def test_z_variation(self, small_abdomen_3d):
        # Different axial slices should not be identical (anatomy varies with depth)
        assert not np.array_equal(small_abdomen_3d[0], small_abdomen_3d[-1])

    def test_seed_reproducible(self):
        a = generate_abdomen_3d(Z=4, H=H, W=W, seed=99)
        b = generate_abdomen_3d(Z=4, H=H, W=W, seed=99)
        np.testing.assert_array_equal(a, b)


# ---------------------------------------------------------------------------
# generate_abdomen_axial
# ---------------------------------------------------------------------------
class TestGenerateAbdomenAxial:
    def test_default_shape(self):
        sl = generate_abdomen_axial()
        assert sl.shape == (260, 320)

    def test_custom_shape(self):
        sl = generate_abdomen_axial(H=H, W=W)
        assert sl.shape == (H, W)

    def test_dtype_uint8(self):
        sl = generate_abdomen_axial(H=H, W=W)
        assert sl.dtype == np.uint8

    def test_valid_labels(self):
        sl = generate_abdomen_axial(H=H, W=W)
        unique = set(np.unique(sl).tolist())
        assert unique.issubset(set(BODY_TISSUES.keys()))


# ---------------------------------------------------------------------------
# generate_knee_3d
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def small_knee_3d():
    return generate_knee_3d(Z=6, H=40, W=40, seed=42)


class TestGenerateKnee3d:
    def test_shape(self, small_knee_3d):
        assert small_knee_3d.shape == (6, 40, 40)

    def test_dtype_uint8(self, small_knee_3d):
        assert small_knee_3d.dtype == np.uint8

    def test_labels_within_known_range(self, small_knee_3d):
        unique = set(np.unique(small_knee_3d).tolist())
        assert unique.issubset(set(BODY_TISSUES.keys()))

    def test_multiple_tissues_present(self, small_knee_3d):
        assert len(np.unique(small_knee_3d)) >= 3

    def test_has_background(self, small_knee_3d):
        assert 0 in np.unique(small_knee_3d)

    def test_seed_reproducible(self):
        a = generate_knee_3d(Z=4, H=30, W=30, seed=5)
        b = generate_knee_3d(Z=4, H=30, W=30, seed=5)
        np.testing.assert_array_equal(a, b)

    def test_z_variation(self, small_knee_3d):
        assert not np.array_equal(small_knee_3d[0], small_knee_3d[-1])


# ---------------------------------------------------------------------------
# generate_spine_3d
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def small_spine_3d():
    return generate_spine_3d(Z=8, H=40, W=40, seed=42)


class TestGenerateSpine3d:
    def test_shape(self, small_spine_3d):
        assert small_spine_3d.shape == (8, 40, 40)

    def test_dtype_uint8(self, small_spine_3d):
        assert small_spine_3d.dtype == np.uint8

    def test_labels_within_known_range(self, small_spine_3d):
        unique = set(np.unique(small_spine_3d).tolist())
        assert unique.issubset(set(BODY_TISSUES.keys()))

    def test_multiple_tissues_present(self, small_spine_3d):
        assert len(np.unique(small_spine_3d)) >= 3

    def test_has_background(self, small_spine_3d):
        assert 0 in np.unique(small_spine_3d)

    def test_seed_reproducible(self):
        a = generate_spine_3d(Z=4, H=30, W=30, seed=7)
        b = generate_spine_3d(Z=4, H=30, W=30, seed=7)
        np.testing.assert_array_equal(a, b)

    def test_z_variation(self, small_spine_3d):
        assert not np.array_equal(small_spine_3d[0], small_spine_3d[-1])


# ---------------------------------------------------------------------------
# generate_pelvis_3d
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def small_pelvis_3d():
    return generate_pelvis_3d(Z=6, H=40, W=50, seed=42)


class TestGeneratePelvis3d:
    def test_shape(self, small_pelvis_3d):
        assert small_pelvis_3d.shape == (6, 40, 50)

    def test_dtype_uint8(self, small_pelvis_3d):
        assert small_pelvis_3d.dtype == np.uint8

    def test_labels_within_known_range(self, small_pelvis_3d):
        unique = set(np.unique(small_pelvis_3d).tolist())
        assert unique.issubset(set(BODY_TISSUES.keys()))

    def test_multiple_tissues_present(self, small_pelvis_3d):
        assert len(np.unique(small_pelvis_3d)) >= 3

    def test_has_background(self, small_pelvis_3d):
        assert 0 in np.unique(small_pelvis_3d)

    def test_seed_reproducible(self):
        a = generate_pelvis_3d(Z=4, H=30, W=40, seed=11)
        b = generate_pelvis_3d(Z=4, H=30, W=40, seed=11)
        np.testing.assert_array_equal(a, b)

    def test_z_variation(self, small_pelvis_3d):
        assert not np.array_equal(small_pelvis_3d[0], small_pelvis_3d[-1])


# ---------------------------------------------------------------------------
# Region registry
# ---------------------------------------------------------------------------
class TestRegionRegistry:
    def test_region_names_has_all_regions(self):
        for name in ("Brain", "Abdomen", "Knee", "Spine", "Pelvis", "Torso"):
            assert name in REGION_NAMES

    def test_region_sequences_has_all_regions(self):
        for name in ("Brain", "Abdomen", "Knee", "Spine", "Pelvis", "Torso"):
            assert name in REGION_SEQUENCES

    def test_brain_has_more_sequences_than_body(self):
        for name in ("Abdomen", "Knee", "Spine", "Pelvis", "Torso"):
            assert len(REGION_SEQUENCES["Brain"]) > len(REGION_SEQUENCES[name])

    def test_all_body_regions_have_spin_echo(self):
        for name in ("Abdomen", "Knee", "Spine", "Pelvis", "Torso"):
            assert "Spin Echo" in REGION_SEQUENCES[name]


# ---------------------------------------------------------------------------
# build_region
# ---------------------------------------------------------------------------
class TestBuildRegion:
    def test_abdomen_returns_ndarray(self):
        vol = build_region("Abdomen")
        assert isinstance(vol, np.ndarray)

    def test_abdomen_3d(self):
        vol = build_region("Abdomen")
        assert vol.ndim == 3

    def test_knee_returns_ndarray(self):
        vol = build_region("Knee")
        assert isinstance(vol, np.ndarray) and vol.ndim == 3

    def test_spine_returns_ndarray(self):
        vol = build_region("Spine")
        assert isinstance(vol, np.ndarray) and vol.ndim == 3

    def test_pelvis_returns_ndarray(self):
        vol = build_region("Pelvis")
        assert isinstance(vol, np.ndarray) and vol.ndim == 3

    def test_unknown_region_raises(self):
        with pytest.raises(KeyError):
            build_region("Thorax_XYZ_Unknown")


# ---------------------------------------------------------------------------
# merge_into_engine
# ---------------------------------------------------------------------------
class TestMergeIntoEngine:
    def test_body_labels_added_to_phantom3d(self):
        import phantom3d
        # Record what was there before
        set(phantom3d.TISSUE_PROPERTIES_3D.keys())
        merge_into_engine()
        after = set(phantom3d.TISSUE_PROPERTIES_3D.keys())
        for lab in _BODY_ONLY:
            assert lab in after, f"label {lab} not added by merge_into_engine"

    def test_brain_labels_not_overwritten(self):
        import phantom3d
        merge_into_engine()
        # Brain label 3 (WM) should have its original T1=830 at 3T
        p = phantom3d.TISSUE_PROPERTIES_3D[3]
        assert p["T1"] == 830, "merge_into_engine overwrote WM T1"


# ---------------------------------------------------------------------------
# render_slice
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def abdomen_label_map():
    return generate_abdomen_axial(H=H, W=W, seed=7)


class TestRenderSlice:
    def test_output_shape_matches_input(self, abdomen_label_map):
        img = render_slice(abdomen_label_map, TR=500, TE=15)
        assert img.shape == abdomen_label_map.shape

    def test_nonnegative(self, abdomen_label_map):
        img = render_slice(abdomen_label_map, TR=500, TE=15)
        assert np.all(img >= 0)

    def test_background_zero(self, abdomen_label_map):
        img = render_slice(abdomen_label_map, TR=500, TE=15, texture=0, blur=0)
        assert np.all(img[abdomen_label_map == 0] == 0.0)

    def test_se_sequence(self, abdomen_label_map):
        img = render_slice(abdomen_label_map, TR=500, TE=15, sequence="SE")
        assert img.max() > 0

    def test_gre_sequence(self, abdomen_label_map):
        img = render_slice(abdomen_label_map, TR=250, TE=5, sequence="GRE",
                           flip_angle=70)
        assert img.shape == abdomen_label_map.shape
        assert img.max() > 0

    def test_ir_sequence(self, abdomen_label_map):
        img = render_slice(abdomen_label_map, TR=9000, TE=90, sequence="IR",
                           TI=2500)
        assert img.shape == abdomen_label_map.shape

    def test_texture_zero_no_randomness(self, abdomen_label_map):
        img1 = render_slice(abdomen_label_map, TR=500, TE=15, texture=0, blur=0)
        img2 = render_slice(abdomen_label_map, TR=500, TE=15, texture=0, blur=0)
        np.testing.assert_array_equal(img1, img2)

    def test_texture_adds_variation(self, abdomen_label_map):
        img_clean = render_slice(abdomen_label_map, TR=500, TE=15, texture=0, blur=0)
        img_text = render_slice(abdomen_label_map, TR=500, TE=15, texture=0.1, blur=0, seed=0)
        brain_mask = abdomen_label_map > 0
        assert not np.allclose(img_clean[brain_mask], img_text[brain_mask])


class TestSyntheticTexture:
    """The procedural texture field that gives synthetic regions parenchymal
    detail (used in the browser build and for the synthetic knee)."""

    def test_texture_shape_and_multiplicative_range(self):
        import body_phantoms as bp
        vol = bp.generate_knee_3d()                    # the synthetic fallback phantom
        tex = bp.synthetic_texture_3d(vol, seed=1)
        assert tex.shape == vol.shape
        assert 0.4 < float(tex.min()) and float(tex.max()) < 1.8
        assert 0.9 < float(tex.mean()) < 1.1          # centred on 1.0 (multiplicative)

    def test_fluid_smoother_than_parenchyma(self):
        """Per-tissue amplitude: fluid (label 1) varies less than bowel (17)."""
        import numpy as np
        import body_phantoms as bp
        vol = np.zeros((12, 40, 40), dtype=np.uint8)
        vol[:, 8:20, 8:32] = 1                         # fluid block
        vol[:, 22:34, 8:32] = 17                       # bowel block
        tex = bp.synthetic_texture_3d(vol, seed=2)
        assert tex[vol == 1].std() < tex[vol == 17].std()

    def test_synthetic_texture_for_a_phantom(self):
        """A synthetic phantom yields a procedural texture (not None), so tissues
        aren't flat fills."""
        import body_phantoms as bp
        vol = bp.generate_knee_3d()
        tex = bp.build_region_texture("Knee", vol)
        assert tex is not None and tex.shape[0] > 0


class TestRealKnee:
    """The real Knee atlas (KneeBones3Dify cache, data/knee_kb3d/)."""

    def test_knee_region_is_real_atlas(self):
        import numpy as np
        import body_phantoms as bp
        vol = bp.build_region("Knee")
        assert vol.shape != (120, 160, 150)            # not the synthetic phantom
        assert set(np.unique(vol).tolist()) >= {0, 13, 14}   # bg + cortical bone + marrow
        tex = bp.build_region_texture("Knee", vol)
        assert tex is not None and tex.shape == vol.shape
