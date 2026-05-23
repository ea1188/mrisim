import numpy as np
import pytest
from fse import (
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


class TestEpgSignal:
    def test_positive(self):
        assert epg_signal(800, 80, 0.8, 4000, 80, 16, 10) > 0

    def test_pd_zero_gives_zero(self):
        assert epg_signal(800, 80, 0.0, 4000, 80, 16, 10) == 0.0

    def test_longer_te_lower_signal(self):
        sig_short = epg_signal(800, 80, 0.8, 4000, 20, 16, 10)
        sig_long = epg_signal(800, 80, 0.8, 4000, 100, 16, 10)
        assert sig_short > sig_long

    def test_csf_bright_on_t2_weighted(self):
        sig_csf = epg_signal(4500, 2200, 1.0, 4000, 80, 16, 10)
        sig_wm = epg_signal(830, 80, 0.65, 4000, 80, 16, 10)
        assert sig_csf > sig_wm


class TestFseScanTime:
    def test_positive(self):
        assert fse_scan_time(4000, 256, 1, 16) > 0

    def test_etl_reduces_time(self):
        t1 = fse_scan_time(4000, 256, 1, ETL=1)
        t16 = fse_scan_time(4000, 256, 1, ETL=16)
        assert t16 == pytest.approx(t1 / 16, rel=1e-5)

    def test_higher_nex_longer_time(self):
        t1 = fse_scan_time(4000, 256, 1, ETL=8)
        t2 = fse_scan_time(4000, 256, 2, ETL=8)
        assert t2 == pytest.approx(t1 * 2, rel=1e-5)

    def test_acceleration_reduces_time(self):
        t_normal = fse_scan_time(4000, 256, 1, ETL=8, acceleration=1)
        t_accel = fse_scan_time(4000, 256, 1, ETL=8, acceleration=2)
        assert t_accel == pytest.approx(t_normal / 2, rel=1e-5)


class TestFseBlurringFactor:
    def test_at_least_one(self):
        bf = fse_blurring_factor(ETL=16, echo_spacing=10, T2=80)
        assert bf >= 1.0

    def test_longer_etl_more_blurring(self):
        bf_short = fse_blurring_factor(ETL=4, echo_spacing=10, T2=80)
        bf_long = fse_blurring_factor(ETL=32, echo_spacing=10, T2=80)
        assert bf_long > bf_short

    def test_shorter_t2_more_blurring(self):
        bf_long_t2 = fse_blurring_factor(ETL=16, echo_spacing=10, T2=2000)
        bf_short_t2 = fse_blurring_factor(ETL=16, echo_spacing=10, T2=20)
        assert bf_short_t2 > bf_long_t2


class TestSimulateFseImage:
    def test_output_shape(self, phantom64):
        img = simulate_fse_image(phantom64, TR=4000, TE_eff=80, ETL=16,
                                 echo_spacing=10, tissue_properties=TISSUE_PROPERTIES)
        assert img.shape == phantom64.shape

    def test_nonnegative(self, phantom64):
        img = simulate_fse_image(phantom64, TR=4000, TE_eff=80, ETL=16,
                                 echo_spacing=10, tissue_properties=TISSUE_PROPERTIES)
        assert np.all(img >= 0)


class TestComputeFseEchoTrain:
    def test_output_length(self):
        te_vals, sigs = compute_fse_echo_train(800, 80, 0.8, 4000, ETL=16, echo_spacing=10)
        assert len(te_vals) == 16
        assert len(sigs) == 16

    def test_signal_decays_over_echoes(self):
        _, sigs = compute_fse_echo_train(800, 80, 0.8, 4000, ETL=16, echo_spacing=10)
        assert sigs[-1] < sigs[0]

    def test_te_values_increase(self):
        te_vals, _ = compute_fse_echo_train(800, 80, 0.8, 4000, ETL=8, echo_spacing=10)
        assert np.all(np.diff(te_vals) > 0)
