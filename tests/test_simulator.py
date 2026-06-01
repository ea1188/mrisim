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


def test_accel_noise_is_spatially_structured(sim, monkeypatch):
    """Parallel imaging applies *spatially-varying* g-factor noise: the sigma fed
    to the Rician step is a scalar without acceleration but a non-uniform 2-D map
    with SENSE/GRAPPA (so the image shows structured g-factor noise, not a flat
    SNR drop)."""
    import rician
    captured = {}

    def spy(image, sigma, *a, **k):
        captured["sigma"] = sigma
        return image

    monkeypatch.setattr(rician, "add_rician_noise", spy)

    sim.simulate(base_params(accel_factor=1))
    assert np.ndim(captured["sigma"]) == 0                 # scalar, uniform noise

    sim.simulate(base_params(accel_factor=4, accel_method="SENSE"))
    s = captured["sigma"]
    assert np.ndim(s) == 2                                 # per-pixel sigma map
    assert float(np.std(s)) > 0                            # genuinely non-uniform


def test_acceleration_is_modest_and_nex_recovers(sim, monkeypatch):
    """Acceleration retains image quality at a modest SNR cost (~g·√R), and NEX
    buys it back: R=2 costs only ~1.4–1.6× more noise, and R=2 with NEX=2 returns
    to ~the unaccelerated noise level (at the same scan time)."""
    import rician
    levels = []

    def spy(image, sigma, *a, **k):
        levels.append(float(np.mean(sigma)))
        return image

    monkeypatch.setattr(rician, "add_rician_noise", spy)

    def noise(**kw):
        levels.clear()
        sim.simulate(base_params(**kw))
        return levels[-1]

    s1 = noise(accel_factor=1)
    s2 = noise(accel_factor=2, accel_method="SENSE")
    s2_nex2 = noise(accel_factor=2, accel_method="SENSE", NEX=2)

    assert 1.3 < s2 / s1 < 1.8            # R=2: modest cost (~g·√2), not a blow-up
    assert abs(s2_nex2 / s1 - 1.0) < 0.15  # NEX=2 recovers to ~unaccelerated noise


def test_cs_less_noise_penalty_than_sense(sim):
    """Compressed sensing carries no coil g-factor penalty, so at the same R it
    reports a lower effective g (and thus less SNR loss) than SENSE."""
    _, m_sense = sim.simulate(base_params(accel_factor=3, accel_method="SENSE"))
    _, m_cs = sim.simulate(base_params(accel_factor=3, accel_method="CS"))
    assert m_cs["g_factor"] < m_sense["g_factor"]
    assert m_cs["g_factor"] == pytest.approx(1.0)


def test_partial_fourier_raises_noise(monkeypatch):
    """Partial Fourier acquires fewer phase-encode lines, so SNR drops
    ~sqrt(fraction) and the *calibrated* noise sigma rises by 1/sqrt(fraction).

    The calibration sigma fed to add_rician_noise is deterministic; the metric
    noise_sigma is re-measured off the (unseeded) noisy image, so we spy on the
    actual sigma instead. With the tissue reference pinned, sigma == 1/eff_snr,
    and this ratio collapses to 1.0 if the PF factor is dropped from eff_snr."""
    import rician
    captured = []
    monkeypatch.setattr(rician, "add_rician_noise",
                        lambda image, sigma, *a, **k: (captured.append(float(sigma)), image)[1])

    vol = np.full((50, 70, 70), 3, np.uint8)   # uniform WM
    s = simulator.Simulator()
    s.volume = vol; s.vessels = vol * 0; s.activation = vol * 0
    s.orientation = "axial"; s.slice_idx = 25; s.native_fov = 220.0
    s._tissue_ref_signal = lambda recon, ph: 1.0   # pin reference -> isolate eff_snr

    s.simulate(base_params(pf_enabled=False, pf_fraction="Full"))
    s.simulate(base_params(pf_enabled=True, pf_fraction="5/8"))
    sigma_full, sigma_pf = captured[0], captured[1]
    ratio = sigma_pf / sigma_full
    assert ratio == pytest.approx(1.0 / np.sqrt(0.625), rel=0.02)  # 1.0 without the fix


def test_real_mri_texture_modulates_signal(monkeypatch):
    """A real-MRI texture field multiplies the per-label signal (restoring organ
    heterogeneity) while preserving label-based contrast. With noise disabled the
    modulation is exact; a shape-mismatched texture is ignored (synthetic fallback)."""
    import rician
    monkeypatch.setattr(rician, "add_rician_noise", lambda img, s, *a, **k: img)
    vol = np.full((40, 60, 60), 3, np.uint8)   # uniform WM
    s = simulator.Simulator()
    s.volume = vol; s.vessels = vol * 0; s.activation = vol * 0
    s.orientation = "axial"; s.slice_idx = 20; s.native_fov = 220.0
    p = base_params(sequence="Spin Echo", TR=500, TE=15, pv_sigma=0)

    s.texture = np.full(vol.shape, 1.0, np.float32)
    img1, _ = s.simulate(p); m1 = float(img1[img1 > 0].mean())
    s.texture = np.full(vol.shape, 1.3, np.float32)
    img2, _ = s.simulate(p); m2 = float(img2[img2 > 0].mean())
    assert m2 / m1 == pytest.approx(1.3, rel=0.05)   # texture scales signal

    s.texture = np.full((5, 5, 5), 1.3, np.float32)   # wrong shape -> ignored
    img3, _ = s.simulate(p)
    assert img3.shape == img1.shape


@pytest.mark.parametrize("display", ["EPI Image", "Activation Map", "T-statistic Map"])
def test_fmri_survives_fov_crop(sim, display):
    """A reduced FOV crops the phantom slice; the activation slice must be cropped
    with the SAME geometry or masking raises IndexError (regression: fMRI crash)."""
    img, _ = sim.simulate(base_params(sequence="fMRI (BOLD)", fmri_display=display,
                                       FOV=160, fmri_volumes=20))
    ph = sim._get_phantom_slice("axial", sim.slice_idx, base_params(FOV=160))
    assert img.shape == ph.shape and img.ndim == 2


def test_synthetic_se_is_t1_weighted(sim):
    """Synthetic SE at short TR/TE shows T1 contrast (WM > GM > CSF), noiseless."""
    p = base_params(sequence="Quantitative (qMRI)", qmri_display="Synthetic SE",
                    TR=500.0, TE=15.0)
    img, _ = sim.simulate(p)
    labels = sim._get_phantom_slice("axial", sim.slice_idx, p)
    wm = np.median(img[labels == 3]); gm = np.median(img[labels == 2]); csf = np.median(img[labels == 1])
    assert wm > gm > csf


def test_slice_profile_weights_centre_weighted():
    """Imperfect RF slice profile weights the slab centre more than the edges."""
    for n in (3, 5, 7):
        w = simulator._slice_profile_weights(n)
        assert w.shape == (n,)
        assert np.isclose(w.sum(), 1.0)
        assert w[n // 2] > w[0]                 # centre heavier than edge
        assert w[0] == pytest.approx(w[-1])     # symmetric
    assert simulator._slice_profile_weights(1).tolist() == [1.0]


def test_crosstalk_factor_contiguous_multislice():
    """Cross-talk loses SNR for contiguous multi-slice; a single slice or a wide
    gap has none, and the loss falls off as the gap grows."""
    assert simulator._crosstalk_snr_factor(1, 0.0, 5) == 1.0          # single slice: none
    f0 = simulator._crosstalk_snr_factor(8, 0.0, 5)
    f_gap = simulator._crosstalk_snr_factor(8, 4.0, 5)
    assert f0 < 0.9                                                   # zero gap: real loss
    assert f0 < f_gap < 1.0                                           # gap recovers signal


def test_crosstalk_raises_noise(sim):
    """Contiguous multi-slice reports more noise than a single slice; a gap recovers it."""
    _, m1 = sim.simulate(base_params(n_slices=1, slice_gap=0, slice_thickness=5))
    _, m_contig = sim.simulate(base_params(n_slices=8, slice_gap=0, slice_thickness=5))
    _, m_gap = sim.simulate(base_params(n_slices=8, slice_gap=12, slice_thickness=5))
    assert m_contig["noise_sigma"] > m1["noise_sigma"]
    assert m_gap["noise_sigma"] < m_contig["noise_sigma"]


def test_dwi_snr_falls_with_b_value(sim):
    """Fixed noise floor: high-b DWI is genuinely noisier (SNR drops with b),
    instead of the noise re-scaling to the attenuated signal."""
    _, m_low = sim.simulate(base_params(sequence="Diffusion (DWI)", diff_display="DWI", b_value=0))
    _, m_high = sim.simulate(base_params(sequence="Diffusion (DWI)", diff_display="DWI", b_value=3000))
    assert m_high["noise_sigma"] == m_high["noise_sigma"]   # finite
    assert m_high["snr_wm"] < 0.6 * m_low["snr_wm"]


def test_reference_protocol_snr_preserved(sim):
    """At the reference protocol (SE 500/15) the fixed noise floor leaves the
    measured SNR ~ the requested snr_level (calibration unchanged)."""
    _, m = sim.simulate(base_params(sequence="Spin Echo", TR=500, TE=15, snr_level=40))
    assert 25 < m["snr_wm"] < 60          # within a reasonable band of the slider
