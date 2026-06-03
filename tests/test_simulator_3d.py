"""Tests for the Simulator's true-3D acquisition path (simulator._simulate_3d /
reslice_3d). Uses a small synthetic labelled volume so the suite stays fast."""
import numpy as np
import pytest

from simulator import Simulator, default_params


def _synthetic_volume(Z=40, Y=48, X=44):
    """A small labelled brain-ish volume (WM/GM/CSF) for fast 3D tests."""
    vol = np.zeros((Z, Y, X), dtype=np.uint8)
    z, y, x = np.ogrid[:Z, :Y, :X]
    r = np.sqrt(((z - Z / 2) / (Z / 2.4)) ** 2 + ((y - Y / 2) / (Y / 2.4)) ** 2
                + ((x - X / 2) / (X / 2.4)) ** 2)
    vol[r < 1.0] = 3                      # white matter
    vol[r < 0.7] = 2                      # gray matter
    vol[r < 0.35] = 1                     # CSF
    return vol


@pytest.fixture(scope="module")
def sim():
    s = Simulator()
    s.volume = _synthetic_volume()
    s.orientation = "axial"
    s.slice_idx = 20
    return s


def _p(**kw):
    base = dict(sequence="Gradient Echo", TR=30, TE=6, flip_angle=30,
                matrix_size=44, acq3d=True, n_partitions=16)
    base.update(kw)
    return default_params(**base)


def test_3d_renders_finite_nonblank(sim):
    img, m = sim.simulate(_p())
    assert img.ndim == 2 and np.all(np.isfinite(img)) and img.max() > 0
    assert m["snr_wm"] > 0 and m["scan_time"] > 0


def test_recon_block_stored(sim):
    sim.simulate(_p(n_partitions=16))
    assert sim._recon3d is not None
    assert sim._recon3d_geom["through"] == 0          # axial → axis 0
    assert sim._recon3d_geom["n_part"] == 16


def test_reslice_same_plane_is_a_partition(sim):
    sim.orientation = "axial"; sim.slice_idx = 20
    img, _ = sim.simulate(_p(n_partitions=16))
    same = sim.reslice_3d("axial", 20)
    assert same is not None and same.shape == img.shape


def test_reslice_orthogonal_is_thin_band(sim):
    sim.orientation = "axial"; sim.slice_idx = 20
    sim.simulate(_p(n_partitions=12))
    cor = sim.reslice_3d("coronal", 24)               # reformat, no re-acquire
    assert cor is not None
    # the through-plane (axial Z) extent of the slab shows up as the short axis
    assert min(cor.shape) == 12


def test_reslice_outside_slab_returns_none(sim):
    sim.orientation = "axial"; sim.slice_idx = 20
    sim.simulate(_p(n_partitions=8))
    assert sim.reslice_3d("axial", 0) is None          # far outside the 8-slab


def test_reslice_none_without_acquisition():
    s = Simulator(); s.volume = _synthetic_volume()
    assert s.reslice_3d("axial", 10) is None


def test_snr_increases_with_partitions(sim):
    # Low base SNR (noise-dominated) so the √Nz gain shows through the empirical
    # ROI measurement rather than saturating at the noiseless ROI heterogeneity.
    lo = sim.simulate(_p(n_partitions=8, snr_level=2))[1]["snr_wm"]
    hi = sim.simulate(_p(n_partitions=64, snr_level=2))[1]["snr_wm"]
    assert hi > 1.5 * lo, f"√Nz SNR gain not seen: 8->{lo:.2f}, 64->{hi:.2f}"


def test_3d_scan_time_longer_than_2d(sim):
    _, m3 = sim.simulate(_p(n_partitions=24))
    _, m2 = sim.simulate(_p(n_partitions=24, acq3d=False, slice_thickness=1))
    assert m3["scan_time"] > 5 * m2["scan_time"]       # encodes ~24 kz partitions


def test_non_3d_sequence_ignores_toggle(sim):
    # Diffusion is not a 3D-capable sequence, so acq3d is ignored (2D path).
    sim.orientation = "axial"; sim.slice_idx = 20; sim._recon3d = None
    img, _ = sim.simulate(_p(sequence="Diffusion (DWI)", acq3d=True,
                             diff_display="DWI", b_value=1000))
    assert img is not None
    assert sim._recon3d is None                        # no 3D recon block built


def test_2d_path_leaves_no_recon_block(sim):
    sim._recon3d = None
    sim.simulate(_p(acq3d=False, slice_thickness=1))
    assert sim._recon3d is None                        # acq3d off → pure 2D path
