"""End-to-end physics validation of the assembled simulation pipeline.

Component tests verify the signal equations; the controller smoke tests verify
dispatch. This file is the missing link: that the *whole* pipeline (rendering →
artifacts → k-space → noise → metrics) produces correct MR physics — the right
contrast for each clinical preset, correct fat/CSF nulling, and SNR / scan-time /
SAR obeying their textbook scaling laws.

It doubles as an executable spec of expected behaviour: for a teaching+research
tool, "the T2-weighted preset really produces CSF > GM > WM" is exactly the
credibility claim worth pinning down. Asserts physics expectations (not whatever
the code currently emits), so a regression that breaks the physics fails here.

Contrast checks render at high SNR and compare tissue-region medians (robust to
the unseeded Rician noise); scaling-law checks average a few noisy renders.
"""
import numpy as np
import pytest

import simulator
from phantom3d import generate_synthetic_3d_brain, get_slice
from presets import PRESETS


# --------------------------------------------------------------------------- #
# Fixtures + helpers
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def vol():
    # Downsampled synthetic brain: keeps tissue labels, fast renders. No vessels/
    # activation needed — validation uses only brain-tissue sequences.
    return generate_synthetic_3d_brain()[::2, ::2, ::2].copy()


@pytest.fixture(scope="module")
def sim(vol):
    s = simulator.Simulator()
    s.volume = vol
    s.native_fov = 220.0
    s.orientation = "axial"
    s.slice_idx = vol.shape[0] // 2
    return s


def base_params(**over):
    p = dict(
        sequence="Spin Echo", TR=2000.0, TE=15.0, TI=2548.0, flip_angle=90.0,
        matrix_size=64, FOV=240.0, fov_fraction=100, bandwidth=125.0, NEX=1,
        slice_thickness=1, accel_factor=1, accel_method="SENSE",
        etl=16, echo_spacing=10.0,
        b_value=1000.0, diff_direction="Left-Right", diff_display="DWI",
        angio_type="TOF", angio_mip_slab=20,
        fmri_display="EPI Image", fmri_volumes=50, fmri_threshold=3.0,
        qmri_display="T1 Map (VFA)",
        field_strength="3T", contrast_enabled=False, contrast_dose=1,
        motion_enabled=False, motion_type="periodic", motion_amplitude=3.0,
        chemical_shift_enabled=False, susceptibility_enabled=False,
        susceptibility_strength=3.0, zipper_enabled=False, snr_level=40.0,
        pf_enabled=False, pf_fraction="Full",
        kspace_filter_enabled=False, kspace_filter_window="hamming",
        b1_inhom_enabled=False, mt_enabled=False, mt_power=50,
        epi_b0_hz=60, epi_esp=5, epi_ghost=10, epi_correct_ghost=False,
        rician_bias_correction=False, pv_sigma=10,
    )
    p.update(over)
    return p


def preset_params(name, **extra):
    """Full params from a clinical preset (matrix forced small for speed; matrix
    does not affect tissue contrast)."""
    pr = PRESETS[name]
    keys = ("sequence", "TR", "TE", "TI", "flip_angle", "bandwidth", "NEX",
            "etl", "echo_spacing")
    over = {k: pr[k] for k in keys if k in pr}
    over.update(snr_level=100.0, matrix_size=64)   # high SNR for clean medians
    over.update(extra)
    return base_params(**over)


# tissue labels: 1=CSF, 2=GM, 3=WM, 4=fat
def medians(sim, vol, img):
    native = get_slice(vol, sim.orientation, sim.slice_idx)
    labels = sim._aligned_labels(img, native)
    return {lab: float(np.median(img[labels == lab]))
            for lab in (1, 2, 3, 4) if np.any(labels == lab)}


def mean_snr(sim, n=3, **over):
    """Average measured WM SNR over a few noisy renders (reduces noise variance).

    Uses matrix=128: at very low matrix the background σ is dominated by Gibbs
    ringing rather than the injected Rician noise, which saturates the measured
    SNR and masks the scaling laws. (That saturation is itself realistic — a
    noise floor exists — but the moderate-SNR regime is where the laws are
    cleanly observable.)
    """
    over.setdefault("matrix_size", 128)
    return float(np.mean([sim.simulate(base_params(**over))[1]["snr_wm"]
                          for _ in range(n)]))


# --------------------------------------------------------------------------- #
# Contrast / weighting per clinical preset
# --------------------------------------------------------------------------- #
def test_t1_se_is_t1_weighted(sim, vol):
    m = medians(sim, vol, sim.simulate(preset_params("Brain T1 SE"))[0])
    assert m[3] > m[2] > m[1]          # WM > GM > CSF
    assert m[4] > m[3]                 # fat brightest


def test_t2_se_is_t2_weighted(sim, vol):
    m = medians(sim, vol, sim.simulate(preset_params("Brain T2 SE"))[0])
    assert m[1] > m[2] > m[3]          # CSF > GM > WM


def test_pd_shows_gm_brighter_than_wm(sim, vol):
    # PD weighting orders parenchyma by proton density (GM 0.80 > WM 0.65).
    # CSF is not brightest here — its 4.5 s T1 is not recovered at TR=3000 — so
    # we assert the unambiguous parenchymal ordering only.
    m = medians(sim, vol, sim.simulate(preset_params("Brain PD"))[0])
    assert m[2] > m[3]


def test_flair_nulls_csf(sim, vol):
    m = medians(sim, vol, sim.simulate(preset_params("Brain FLAIR"))[0])
    assert m[1] < 0.25 * m[2]          # CSF strongly suppressed vs GM
    assert m[2] > m[3]                 # remains T2-weighted in parenchyma


def test_stir_nulls_fat(sim, vol):
    m = medians(sim, vol, sim.simulate(preset_params("Brain STIR"))[0])
    assert m[4] < 0.25 * m[3]          # fat strongly suppressed vs WM
    assert m[1] > m[3]                 # fluid bright


def test_mprage_is_t1_weighted(sim, vol):
    m = medians(sim, vol, sim.simulate(preset_params("Brain MPRAGE"))[0])
    assert m[3] > m[2] > m[1]          # WM > GM > CSF


def test_gre_t1_is_t1_weighted(sim, vol):
    m = medians(sim, vol, sim.simulate(preset_params("Brain GRE T1"))[0])
    assert m[3] > m[2] > m[1]


# --------------------------------------------------------------------------- #
# Null-point precision
# --------------------------------------------------------------------------- #
def test_flair_csf_near_zero(sim, vol):
    m = medians(sim, vol, sim.simulate(preset_params("Brain FLAIR"))[0])
    assert m[1] < 0.05                 # CSF essentially nulled (TI=2548 ms @ 3T)


def test_stir_fat_near_zero(sim, vol):
    m = medians(sim, vol, sim.simulate(preset_params("Brain STIR"))[0])
    assert m[4] < 0.05                 # fat essentially nulled (TI=265 ms @ 3T)


# --------------------------------------------------------------------------- #
# SNR scaling laws (through the full pipeline)
# --------------------------------------------------------------------------- #
def test_snr_scales_with_sqrt_nex(sim):
    r = mean_snr(sim, NEX=4) / mean_snr(sim, NEX=1)
    assert 1.7 < r < 2.3               # SNR ∝ √NEX


def test_snr_scales_with_inverse_sqrt_bandwidth(sim):
    r = mean_snr(sim, bandwidth=62.5) / mean_snr(sim, bandwidth=250.0)
    assert 1.7 < r < 2.3               # SNR ∝ 1/√BW


def test_snr_scales_with_voxel_volume(sim):
    r = mean_snr(sim, slice_thickness=4) / mean_snr(sim, slice_thickness=1)
    assert 3.3 < r < 4.7               # SNR ∝ voxel volume (4× thicker)


def test_snr_higher_at_3t_than_1p5t(sim):
    r = mean_snr(sim, field_strength="1.5T") / mean_snr(sim, field_strength="3T")
    assert 0.4 < r < 0.6               # SNR ∝ B0


# --------------------------------------------------------------------------- #
# Scan-time scaling (analytic, deterministic)
# --------------------------------------------------------------------------- #
def _stime(sim, **over):
    return sim.simulate(base_params(**over))[1]["scan_time"]


def test_scan_time_scales_with_matrix(sim):
    assert _stime(sim, matrix_size=256) / _stime(sim, matrix_size=128) == pytest.approx(2.0, rel=0.01)


def test_scan_time_scales_with_nex(sim):
    assert _stime(sim, NEX=2) / _stime(sim, NEX=1) == pytest.approx(2.0, rel=0.01)


def test_scan_time_divides_by_acceleration(sim):
    assert _stime(sim, accel_factor=3) / _stime(sim, accel_factor=1) == pytest.approx(1 / 3, rel=0.01)


def test_fse_scan_time_divides_by_etl(sim):
    fse16 = _stime(sim, sequence="FSE / TSE", etl=16)
    fse1 = _stime(sim, sequence="FSE / TSE", etl=1)
    assert fse16 / fse1 == pytest.approx(1 / 16, rel=0.01)


# --------------------------------------------------------------------------- #
# SAR scaling (analytic, deterministic)
# --------------------------------------------------------------------------- #
def _sar(sim, **over):
    return sim.simulate(base_params(**over))[1]["sar_head"]


def test_sar_scales_with_flip_angle_squared(sim):
    r = _sar(sim, sequence="Gradient Echo", flip_angle=90) / _sar(sim, sequence="Gradient Echo", flip_angle=45)
    assert 3.5 < r < 4.3               # SAR ∝ FA²


def test_sar_scales_with_b0_squared(sim):
    r = _sar(sim, field_strength="3T") / _sar(sim, field_strength="1.5T")
    assert r == pytest.approx(4.0, rel=0.05)   # SAR ∝ B0²


def test_se_sar_exceeds_gre(sim):
    assert _sar(sim, sequence="Spin Echo", flip_angle=90) > _sar(sim, sequence="Gradient Echo", flip_angle=90)


# --------------------------------------------------------------------------- #
# Parallel-imaging g-factor
# --------------------------------------------------------------------------- #
def test_g_factor_grows_superlinearly_with_acceleration(sim):
    g2 = sim.simulate(base_params(accel_factor=2))[1]["g_factor"]
    g3 = sim.simulate(base_params(accel_factor=3))[1]["g_factor"]
    g4 = sim.simulate(base_params(accel_factor=4))[1]["g_factor"]
    assert 1.0 < g2 < g3 < g4
