import numpy as np
import pytest

import reconstruction as rc
import web_adapter as wa


@pytest.fixture(scope="module")
def block():
    """A small synthetic 3-D recon block (Z, Y, X) with a bright blob, so MIP and
    MPR have something to find."""
    b = np.zeros((20, 40, 36), dtype=float)
    b[:] = 0.1
    b[8:12, 18:22, 16:20] = 1.0          # bright cube
    b[5, 10, 10] = 0.8                    # a stray bright voxel for MIP
    return b


class TestMPR:
    def test_triplanar_shapes_and_planes(self, block):
        tri = rc.mpr_triplanar(block, (10, 20, 18))
        assert set(tri) == {"axial", "coronal", "sagittal"}
        assert tri["axial"].shape == (40, 36)     # (Y, X)
        assert tri["coronal"].shape == (20, 36)   # (Z, X)
        assert tri["sagittal"].shape == (20, 40)  # (Z, Y)

    def test_center_is_clamped(self, block):
        tri = rc.mpr_triplanar(block, (999, -5, 18))   # out of range -> clamped
        assert tri["axial"].shape == (40, 36)


class TestMIP:
    def test_mip_is_brightest_along_ray(self, block):
        # A thick-slab MIP must be >= the central slice everywhere (it takes the max).
        ax = rc.THROUGH_AXIS["axial"]
        central = block[10]
        mip = rc.thick_slab_mip(block, "axial", 10, thickness=block.shape[ax])
        assert mip.shape == central.shape
        assert np.all(mip >= central - 1e-9)
        assert mip.max() >= central.max()

    def test_thickness_one_is_a_plain_slice(self, block):
        mip1 = rc.thick_slab_mip(block, "coronal", 20, thickness=1)
        assert mip1.shape == (20, 36)
        # full-thickness MIP must be at least as bright as the 1-slice version
        full = rc.thick_slab_mip(block, "coronal", 20, thickness=40)
        assert full.max() >= mip1.max()

    def test_mip_thicker_is_monotone(self, block):
        thin = rc.thick_slab_mip(block, "axial", 10, 2).sum()
        thick = rc.thick_slab_mip(block, "axial", 10, 20).sum()
        assert thick >= thin

    def test_projection_modes_ordered(self, block):
        """MinIP <= AIP <= MIP at every pixel (min <= mean <= max along the ray)."""
        mip = rc.thick_slab_projection(block, "coronal", 10, 16, "mip")
        minip = rc.thick_slab_projection(block, "coronal", 10, 16, "minip")
        aip = rc.thick_slab_projection(block, "coronal", 10, 16, "aip")
        assert minip.shape == aip.shape == mip.shape
        assert np.all(minip <= aip + 1e-9) and np.all(aip <= mip + 1e-9)
        # An unknown mode falls back to MIP (never errors).
        assert np.array_equal(rc.thick_slab_projection(block, "coronal", 10, 16, "bogus"), mip)

    def test_thick_slab_mip_wrapper_matches_mip_mode(self, block):
        assert np.array_equal(rc.thick_slab_mip(block, "axial", 10, 12),
                              rc.thick_slab_projection(block, "axial", 10, 12, "mip"))


class TestRotatingAndOblique:
    def test_rotating_mip_shape(self, block):
        proj = rc.rotating_mip(block, azimuth_deg=0, elevation_deg=0)
        assert proj.ndim == 2 and proj.shape[0] == block.shape[0]

    def test_oblique_is_finite(self, block):
        ob = rc.oblique_mpr(block, (10, 20, 18), tilt_deg=15, rot_deg=10)
        assert ob.ndim == 2 and np.isfinite(ob).all()

    def test_oblique_zero_angle_matches_axial(self, block):
        """At tilt=rot=0 the oblique plane through the centre is the axial slice."""
        ob = rc.oblique_mpr(block, (10, 20, 18), 0, 0, base="axial",
                            shape=(40, 36))
        ax = rc.mpr_triplanar(block, (10, 20, 18))["axial"]
        # same bright region recovered (allow interpolation tolerance)
        assert abs(float(ob.max()) - float(ax.max())) < 0.2


@pytest.mark.parametrize("mode,extra", [
    ("mpr", {}),
    ("mip", {"mip_plane": "coronal", "mip_thickness": 16}),
    ("mip", {"mip_plane": "coronal", "mip_thickness": 16, "mip_mode": "minip"}),
    ("mip", {"mip_plane": "coronal", "mip_thickness": 16, "mip_mode": "aip"}),
    ("mip", {"mip_plane": "axial", "mip_thickness": 10, "mip_center_frac": 0.25}),
    ("rmip", {"azimuth": 30, "elevation": 10}),
    ("oblique", {"tilt": 20, "rot": 15}),
])
def test_reconstruct_endpoint_renders(mode, extra):
    wa.init()
    base = {"region": "Brain", "orientation": "axial", "slice_idx": 90,
            "params": {"sequence": "Gradient Echo", "TR": 500, "TE": 15,
                       "acq3d": True, "n_partitions": 40}}
    r = wa.reconstruct({**base, "mode": mode, **extra})
    assert r["ok"], r.get("error")
    assert r["mode"] == mode and r["panels"]
    for png in r["panels"].values():
        assert png.startswith("data:image/png")
    if mode == "mpr":
        assert set(r["panels"]) == {"axial", "coronal", "sagittal"}


def test_reconstruct_requires_3d_slab():
    wa.init()
    r = wa.reconstruct({"region": "Brain", "orientation": "axial", "slice_idx": 90,
                        "mode": "mpr", "params": {"sequence": "Spin Echo"}})
    assert not r["ok"] and "3-D" in r["error"]


def test_reconstruct_cine_returns_distinct_frames():
    """The rotating-MIP cine pre-renders a stack of distinct frames (a full spin)
    and needs a 3-D slab."""
    wa.init()
    base = {"region": "Brain", "orientation": "axial", "slice_idx": 90,
            "params": {"sequence": "Gradient Echo", "TR": 500, "TE": 15,
                       "acq3d": True, "n_partitions": 40}}
    r = wa._host().reconstruct_cine({**base, "n_frames": 8, "elevation": 10})
    assert r["ok"] and len(r["frames"]) == 8
    assert all(f.startswith("data:image/png") for f in r["frames"])
    assert len(set(r["frames"])) == 8, "cine frames should differ (the MIP rotates)"
    r2 = wa._host().reconstruct_cine({"region": "Brain", "orientation": "axial",
                                      "slice_idx": 90, "params": {"sequence": "Spin Echo"}})
    assert not r2["ok"]
