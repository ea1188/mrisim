import numpy as np
import pytest
from oblique import (
    _rot_matrix,
    _intersect_line,
    plane_from_angles,
    oblique_plane,
    oblique_slab,
    simulate_oblique,
    simulate_oblique_slab,
    scout_lines,
    scout_band,
    three_scouts,
)
from phantom3d import generate_synthetic_3d_brain, get_slice


@pytest.fixture(scope="module")
def small_vol():
    return generate_synthetic_3d_brain(nx=30, ny=36, nz=30)


# ---------------------------------------------------------------------------
# _rot_matrix
# ---------------------------------------------------------------------------
class TestRotMatrix:
    def test_identity_at_zero(self):
        R = _rot_matrix([1, 0, 0], 0.0)
        np.testing.assert_allclose(R, np.eye(3), atol=1e-12)

    def test_orthogonal(self):
        R = _rot_matrix([1, 1, 1], np.radians(37))
        np.testing.assert_allclose(R @ R.T, np.eye(3), atol=1e-12)

    def test_determinant_one(self):
        R = _rot_matrix([0, 1, 0], np.radians(60))
        assert abs(np.linalg.det(R) - 1.0) < 1e-12

    def test_90deg_around_x_maps_y_to_z(self):
        R = _rot_matrix([1, 0, 0], np.radians(90))
        np.testing.assert_allclose(R @ [0., 1., 0.], [0., 0., 1.], atol=1e-12)

    def test_180deg_around_z_inverts_x(self):
        R = _rot_matrix([0, 0, 1], np.radians(180))
        np.testing.assert_allclose(R @ [1., 0., 0.], [-1., 0., 0.], atol=1e-12)

    def test_unnormalised_axis_same_as_unit(self):
        R1 = _rot_matrix([3, 0, 0], np.radians(45))
        R2 = _rot_matrix([1, 0, 0], np.radians(45))
        np.testing.assert_allclose(R1, R2, atol=1e-12)


# ---------------------------------------------------------------------------
# plane_from_angles
# ---------------------------------------------------------------------------
class TestPlaneFromAngles:
    def test_zero_angles_axial(self):
        n, r, c = plane_from_angles("axial", 0, 0)
        np.testing.assert_allclose(n, [1, 0, 0], atol=1e-12)
        np.testing.assert_allclose(r, [0, 1, 0], atol=1e-12)
        np.testing.assert_allclose(c, [0, 0, 1], atol=1e-12)

    def test_zero_angles_coronal(self):
        n, r, c = plane_from_angles("coronal", 0, 0)
        np.testing.assert_allclose(n, [0, 1, 0], atol=1e-12)

    def test_zero_angles_sagittal(self):
        n, r, c = plane_from_angles("sagittal", 0, 0)
        np.testing.assert_allclose(n, [0, 0, 1], atol=1e-12)

    def test_vectors_unit_length_after_tilt(self):
        for base in ("axial", "coronal", "sagittal"):
            n, r, c = plane_from_angles(base, 30, 20)
            assert abs(np.linalg.norm(n) - 1) < 1e-12
            assert abs(np.linalg.norm(r) - 1) < 1e-12
            assert abs(np.linalg.norm(c) - 1) < 1e-12

    def test_vectors_mutually_orthogonal(self):
        n, r, c = plane_from_angles("axial", 30, 20)
        assert abs(np.dot(n, r)) < 1e-12
        assert abs(np.dot(n, c)) < 1e-12
        assert abs(np.dot(r, c)) < 1e-12

    def test_tilt_90_around_col_rotates_axial_to_coronal(self):
        # col_vec for axial = [0,0,1]; rotating axial normal [1,0,0] by +90° around [0,0,1]
        # gives [0,1,0]
        n, _, _ = plane_from_angles("axial", tilt_deg=90, rot_deg=0)
        np.testing.assert_allclose(n, [0., 1., 0.], atol=1e-12)

    def test_rot_90_around_row_rotates_normal(self):
        # row_vec for axial = [0,1,0]; rotating [1,0,0] by +90° around [0,1,0] → [0,0,-1]
        n, _, _ = plane_from_angles("axial", tilt_deg=0, rot_deg=90)
        np.testing.assert_allclose(n, [0., 0., -1.], atol=1e-12)

    def test_double_oblique_has_components_in_multiple_axes(self):
        n, _, _ = plane_from_angles("axial", tilt_deg=30, rot_deg=20)
        assert np.count_nonzero(np.abs(n) > 0.01) >= 2

    def test_invalid_base_raises(self):
        with pytest.raises(ValueError):
            plane_from_angles("unknown_base")

    def test_composition_order_matters(self):
        n_tr, _, _ = plane_from_angles("axial", tilt_deg=30, rot_deg=20)
        n_rt, _, _ = plane_from_angles("axial", tilt_deg=20, rot_deg=30)
        # Different tilt/rot angles should give different normals
        assert not np.allclose(n_tr, n_rt)

    # --- in-plane rotation ---

    def test_inplane_zero_unchanged(self):
        n0, r0, c0 = plane_from_angles("axial", 30, 20, rot_inplane_deg=0)
        n1, r1, c1 = plane_from_angles("axial", 30, 20)
        np.testing.assert_allclose(n0, n1, atol=1e-12)
        np.testing.assert_allclose(r0, r1, atol=1e-12)
        np.testing.assert_allclose(c0, c1, atol=1e-12)

    def test_inplane_preserves_normal(self):
        for ang in (30, 45, 90, 135):
            n_base, _, _ = plane_from_angles("axial", 30, 20)
            n_rot, _, _ = plane_from_angles("axial", 30, 20, rot_inplane_deg=ang)
            np.testing.assert_allclose(n_base, n_rot, atol=1e-12)

    def test_inplane_preserves_orthogonality(self):
        n, r, c = plane_from_angles("coronal", 20, 15, rot_inplane_deg=55)
        assert abs(np.dot(n, r)) < 1e-12
        assert abs(np.dot(n, c)) < 1e-12
        assert abs(np.dot(r, c)) < 1e-12

    def test_inplane_90_from_axial_rotates_row_to_col(self):
        # Axial base: n=[1,0,0], r=[0,1,0], c=[0,0,1].
        # 90° rotation around n=[1,0,0]: r→[0,0,1], c→[0,-1,0].
        _, r, c = plane_from_angles("axial", rot_inplane_deg=90)
        np.testing.assert_allclose(r, [0., 0., 1.], atol=1e-12)
        np.testing.assert_allclose(c, [0., -1., 0.], atol=1e-12)

    def test_inplane_360_is_identity(self):
        n0, r0, c0 = plane_from_angles("axial", 30, 20, rot_inplane_deg=0)
        n1, r1, c1 = plane_from_angles("axial", 30, 20, rot_inplane_deg=360)
        np.testing.assert_allclose(n0, n1, atol=1e-12)
        np.testing.assert_allclose(r0, r1, atol=1e-12)
        np.testing.assert_allclose(c0, c1, atol=1e-12)

    def test_inplane_180_inverts_row_and_col(self):
        _, r0, c0 = plane_from_angles("coronal", 15, 10, rot_inplane_deg=0)
        _, r1, c1 = plane_from_angles("coronal", 15, 10, rot_inplane_deg=180)
        np.testing.assert_allclose(r1, -r0, atol=1e-12)
        np.testing.assert_allclose(c1, -c0, atol=1e-12)

    def test_inplane_combined_with_tilt_rot(self):
        # Sanity: combining all three angles still yields a unit orthonormal frame.
        n, r, c = plane_from_angles("sagittal", tilt_deg=25, rot_deg=15,
                                    rot_inplane_deg=40)
        assert abs(np.linalg.norm(n) - 1) < 1e-12
        assert abs(np.linalg.norm(r) - 1) < 1e-12
        assert abs(np.linalg.norm(c) - 1) < 1e-12
        assert abs(np.dot(n, r)) < 1e-12
        assert abs(np.dot(r, c)) < 1e-12


# ---------------------------------------------------------------------------
# oblique_plane
# ---------------------------------------------------------------------------
class TestObliquePlane:
    def test_output_shape_default(self, small_vol):
        _, r, c = plane_from_angles("axial")
        nz, ny, nx = small_vol.shape
        ctr = (nz // 2, ny // 2, nx // 2)
        out = oblique_plane(small_vol, r, c, ctr)
        d = max(small_vol.shape)
        assert out.shape == (d, d)

    def test_output_shape_custom(self, small_vol):
        _, r, c = plane_from_angles("axial")
        out = oblique_plane(small_vol, r, c, (15, 18, 15), shape=(20, 24))
        assert out.shape == (20, 24)

    def test_dtype_preserved(self, small_vol):
        assert small_vol.dtype == np.uint8
        _, r, c = plane_from_angles("axial")
        out = oblique_plane(small_vol, r, c, (15, 18, 15), shape=(10, 10))
        assert out.dtype == np.uint8

    def test_axial_matches_get_slice(self, small_vol):
        nz, ny, nx = small_vol.shape
        _, r, c = plane_from_angles("axial")
        cz = nz // 2
        out = oblique_plane(small_vol, r, c, (cz, ny // 2, nx // 2), shape=(ny, nx))
        np.testing.assert_array_equal(out, get_slice(small_vol, "axial", cz))

    def test_coronal_matches_get_slice(self, small_vol):
        nz, ny, nx = small_vol.shape
        _, r, c = plane_from_angles("coronal")
        cy = ny // 2
        out = oblique_plane(small_vol, r, c, (nz // 2, cy, nx // 2), shape=(nz, nx))
        np.testing.assert_array_equal(out, get_slice(small_vol, "coronal", cy))

    def test_sagittal_samples_correct_x_plane(self, small_vol):
        nz, ny, nx = small_vol.shape
        _, r, c = plane_from_angles("sagittal")
        cx = nx // 2
        out = oblique_plane(small_vol, r, c, (nz // 2, ny // 2, cx), shape=(nz, ny))
        # Should sample vol[:, :, cx] — same unique labels, same shape
        expected = small_vol[:, :, cx]
        assert out.shape == expected.shape
        assert set(np.unique(out).tolist()) == set(np.unique(expected).tolist())

    def test_oblique_has_nonzero_content(self, small_vol):
        nz, ny, nx = small_vol.shape
        _, r, c = plane_from_angles("axial", tilt_deg=30, rot_deg=15)
        out = oblique_plane(small_vol, r, c, (nz // 2, ny // 2, nx // 2), shape=(ny, nx))
        assert out.max() > 0

    def test_out_of_volume_center_returns_zeros(self, small_vol):
        _, r, c = plane_from_angles("axial")
        out = oblique_plane(small_vol, r, c, (5000, 5000, 5000), shape=(8, 8))
        assert np.all(out == 0)

    def test_order1_returns_float_dtype(self, small_vol):
        nz, ny, nx = small_vol.shape
        _, r, c = plane_from_angles("axial")
        out = oblique_plane(small_vol.astype(float), r, c,
                            (nz // 2, ny // 2, nx // 2), shape=(10, 10), order=1)
        assert np.issubdtype(out.dtype, np.floating)

    def test_inplane_rotation_changes_sampled_image(self, small_vol):
        # In-plane rotation spins the FOV: row/col vectors change, so different
        # voxels are sampled even though the plane cuts through the same anatomy.
        nz, ny, nx = small_vol.shape
        ctr = (nz // 2, ny // 2, nx // 2)
        shape = (ny, nx)
        _, r0, c0 = plane_from_angles("axial", rot_inplane_deg=0)
        _, r1, c1 = plane_from_angles("axial", rot_inplane_deg=45)
        out0 = oblique_plane(small_vol, r0, c0, ctr, shape=shape)
        out1 = oblique_plane(small_vol, r1, c1, ctr, shape=shape)
        assert not np.array_equal(out0, out1)

    def test_different_tilts_give_different_slices(self, small_vol):
        nz, ny, nx = small_vol.shape
        ctr = (nz // 2, ny // 2, nx // 2)
        _, r0, c0 = plane_from_angles("axial", tilt_deg=0)
        _, r1, c1 = plane_from_angles("axial", tilt_deg=45)
        out0 = oblique_plane(small_vol, r0, c0, ctr, shape=(ny, nx))
        out1 = oblique_plane(small_vol, r1, c1, ctr, shape=(ny, nx))
        assert not np.array_equal(out0, out1)


# ---------------------------------------------------------------------------
# _intersect_line
# ---------------------------------------------------------------------------
class TestIntersectLine:
    def test_axial_plane_parallel_to_axial_scout(self):
        # Axial normal n=[1,0,0]; axial scout row_axis=1, col_axis=2 → nr=nc=0
        n = np.array([1., 0., 0.])
        ctr = np.array([15., 18., 15.])
        assert _intersect_line(n, ctr, 0, 15.0, 1, 2, 36, 30) is None

    def test_coronal_plane_on_axial_scout_is_horizontal(self):
        # n=[0,1,0]; axial scout: nr=n[1]=1, nc=n[2]=0 → horizontal line r=center[1]
        n = np.array([0., 1., 0.])
        ctr = np.array([15., 18., 15.])
        result = _intersect_line(n, ctr, 0, 15.0, 1, 2, 36, 30)
        assert result is not None
        c0, r0, c1, r1 = result
        assert abs(r0 - 18.0) < 1e-9
        assert abs(r1 - 18.0) < 1e-9

    def test_endpoints_within_image_bounds(self):
        n = np.array([1., 1., 0.]) / np.sqrt(2)
        ctr = np.array([15., 18., 15.])
        result = _intersect_line(n, ctr, 0, 15.0, 1, 2, 36, 30)
        if result is not None:
            c0, r0, c1, r1 = result
            assert 0 <= r0 <= 35
            assert 0 <= r1 <= 35
            assert 0 <= c0 <= 29
            assert 0 <= c1 <= 29

    def test_returns_four_floats(self):
        n = np.array([0., 0., 1.])  # sagittal plane
        ctr = np.array([15., 18., 15.])
        # On coronal scout (fixed_axis=1): nr=n[0]=0, nc=n[2]=1 → vertical line
        result = _intersect_line(n, ctr, 1, 18.0, 0, 2, 30, 30)
        assert result is not None
        assert len(result) == 4


# ---------------------------------------------------------------------------
# scout_lines
# ---------------------------------------------------------------------------
class TestScoutLines:
    def test_returns_three_keys(self, small_vol):
        n, _, _ = plane_from_angles("axial", 30, 20)
        lines = scout_lines(small_vol.shape, n, (15, 18, 15))
        assert set(lines.keys()) == {"axial", "coronal", "sagittal"}

    def test_axial_plane_no_axial_scout_line(self, small_vol):
        n, _, _ = plane_from_angles("axial", 0, 0)
        lines = scout_lines(small_vol.shape, n, (15, 18, 15))
        assert lines["axial"] is None

    def test_coronal_plane_no_coronal_scout_line(self, small_vol):
        n, _, _ = plane_from_angles("coronal", 0, 0)
        lines = scout_lines(small_vol.shape, n, (15, 18, 15))
        assert lines["coronal"] is None

    def test_sagittal_plane_no_sagittal_scout_line(self, small_vol):
        n, _, _ = plane_from_angles("sagittal", 0, 0)
        lines = scout_lines(small_vol.shape, n, (15, 18, 15))
        assert lines["sagittal"] is None

    def test_double_oblique_has_lines_on_all_scouts(self, small_vol):
        n, _, _ = plane_from_angles("axial", tilt_deg=45, rot_deg=30)
        lines = scout_lines(small_vol.shape, n, (15, 18, 15))
        assert lines["axial"] is not None
        assert lines["coronal"] is not None
        assert lines["sagittal"] is not None

    def test_coronal_plane_axial_line_is_horizontal(self, small_vol):
        n, _, _ = plane_from_angles("coronal", 0, 0)
        lines = scout_lines(small_vol.shape, n, (15, 18, 15))
        c0, r0, c1, r1 = lines["axial"]
        # Coronal plane appears as a horizontal line on the axial scout at row=center[1]
        assert abs(r0 - 18) < 1e-9
        assert abs(r1 - 18) < 1e-9

    def test_each_present_line_has_four_values(self, small_vol):
        n, _, _ = plane_from_angles("axial", 30, 20)
        lines = scout_lines(small_vol.shape, n, (15, 18, 15))
        for val in lines.values():
            if val is not None:
                assert len(val) == 4


# ---------------------------------------------------------------------------
# simulate_oblique
# ---------------------------------------------------------------------------
class TestSimulateOblique:
    def test_output_dtype_float(self, small_vol):
        _, r, c = plane_from_angles("axial")
        nz, ny, nx = small_vol.shape
        img = simulate_oblique(small_vol, r, c, (nz//2, ny//2, nx//2),
                               TR=500, TE=15, shape=(20, 20))
        assert np.issubdtype(img.dtype, np.floating)

    def test_output_shape(self, small_vol):
        _, r, c = plane_from_angles("axial")
        nz, ny, nx = small_vol.shape
        img = simulate_oblique(small_vol, r, c, (nz//2, ny//2, nx//2),
                               TR=500, TE=15, shape=(24, 30))
        assert img.shape == (24, 30)

    def test_output_2d(self, small_vol):
        _, r, c = plane_from_angles("axial")
        nz, ny, nx = small_vol.shape
        img = simulate_oblique(small_vol, r, c, (nz//2, ny//2, nx//2),
                               TR=500, TE=15)
        assert img.ndim == 2

    def test_nonnegative(self, small_vol):
        _, r, c = plane_from_angles("axial", tilt_deg=20, rot_deg=10)
        nz, ny, nx = small_vol.shape
        img = simulate_oblique(small_vol, r, c, (nz//2, ny//2, nx//2),
                               TR=500, TE=15, shape=(ny, nx))
        assert np.all(img >= 0)

    def test_background_label_is_zero_signal(self, small_vol):
        _, r, c = plane_from_angles("axial")
        nz, ny, nx = small_vol.shape
        ctr = (nz//2, ny//2, nx//2)
        label_map = oblique_plane(small_vol, r, c, ctr, shape=(ny, nx))
        img = simulate_oblique(small_vol, r, c, ctr, TR=500, TE=15, shape=(ny, nx))
        assert np.all(img[label_map == 0] == 0.0)

    def test_brain_tissue_has_nonzero_signal(self, small_vol):
        _, r, c = plane_from_angles("axial")
        nz, ny, nx = small_vol.shape
        img = simulate_oblique(small_vol, r, c, (nz//2, ny//2, nx//2),
                               TR=500, TE=15, shape=(ny, nx))
        assert img.max() > 0

    def test_axial_matches_simulate_slice(self, small_vol):
        from phantom3d import simulate_slice
        nz, ny, nx = small_vol.shape
        _, r, c = plane_from_angles("axial")
        cz = nz // 2
        img = simulate_oblique(small_vol, r, c, (cz, ny//2, nx//2),
                               TR=800, TE=20, sequence="SE", shape=(ny, nx))
        expected = simulate_slice(small_vol[cz, :, :], TR=800, TE=20, sequence="SE")
        np.testing.assert_allclose(img, expected, rtol=1e-10)

    def test_se_sequence(self, small_vol):
        _, r, c = plane_from_angles("axial")
        nz, ny, nx = small_vol.shape
        img = simulate_oblique(small_vol, r, c, (nz//2, ny//2, nx//2),
                               TR=500, TE=15, sequence="SE", shape=(20, 20))
        assert img.max() > 0

    def test_gre_sequence(self, small_vol):
        _, r, c = plane_from_angles("axial", tilt_deg=15)
        nz, ny, nx = small_vol.shape
        img = simulate_oblique(small_vol, r, c, (nz//2, ny//2, nx//2),
                               TR=250, TE=5, sequence="GRE", flip_angle=70,
                               shape=(20, 20))
        assert img.ndim == 2
        assert img.max() > 0

    def test_ir_sequence(self, small_vol):
        _, r, c = plane_from_angles("coronal")
        nz, ny, nx = small_vol.shape
        img = simulate_oblique(small_vol, r, c, (nz//2, ny//2, nx//2),
                               TR=9000, TE=90, sequence="IR", TI=2500,
                               shape=(20, 20))
        assert img.ndim == 2

    def test_custom_tissue_props(self, small_vol):
        custom = {
            0: {"T1": 1,    "T2": 1,    "PD": 0.0, "T2star": 1,  "name": "BG"},
            1: {"T1": 4500, "T2": 2200, "PD": 1.0, "T2star": 1500, "name": "CSF"},
            2: {"T1": 1330, "T2": 100,  "PD": 0.8, "T2star": 60, "name": "GM"},
            3: {"T1": 830,  "T2": 80,   "PD": 0.65,"T2star": 48, "name": "WM"},
            4: {"T1": 370,  "T2": 60,   "PD": 0.95,"T2star": 40, "name": "Fat"},
            5: {"T1": 200,  "T2": 5,    "PD": 0.1, "T2star": 3,  "name": "Bone"},
        }
        _, r, c = plane_from_angles("axial")
        nz, ny, nx = small_vol.shape
        img = simulate_oblique(small_vol, r, c, (nz//2, ny//2, nx//2),
                               TR=500, TE=15, tissue_props=custom, shape=(20, 20))
        assert img.ndim == 2
        assert img.max() > 0

    def test_t1_contrast_direction(self, small_vol):
        # Short TR → T1-weighted: WM (T1=830) brighter than CSF (T1=4500)
        _, r, c = plane_from_angles("axial")
        nz, ny, nx = small_vol.shape
        ctr = (nz//2, ny//2, nx//2)
        label_map = oblique_plane(small_vol, r, c, ctr, shape=(ny, nx))
        img = simulate_oblique(small_vol, r, c, ctr,
                               TR=500, TE=15, sequence="SE", shape=(ny, nx))
        if np.any(label_map == 3) and np.any(label_map == 1):
            assert img[label_map == 3].mean() > img[label_map == 1].mean()


# ---------------------------------------------------------------------------
# simulate_oblique_slab
# ---------------------------------------------------------------------------
class TestSimulateObliqueSlab:
    def test_output_shape(self, small_vol):
        n, r, c = plane_from_angles("axial")
        nz, ny, nx = small_vol.shape
        out = simulate_oblique_slab(small_vol, n, r, c, (nz//2, ny//2, nx//2),
                                    n_slices=4, thickness_mm=2.0,
                                    TR=500, TE=15, shape=(20, 24))
        assert out.shape == (4, 20, 24)

    def test_output_dtype_float(self, small_vol):
        n, r, c = plane_from_angles("axial")
        nz, ny, nx = small_vol.shape
        out = simulate_oblique_slab(small_vol, n, r, c, (nz//2, ny//2, nx//2),
                                    n_slices=2, thickness_mm=2.0, TR=500, TE=15)
        assert np.issubdtype(out.dtype, np.floating)

    def test_all_nonnegative(self, small_vol):
        n, r, c = plane_from_angles("axial", tilt_deg=20)
        nz, ny, nx = small_vol.shape
        out = simulate_oblique_slab(small_vol, n, r, c, (nz//2, ny//2, nx//2),
                                    n_slices=3, thickness_mm=2.0,
                                    TR=500, TE=15, shape=(ny, nx))
        assert np.all(out >= 0)

    def test_single_slice_matches_simulate_oblique(self, small_vol):
        nz, ny, nx = small_vol.shape
        n, r, c = plane_from_angles("axial", tilt_deg=20)
        ctr = (nz//2, ny//2, nx//2)
        shape = (20, 20)
        slab = simulate_oblique_slab(small_vol, n, r, c, ctr,
                                     n_slices=1, thickness_mm=1.0,
                                     TR=500, TE=15, shape=shape)
        single = simulate_oblique(small_vol, r, c, ctr, TR=500, TE=15, shape=shape)
        np.testing.assert_array_equal(slab[0], single)

    def test_center_slice_matches_simulate_oblique(self, small_vol):
        nz, ny, nx = small_vol.shape
        n, r, c = plane_from_angles("axial")
        ctr = (nz//2, ny//2, nx//2)
        shape = (ny, nx)
        slab = simulate_oblique_slab(small_vol, n, r, c, ctr,
                                     n_slices=5, thickness_mm=2.0,
                                     TR=500, TE=15, shape=shape)
        ref = simulate_oblique(small_vol, r, c, ctr, TR=500, TE=15, shape=shape)
        np.testing.assert_array_equal(slab[2], ref)

    def test_gre_sequence(self, small_vol):
        n, r, c = plane_from_angles("coronal", tilt_deg=10)
        nz, ny, nx = small_vol.shape
        out = simulate_oblique_slab(small_vol, n, r, c, (nz//2, ny//2, nx//2),
                                    n_slices=2, thickness_mm=2.0,
                                    TR=250, TE=5, sequence="GRE", flip_angle=70,
                                    shape=(20, 20))
        assert out.shape[0] == 2
        assert out.max() > 0

    def test_ir_sequence(self, small_vol):
        n, r, c = plane_from_angles("axial")
        nz, ny, nx = small_vol.shape
        out = simulate_oblique_slab(small_vol, n, r, c, (nz//2, ny//2, nx//2),
                                    n_slices=2, thickness_mm=2.0,
                                    TR=9000, TE=90, sequence="IR", TI=2500,
                                    shape=(20, 20))
        assert out.ndim == 3


# ---------------------------------------------------------------------------
# oblique_slab
# ---------------------------------------------------------------------------
class TestObliqueSlab:
    def test_output_ndim(self, small_vol):
        n, r, c = plane_from_angles("axial")
        out = oblique_slab(small_vol, n, r, c, (15, 18, 15), n_slices=3,
                           thickness_mm=2.0)
        assert out.ndim == 3

    def test_output_shape_n_slices(self, small_vol):
        n, r, c = plane_from_angles("axial")
        out = oblique_slab(small_vol, n, r, c, (15, 18, 15), n_slices=7,
                           thickness_mm=2.0)
        assert out.shape[0] == 7

    def test_inplane_shape_propagated(self, small_vol):
        n, r, c = plane_from_angles("axial")
        out = oblique_slab(small_vol, n, r, c, (15, 18, 15), n_slices=4,
                           thickness_mm=2.0, shape=(20, 24))
        assert out.shape == (4, 20, 24)

    def test_dtype_preserved(self, small_vol):
        n, r, c = plane_from_angles("axial")
        out = oblique_slab(small_vol, n, r, c, (15, 18, 15), n_slices=3,
                           thickness_mm=2.0)
        assert out.dtype == small_vol.dtype

    def test_single_slice_matches_oblique_plane(self, small_vol):
        nz, ny, nx = small_vol.shape
        n, r, c = plane_from_angles("axial", tilt_deg=20)
        ctr = (nz // 2, ny // 2, nx // 2)
        shape = (20, 20)
        slab = oblique_slab(small_vol, n, r, c, ctr,
                            n_slices=1, thickness_mm=1.0, shape=shape)
        single = oblique_plane(small_vol, r, c, ctr, shape=shape)
        np.testing.assert_array_equal(slab[0], single)

    def test_center_slice_of_odd_slab_matches_plane_at_center(self, small_vol):
        # For odd n_slices the middle slice has zero offset → same as oblique_plane
        nz, ny, nx = small_vol.shape
        n, r, c = plane_from_angles("axial")
        ctr = (nz // 2, ny // 2, nx // 2)
        shape = (ny, nx)
        slab = oblique_slab(small_vol, n, r, c, ctr,
                            n_slices=5, thickness_mm=2.0, shape=shape)
        ref = oblique_plane(small_vol, r, c, ctr, shape=shape)
        np.testing.assert_array_equal(slab[2], ref)

    def test_outer_slices_differ_from_each_other(self, small_vol):
        nz, ny, nx = small_vol.shape
        n, r, c = plane_from_angles("axial")
        ctr = (nz // 2, ny // 2, nx // 2)
        out = oblique_slab(small_vol, n, r, c, ctr,
                           n_slices=5, thickness_mm=2.0, shape=(ny, nx))
        assert not np.array_equal(out[0], out[-1])

    def test_gap_separates_outer_slices_further(self, small_vol):
        nz, ny, nx = small_vol.shape
        n, r, c = plane_from_angles("axial")
        ctr = (nz // 2, ny // 2, nx // 2)
        shape = (ny, nx)
        no_gap = oblique_slab(small_vol, n, r, c, ctr,
                              n_slices=3, thickness_mm=2.0, gap_mm=0.0, shape=shape)
        with_gap = oblique_slab(small_vol, n, r, c, ctr,
                                n_slices=3, thickness_mm=2.0, gap_mm=4.0, shape=shape)
        # Outer slices are farther apart with gap → different voxels sampled
        assert not np.array_equal(no_gap[0], with_gap[0])

    def test_anisotropic_voxels_change_inter_slice_spacing(self, small_vol):
        # 3 mm thickness with 3 mm Z voxels = 1 voxel step; with 1 mm Z = 3 voxels
        nz, ny, nx = small_vol.shape
        n, r, c = plane_from_angles("axial")
        ctr = (nz // 2, ny // 2, nx // 2)
        shape = (ny, nx)
        iso = oblique_slab(small_vol, n, r, c, ctr,
                           n_slices=3, thickness_mm=3.0,
                           voxel_size=(1, 1, 1), shape=shape)
        aniso = oblique_slab(small_vol, n, r, c, ctr,
                             n_slices=3, thickness_mm=3.0,
                             voxel_size=(3, 1, 1), shape=shape)
        assert not np.array_equal(iso[0], aniso[0])

    def test_oblique_slab_has_nonzero_content(self, small_vol):
        nz, ny, nx = small_vol.shape
        n, r, c = plane_from_angles("axial", tilt_deg=30, rot_deg=15)
        ctr = (nz // 2, ny // 2, nx // 2)
        out = oblique_slab(small_vol, n, r, c, ctr,
                           n_slices=4, thickness_mm=2.0)
        assert out.max() > 0


# ---------------------------------------------------------------------------
# scout_band
# ---------------------------------------------------------------------------
class TestScoutBand:
    def test_returns_three_scout_keys(self, small_vol):
        n, _, _ = plane_from_angles("axial")
        band = scout_band(small_vol.shape, n, (15, 18, 15), n_slices=3, thickness_mm=2)
        assert set(band.keys()) == {"axial", "coronal", "sagittal"}

    def test_each_scout_has_edges_and_slices_keys(self, small_vol):
        n, _, _ = plane_from_angles("axial")
        band = scout_band(small_vol.shape, n, (15, 18, 15), n_slices=3, thickness_mm=2)
        for v in band.values():
            assert "edges"  in v
            assert "slices" in v

    def test_edges_always_two_entries(self, small_vol):
        n, _, _ = plane_from_angles("axial")
        band = scout_band(small_vol.shape, n, (15, 18, 15), n_slices=3, thickness_mm=2)
        for v in band.values():
            assert len(v["edges"]) == 2

    def test_slices_count_matches_n_slices(self, small_vol):
        n, _, _ = plane_from_angles("axial")
        for ns in (1, 3, 7):
            band = scout_band(small_vol.shape, n, (15, 18, 15),
                              n_slices=ns, thickness_mm=2)
            for v in band.values():
                assert len(v["slices"]) == ns

    def test_axial_slab_no_axial_band(self, small_vol):
        # Pure axial normal → parallel to axial scout → all axial lines are None
        n, _, _ = plane_from_angles("axial")
        band = scout_band(small_vol.shape, n, (15, 18, 15), n_slices=3, thickness_mm=2)
        assert band["axial"]["edges"] == [None, None]
        assert all(s is None for s in band["axial"]["slices"])

    def test_axial_slab_coronal_edges_are_horizontal(self, small_vol):
        # Axial plane intersects coronal scout as horizontal lines (r0 == r1)
        n, _, _ = plane_from_angles("axial")
        band = scout_band(small_vol.shape, n, (15, 18, 15),
                          n_slices=1, thickness_mm=4.0, voxel_size=(1, 1, 1))
        front, back = band["coronal"]["edges"]
        assert front is not None and back is not None
        assert abs(front[1] - front[3]) < 1e-9   # r0 == r1 → horizontal
        assert abs(back[1]  - back[3])  < 1e-9

    def test_axial_slab_edges_symmetric_about_center(self, small_vol):
        # thickness=4, n_slices=1 → half_coverage=2 → edges at ctr[0]±2
        n, _, _ = plane_from_angles("axial")
        ctr = (15, 18, 15)
        band = scout_band(small_vol.shape, n, ctr,
                          n_slices=1, thickness_mm=4.0, voxel_size=(1, 1, 1))
        front, back = band["coronal"]["edges"]
        assert abs(front[1] - (ctr[0] - 2.0)) < 1e-9
        assert abs(back[1]  - (ctr[0] + 2.0)) < 1e-9

    def test_single_slice_centre_line_matches_scout_lines(self, small_vol):
        # The n_slices=1 centre slice line must equal scout_lines at the same center
        n, _, _ = plane_from_angles("axial", tilt_deg=30, rot_deg=20)
        ctr = (15, 18, 15)
        band = scout_band(small_vol.shape, n, ctr, n_slices=1, thickness_mm=2,
                          voxel_size=(1, 1, 1))
        ref  = scout_lines(small_vol.shape, n, ctr, voxel_size=(1, 1, 1))
        for key in ("axial", "coronal", "sagittal"):
            bline = band[key]["slices"][0]
            rline = ref[key]
            if bline is None:
                assert rline is None
            else:
                np.testing.assert_allclose(bline, rline, atol=1e-9)

    def test_oblique_band_has_lines_on_all_scouts(self, small_vol):
        # A fully oblique normal (all axes non-zero) → intersects every scout
        n, _, _ = plane_from_angles("axial", tilt_deg=45, rot_deg=30)
        band = scout_band(small_vol.shape, n, (15, 18, 15), n_slices=3, thickness_mm=2)
        for key in ("axial", "coronal", "sagittal"):
            assert not all(e is None for e in band[key]["edges"])

    def test_gap_moves_edges_further_apart(self, small_vol):
        # Larger gap → larger half_coverage → front edge is further from centre
        n, _, _ = plane_from_angles("axial")
        ctr = (15, 18, 15)
        b0 = scout_band(small_vol.shape, n, ctr, n_slices=3,
                        thickness_mm=2.0, gap_mm=0.0, voxel_size=(1, 1, 1))
        b2 = scout_band(small_vol.shape, n, ctr, n_slices=3,
                        thickness_mm=2.0, gap_mm=2.0, voxel_size=(1, 1, 1))
        # front edge row: ctr[0] - half_cov; with gap half_cov is larger → row smaller
        assert b2["coronal"]["edges"][0][1] < b0["coronal"]["edges"][0][1]

    def test_anisotropic_voxels_shift_edges(self, small_vol):
        # 4.5mm half-coverage: 4.5 vox with 1mm voxels, 1.5 vox with 3mm voxels
        n, _, _ = plane_from_angles("axial")
        ctr = (15, 18, 15)
        b_iso   = scout_band(small_vol.shape, n, ctr, n_slices=3,
                             thickness_mm=3.0, voxel_size=(1, 1, 1))
        b_aniso = scout_band(small_vol.shape, n, ctr, n_slices=3,
                             thickness_mm=3.0, voxel_size=(3, 1, 1))
        front_iso   = b_iso["coronal"]["edges"][0][1]
        front_aniso = b_aniso["coronal"]["edges"][0][1]
        assert not np.isclose(front_iso, front_aniso)

    def test_custom_scout_positions(self, small_vol):
        # Scout planes at an off-centre position shift where edge lines appear
        n, _, _ = plane_from_angles("axial")
        ctr = (15, 18, 15)
        band_default = scout_band(small_vol.shape, n, ctr,
                                  n_slices=1, thickness_mm=4.0, voxel_size=(1, 1, 1))
        band_shifted = scout_band(small_vol.shape, n, ctr,
                                  n_slices=1, thickness_mm=4.0, voxel_size=(1, 1, 1),
                                  scout_positions=(15, 10, 15))
        # The sagittal scout is now at x=15 (same) but coronal scout at y=10
        # → coronal intersection stays the same (normal has no Y component)
        np.testing.assert_allclose(
            band_default["coronal"]["edges"][0],
            band_shifted["coronal"]["edges"][0],
        )


# ---------------------------------------------------------------------------
# Anisotropic voxel spacing
# ---------------------------------------------------------------------------
class TestAnisotropicVoxelSpacing:
    # --- oblique_plane ---

    def test_isotropic_axial_still_matches_get_slice(self, small_vol):
        nz, ny, nx = small_vol.shape
        _, r, c = plane_from_angles("axial")
        ctr = (nz // 2, ny // 2, nx // 2)
        out = oblique_plane(small_vol, r, c, ctr, shape=(ny, nx),
                            voxel_size=(1, 1, 1), pixel_size_mm=1.0)
        np.testing.assert_array_equal(out, get_slice(small_vol, "axial", nz // 2))

    def test_anisotropic_z_axial_base_still_matches_get_slice(self, small_vol):
        # Z voxels being larger doesn't affect an axis-aligned axial slice
        # because row_vec and col_vec have zero Z component.
        nz, ny, nx = small_vol.shape
        _, r, c = plane_from_angles("axial")
        ctr = (nz // 2, ny // 2, nx // 2)
        out = oblique_plane(small_vol, r, c, ctr, shape=(ny, nx),
                            voxel_size=(5, 1, 1), pixel_size_mm=1.0)
        np.testing.assert_array_equal(out, get_slice(small_vol, "axial", nz // 2))

    def test_tilted_plane_differs_with_anisotropic_z(self, small_vol):
        # A 45° tilt samples different Z voxels when Z voxels are 4 mm vs 1 mm.
        nz, ny, nx = small_vol.shape
        _, r, c = plane_from_angles("axial", tilt_deg=45)
        ctr = (nz // 2, ny // 2, nx // 2)
        shape = (20, 20)
        out_iso = oblique_plane(small_vol, r, c, ctr, shape=shape,
                                voxel_size=(1, 1, 1), pixel_size_mm=1.0)
        out_aniso = oblique_plane(small_vol, r, c, ctr, shape=shape,
                                  voxel_size=(4, 1, 1), pixel_size_mm=1.0)
        assert not np.array_equal(out_iso, out_aniso)

    def test_pixel_size_scales_fov(self, small_vol):
        # A larger pixel_size_mm covers more physical space → samples a wider
        # range of voxels → result changes relative to the default.
        nz, ny, nx = small_vol.shape
        _, r, c = plane_from_angles("axial", tilt_deg=30)
        ctr = (nz // 2, ny // 2, nx // 2)
        shape = (20, 20)
        out_small = oblique_plane(small_vol, r, c, ctr, shape=shape,
                                  voxel_size=(1, 1, 1), pixel_size_mm=1.0)
        out_large = oblique_plane(small_vol, r, c, ctr, shape=shape,
                                  voxel_size=(1, 1, 1), pixel_size_mm=3.0)
        assert not np.array_equal(out_small, out_large)

    def test_default_pixel_size_is_min_voxel_size(self, small_vol):
        # pixel_size_mm=None should default to min(voxel_size).
        nz, ny, nx = small_vol.shape
        _, r, c = plane_from_angles("axial", tilt_deg=30)
        ctr = (nz // 2, ny // 2, nx // 2)
        shape = (20, 20)
        vox = (2.0, 0.5, 0.5)
        out_default = oblique_plane(small_vol, r, c, ctr, shape=shape,
                                    voxel_size=vox)
        out_explicit = oblique_plane(small_vol, r, c, ctr, shape=shape,
                                     voxel_size=vox, pixel_size_mm=0.5)
        np.testing.assert_array_equal(out_default, out_explicit)

    # --- scout_lines ---

    def test_isotropic_scout_lines_unchanged(self, small_vol):
        n, _, _ = plane_from_angles("axial", 30, 20)
        ctr = (15, 18, 15)
        lines_default = scout_lines(small_vol.shape, n, ctr)
        lines_iso = scout_lines(small_vol.shape, n, ctr, voxel_size=(1, 1, 1))
        for key in lines_default:
            if lines_default[key] is None:
                assert lines_iso[key] is None
            else:
                np.testing.assert_allclose(lines_default[key], lines_iso[key])

    def test_anisotropic_z_changes_sagittal_line_slope(self, small_vol):
        # A double-oblique with tilt+rot has non-zero Z and Y components in its
        # normal.  Scaling Z by 4× changes n_idx[0] → different sagittal slope.
        n, _, _ = plane_from_angles("axial", tilt_deg=30, rot_deg=45)
        ctr = (15, 18, 15)
        lines_iso = scout_lines(small_vol.shape, n, ctr, voxel_size=(1, 1, 1))
        lines_aniso = scout_lines(small_vol.shape, n, ctr, voxel_size=(4, 1, 1))
        assert lines_iso["sagittal"] is not None
        assert lines_aniso["sagittal"] is not None
        # Both lines pass through center, but their slopes differ → different endpoints
        assert not np.allclose(lines_iso["sagittal"], lines_aniso["sagittal"])

    def test_coronal_plane_axial_line_unaffected_by_z_scaling(self, small_vol):
        # Coronal normal [0,1,0] has zero Z component → n_idx is unchanged by vox_z.
        n, _, _ = plane_from_angles("coronal")
        ctr = (15, 18, 15)
        lines_1 = scout_lines(small_vol.shape, n, ctr, voxel_size=(1, 1, 1))
        lines_4 = scout_lines(small_vol.shape, n, ctr, voxel_size=(4, 1, 1))
        np.testing.assert_allclose(lines_1["axial"], lines_4["axial"])


# ---------------------------------------------------------------------------
# three_scouts
# ---------------------------------------------------------------------------
class TestThreeScouts:
    def test_returns_three_keys(self, small_vol):
        assert set(three_scouts(small_vol).keys()) == {"axial", "coronal", "sagittal"}

    def test_all_slices_2d(self, small_vol):
        for v in three_scouts(small_vol).values():
            assert v.ndim == 2

    def test_shapes_match_volume(self, small_vol):
        nz, ny, nx = small_vol.shape
        scouts = three_scouts(small_vol)
        assert scouts["axial"].shape    == (ny, nx)
        assert scouts["coronal"].shape  == (nz, nx)
        assert scouts["sagittal"].shape == (nz, ny)

    def test_default_center_is_mid_volume(self, small_vol):
        nz, ny, nx = small_vol.shape
        scouts = three_scouts(small_vol)
        np.testing.assert_array_equal(scouts["axial"],    small_vol[nz // 2, :, :])
        np.testing.assert_array_equal(scouts["coronal"],  small_vol[:, ny // 2, :])
        np.testing.assert_array_equal(scouts["sagittal"], small_vol[:, :, nx // 2])

    def test_custom_center(self, small_vol):
        scouts = three_scouts(small_vol, center=(5, 10, 8))
        np.testing.assert_array_equal(scouts["axial"],    small_vol[5,  :, :])
        np.testing.assert_array_equal(scouts["coronal"],  small_vol[:, 10, :])
        np.testing.assert_array_equal(scouts["sagittal"], small_vol[:, :,  8])

    def test_out_of_bounds_center_clamped(self, small_vol):
        nz, ny, nx = small_vol.shape
        scouts = three_scouts(small_vol, center=(9999, 9999, 9999))
        np.testing.assert_array_equal(scouts["axial"], small_vol[nz - 1, :, :])


# ---------------------------------------------------------------------------
# Branch coverage additions
# ---------------------------------------------------------------------------
class TestIntersectLineSinglePoint:
    def test_returns_none_when_line_clips_single_corner(self):
        """When the intersection line passes through exactly one image corner,
        deduplication leaves len(unique)==1 → `return None` (line 409)."""
        # n = [1,1,1]/√3, center at origin, image 10×10.
        # Line equation: nr*r + nc*c = 0 → only point (0,0) is in-bounds.
        n = np.array([1., 1., 1.]) / np.sqrt(3.)
        ctr = np.array([0., 0., 0.])
        # fixed_axis=0 at 0; row_axis=1, col_axis=2; row_len=col_len=10
        result = _intersect_line(n, ctr, 0, 0.0, 1, 2, 10, 10)
        assert result is None
