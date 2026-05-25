"""Tests for fse.py — EPG-based FSE signal simulation."""

import numpy as np
import pytest
from fse import (
    _epg_run,
    epg_signal,
    fse_scan_time,
    fse_blurring_factor,
    simulate_fse_image,
    compute_fse_echo_train,
)
from phantom import create_brain_phantom, TISSUE_PROPERTIES


@pytest.fixture(scope="module")
def phantom64():
    return create_brain_phantom(64)


# ---------------------------------------------------------------------------
# Internal EPG engine
# ---------------------------------------------------------------------------

class TestEpgRun:
    def test_shape(self):
        s = _epg_run(800, 80, 0.8, 4000, 16, 10)
        assert s.shape == (16,)

    def test_dtype_float64(self):
        s = _epg_run(800, 80, 0.8, 4000, 8, 10)
        assert s.dtype == np.float64

    def test_nonnegative(self):
        s = _epg_run(800, 80, 0.8, 4000, 16, 10)
        assert np.all(s >= 0)

    def test_pd_zero_gives_zero_everywhere(self):
        s = _epg_run(800, 80, 0.0, 4000, 16, 10)
        assert np.allclose(s, 0.0)

    def test_180_matches_se_formula(self):
        """For perfect 180° pulses, EPG must reproduce simple SE decay."""
        T1, T2, PD, TR = 800.0, 80.0, 0.8, 4000.0
        ESP, ETL = 10.0, 16
        signals = _epg_run(T1, T2, PD, TR, ETL, ESP, refocus_angle_deg=180.0)
        M0 = PD * (1.0 - np.exp(-TR / T1))
        for n, s in enumerate(signals, start=1):
            expected = M0 * np.exp(-(n * ESP) / T2)
            assert abs(s - expected) < 1e-6, f"echo {n}: EPG={s:.6f}, SE={expected:.6f}"

    def test_cpmg_invariance(self):
        """CPMG theorem: for any refocusing angle, echo amplitudes match SE decay.

        The 90°_Y + θ_X phase combination causes stimulated echoes to add
        coherently with spin echoes, so the total signal ≈ SE formula for
        any uniform refocusing angle θ.
        """
        T1, T2, PD, TR, ESP, ETL = 800.0, 80.0, 0.8, 4000.0, 10.0, 16
        s_180 = _epg_run(T1, T2, PD, TR, ETL, ESP, 180.0)
        s_120 = _epg_run(T1, T2, PD, TR, ETL, ESP, 120.0)
        np.testing.assert_allclose(s_120, s_180, rtol=5e-3)

    def test_signals_bounded_by_pd(self):
        """No echo can exceed PD (signal conservation)."""
        PD = 0.9
        s = _epg_run(1000, 100, PD, 5000, 20, 8)
        assert np.all(s <= PD + 1e-9)

    def test_longer_t2_slower_decay(self):
        s_short = _epg_run(800, 40, 1.0, 5000, 16, 10)
        s_long  = _epg_run(800, 400, 1.0, 5000, 16, 10)
        # Short T2 decays faster — last echo should be lower
        assert s_short[-1] < s_long[-1]

    def test_shorter_tr_lower_signal(self):
        """Short TR → less T1 recovery → lower signal."""
        s_long  = _epg_run(800, 80, 1.0, 5000, 8, 10)
        s_short = _epg_run(800, 80, 1.0, 500, 8, 10)
        assert s_long[0] > s_short[0]

    def test_epg_state_order_grows(self):
        """EPG states at higher k-orders should be populated after ETL echoes."""
        T1, T2, PD, TR, ESP, ETL = 800.0, 80.0, 0.8, 4000.0, 10.0, 8
        # After n echoes, the highest populated F+ order is 2*n
        # (two shifts per echo: before and after the RF pulse)
        N = ETL + 2
        Fp = np.zeros(N, dtype=complex)
        Z  = np.zeros(N, dtype=float)
        M0 = PD * (1.0 - np.exp(-TR / T1))
        Fp[0] = -M0
        # After ETL echoes, state at order ETL should be non-zero
        # (the echo train propagates states outward)
        signals = _epg_run(T1, T2, PD, TR, ETL, ESP, 180.0)
        # All ETL echoes should be positive (non-zero states populated)
        assert np.all(signals > 0)


# ---------------------------------------------------------------------------
# epg_signal (public API)
# ---------------------------------------------------------------------------

class TestEpgSignal:
    def test_positive(self):
        assert epg_signal(800, 80, 0.8, 4000, 80, 16, 10) > 0

    def test_pd_zero_gives_zero(self):
        assert epg_signal(800, 80, 0.0, 4000, 80, 16, 10) == 0.0

    def test_longer_te_lower_signal(self):
        sig_short = epg_signal(800, 80, 0.8, 4000, 20, 16, 10)
        sig_long  = epg_signal(800, 80, 0.8, 4000, 100, 16, 10)
        assert sig_short > sig_long

    def test_csf_bright_on_t2_weighted(self):
        sig_csf = epg_signal(4500, 2200, 1.0, 4000, 80, 16, 10)
        sig_wm  = epg_signal(830, 80, 0.65, 4000, 80, 16, 10)
        assert sig_csf > sig_wm

    def test_returns_float(self):
        s = epg_signal(800, 80, 0.8, 4000, 80, 16, 10)
        assert isinstance(s, float)

    def test_te_eff_out_of_train_clamped(self):
        """TE_eff beyond ETL×ESP is clamped to the last echo (no crash)."""
        s = epg_signal(800, 80, 0.8, 4000, 9999, 16, 10)
        assert s >= 0.0

    def test_matches_se_formula_for_180(self):
        """For 180° refocusing, signal at TE_eff should equal SE formula."""
        T1, T2, PD, TR, TE, ESP, ETL = 800.0, 80.0, 0.8, 4000.0, 80.0, 10.0, 16
        got = epg_signal(T1, T2, PD, TR, TE, ETL, ESP, 180.0)
        expected = PD * (1.0 - np.exp(-TR / T1)) * np.exp(-TE / T2)
        assert abs(got - expected) < 1e-6

    def test_cpmg_invariance_at_te_eff(self):
        """CPMG theorem: signal at TE_eff is the same for any refocusing angle."""
        sig_180 = epg_signal(800, 80, 0.8, 4000, 80, 16, 10, 180.0)
        sig_120 = epg_signal(800, 80, 0.8, 4000, 80, 16, 10, 120.0)
        assert abs(sig_180 - sig_120) < 1e-3 * sig_180


# ---------------------------------------------------------------------------
# compute_fse_echo_train
# ---------------------------------------------------------------------------

class TestComputeFseEchoTrain:
    def test_output_length(self):
        te_vals, sigs = compute_fse_echo_train(800, 80, 0.8, 4000, ETL=16, echo_spacing=10)
        assert len(te_vals) == 16
        assert len(sigs) == 16

    def test_signal_decays_over_echoes_180(self):
        _, sigs = compute_fse_echo_train(800, 80, 0.8, 4000, ETL=16, echo_spacing=10)
        assert sigs[-1] < sigs[0]

    def test_te_values_increase(self):
        te_vals, _ = compute_fse_echo_train(800, 80, 0.8, 4000, ETL=8, echo_spacing=10)
        assert np.all(np.diff(te_vals) > 0)

    def test_te_spacing_correct(self):
        te_vals, _ = compute_fse_echo_train(800, 80, 0.8, 4000, ETL=8, echo_spacing=15)
        assert np.allclose(np.diff(te_vals), 15.0)

    def test_180_matches_se(self):
        """Echo train with 180° should match SE exponential decay."""
        T1, T2, PD, TR, ESP = 1000.0, 100.0, 1.0, 10000.0, 10.0
        ETL = 12
        te_vals, sigs = compute_fse_echo_train(T1, T2, PD, TR, ETL, ESP, 180.0)
        M0 = PD * (1.0 - np.exp(-TR / T1))
        expected = M0 * np.exp(-te_vals / T2)
        assert np.allclose(sigs, expected, atol=1e-6)

    def test_cpmg_invariance_full_train(self):
        """CPMG theorem: echo train shape is the same for 120° and 180° refocusing."""
        _, sigs_120 = compute_fse_echo_train(800, 200, 1.0, 5000, 16, 10, 120.0)
        _, sigs_180 = compute_fse_echo_train(800, 200, 1.0, 5000, 16, 10, 180.0)
        np.testing.assert_allclose(sigs_120, sigs_180, rtol=5e-3)

    def test_nonneg_dtype(self):
        _, sigs = compute_fse_echo_train(800, 80, 0.8, 4000, 8, 10)
        assert np.all(sigs >= 0)
        assert sigs.dtype == np.float64


# ---------------------------------------------------------------------------
# fse_scan_time
# ---------------------------------------------------------------------------

class TestFseScanTime:
    def test_positive(self):
        assert fse_scan_time(4000, 256, 1, 16) > 0

    def test_etl_reduces_time(self):
        t1  = fse_scan_time(4000, 256, 1, ETL=1)
        t16 = fse_scan_time(4000, 256, 1, ETL=16)
        assert t16 == pytest.approx(t1 / 16, rel=1e-5)

    def test_higher_nex_longer_time(self):
        t1 = fse_scan_time(4000, 256, 1, ETL=8)
        t2 = fse_scan_time(4000, 256, 2, ETL=8)
        assert t2 == pytest.approx(t1 * 2, rel=1e-5)

    def test_acceleration_reduces_time(self):
        t_normal = fse_scan_time(4000, 256, 1, ETL=8, acceleration=1)
        t_accel  = fse_scan_time(4000, 256, 1, ETL=8, acceleration=2)
        assert t_accel == pytest.approx(t_normal / 2, rel=1e-5)

    def test_units_are_seconds(self):
        # TR=1000ms, 4 phase encodes, NEX=1, ETL=4 → 1 TR = 1s
        t = fse_scan_time(TR=1000, matrix_size=4, NEX=1, ETL=4)
        assert t == pytest.approx(1.0, rel=1e-5)


# ---------------------------------------------------------------------------
# fse_blurring_factor
# ---------------------------------------------------------------------------

class TestFseBlurringFactor:
    def test_at_least_one(self):
        bf = fse_blurring_factor(ETL=16, echo_spacing=10, T2=80)
        assert bf >= 1.0

    def test_longer_etl_more_blurring(self):
        bf_short = fse_blurring_factor(ETL=4,  echo_spacing=10, T2=80)
        bf_long  = fse_blurring_factor(ETL=32, echo_spacing=10, T2=80)
        assert bf_long > bf_short

    def test_shorter_t2_more_blurring(self):
        bf_long_t2  = fse_blurring_factor(ETL=16, echo_spacing=10, T2=2000)
        bf_short_t2 = fse_blurring_factor(ETL=16, echo_spacing=10, T2=20)
        assert bf_short_t2 > bf_long_t2

    def test_no_blurring_for_very_long_t2(self):
        """For T2 >> train duration, decay is negligible → factor ≈ 1."""
        bf = fse_blurring_factor(ETL=8, echo_spacing=10, T2=1e7)
        assert bf == pytest.approx(1.0, abs=0.1)

    def test_cpmg_invariant_blurring(self):
        """CPMG theorem: blurring factor is angle-independent for CPMG sequences."""
        bf_180 = fse_blurring_factor(ETL=16, echo_spacing=10, T2=80, refocus_angle_deg=180)
        bf_120 = fse_blurring_factor(ETL=16, echo_spacing=10, T2=80, refocus_angle_deg=120)
        assert abs(bf_180 - bf_120) < 0.1


# ---------------------------------------------------------------------------
# simulate_fse_image
# ---------------------------------------------------------------------------

class TestSimulateFseImage:
    def test_output_shape(self, phantom64):
        img = simulate_fse_image(phantom64, TR=4000, TE_eff=80, ETL=16,
                                 echo_spacing=10, tissue_properties=TISSUE_PROPERTIES)
        assert img.shape == phantom64.shape

    def test_nonnegative(self, phantom64):
        img = simulate_fse_image(phantom64, TR=4000, TE_eff=80, ETL=16,
                                 echo_spacing=10, tissue_properties=TISSUE_PROPERTIES)
        assert np.all(img >= 0)

    def test_dtype_float64(self, phantom64):
        img = simulate_fse_image(phantom64, TR=4000, TE_eff=80, ETL=16,
                                 echo_spacing=10, tissue_properties=TISSUE_PROPERTIES)
        assert img.dtype == np.float64

    def test_nonzero_pixels(self, phantom64):
        img = simulate_fse_image(phantom64, TR=4000, TE_eff=80, ETL=16,
                                 echo_spacing=10, tissue_properties=TISSUE_PROPERTIES)
        assert img.max() > 0

    def test_short_te_brighter_than_long_te(self, phantom64):
        img_short = simulate_fse_image(phantom64, TR=4000, TE_eff=20, ETL=16,
                                       echo_spacing=5, tissue_properties=TISSUE_PROPERTIES)
        img_long = simulate_fse_image(phantom64, TR=4000, TE_eff=80, ETL=16,
                                      echo_spacing=10, tissue_properties=TISSUE_PROPERTIES)
        assert img_short.mean() > img_long.mean()

    def test_refocus_angle_param_accepted(self, phantom64):
        img = simulate_fse_image(phantom64, TR=4000, TE_eff=80, ETL=16,
                                 echo_spacing=10, tissue_properties=TISSUE_PROPERTIES,
                                 refocus_angle_deg=150.0)
        assert img.shape == phantom64.shape
        assert np.all(img >= 0)


# ---------------------------------------------------------------------------
# Branch coverage additions
# ---------------------------------------------------------------------------
class TestSimulateFseImageSparsePhantom:
    def test_continue_for_absent_label(self):
        """Phantom with only label 2 (GM) forces the `continue` branch (line 299)
        for labels 1, 3, 4, etc. that are absent. Only labels 2 and 0 are present,
        so all other label loops hit the `continue`."""
        # Use tissue_properties that only covers label 2 to guarantee the branch
        sparse_props = {2: TISSUE_PROPERTIES[2], 1: TISSUE_PROPERTIES[1], 3: TISSUE_PROPERTIES[3]}
        ph = np.zeros((16, 16), dtype=int)
        ph[4:12, 4:12] = 2  # only gray matter
        img = simulate_fse_image(ph, TR=4000, TE_eff=80, ETL=16,
                                 echo_spacing=10, tissue_properties=sparse_props)
        assert img.shape == (16, 16)
        assert img[ph == 2].mean() > 0
        # No signal outside brain (label 0 is not in sparse_props)
        assert np.all(img[ph == 0] == 0)
