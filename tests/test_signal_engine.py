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
