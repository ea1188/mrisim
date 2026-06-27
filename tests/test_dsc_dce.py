"""Dynamic contrast-bolus perfusion: DSC + DCE (dsc_dce.py)."""
import numpy as np
import pytest

import dsc_dce


def test_gamma_variate_bolus_shape():
    t = np.linspace(0, 40, 400)
    c = dsc_dce.gamma_variate(t, t0=10, alpha=3, beta=1.5, amp=1.0)
    assert np.all(c[t <= 10] == 0)                       # nothing before bolus arrival
    assert c.max() > 0
    peak_t = t[np.argmax(c)]
    assert 13 < peak_t < 17                              # single peak near t0 + alpha*beta
    c2 = dsc_dce.gamma_variate(t, t0=10, alpha=3, beta=1.5, amp=2.0)
    assert c2.sum() == pytest.approx(2 * c.sum(), rel=1e-6)   # area (∝ CBV) scales with amp


def test_tofts_uptake_increases_with_ktrans():
    t = np.linspace(0, 60, 200)
    assert np.all(dsc_dce.tofts_curve(t, ktrans=0.0) == 0)       # intact BBB → no enhancement
    low = dsc_dce.tofts_curve(t, ktrans=0.02)
    high = dsc_dce.tofts_curve(t, ktrans=0.28)
    assert high.max() > low.max() > 0                            # leakier → more uptake
    assert 0 < int(high.argmax()) < len(high) - 1               # rises to a peak, then washes out


def test_cbv_map_grey_white_csf():
    ph = np.array([[2, 3, 1], [2, 3, 0], [1, 2, 3]])
    cbv = dsc_dce.compute_cbv_map(ph)
    assert cbv[ph == 2].mean() > cbv[ph == 3].mean() > 0        # grey > white > 0
    assert np.all(cbv[ph == 1] == 0) and np.all(cbv[ph == 0] == 0)   # CSF / background avascular
    assert 3 < cbv[ph == 2].mean() < 6                          # physiological GM CBV (mL/100g)


def test_mtt_central_volume_theorem_and_infarct_prolonged():
    ph = np.array([[2, 2, 24], [2, 24, 2], [3, 2, 24]])
    mtt = dsc_dce.compute_mtt_map(ph)
    assert 2 < mtt[ph == 2].mean() < 7                          # GM MTT ~4 s
    assert mtt[ph == 24].mean() > mtt[ph == 2].mean()           # infarct: prolonged transit
    cbv, cbf = dsc_dce.compute_cbv_map(ph), dsc_dce.compute_cbf_map(ph)
    ok = cbf > 0
    assert np.allclose(mtt[ok], 60 * cbv[ok] / cbf[ok])         # MTT = 60·CBV/CBF identity


def test_ktrans_tumour_leaks_normal_brain_intact():
    ph = np.array([[2, 3, 26], [2, 26, 3], [1, 2, 26]])
    kt = dsc_dce.compute_ktrans_map(ph)
    assert kt[ph == 26].mean() > 10 * kt[ph == 2].mean()       # tumour >> normal grey (intact BBB)
    assert kt[ph == 2].mean() < 0.02                           # normal brain barely leaks
    assert np.all(kt[ph == 1] == 0)                            # CSF no uptake


def test_table_relationships():
    assert dsc_dce.CBV_ML100G[2] > dsc_dce.CBV_ML100G[3]           # GM > WM blood volume
    assert dsc_dce.CBV_ML100G[26] > dsc_dce.CBV_ML100G[2]          # tumour high CBV
    assert dsc_dce.CBV_ML100G[24] < dsc_dce.CBV_ML100G[2]          # infarct low CBV
    assert dsc_dce.KTRANS_PERMIN[26] > dsc_dce.KTRANS_PERMIN[2]    # tumour leaks, grey doesn't
