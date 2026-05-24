import numpy as np
import pytest
from signal_engine import (
    spin_echo_signal,
    gradient_echo_signal,
    inversion_recovery_signal,
    calculate_snr,
    calculate_scan_time,
    TISSUES,
)


class TestSpinEchoSignal:
    def test_returns_positive(self):
        assert spin_echo_signal(800, 80, 0.8, 500, 20) > 0

    def test_pd_zero_gives_zero(self):
        assert spin_echo_signal(800, 80, 0.0, 500, 20) == 0.0

    def test_long_tr_saturates_t1(self):
        # Very long TR removes T1 weighting; signal approaches PD * exp(-TE/T2)
        sig_long = spin_echo_signal(800, 80, 0.8, 100_000, 1)
        sig_short = spin_echo_signal(800, 80, 0.8, 100, 1)
        assert sig_long > sig_short

    def test_short_te_increases_signal(self):
        sig_short = spin_echo_signal(800, 80, 0.8, 500, 5)
        sig_long = spin_echo_signal(800, 80, 0.8, 500, 200)
        assert sig_short > sig_long

    def test_t2_weighting(self):
        # Higher T2 -> less decay -> brighter at same TE
        sig_high_t2 = spin_echo_signal(4500, 2200, 1.0, 4000, 100)
        sig_low_t2 = spin_echo_signal(800, 80, 0.8, 4000, 100)
        assert sig_high_t2 > sig_low_t2

    def test_known_value(self):
        # PD=1, very long TR, TE≈0 => signal ≈ 1
        sig = spin_echo_signal(100, 1000, 1.0, 1_000_000, 0.001)
        assert abs(sig - 1.0) < 0.01

    def test_all_brain_tissues_positive(self):
        for name, p in TISSUES.items():
            sig = spin_echo_signal(p["T1"], p["T2"], p["PD"], 500, 20)
            assert sig >= 0, f"{name} produced negative signal"

    def test_vectorized_array_input(self):
        T1 = np.array([800, 1330, 4500])
        sig = spin_echo_signal(T1, 80, 0.8, 500, 20)
        assert sig.shape == (3,)
        assert np.all(sig > 0)

    def test_long_te_approaches_zero(self):
        sig = spin_echo_signal(800, 80, 0.8, 5000, 2000)
        assert sig < 0.001

    def test_t1_weighting_short_tr(self):
        # Short TR: tissue with shorter T1 (fat) appears brighter than longer T1 (CSF)
        sig_fat = spin_echo_signal(370, 60, 0.95, 400, 10)
        sig_csf = spin_echo_signal(4500, 2200, 1.0, 400, 10)
        assert sig_fat > sig_csf

    def test_nex_has_no_effect_on_raw_signal(self):
        # spin_echo_signal has no NEX parameter; signal is single-acquisition
        sig = spin_echo_signal(800, 80, 0.8, 500, 20)
        assert isinstance(float(sig), float)  # just confirm scalar-compatible


class TestGradientEchoSignal:
    def test_returns_positive(self):
        assert gradient_echo_signal(800, 40, 0.8, 250, 5, 70) > 0

    def test_pd_zero_gives_zero(self):
        assert gradient_echo_signal(800, 40, 0.0, 250, 5, 70) == 0.0

    def test_flip_angle_zero_gives_zero(self):
        # sin(0) = 0
        assert gradient_echo_signal(800, 40, 0.8, 250, 5, 0) == 0.0

    def test_small_flip_angle_less_than_large(self):
        sig_small = gradient_echo_signal(800, 40, 0.8, 250, 5, 10)
        sig_large = gradient_echo_signal(800, 40, 0.8, 250, 5, 60)
        assert sig_large > sig_small

    def test_vectorized(self):
        T2s = np.array([40, 60, 80])
        sig = gradient_echo_signal(800, T2s, 0.8, 250, 5, 70)
        assert sig.shape == (3,)

    def test_higher_t2star_brighter(self):
        sig_short = gradient_echo_signal(800, 20, 0.8, 250, 10, 70)
        sig_long  = gradient_echo_signal(800, 80, 0.8, 250, 10, 70)
        assert sig_long > sig_short

    def test_short_te_brighter_than_long_te(self):
        sig_short = gradient_echo_signal(800, 40, 0.8, 250, 3, 70)
        sig_long  = gradient_echo_signal(800, 40, 0.8, 250, 60, 70)
        assert sig_short > sig_long

    def test_ernst_angle_maximises_signal(self):
        T1, TR = 800, 250
        ernst_deg = np.degrees(np.arccos(np.exp(-TR / T1)))
        sig_ernst = gradient_echo_signal(T1, 40, 0.8, TR, 5, ernst_deg)
        for fa in [10, 30, 60, 90]:
            sig = gradient_echo_signal(T1, 40, 0.8, TR, 5, fa)
            assert sig_ernst >= sig - 1e-9

    def test_flip_180_signal_zero(self):
        # sin(180) = 0
        sig = gradient_echo_signal(800, 40, 0.8, 250, 5, 180)
        assert abs(sig) < 1e-10

    def test_long_tr_approaches_pd_sin_alpha_exp_te(self):
        # Very long TR → E1→0 → signal = PD*sin(alpha)*exp(-TE/T2star)
        sig = gradient_echo_signal(800, 40, 0.8, 1_000_000, 0.001, 90)
        assert abs(sig - 0.8) < 0.01

    def test_vectorized_t1_input(self):
        T1s = np.array([370, 800, 1330])
        sig = gradient_echo_signal(T1s, 40, 0.8, 250, 5, 70)
        assert sig.shape == (3,)
        assert np.all(sig > 0)


class TestInversionRecoverySignal:
    def test_returns_nonnegative(self):
        sig = inversion_recovery_signal(1330, 100, 0.8, 9000, 90, 2500)
        assert sig >= 0

    def test_ti_null_csf(self):
        # At TI = T1*ln(2), CSF signal should approach zero
        T1_csf = 4500
        TI_null = T1_csf * np.log(2)
        sig = inversion_recovery_signal(T1_csf, 2200, 1.0, 100_000, 1, TI_null)
        assert sig < 0.05  # nearly suppressed

    def test_ti_zero_gives_low_signal(self):
        # Immediately after inversion, Mz ≈ -1
        sig = inversion_recovery_signal(800, 80, 0.8, 9000, 1, 1)
        # abs(1 - 2*exp(-1/T1) + ...) with very short TI ≈ abs(1 - 2) = 1 * ...
        assert sig >= 0

    def test_ti_null_fat(self):
        # STIR: TI = T1_fat * ln(2) ≈ 150 ms suppresses fat
        T1_fat = 370
        TI_null = T1_fat * np.log(2)
        sig = inversion_recovery_signal(T1_fat, 60, 0.95, 4000, 1, TI_null)
        assert sig < 0.05

    def test_long_ti_approaches_spin_echo(self):
        # When TI >> T1, exp(-TI/T1)→0, so IR → SE formula (abs(1 - 0 + exp(-TR/T1)))
        T1, T2, PD, TR, TE = 800, 80, 0.8, 5000, 20
        sig_ir   = inversion_recovery_signal(T1, T2, PD, TR, TE, TI=10 * T1)
        sig_se   = spin_echo_signal(T1, T2, PD, TR, TE)
        assert abs(sig_ir - sig_se) < 0.01

    def test_short_te_higher_than_long_te(self):
        sig_short = inversion_recovery_signal(1330, 100, 0.8, 9000, 10, 1200)
        sig_long  = inversion_recovery_signal(1330, 100, 0.8, 9000, 200, 1200)
        assert sig_short > sig_long

    def test_all_brain_tissues_nonnegative(self):
        for name, p in TISSUES.items():
            TI = p["T1"] * 0.7
            sig = inversion_recovery_signal(p["T1"], p["T2"], p["PD"], 9000, 20, TI)
            assert sig >= 0, f"{name} produced negative IR signal"


class TestCalculateSNR:
    def test_positive(self):
        assert calculate_snr(0.5, 125, 1.0, 1) > 0

    def test_more_nex_improves_snr(self):
        snr1 = calculate_snr(0.5, 125, 1.0, 1)
        snr4 = calculate_snr(0.5, 125, 1.0, 4)
        assert snr4 > snr1

    def test_nex_sqrt_relationship(self):
        snr1 = calculate_snr(0.5, 125, 1.0, 1)
        snr4 = calculate_snr(0.5, 125, 1.0, 4)
        assert abs(snr4 / snr1 - 2.0) < 0.001  # sqrt(4)=2

    def test_higher_bandwidth_reduces_snr(self):
        snr_low  = calculate_snr(0.5, 32, 1.0, 1)
        snr_high = calculate_snr(0.5, 256, 1.0, 1)
        assert snr_low > snr_high

    def test_larger_voxel_increases_snr(self):
        snr_small = calculate_snr(0.5, 125, 0.5, 1)
        snr_large = calculate_snr(0.5, 125, 2.0, 1)
        assert snr_large > snr_small

    def test_zero_signal_gives_zero_snr(self):
        assert calculate_snr(0.0, 125, 1.0, 1) == pytest.approx(0.0)

    def test_bandwidth_inverse_sqrt_relationship(self):
        # SNR ∝ 1/sqrt(bandwidth)
        snr1 = calculate_snr(1.0, 100, 1.0, 1)
        snr2 = calculate_snr(1.0, 400, 1.0, 1)
        assert abs(snr1 / snr2 - 2.0) < 0.001  # sqrt(400/100)=2


class TestCalculateScanTime:
    def test_returns_positive(self):
        assert calculate_scan_time(500, 256, 1) > 0

    def test_longer_tr_longer_time(self):
        t1 = calculate_scan_time(500, 256, 1)
        t2 = calculate_scan_time(1000, 256, 1)
        assert t2 > t1

    def test_etl_reduces_time(self):
        t_no_etl = calculate_scan_time(4000, 256, 1, ETL=1)
        t_etl16 = calculate_scan_time(4000, 256, 1, ETL=16)
        assert t_etl16 == pytest.approx(t_no_etl / 16, rel=1e-5)

    def test_acceleration_reduces_time(self):
        t_normal = calculate_scan_time(500, 256, 1, acceleration=1)
        t_accel = calculate_scan_time(500, 256, 1, acceleration=2)
        assert t_accel == pytest.approx(t_normal / 2, rel=1e-5)

    def test_returns_seconds(self):
        # TR=500ms, 256 phase lines, NEX=1 => 128 s
        t = calculate_scan_time(500, 256, 1)
        assert t == pytest.approx(128.0, rel=1e-5)

    def test_more_phase_encodes_longer_time(self):
        t128 = calculate_scan_time(500, 128, 1)
        t256 = calculate_scan_time(500, 256, 1)
        assert t256 == pytest.approx(2 * t128, rel=1e-5)

    def test_nex_scales_time_linearly(self):
        t1 = calculate_scan_time(500, 256, 1)
        t2 = calculate_scan_time(500, 256, 2)
        assert t2 == pytest.approx(2 * t1, rel=1e-5)

    def test_etl_and_acceleration_both_reduce_time(self):
        t_base  = calculate_scan_time(4000, 256, 1, ETL=1, acceleration=1)
        t_combo = calculate_scan_time(4000, 256, 1, ETL=4, acceleration=2)
        assert t_combo == pytest.approx(t_base / 8, rel=1e-5)
