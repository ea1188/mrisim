"""Tests for src/mt.py — Magnetization Transfer two-pool model."""

import numpy as np
import pytest
from mt import (
    MT_PARAMS,
    gaussian_lineshape,
    lorentzian_lineshape,
    saturation_rate_bound,
    saturation_rate_free,
    mt_steady_state,
    mt_ratio,
    simulate_mt_weighted,
    simulate_no_mt,
    simulate_mtr_map,
    z_spectrum,
    simulate_z_spectrum_map,
)


# ---------------------------------------------------------------------------
# TestMtParams
# ---------------------------------------------------------------------------
class TestMtParams:
    def test_covers_all_22_labels(self):
        assert set(MT_PARAMS.keys()) == set(range(22))

    def test_required_keys(self):
        for lab, mp in MT_PARAMS.items():
            for k in ("f", "k_ab", "T2b_us", "T1b_ms"):
                assert k in mp, f"label {lab} missing key {k}"

    def test_f_in_unit_interval(self):
        for lab, mp in MT_PARAMS.items():
            assert 0. <= mp["f"] <= 1., f"label {lab}: f out of [0,1]"

    def test_k_ab_nonneg(self):
        for lab, mp in MT_PARAMS.items():
            assert mp["k_ab"] >= 0., f"label {lab}: k_ab < 0"

    def test_white_matter_higher_f_than_csf(self):
        assert MT_PARAMS[3]["f"] > MT_PARAMS[1]["f"]

    def test_white_matter_higher_f_than_gray_matter(self):
        assert MT_PARAMS[3]["f"] > MT_PARAMS[2]["f"]

    def test_background_zero_f(self):
        assert MT_PARAMS[0]["f"] == 0.
        assert MT_PARAMS[0]["k_ab"] == 0.


# ---------------------------------------------------------------------------
# TestGaussianLineshape
# ---------------------------------------------------------------------------
class TestGaussianLineshape:
    def test_peaks_at_zero_offset(self):
        g0 = gaussian_lineshape(0., T2b_us=10.)
        g1 = gaussian_lineshape(500., T2b_us=10.)
        assert g0 > g1

    def test_symmetric(self):
        g_pos = gaussian_lineshape(1000., T2b_us=10.)
        g_neg = gaussian_lineshape(-1000., T2b_us=10.)
        assert g_pos == pytest.approx(g_neg, rel=1e-10)

    def test_integrates_to_one_over_two_pi(self):
        # g is normalized in rad/s: ∫g_rad dΔω = 1
        # Expressed in Hz: ∫g(f) df = 1 / (2π) ≈ 0.159
        f = np.linspace(-1e7, 1e7, 200001)
        g = gaussian_lineshape(f, T2b_us=10.)
        integral = np.trapezoid(g, f)
        assert integral == pytest.approx(1.0 / (2.0 * np.pi), rel=0.01)

    def test_shorter_t2b_broader_lineshape(self):
        # Shorter T2b → broader (less peaked at 0)
        g_short = gaussian_lineshape(0., T2b_us=5.)
        g_long  = gaussian_lineshape(0., T2b_us=15.)
        assert g_short < g_long

    def test_nonneg(self):
        offsets = np.linspace(-5000., 5000., 100)
        assert gaussian_lineshape(offsets, T2b_us=10.).min() >= 0.

    def test_output_shape(self):
        offsets = np.zeros((3, 4))
        assert gaussian_lineshape(offsets, 10.).shape == (3, 4)


# ---------------------------------------------------------------------------
# TestLorentzianLineshape
# ---------------------------------------------------------------------------
class TestLorentzianLineshape:
    def test_peaks_at_zero(self):
        assert lorentzian_lineshape(0., 80.) > lorentzian_lineshape(500., 80.)

    def test_symmetric(self):
        assert lorentzian_lineshape(200., 80.) == pytest.approx(
            lorentzian_lineshape(-200., 80.))

    def test_integrates_to_one_over_two_pi(self):
        # Same rad/s normalization as Gaussian: ∫g(f) df = 1/(2π)
        f = np.linspace(-1e6, 1e6, 2000001)
        g = lorentzian_lineshape(f, T2a_ms=80.)
        assert np.trapezoid(g, f) == pytest.approx(1.0 / (2.0 * np.pi), rel=0.01)

    def test_nonneg(self):
        offsets = np.linspace(-2000., 2000., 100)
        assert lorentzian_lineshape(offsets, 80.).min() >= 0.


# ---------------------------------------------------------------------------
# TestSaturationRateBound
# ---------------------------------------------------------------------------
class TestSaturationRateBound:
    def test_zero_at_large_offset(self):
        Wb = saturation_rate_bound(3., 1e8, T2b_us=10.)
        assert float(Wb) < 1e-10

    def test_scales_with_b1_squared(self):
        Wb1 = saturation_rate_bound(1., 2000., 10.)
        Wb2 = saturation_rate_bound(2., 2000., 10.)
        assert float(Wb2) == pytest.approx(4. * float(Wb1), rel=1e-6)

    def test_larger_at_smaller_offset(self):
        Wb_close = saturation_rate_bound(3., 500., 10.)
        Wb_far   = saturation_rate_bound(3., 5000., 10.)
        assert float(Wb_close) > float(Wb_far)

    def test_nonneg(self):
        assert float(saturation_rate_bound(3., 2000., 10.)) >= 0.

    def test_output_shape(self):
        offsets = np.array([1000., 2000., 3000.])
        assert saturation_rate_bound(3., offsets, 10.).shape == (3,)


# ---------------------------------------------------------------------------
# TestMtSteadyState
# ---------------------------------------------------------------------------
class TestMtSteadyState:
    def test_no_saturation_returns_one(self):
        result = mt_steady_state(f=0.1, k_ab=30., T1a_ms=1000.,
                                  T1b_ms=1000., W_b=0.0)
        assert float(result) == pytest.approx(1.0, rel=1e-6)

    def test_zero_f_returns_one(self):
        result = mt_steady_state(f=0., k_ab=0., T1a_ms=1000.,
                                  T1b_ms=1000., W_b=100.)
        assert np.all(result == pytest.approx(1.0))

    def test_saturation_reduces_signal(self):
        result = mt_steady_state(f=0.15, k_ab=45., T1a_ms=1000.,
                                  T1b_ms=1000., W_b=50.)
        assert float(result) < 1.0

    def test_larger_wb_lower_signal(self):
        r_low  = mt_steady_state(0.1, 30., 1000., 1000., W_b=10.)
        r_high = mt_steady_state(0.1, 30., 1000., 1000., W_b=100.)
        assert float(r_high) < float(r_low)

    def test_larger_f_lower_signal(self):
        r_small = mt_steady_state(f=0.05, k_ab=20., T1a_ms=1000.,
                                   T1b_ms=1000., W_b=30.)
        r_large = mt_steady_state(f=0.15, k_ab=20., T1a_ms=1000.,
                                   T1b_ms=1000., W_b=30.)
        assert float(r_large) < float(r_small)

    def test_result_clipped_to_unit_interval(self):
        Wb = np.array([0., 10., 100., 1000.])
        r = mt_steady_state(0.1, 30., 1000., 1000., W_b=Wb)
        assert r.min() >= 0.
        assert r.max() <= 1.0

    def test_array_input(self):
        Wb = np.linspace(0., 100., 50)
        r = mt_steady_state(0.1, 30., 1000., 1000., W_b=Wb)
        assert r.shape == (50,)

    def test_direct_water_saturation_reduces_signal(self):
        r_no_wa  = mt_steady_state(0.1, 30., 1000., 1000., W_b=0., W_a=0.)
        r_with_wa = mt_steady_state(0.1, 30., 1000., 1000., W_b=0., W_a=10.)
        assert float(r_with_wa) < float(r_no_wa)


# ---------------------------------------------------------------------------
# TestMtRatio
# ---------------------------------------------------------------------------
class TestMtRatio:
    def test_zero_saturation_gives_zero_mtr(self):
        s = np.ones((5, 5))
        mtr = mt_ratio(s, s)
        np.testing.assert_allclose(mtr, 0.)

    def test_full_saturation_gives_100_percent(self):
        s0  = np.ones((5, 5))
        sat = np.zeros((5, 5))
        mtr = mt_ratio(sat, s0)
        np.testing.assert_allclose(mtr, 100.)

    def test_mtr_in_percent_range(self):
        s0  = np.ones((8, 8))
        sat = np.full((8, 8), 0.7)
        mtr = mt_ratio(sat, s0)
        assert mtr.min() >= 0.
        assert mtr.max() <= 100.

    def test_known_value(self):
        s0  = np.full((3, 3), 1.0)
        sat = np.full((3, 3), 0.6)
        mtr = mt_ratio(sat, s0)
        np.testing.assert_allclose(mtr, 40., rtol=1e-8)

    def test_zero_reference_gives_zero(self):
        mtr = mt_ratio(np.zeros((4, 4)), np.zeros((4, 4)))
        np.testing.assert_allclose(mtr, 0.)

    def test_output_shape(self):
        assert mt_ratio(np.ones((6, 7)), np.ones((6, 7))).shape == (6, 7)


# ---------------------------------------------------------------------------
# TestSimulateMtWeighted / TestSimulateNoMt
# ---------------------------------------------------------------------------
def _brain_map():
    lm = np.zeros((10, 15), dtype=np.uint8)
    lm[:, :5]  = 1   # CSF
    lm[:, 5:10] = 2  # gray matter
    lm[:, 10:]  = 3  # white matter
    return lm


class TestSimulateNoMt:
    def test_output_shape(self):
        lm = _brain_map()
        img = simulate_no_mt(lm)
        assert img.shape == lm.shape

    def test_background_zero(self):
        lm = np.zeros((5, 5), dtype=np.uint8)
        assert simulate_no_mt(lm).max() == pytest.approx(0.)

    def test_nonneg(self):
        assert simulate_no_mt(_brain_map()).min() >= 0.

    def test_dtype_float64(self):
        assert simulate_no_mt(_brain_map()).dtype == np.float64


class TestSimulateMtWeighted:
    def test_output_shape(self):
        assert simulate_mt_weighted(_brain_map()).shape == (10, 15)

    def test_mt_reduces_signal(self):
        lm = _brain_map()
        s_mt = simulate_mt_weighted(lm, B1_sat_uT=3., offset_hz=2000.)
        s_ref = simulate_no_mt(lm)
        assert s_mt.mean() <= s_ref.mean()

    def test_white_matter_more_reduced_than_csf(self):
        lm = _brain_map()
        s_mt  = simulate_mt_weighted(lm, B1_sat_uT=3., offset_hz=2000.)
        s_ref = simulate_no_mt(lm)
        wm_reduction = (s_ref[:, 10:] - s_mt[:, 10:]).mean()
        csf_reduction = (s_ref[:, :5]  - s_mt[:, :5]).mean()
        assert wm_reduction > csf_reduction

    def test_background_zero(self):
        lm = np.zeros((5, 5), dtype=np.uint8)
        assert simulate_mt_weighted(lm).max() == pytest.approx(0.)

    def test_nonneg(self):
        assert simulate_mt_weighted(_brain_map()).min() >= 0.

    def test_larger_b1_more_saturation(self):
        lm = _brain_map()
        s_low  = simulate_mt_weighted(lm, B1_sat_uT=1., offset_hz=2000.)
        s_high = simulate_mt_weighted(lm, B1_sat_uT=5., offset_hz=2000.)
        assert s_high.mean() <= s_low.mean()


# ---------------------------------------------------------------------------
# TestSimulateMtrMap
# ---------------------------------------------------------------------------
class TestSimulateMtrMap:
    def test_output_shape(self):
        assert simulate_mtr_map(_brain_map()).shape == (10, 15)

    def test_values_in_percent_range(self):
        mtr = simulate_mtr_map(_brain_map())
        assert mtr.min() >= 0.
        assert mtr.max() <= 100.

    def test_wm_mtr_greater_than_csf_mtr(self):
        lm = _brain_map()
        mtr = simulate_mtr_map(lm, B1_sat_uT=3., offset_hz=2000.)
        assert mtr[:, 10:].mean() > mtr[:, :5].mean()

    def test_wm_mtr_greater_than_gm_mtr(self):
        lm = _brain_map()
        mtr = simulate_mtr_map(lm, B1_sat_uT=3., offset_hz=2000.)
        assert mtr[:, 10:].mean() > mtr[:, 5:10].mean()

    def test_background_zero(self):
        lm = np.zeros((5, 5), dtype=np.uint8)
        mtr = simulate_mtr_map(lm)
        np.testing.assert_allclose(mtr, 0.)

    def test_dtype_float64(self):
        assert simulate_mtr_map(_brain_map()).dtype == np.float64


# ---------------------------------------------------------------------------
# TestZSpectrum
# ---------------------------------------------------------------------------
class TestZSpectrum:
    def test_output_shape(self):
        offsets = np.linspace(-5000., 5000., 50)
        z = z_spectrum(0.1, 30., 1000., 1000., 12., 80., offsets)
        assert z.shape == (50,)

    def test_values_in_unit_interval(self):
        offsets = np.linspace(-5000., 5000., 100)
        z = z_spectrum(0.1, 30., 1000., 1000., 12., 80., offsets)
        assert z.min() >= 0.
        assert z.max() <= 1.

    def test_symmetric_about_zero(self):
        offsets = np.linspace(100., 5000., 50)
        z_pos = z_spectrum(0.1, 30., 1000., 1000., 12., 80.,  offsets)
        z_neg = z_spectrum(0.1, 30., 1000., 1000., 12., 80., -offsets)
        np.testing.assert_allclose(z_pos, z_neg, rtol=1e-6)

    def test_dip_at_small_offset(self):
        # Near 0 Hz, direct water saturation causes deep dip
        z_near = z_spectrum(0.1, 30., 1000., 1000., 12., 80.,
                             np.array([10.]),  B1_sat_uT=1.)
        z_far  = z_spectrum(0.1, 30., 1000., 1000., 12., 80.,
                             np.array([50000.]), B1_sat_uT=1.)
        assert z_near[0] < z_far[0]

    def test_high_f_lower_z_at_mt_offset(self):
        # More bound pool → more MT → lower Mz at typical MT offset
        offsets = np.array([2000.])
        z_low  = z_spectrum(f=0.02, k_ab=10., T1a_ms=1000., T1b_ms=1000.,
                             T2b_us=12., T2a_ms=80., offset_hz_list=offsets)
        z_high = z_spectrum(f=0.16, k_ab=45., T1a_ms=1000., T1b_ms=1000.,
                             T2b_us=12., T2a_ms=80., offset_hz_list=offsets)
        assert z_high[0] < z_low[0]

    def test_zero_f_returns_ones(self):
        offsets = np.linspace(-5000., 5000., 20)
        z = z_spectrum(f=0., k_ab=0., T1a_ms=1000., T1b_ms=1000.,
                        T2b_us=12., T2a_ms=80., offset_hz_list=offsets,
                        B1_sat_uT=0.001)
        np.testing.assert_allclose(z, 1., atol=0.01)


# ---------------------------------------------------------------------------
# TestSimulateZSpectrumMap
# ---------------------------------------------------------------------------
class TestSimulateZSpectrumMap:
    def test_output_shape(self):
        lm = _brain_map()
        offsets = np.linspace(-5000., 5000., 20)
        stack = simulate_z_spectrum_map(lm, offsets)
        assert stack.shape == (20, 10, 15)

    def test_background_is_one(self):
        lm = np.zeros((5, 5), dtype=np.uint8)
        offsets = np.array([2000., -2000.])
        stack = simulate_z_spectrum_map(lm, offsets, B1_sat_uT=3.)
        # background f=0 → no MT → Mz=1
        np.testing.assert_allclose(stack, 1., atol=1e-6)

    def test_values_in_unit_interval(self):
        offsets = np.linspace(-5000., 5000., 30)
        stack = simulate_z_spectrum_map(_brain_map(), offsets, B1_sat_uT=2.)
        assert stack.min() >= 0.
        assert stack.max() <= 1.

    def test_wm_lower_than_csf_at_mt_offset(self):
        lm = _brain_map()
        offsets = np.array([2000.])
        stack = simulate_z_spectrum_map(lm, offsets, B1_sat_uT=3.)
        z_wm  = stack[0, :, 10:].mean()
        z_csf = stack[0, :, :5].mean()
        assert z_wm < z_csf


# ---------------------------------------------------------------------------
# Branch coverage additions
# ---------------------------------------------------------------------------
class TestSimulateMtWeightedSESequence:
    def test_se_sequence_runs(self):
        """sequence='SE' hits the spin_echo_signal branch (line 250)."""
        lm = _brain_map()
        out = simulate_mt_weighted(lm, B1_sat_uT=3., TR_ms=500., TE_ms=15.,
                                   sequence="SE")
        assert out.shape == lm.shape
        assert np.all(np.isfinite(out))

    def test_se_output_positive(self):
        lm = _brain_map()
        out = simulate_mt_weighted(lm, B1_sat_uT=3., sequence="SE")
        assert out[lm > 0].min() > 0.


class TestSimulateNoMtSESequence:
    def test_se_sequence_runs(self):
        """sequence='SE' in simulate_no_mt hits line 277."""
        lm = _brain_map()
        out = simulate_no_mt(lm, TR_ms=500., TE_ms=15., sequence="SE")
        assert out.shape == lm.shape
        assert np.all(np.isfinite(out))

    def test_se_gre_differ(self):
        lm = _brain_map()
        se  = simulate_no_mt(lm, TR_ms=500., TE_ms=15., sequence="SE")
        gre = simulate_no_mt(lm, TR_ms=500., TE_ms=15., sequence="GRE")
        # SE and GRE produce different contrast
        assert not np.allclose(se, gre)
