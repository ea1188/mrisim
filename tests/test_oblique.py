import numpy as np
import pytest
from oblique import (
    _rot_matrix,
    _intersect_line,
    plane_from_angles,
    oblique_plane,
    scout_lines,
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
