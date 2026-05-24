"""Tests for src/qmri.py — quantitative MRI parameter mapping."""

import numpy as np
import pytest
from qmri import (
    simulate_vfa_series,
    simulate_ir_series,
    simulate_multi_echo_series,
    vfa_t1_map,
    multi_echo_t2_map,
    t2star_map,
    ir_t1_map,
    synthetic_contrast,
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _uniform_map(label, shape=(8, 8)):
    """Label map with one tissue everywhere (no background)."""
    return np.full(shape, label, dtype=np.uint8)


def _gre_signal(T1, T2star, PD, TR, TE, alpha_deg):
    alpha = np.radians(alpha_deg)
    E1 = np.exp(-TR / T1)
    return PD * np.sin(alpha) * (1 - E1) / (1 - np.cos(alpha) * E1) * np.exp(-TE / T2star)


def _se_signal(T1, T2, PD, TR, TE):
    return PD * (1 - np.exp(-TR / T1)) * np.exp(-TE / T2)


def _make_vfa_series(T1, T2star, PD, flip_angles, TR, TE, shape=(5, 5)):
    """Pure-signal VFA series with known tissue parameters."""
    frames = [np.full(shape, _gre_signal(T1, T2star, PD, TR, TE, a))
              for a in flip_angles]
    return np.stack(frames, axis=0)


def _make_t2_series(T1, T2, PD, TE_list, TR, shape=(5, 5)):
    """Pure-signal multi-echo SE series."""
    frames = [np.full(shape, _se_signal(T1, T2, PD, TR, te)) for te in TE_list]
    return np.stack(frames, axis=0)


def _make_ir_series(T1, PD, TI_list, TR, shape=(3, 3)):
    """Pure-signal IR magnitude series (TE=0 simplification)."""
    frames = [np.full(shape, PD * abs(1 - 2 * np.exp(-ti / T1) + np.exp(-TR / T1)))
              for ti in TI_list]
    return np.stack(frames, axis=0)


# ---------------------------------------------------------------------------
# TestSimulateVfaSeries
# ---------------------------------------------------------------------------
class TestSimulateVfaSeries:
    def test_output_shape(self):
        lm = _uniform_map(3, shape=(10, 12))
        out = simulate_vfa_series(lm, [5., 15., 25.], TR_ms=20., TE_ms=5.)
        assert out.shape == (3, 10, 12)

    def test_values_nonneg(self):
        lm = _uniform_map(3)
        out = simulate_vfa_series(lm, [5., 15., 30.], TR_ms=20., TE_ms=5.)
        assert out.min() >= 0.

    def test_background_label_zero_gives_zero_signal(self):
        lm = np.zeros((8, 8), dtype=np.uint8)
        out = simulate_vfa_series(lm, [10., 20.], TR_ms=20., TE_ms=5.)
        assert out.max() == pytest.approx(0.0)

    def test_more_flip_angles_more_frames(self):
        lm = _uniform_map(2)
        out3 = simulate_vfa_series(lm, [5., 10., 20.], TR_ms=20., TE_ms=5.)
        out5 = simulate_vfa_series(lm, [5., 10., 15., 20., 30.], TR_ms=20., TE_ms=5.)
        assert out3.shape[0] == 3
        assert out5.shape[0] == 5

    def test_custom_tissue_props(self):
        lm = np.ones((4, 4), dtype=np.uint8)
        props = {1: {"T1": 1000., "T2": 80., "T2star": 50., "PD": 0.8}}
        out = simulate_vfa_series(lm, [20.], TR_ms=20., TE_ms=5., tissue_props=props)
        expected = _gre_signal(1000., 50., 0.8, 20., 5., 20.)
        np.testing.assert_allclose(out[0], expected, rtol=1e-6)

    def test_output_dtype_float64(self):
        lm = _uniform_map(3)
        out = simulate_vfa_series(lm, [10., 20.], TR_ms=20., TE_ms=5.)
        assert out.dtype == np.float64


# ---------------------------------------------------------------------------
# TestSimulateIrSeries
# ---------------------------------------------------------------------------
class TestSimulateIrSeries:
    def test_output_shape(self):
        lm = _uniform_map(3, (10, 10))
        out = simulate_ir_series(lm, [100., 500., 1000., 2000.])
        assert out.shape == (4, 10, 10)

    def test_values_nonneg(self):
        lm = _uniform_map(3)
        out = simulate_ir_series(lm, [50., 300., 700., 1500.])
        assert out.min() >= 0.

    def test_background_gives_zero(self):
        lm = np.zeros((6, 6), dtype=np.uint8)
        out = simulate_ir_series(lm, [100., 500., 1000.])
        assert out.max() == pytest.approx(0.0)

    def test_signal_recovers_with_ti(self):
        # At very long TI the signal approaches full magnetisation (PD*|1-exp(-TR/T1)|)
        lm = _uniform_map(3)  # gray matter, T1=1330
        out = simulate_ir_series(lm, [100., 3000., 9000.], TR_ms=10000.)
        # Signal at TI=9000 should be larger than at TI=100 (well past null)
        assert out[2].mean() > out[0].mean()

    def test_null_point_is_minimum(self):
        # For gray matter T1≈1330ms, null at TI≈1330*ln2≈922ms
        lm = _uniform_map(2)  # gray matter
        TI_list = [200., 500., 900., 1300., 2000., 3000.]
        out = simulate_ir_series(lm, TI_list, TR_ms=5000.)
        # Minimum signal should be near the null-crossing TI (~900ms = index 2)
        min_idx = out.reshape(len(TI_list), -1).mean(axis=1).argmin()
        assert min_idx in (2, 3)  # around 900-1300 ms


# ---------------------------------------------------------------------------
# TestSimulateMultiEchoSeries
# ---------------------------------------------------------------------------
class TestSimulateMultiEchoSeries:
    TE_LIST = [10., 30., 60., 100., 150.]

    def test_output_shape_se(self):
        lm = _uniform_map(3, (8, 9))
        out = simulate_multi_echo_series(lm, self.TE_LIST, sequence="SE")
        assert out.shape == (5, 8, 9)

    def test_output_shape_gre(self):
        lm = _uniform_map(3, (8, 9))
        out = simulate_multi_echo_series(lm, self.TE_LIST, sequence="GRE")
        assert out.shape == (5, 8, 9)

    def test_se_decay_monotonic(self):
        lm = _uniform_map(3)
        out = simulate_multi_echo_series(lm, self.TE_LIST, TR_ms=2000., sequence="SE")
        means = out.reshape(out.shape[0], -1).mean(axis=1)
        assert np.all(np.diff(means) < 0)

    def test_gre_decay_monotonic(self):
        lm = _uniform_map(3)
        out = simulate_multi_echo_series(lm, self.TE_LIST, TR_ms=2000.,
                                         sequence="GRE", flip_angle_deg=30.)
        means = out.reshape(out.shape[0], -1).mean(axis=1)
        assert np.all(np.diff(means) < 0)

    def test_background_zero(self):
        lm = np.zeros((6, 6), dtype=np.uint8)
        out = simulate_multi_echo_series(lm, self.TE_LIST)
        assert out.max() == pytest.approx(0.)

    def test_se_slower_decay_than_gre(self):
        # T2 > T2star for all tissues → SE decays slower than GRE
        lm = _uniform_map(3)
        se = simulate_multi_echo_series(lm, self.TE_LIST, TR_ms=2000., sequence="SE")
        gre = simulate_multi_echo_series(lm, self.TE_LIST, TR_ms=2000.,
                                          sequence="GRE", flip_angle_deg=90.)
        # At later TEs, SE signal should be higher than GRE
        assert se[-1].mean() > gre[-1].mean()


# ---------------------------------------------------------------------------
# TestVfaT1Map
# ---------------------------------------------------------------------------
FLIP_ANGLES_VFA = [5., 10., 15., 20., 25., 30.]
TR_VFA = 20.
TE_VFA = 5.


class TestVfaT1Map:
    def test_output_shape(self):
        series = np.ones((6, 10, 12))
        T1 = vfa_t1_map(series, FLIP_ANGLES_VFA, TR_VFA)
        assert T1.shape == (10, 12)

    def test_roundtrip_known_t1(self):
        T1_true, T2star, PD = 1000., 50., 0.8
        series = _make_vfa_series(T1_true, T2star, PD, FLIP_ANGLES_VFA, TR_VFA, TE_VFA)
        T1_fit = vfa_t1_map(series, FLIP_ANGLES_VFA, TR_VFA)
        np.testing.assert_allclose(T1_fit, T1_true, rtol=1e-4)

    def test_roundtrip_short_t1(self):
        T1_true, T2star, PD = 370., 40., 0.95
        series = _make_vfa_series(T1_true, T2star, PD, FLIP_ANGLES_VFA, TR_VFA, TE_VFA)
        T1_fit = vfa_t1_map(series, FLIP_ANGLES_VFA, TR_VFA)
        np.testing.assert_allclose(T1_fit, T1_true, rtol=1e-4)

    def test_roundtrip_long_t1(self):
        T1_true, T2star, PD = 4500., 1500., 1.0
        series = _make_vfa_series(T1_true, T2star, PD, FLIP_ANGLES_VFA, TR_VFA, TE_VFA)
        T1_fit = vfa_t1_map(series, FLIP_ANGLES_VFA, TR_VFA)
        np.testing.assert_allclose(T1_fit, T1_true, rtol=1e-3)

    def test_two_flip_angles_sufficient(self):
        T1_true, T2star, PD = 1000., 50., 0.8
        series = _make_vfa_series(T1_true, T2star, PD, [10., 25.], TR_VFA, TE_VFA)
        T1_fit = vfa_t1_map(series, [10., 25.], TR_VFA)
        np.testing.assert_allclose(T1_fit, T1_true, rtol=1e-4)

    def test_result_clipped_to_valid_range(self):
        # All-zero signal → denom collapses → T1 clipped to T1_MIN
        series = np.zeros((6, 5, 5))
        T1 = vfa_t1_map(series, FLIP_ANGLES_VFA, TR_VFA)
        assert T1.min() >= 10.
        assert T1.max() <= 10000.

    def test_output_dtype_float64(self):
        series = _make_vfa_series(1000., 50., 0.8, FLIP_ANGLES_VFA, TR_VFA, TE_VFA)
        assert vfa_t1_map(series, FLIP_ANGLES_VFA, TR_VFA).dtype == np.float64

    def test_simulate_then_map_roundtrip(self):
        # Full pipeline: label_map → simulate_vfa_series → vfa_t1_map
        lm = _uniform_map(3)  # white matter: T1=830ms
        series = simulate_vfa_series(lm, FLIP_ANGLES_VFA, TR_ms=TR_VFA, TE_ms=TE_VFA)
        T1_fit = vfa_t1_map(series, FLIP_ANGLES_VFA, TR_VFA)
        np.testing.assert_allclose(T1_fit, 830., rtol=1e-3)


# ---------------------------------------------------------------------------
# TestMultiEchoT2Map
# ---------------------------------------------------------------------------
TE_LIST_T2 = [10., 30., 60., 100., 150., 200.]
TR_T2 = 2000.


class TestMultiEchoT2Map:
    def test_output_shape(self):
        series = np.ones((6, 10, 12))
        T2 = multi_echo_t2_map(series, TE_LIST_T2)
        assert T2.shape == (10, 12)

    def test_roundtrip_known_t2(self):
        T1, T2_true, PD = 1000., 80., 0.8
        series = _make_t2_series(T1, T2_true, PD, TE_LIST_T2, TR_T2)
        T2_fit = multi_echo_t2_map(series, TE_LIST_T2)
        np.testing.assert_allclose(T2_fit, T2_true, rtol=1e-5)

    def test_roundtrip_long_t2(self):
        T1, T2_true, PD = 4500., 2200., 1.0
        series = _make_t2_series(T1, T2_true, PD, TE_LIST_T2, TR_T2)
        T2_fit = multi_echo_t2_map(series, TE_LIST_T2)
        np.testing.assert_allclose(T2_fit, T2_true, rtol=1e-4)

    def test_roundtrip_short_t2(self):
        T1, T2_true, PD = 200., 5., 0.1
        # Use earlier echo times to capture fast decay
        TE_short = [1., 3., 6., 10., 15., 20.]
        series = _make_t2_series(T1, T2_true, PD, TE_short, TR_T2)
        T2_fit = multi_echo_t2_map(series, TE_short)
        np.testing.assert_allclose(T2_fit, T2_true, rtol=1e-4)

    def test_zero_signal_gives_zero_t2(self):
        series = np.zeros((6, 5, 5))
        T2 = multi_echo_t2_map(series, TE_LIST_T2)
        assert np.all(T2 == 0.)

    def test_result_nonneg(self):
        lm = _uniform_map(3)
        series = simulate_multi_echo_series(lm, TE_LIST_T2, TR_ms=TR_T2, sequence="SE")
        T2 = multi_echo_t2_map(series, TE_LIST_T2)
        assert T2.min() >= 0.

    def test_output_dtype_float64(self):
        series = _make_t2_series(1000., 80., 0.8, TE_LIST_T2, TR_T2)
        assert multi_echo_t2_map(series, TE_LIST_T2).dtype == np.float64

    def test_simulate_then_map_roundtrip(self):
        lm = _uniform_map(3)  # white matter: T2=80ms
        series = simulate_multi_echo_series(lm, TE_LIST_T2, TR_ms=TR_T2, sequence="SE")
        T2_fit = multi_echo_t2_map(series, TE_LIST_T2)
        np.testing.assert_allclose(T2_fit, 80., rtol=1e-3)


# ---------------------------------------------------------------------------
# TestT2starMap
# ---------------------------------------------------------------------------
class TestT2starMap:
    def test_same_result_as_multi_echo_t2_map(self):
        series = _make_t2_series(1000., 80., 0.8, TE_LIST_T2, TR_T2)
        np.testing.assert_array_equal(
            t2star_map(series, TE_LIST_T2),
            multi_echo_t2_map(series, TE_LIST_T2),
        )

    def test_output_shape(self):
        series = np.ones((6, 7, 8))
        assert t2star_map(series, TE_LIST_T2).shape == (7, 8)

    def test_gre_series_roundtrip(self):
        T1, T2star_true, PD = 1000., 50., 0.8
        TR, flip_a = 100., 30.
        TE_short = [5., 10., 20., 35., 50.]
        # Build GRE series manually
        frames = [np.full((4, 4), _gre_signal(T1, T2star_true, PD, TR, te, flip_a))
                  for te in TE_short]
        series = np.stack(frames, axis=0)
        T2s_fit = t2star_map(series, TE_short)
        np.testing.assert_allclose(T2s_fit, T2star_true, rtol=1e-4)

    def test_simulate_then_map_roundtrip_gre(self):
        lm = _uniform_map(3)  # white matter: T2*=48ms
        TE_short = [5., 15., 30., 50., 75.]
        series = simulate_multi_echo_series(lm, TE_short, TR_ms=200.,
                                             flip_angle_deg=30., sequence="GRE")
        T2s = t2star_map(series, TE_short)
        np.testing.assert_allclose(T2s, 48., rtol=1e-3)


# ---------------------------------------------------------------------------
# TestIrT1Map
# ---------------------------------------------------------------------------
TI_LIST_IR = [50., 100., 300., 500., 700., 900., 1200., 1800., 2500.]
TR_IR = 5000.


class TestIrT1Map:
    def test_output_shape(self):
        series = _make_ir_series(1000., 0.8, TI_LIST_IR, TR_IR, shape=(4, 4))
        T1 = ir_t1_map(series, TI_LIST_IR, TR_IR)
        assert T1.shape == (4, 4)

    def test_roundtrip_known_t1(self):
        T1_true = 1000.
        series = _make_ir_series(T1_true, 0.8, TI_LIST_IR, TR_IR)
        T1_fit = ir_t1_map(series, TI_LIST_IR, TR_IR)
        np.testing.assert_allclose(T1_fit, T1_true, rtol=0.02)

    def test_roundtrip_short_t1(self):
        T1_true = 370.   # fat-like
        TI_short = [20., 50., 100., 200., 300., 500., 800., 1200.]
        series = _make_ir_series(T1_true, 0.95, TI_short, TR_IR)
        T1_fit = ir_t1_map(series, TI_short, TR_IR)
        np.testing.assert_allclose(T1_fit, T1_true, rtol=0.03)

    def test_background_gives_zero(self):
        series = np.zeros((len(TI_LIST_IR), 4, 4))
        T1 = ir_t1_map(series, TI_LIST_IR, TR_IR)
        assert np.all(T1 == 0.)

    def test_result_positive_for_tissue(self):
        series = _make_ir_series(1000., 0.8, TI_LIST_IR, TR_IR)
        T1 = ir_t1_map(series, TI_LIST_IR, TR_IR)
        assert T1.min() > 0.

    def test_simulate_then_map_roundtrip(self):
        lm = _uniform_map(3)  # white matter: T1=830ms
        series = simulate_ir_series(lm, TI_LIST_IR, TR_ms=TR_IR, TE_ms=1.)
        T1_fit = ir_t1_map(series, TI_LIST_IR, TR_IR)
        np.testing.assert_allclose(T1_fit, 830., rtol=0.03)


# ---------------------------------------------------------------------------
# TestSyntheticContrast
# ---------------------------------------------------------------------------
class TestSyntheticContrast:
    _T1  = np.full((6, 6), 1000.)
    _T2  = np.full((6, 6), 80.)
    _PD  = np.full((6, 6), 0.8)

    def test_se_formula(self):
        img = synthetic_contrast(self._T1, self._T2, self._PD, 500., 20., sequence="SE")
        expected = 0.8 * (1 - np.exp(-500. / 1000.)) * np.exp(-20. / 80.)
        np.testing.assert_allclose(img, expected, rtol=1e-8)

    def test_gre_formula(self):
        TR, TE, alpha = 100., 5., 30.
        img = synthetic_contrast(self._T1, self._T2, self._PD, TR, TE,
                                  sequence="GRE", flip_angle_deg=alpha)
        expected = _gre_signal(1000., 80., 0.8, TR, TE, alpha)
        np.testing.assert_allclose(img, expected, rtol=1e-8)

    def test_ir_formula(self):
        TR, TE, TI = 3000., 10., 900.
        img = synthetic_contrast(self._T1, self._T2, self._PD, TR, TE,
                                  sequence="IR", TI_ms=TI)
        expected = (0.8 * abs(1 - 2 * np.exp(-TI / 1000.) + np.exp(-TR / 1000.))
                    * np.exp(-TE / 80.))
        np.testing.assert_allclose(img, expected, rtol=1e-8)

    def test_background_zero(self):
        T1 = np.zeros((5, 5))
        T2 = np.full((5, 5), 80.)
        PD = np.full((5, 5), 0.8)
        img = synthetic_contrast(T1, T2, PD, 500., 20.)
        assert np.all(img == 0.)

    def test_output_shape_preserved(self):
        img = synthetic_contrast(self._T1, self._T2, self._PD, 500., 20.)
        assert img.shape == (6, 6)

    def test_longer_tr_increases_se_signal(self):
        img_short = synthetic_contrast(self._T1, self._T2, self._PD, 200., 20.)
        img_long  = synthetic_contrast(self._T1, self._T2, self._PD, 5000., 20.)
        assert img_long.mean() > img_short.mean()

    def test_longer_te_decreases_se_signal(self):
        img_short = synthetic_contrast(self._T1, self._T2, self._PD, 500., 10.)
        img_long  = synthetic_contrast(self._T1, self._T2, self._PD, 500., 150.)
        assert img_long.mean() < img_short.mean()

    def test_ir_requires_ti(self):
        with pytest.raises(ValueError, match="TI_ms"):
            synthetic_contrast(self._T1, self._T2, self._PD, 3000., 10., sequence="IR")

    def test_unknown_sequence_raises(self):
        with pytest.raises(ValueError):
            synthetic_contrast(self._T1, self._T2, self._PD, 500., 20., sequence="XYZ")

    def test_synthetic_matches_simulate_se(self):
        # Roundtrip: simulate_multi_echo_series at one TE should match
        # synthetic_contrast built from the ground-truth parameter maps.
        lm = _uniform_map(3)  # white matter: T1=830, T2=80, PD=0.65
        TR, TE = 2000., 30.
        series = simulate_multi_echo_series(lm, [TE], TR_ms=TR, sequence="SE")
        direct = series[0]

        T1_gt = np.full(lm.shape, 830.)
        T2_gt = np.full(lm.shape, 80.)
        PD_gt = np.full(lm.shape, 0.65)
        synth = synthetic_contrast(T1_gt, T2_gt, PD_gt, TR, TE, sequence="SE")

        np.testing.assert_allclose(synth, direct, rtol=1e-6)
