"""Integration tests for the Qt-free simulation controller (simulator.Simulator).

This is the orchestration layer where every wired physics module connects. It
was previously embedded in the PyQt widget and untestable; extracting it into a
plain class makes these end-to-end checks possible without any display.

Discriminating physics checks use the deterministic `is_map` outputs (qMRI
parameter maps), which skip the unseeded Rician noise that makes image-sequence
renders non-reproducible.
"""
import numpy as np
import pytest

import simulator
from phantom3d import generate_synthetic_3d_brain, get_slice
from phantom3d_extended import add_vessels_3d, add_activation_3d


def base_params(**over):
    """A complete params dict — documents the simulate() input contract."""
    p = dict(
        sequence="Spin Echo", TR=500.0, TE=15.0, TI=2548.0, flip_angle=90.0,
        matrix_size=128, FOV=240.0, fov_fraction=100, bandwidth=125.0, NEX=1,
        slice_thickness=1, accel_factor=1, accel_method="SENSE",
        etl=16, echo_spacing=10.0,
        b_value=1000.0, diff_direction="Left-Right", diff_display="DWI",
        angio_type="TOF", angio_mip_slab=20,
        fmri_display="EPI Image", fmri_volumes=50, fmri_threshold=3.0,
        qmri_display="T1 Map (VFA)",
        field_strength="3T", contrast_enabled=False, contrast_dose=1,
        motion_enabled=False, motion_type="periodic", motion_amplitude=3.0,
        chemical_shift_enabled=False, susceptibility_enabled=False,
        susceptibility_strength=3.0, zipper_enabled=False, snr_level=35.0,
        pf_enabled=False, pf_fraction="Full",
        kspace_filter_enabled=False, kspace_filter_window="hamming",
        b1_inhom_enabled=False, mt_enabled=False, mt_power=50,
        epi_b0_hz=60, epi_esp=5, epi_ghost=10, epi_correct_ghost=False,
        rician_bias_correction=False, pv_sigma=10,
    )
    p.update(over)
    return p


@pytest.fixture(scope="module")
def sim():
    # Downsample the synthetic brain: keeps all tissue labels for the recovery
    # checks while making the vessel builder / B0 FFT / renders fast.
    vol = generate_synthetic_3d_brain()[::2, ::2, ::2].copy()
    s = simulator.Simulator()
    s.volume = vol
    s.vessels = add_vessels_3d(vol)
    s.activation = add_activation_3d(vol)
    s.real_tof = None
    s.native_fov = 220.0
    s.orientation = "axial"
    s.slice_idx = vol.shape[0] // 2
    return s


SEQUENCES = [
    "Spin Echo", "FSE / TSE", "Gradient Echo", "Inversion Recovery",
    "Diffusion (DWI)", "MR Angiography", "fMRI (BOLD)",
    "Quantitative (qMRI)", "Echo Planar (EPI)",
]


def test_default_params_is_a_valid_contract(sim):
    """simulator.default_params() drives a render end-to-end (headless API)."""
    img, m = sim.simulate(simulator.default_params(matrix_size=64))
    assert img.ndim == 2 and np.all(np.isfinite(img))
    assert "scan_time" in m and m["scan_time"] > 0


@pytest.mark.parametrize("seq", SEQUENCES)
def test_each_sequence_renders_sane(sim, seq):
    """Every sequence dispatches to a finite, non-negative 2-D image with metrics."""
    img, metrics = sim.simulate(base_params(sequence=seq))
    assert img.ndim == 2 and img.size > 0
    assert np.all(np.isfinite(img))
    assert np.all(img >= 0)
    assert float(img.max()) > 0.0
    for key in ("scan_time", "resolution", "sar_head", "g_factor", "snr_eff"):
        assert key in metrics
    assert metrics["scan_time"] > 0
    assert metrics["g_factor"] >= 1.0


def test_qmri_t1_map_recovers_tissue_values(sim):
    """Full controller path: VFA T1 map recovers the tissue_db 3T values.

    pv_sigma=0 isolates fit accuracy from partial-volume boundary blending
    (which is exercised separately in test_rendering)."""
    p = base_params(sequence="Quantitative (qMRI)", qmri_display="T1 Map (VFA)",
                    field_strength="3T", pv_sigma=0)
    t1, _ = sim.simulate(p)
    labels = sim._get_phantom_slice("axial", sim.slice_idx, p)
    assert t1.shape == labels.shape
    assert np.median(t1[labels == 3]) == pytest.approx(830, abs=20)   # WM
    assert np.median(t1[labels == 2]) == pytest.approx(1330, abs=30)  # GM
    assert np.median(t1[labels == 1]) == pytest.approx(4500, abs=50)  # CSF


def test_qmri_t1_map_tracks_field_strength(sim):
    """Deterministic map: WM T1 ~580 at 1.5T vs ~830 at 3T."""
    p15 = base_params(sequence="Quantitative (qMRI)", qmri_display="T1 Map (VFA)",
                      field_strength="1.5T")
    p3 = base_params(sequence="Quantitative (qMRI)", qmri_display="T1 Map (VFA)",
                     field_strength="3T")
    t1_15, _ = sim.simulate(p15)
    t1_3, _ = sim.simulate(p3)
    labels = sim._get_phantom_slice("axial", sim.slice_idx, p3)
    assert np.median(t1_15[labels == 3]) == pytest.approx(580, abs=20)
    assert np.median(t1_3[labels == 3]) == pytest.approx(830, abs=20)


def test_t2_map_exceeds_t2star_map(sim):
    """T2 (SE) and T2* (GRE) quantitative maps are distinct, with T2 > T2*."""
    t2, _ = sim.simulate(base_params(sequence="Quantitative (qMRI)",
                                     qmri_display="T2 Map (multi-echo)"))
    t2s, _ = sim.simulate(base_params(sequence="Quantitative (qMRI)",
                                      qmri_display="T2* Map (multi-echo)"))
    assert t2.max() > t2s.max()


def test_accel_lowers_snr_via_real_g_factor(sim):
    """R=3 carries a g-factor > 1, so its metric reflects the real coil penalty."""
    _, m1 = sim.simulate(base_params(accel_factor=1))
    _, m3 = sim.simulate(base_params(accel_factor=3))
    assert m1["g_factor"] == pytest.approx(1.0)
    assert m3["g_factor"] > 1.2


def test_synthetic_se_is_t1_weighted(sim):
    """Synthetic SE at short TR/TE shows T1 contrast (WM > GM > CSF), noiseless."""
    p = base_params(sequence="Quantitative (qMRI)", qmri_display="Synthetic SE",
                    TR=500.0, TE=15.0)
    img, _ = sim.simulate(p)
    labels = sim._get_phantom_slice("axial", sim.slice_idx, p)
    wm = np.median(img[labels == 3]); gm = np.median(img[labels == 2]); csf = np.median(img[labels == 1])
    assert wm > gm > csf
