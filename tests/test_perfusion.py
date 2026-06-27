"""Arterial Spin Labeling (ASL) perfusion model (perfusion.py)."""
import numpy as np

import perfusion


def test_delta_fraction_is_about_one_percent_for_grey_matter():
    """The label−control perfusion signal is a ~1% modulation of M0 for grey-matter flow
    — the defining (and challenging) feature of ASL."""
    frac = perfusion.asl_delta_fraction(60.0, pld_ms=1800, label_dur_ms=1800, t1_blood_ms=1650)
    assert 0.002 < frac < 0.02, frac


def test_delta_fraction_scales_with_flow_and_decays_with_pld():
    def f(cbf, pld):
        return perfusion.asl_delta_fraction(cbf, pld, 1800, 1650)
    assert f(60, 1800) > f(20, 1800)            # more flow → more delivered label
    assert f(60, 1800) < f(60, 1000)            # longer PLD → more blood-T1 decay → less signal
    assert f(0, 1800) == 0.0                    # no flow → no label delivered


def test_cbf_map_grey_brighter_than_white_csf_zero():
    phantom = np.array([[1, 2, 3], [2, 3, 1], [0, 2, 3]])   # CSF / GM / WM / background
    cbf = perfusion.compute_cbf_map(phantom)
    gm, wm = cbf[phantom == 2], cbf[phantom == 3]
    assert gm.mean() > wm.mean() > 0            # grey > white > 0
    assert np.all(cbf[phantom == 1] == 0)       # CSF unperfused
    assert np.all(cbf[phantom == 0] == 0)       # background 0
    assert 35 < gm.mean() < 90 and 12 < wm.mean() < 35   # physiological range


def test_cbf_table_relationships():
    assert perfusion.CBF_ML100G[2] > 2 * perfusion.CBF_ML100G[3]   # GM ≈ 2.5–3× WM
    assert perfusion.CBF_ML100G[24] < perfusion.CBF_ML100G[2]      # infarct hypoperfused
    assert perfusion.CBF_ML100G[26] > perfusion.CBF_ML100G[3]      # tumour hyperperfused


def test_perfusion_weighted_grey_brightest_and_nonneg():
    phantom = np.array([[1, 2, 3], [2, 3, 1], [0, 2, 3]])
    pw = perfusion.simulate_asl_weighted(phantom, field="3T")
    assert np.all(pw >= 0)                                       # non-negative ΔM image
    assert pw[phantom == 2].mean() > pw[phantom == 3].mean()     # grey matter brightest
    assert pw[phantom == 1].mean() < pw[phantom == 2].mean()     # CSF has no perfusion signal


def test_blood_t1_increases_with_field():
    assert perfusion.T1_BLOOD_MS[3.0] > perfusion.T1_BLOOD_MS[1.5]
