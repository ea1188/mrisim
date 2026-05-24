"""Tests for src/dixon.py — Dixon fat-water separation and STIR."""

import numpy as np
import pytest
from dixon import (
    FAT_CS_PPM,
    FAT_LABELS,
    fat_water_shift_hz,
    inphase_te_ms,
    opposed_phase_te_ms,
    combined_gre_signal,
    simulate_inphase,
    simulate_opposed,
    two_point_dixon,
    three_point_dixon,
    fat_fraction,
    stir_ti_optimal,
    simulate_stir,
    chemical_shift_pixels,
)
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from phantom3d import TISSUE_PROPERTIES_3D


# ---------------------------------------------------------------------------
# TestFatWaterShiftHz
# ---------------------------------------------------------------------------
class TestFatWaterShiftHz:
    def test_1p5t_approx_224hz(self):
        df = fat_water_shift_hz(1.5)
        assert df == pytest.approx(220., abs=10.)   # ~224 Hz at 1.5T

    def test_3t_is_double_1p5t(self):
        assert fat_water_shift_hz(3.0) == pytest.approx(
            2.0 * fat_water_shift_hz(1.5), rel=1e-10)

    def test_scales_linearly_with_b0(self):
        assert fat_water_shift_hz(4.5) == pytest.approx(
            3.0 * fat_water_shift_hz(1.5), rel=1e-10)

    def test_positive(self):
        assert fat_water_shift_hz(1.5) > 0.


# ---------------------------------------------------------------------------
# TestInphaseTe
# ---------------------------------------------------------------------------
class TestInphaseTe:
    def test_1p5t_first_ip(self):
        # TE_ip = 1/224Hz ≈ 4.46 ms
        te = inphase_te_ms(1.5, n=1)
        assert te == pytest.approx(1000. / fat_water_shift_hz(1.5), rel=1e-6)

    def test_second_echo_double_first(self):
        assert inphase_te_ms(1.5, n=2) == pytest.approx(
            2. * inphase_te_ms(1.5, n=1), rel=1e-10)

    def test_3t_half_of_1p5t(self):
        assert inphase_te_ms(3.0) == pytest.approx(
            inphase_te_ms(1.5) / 2., rel=1e-6)

    def test_fat_phase_is_2pi_at_ip_te(self):
        te = inphase_te_ms(1.5, n=1)
        df = fat_water_shift_hz(1.5)
        phase = 2. * np.pi * df * te * 1e-3
        assert phase == pytest.approx(2. * np.pi, rel=1e-5)


# ---------------------------------------------------------------------------
# TestOpposedPhaseTe
# ---------------------------------------------------------------------------
class TestOpposedPhaseTe:
    def test_1p5t_first_opp(self):
        te = opposed_phase_te_ms(1.5, n=1)
        assert te == pytest.approx(500. / fat_water_shift_hz(1.5), rel=1e-6)

    def test_half_of_inphase(self):
        assert opposed_phase_te_ms(1.5, n=1) == pytest.approx(
            inphase_te_ms(1.5, n=1) / 2., rel=1e-6)

    def test_fat_phase_is_pi_at_opp_te(self):
        te = opposed_phase_te_ms(1.5, n=1)
        df = fat_water_shift_hz(1.5)
        phase = 2. * np.pi * df * te * 1e-3
        assert phase == pytest.approx(np.pi, rel=1e-5)

    def test_second_echo(self):
        te1 = opposed_phase_te_ms(1.5, n=1)
        te2 = opposed_phase_te_ms(1.5, n=2)
        assert te2 == pytest.approx(3. * te1, rel=1e-6)


# ---------------------------------------------------------------------------
# TestCombinedGreSignal
# ---------------------------------------------------------------------------
class TestCombinedGreSignal:
    def test_at_inphase_te_signals_add(self):
        W, F = 0.6, 0.4
        te = inphase_te_ms(1.5, n=1)
        s = combined_gre_signal(W, F, 1.5, te)
        assert abs(s) == pytest.approx(W + F, rel=1e-5)

    def test_at_opposed_te_signals_subtract(self):
        W, F = 0.6, 0.4
        te = opposed_phase_te_ms(1.5, n=1)
        s = combined_gre_signal(W, F, 1.5, te)
        assert abs(s) == pytest.approx(W - F, rel=1e-5)

    def test_water_only_magnitude_unchanged(self):
        # No fat → magnitude equals water signal regardless of TE
        te = opposed_phase_te_ms(1.5)
        s = combined_gre_signal(0.7, 0.0, 1.5, te)
        assert abs(s) == pytest.approx(0.7, rel=1e-8)

    def test_fat_only_magnitude_unchanged(self):
        te = inphase_te_ms(1.5)
        s = combined_gre_signal(0.0, 0.5, 1.5, te)
        assert abs(s) == pytest.approx(0.5, rel=1e-8)

    def test_output_is_complex(self):
        s = combined_gre_signal(0.5, 0.3, 1.5, 3.0)
        assert np.iscomplexobj(np.array(s))

    def test_output_shape(self):
        W = np.ones((5, 6))
        F = np.ones((5, 6)) * 0.3
        s = combined_gre_signal(W, F, 1.5, 3.0)
        assert s.shape == (5, 6)


# ---------------------------------------------------------------------------
# TestSimulateInphase / TestSimulateOpposed
# ---------------------------------------------------------------------------

def _fat_water_map():
    """4×8 label map: left half water (GM=2), right half fat (4)."""
    lm = np.zeros((4, 8), dtype=np.uint8)
    lm[:, :4] = 2    # gray matter (water-like)
    lm[:, 4:] = 4    # fat
    return lm


class TestSimulateInphase:
    def test_output_shape(self):
        lm = _fat_water_map()
        img = simulate_inphase(lm)
        assert img.shape == lm.shape

    def test_nonneg(self):
        img = simulate_inphase(_fat_water_map())
        assert img.min() >= 0.

    def test_output_dtype_float64(self):
        img = simulate_inphase(_fat_water_map())
        assert img.dtype == np.float64

    def test_background_zero(self):
        lm = np.zeros((5, 5), dtype=np.uint8)
        img = simulate_inphase(lm)
        assert img.max() == pytest.approx(0.)

    def test_water_and_fat_regions_nonzero(self):
        lm = _fat_water_map()
        img = simulate_inphase(lm)
        assert img[:, :4].mean() > 0.   # water region
        assert img[:, 4:].mean() > 0.   # fat region


class TestSimulateOpposed:
    def test_output_shape(self):
        assert simulate_opposed(_fat_water_map()).shape == (4, 8)

    def test_nonneg(self):
        assert simulate_opposed(_fat_water_map()).min() >= 0.

    def test_background_zero(self):
        lm = np.zeros((5, 5), dtype=np.uint8)
        assert simulate_opposed(lm).max() == pytest.approx(0.)

    def test_pure_water_ip_op_ratio_matches_t2star(self):
        # No fat → ip/op ratio == T2* decay between the two TEs
        lm = np.full((4, 4), 2, dtype=np.uint8)   # gray matter, T2*=60ms
        B0 = 1.5
        ip = simulate_inphase(lm,  field_strength_T=B0)
        op = simulate_opposed(lm, field_strength_T=B0)
        T2s = TISSUE_PROPERTIES_3D[2]["T2star"]  # 60 ms
        expected_ratio = np.exp(-(inphase_te_ms(B0) - opposed_phase_te_ms(B0)) / T2s)
        np.testing.assert_allclose(ip.mean() / op.mean(), expected_ratio, rtol=0.01)

    def test_pure_fat_ip_op_ratio_matches_t2star(self):
        # No water → same T2*-driven ratio for fat pixels
        lm = np.full((4, 4), 4, dtype=np.uint8)   # fat, T2*=40ms
        B0 = 1.5
        ip = simulate_inphase(lm,  field_strength_T=B0)
        op = simulate_opposed(lm, field_strength_T=B0)
        T2s = TISSUE_PROPERTIES_3D[4]["T2star"]  # 40 ms
        expected_ratio = np.exp(-(inphase_te_ms(B0) - opposed_phase_te_ms(B0)) / T2s)
        np.testing.assert_allclose(ip.mean() / op.mean(), expected_ratio, rtol=0.01)


# ---------------------------------------------------------------------------
# TestTwoPointDixon
# ---------------------------------------------------------------------------
class TestTwoPointDixon:
    def test_exact_recovery_known_values(self):
        W, F = 0.7, 0.3
        ip = np.full((4, 4), W + F)
        op = np.full((4, 4), W - F)
        water, fat = two_point_dixon(ip, op)
        np.testing.assert_allclose(water, W, rtol=1e-8)
        np.testing.assert_allclose(fat,   F, rtol=1e-8)

    def test_pure_water_gives_zero_fat(self):
        S = np.full((5, 5), 0.8)
        water, fat = two_point_dixon(S, S)   # ip == op → F = 0
        np.testing.assert_allclose(fat, 0., atol=1e-10)
        np.testing.assert_allclose(water, 0.8, rtol=1e-8)

    def test_fat_nonneg(self):
        ip = np.ones((5, 5))
        op = np.ones((5, 5)) * 1.1   # noisy: op > ip → fat would be negative
        _, fat = two_point_dixon(ip, op)
        assert fat.min() >= 0.

    def test_output_shapes(self):
        ip = np.ones((6, 7))
        op = np.ones((6, 7)) * 0.5
        water, fat = two_point_dixon(ip, op)
        assert water.shape == (6, 7)
        assert fat.shape   == (6, 7)

    def test_conservation_water_plus_fat_equals_half_inphase(self):
        # water + fat = (ip+op)/2 + (ip-op)/2 = ip
        ip = np.random.default_rng(0).uniform(0.3, 1., (8, 8))
        op = ip * 0.6
        water, fat = two_point_dixon(ip, op)
        np.testing.assert_allclose(water + fat, ip, rtol=1e-8)

    def test_roundtrip_from_combined_signal(self):
        # Build mixed voxels using combined_gre_signal then recover W, F
        W_true = np.full((5, 5), 0.6)
        F_true = np.full((5, 5), 0.3)
        B0 = 1.5
        ip_cmplx = combined_gre_signal(W_true, F_true, B0, inphase_te_ms(B0))
        op_cmplx = combined_gre_signal(W_true, F_true, B0, opposed_phase_te_ms(B0))
        water, fat = two_point_dixon(np.abs(ip_cmplx), np.abs(op_cmplx))
        np.testing.assert_allclose(water, W_true, rtol=1e-5)
        np.testing.assert_allclose(fat,   F_true, rtol=1e-5)


# ---------------------------------------------------------------------------
# TestThreePointDixon
# ---------------------------------------------------------------------------
class TestThreePointDixon:
    def _make_echoes(self, W, F, B0_hz_extra=0.):
        """Three echoes at ip1, op, ip2 with optional extra B0 phase."""
        B0 = 1.5
        te1 = inphase_te_ms(B0, n=1)
        te_op = opposed_phase_te_ms(B0, n=1)
        te2 = inphase_te_ms(B0, n=2)
        def s(te):
            cs = combined_gre_signal(W, F, B0, te)
            return cs * np.exp(1j * 2 * np.pi * B0_hz_extra * te * 1e-3)
        return s(te1), s(te_op), s(te2)

    def test_exact_recovery_no_b0(self):
        W, F = 0.7, 0.3
        shape = (4, 4)
        s1, sm, s2 = self._make_echoes(
            np.full(shape, W), np.full(shape, F))
        water, fat = three_point_dixon(s1, sm, s2)
        np.testing.assert_allclose(water, W, atol=0.02)
        np.testing.assert_allclose(fat,   F, atol=0.02)

    def test_output_nonneg(self):
        shape = (5, 5)
        s1, sm, s2 = self._make_echoes(
            np.full(shape, 0.6), np.full(shape, 0.3))
        water, fat = three_point_dixon(s1, sm, s2)
        assert water.min() >= 0.
        assert fat.min()   >= 0.

    def test_output_shapes(self):
        shape = (6, 7)
        s1, sm, s2 = self._make_echoes(
            np.full(shape, 0.5), np.full(shape, 0.2))
        water, fat = three_point_dixon(s1, sm, s2)
        assert water.shape == shape
        assert fat.shape   == shape

    def test_water_dominant_signal(self):
        # W >> F → most signal ends up in water channel
        shape = (4, 4)
        s1, sm, s2 = self._make_echoes(
            np.full(shape, 0.8), np.full(shape, 0.05))
        water, fat = three_point_dixon(s1, sm, s2)
        assert water.mean() > fat.mean()


# ---------------------------------------------------------------------------
# TestFatFraction
# ---------------------------------------------------------------------------
class TestFatFraction:
    def test_pure_fat_gives_one(self):
        ff = fat_fraction(np.ones((5, 5)), np.zeros((5, 5)))
        np.testing.assert_allclose(ff, 1.0)

    def test_pure_water_gives_zero(self):
        ff = fat_fraction(np.zeros((5, 5)), np.ones((5, 5)))
        np.testing.assert_allclose(ff, 0.0)

    def test_equal_gives_half(self):
        ff = fat_fraction(np.ones((5, 5)), np.ones((5, 5)))
        np.testing.assert_allclose(ff, 0.5)

    def test_values_in_unit_interval(self):
        fat = np.abs(np.random.default_rng(0).standard_normal((10, 10)))
        wat = np.abs(np.random.default_rng(1).standard_normal((10, 10)))
        ff = fat_fraction(fat, wat)
        assert ff.min() >= 0. and ff.max() <= 1.0

    def test_zero_denominator_gives_zero(self):
        ff = fat_fraction(np.zeros((4, 4)), np.zeros((4, 4)))
        np.testing.assert_allclose(ff, 0.0)

    def test_known_fraction(self):
        F, W = 0.3, 0.7
        ff = fat_fraction(np.full((3, 3), F), np.full((3, 3), W))
        np.testing.assert_allclose(ff, F / (F + W), rtol=1e-8)


# ---------------------------------------------------------------------------
# TestStirTiOptimal
# ---------------------------------------------------------------------------
class TestStirTiOptimal:
    def test_fat_t1_370(self):
        ti = stir_ti_optimal(370.)
        assert ti == pytest.approx(370. * np.log(2.), rel=1e-8)

    def test_proportional_to_t1(self):
        assert stir_ti_optimal(1000.) == pytest.approx(
            1000. * np.log(2.), rel=1e-8)

    def test_1p5t_fat_approx_256ms(self):
        # T1 fat ≈ 370ms at 1.5T → TI ≈ 256ms
        ti = stir_ti_optimal(370.)
        assert 240. < ti < 280.


# ---------------------------------------------------------------------------
# TestSimulateStir
# ---------------------------------------------------------------------------
class TestSimulateStir:
    def test_output_shape(self):
        lm = np.zeros((10, 10), dtype=np.uint8)
        lm[2:8, 2:8] = 2
        assert simulate_stir(lm).shape == (10, 10)

    def test_background_zero(self):
        lm = np.zeros((8, 8), dtype=np.uint8)
        img = simulate_stir(lm)
        assert img.max() == pytest.approx(0.)

    def test_fat_signal_nulled_at_optimal_ti(self):
        # At TI = T1_fat * ln2, fat signal should be ≈ 0
        T1_fat = TISSUE_PROPERTIES_3D[4]["T1"]
        TI = stir_ti_optimal(T1_fat)
        lm = np.full((4, 4), 4, dtype=np.uint8)
        img = simulate_stir(lm, TR_ms=10000., TE_ms=1., TI_ms=TI)
        assert img.max() < 0.02   # nearly nulled

    def test_fat_signal_lower_than_water_at_optimal_ti(self):
        lm = _fat_water_map()
        img = simulate_stir(lm, TR_ms=5000., TE_ms=10.)
        fat_mean   = img[:, 4:].mean()   # fat region
        water_mean = img[:, :4].mean()   # water/GM region
        assert fat_mean < water_mean

    def test_nonneg(self):
        lm = _fat_water_map()
        assert simulate_stir(lm).min() >= 0.

    def test_output_dtype_float64(self):
        lm = np.full((4, 4), 2, dtype=np.uint8)
        assert simulate_stir(lm).dtype == np.float64


# ---------------------------------------------------------------------------
# TestChemicalShiftPixels
# ---------------------------------------------------------------------------
class TestChemicalShiftPixels:
    def test_1p5t_400hz_bw(self):
        shift = chemical_shift_pixels(1.5, 400.)
        assert shift == pytest.approx(fat_water_shift_hz(1.5) / 400., rel=1e-6)

    def test_3t_double_1p5t(self):
        s15 = chemical_shift_pixels(1.5, 200.)
        s30 = chemical_shift_pixels(3.0, 200.)
        assert s30 == pytest.approx(2. * s15, rel=1e-8)

    def test_higher_bw_smaller_shift(self):
        s_narrow = chemical_shift_pixels(1.5, 100.)
        s_wide   = chemical_shift_pixels(1.5, 500.)
        assert s_wide < s_narrow

    def test_positive(self):
        assert chemical_shift_pixels(1.5, 200.) > 0.

    def test_typical_value_at_1p5t(self):
        # BW=200 Hz/pixel at 1.5T → ~224/200 ≈ 1.1 pixels
        shift = chemical_shift_pixels(1.5, 200.)
        assert 0.8 < shift < 2.0
