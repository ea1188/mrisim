"""Dynamic, contrast-bolus perfusion: DSC and DCE.

Unlike ASL (`perfusion.py`), these inject a gadolinium bolus and acquire a *time series*
as it passes through the tissue, then fit the concentration–time curve to a kinetic model
to produce quantitative maps:

* **DSC** (Dynamic Susceptibility Contrast) — a T2*-weighted bolus-tracking acquisition.
  As the paramagnetic bolus passes it transiently shortens T2* → a signal **drop**. The
  concentration curve C(t) ~ -dR2*(t) is fitted (gamma-variate, no recirculation) to give:
    - **CBV**  (mL/100 g)        ∝ ∫C(t)dt          — area under the curve (blood volume)
    - **CBF**  (mL/100 g/min)    — peak delivery rate (shared with the ASL flow table)
    - **MTT**  (s)               = CBV / CBF        — central volume theorem (transit time)
  Used for stroke (the infarct core has low CBV + prolonged MTT) and tumour grading (high
  CBV = high grade).

* **DCE** (Dynamic Contrast Enhanced) — a T1-weighted dynamic. Where the blood–brain
  barrier leaks, gadolinium accumulates in the extravascular space → T1 shortening → signal
  **rise**. The Tofts model fits the uptake to **Ktrans** (min⁻¹, the volume transfer
  constant / permeability). Normal brain behind an intact BBB ≈ 0; tumour neovasculature and
  active demyelination leak (high Ktrans).

The per-slice engine has no time axis, so the dynamics live here (the curves justify the
parameter values) and the engine emits the **parameter maps** via the quantitative-map path.

Public API:
    gamma_variate(t, t0, alpha, beta, amp)            — DSC bolus concentration curve C(t)
    tofts_curve(t, ktrans, ve, ...)                   — DCE tissue-uptake concentration curve
    compute_cbv_map / compute_cbf_map / compute_mtt_map(labels)   — DSC maps
    compute_ktrans_map(labels)                        — DCE map
"""
from __future__ import annotations

import numpy as np
from scipy.ndimage import gaussian_filter

import perfusion

# Cerebral blood VOLUME (mL / 100 g) per tissue_db label. Grey matter ~4, white ~2 (grey
# ≈ 2× white, as for flow); CSF/fat/bone/air avascular. Organs carry a sizeable blood pool.
CBV_ML100G: dict[int, float] = {
    0: 0.0, 1: 0.0, 2: 4.0, 3: 2.0, 4: 0.0, 5: 0.0, 6: 1.2,
    7: 12.0, 8: 14.0, 9: 16.0, 10: 12.0, 11: 0.0, 12: 0.0, 13: 0.0,
    14: 1.0, 15: 0.0, 16: 2.2, 17: 4.0, 18: 0.0, 19: 8.0, 20: 10.0,
    21: 3.0, 22: 0.0,
    # Pathologies: infarct core loses blood volume; tumour neovasculature raises it.
    23: 2.6,    # WM (demyelinating) lesion
    24: 1.5,    # Acute infarct — reduced CBV (core)
    25: 1.2,    # Microhaemorrhage
    26: 8.5,    # Tumour — high CBV (neovascular, high-grade marker)
    27: 0.8,    # Abscess core — avascular pus
    28: 3.5,    # Abscess rim (hypervascular capsule)
}

# DCE volume transfer constant Ktrans (min⁻¹) per label — permeability of the
# vasculature. Behind an intact blood–brain barrier it is ~0; leaky tumour / active lesion
# vasculature and the (BBB-free) body organs enhance.
KTRANS_PERMIN: dict[int, float] = {
    0: 0.0, 1: 0.0, 2: 0.006, 3: 0.004, 4: 0.0, 5: 0.0, 6: 0.08,
    7: 0.45, 8: 0.40, 9: 0.55, 10: 0.45, 11: 0.0, 12: 0.0, 13: 0.0,
    14: 0.03, 15: 0.0, 16: 0.005, 17: 0.15, 18: 0.0, 19: 0.35, 20: 0.30,
    21: 0.20, 22: 0.0,
    # Pathologies: BBB breakdown → leakage. Tumour highest, then abscess rim / active lesion.
    23: 0.09,   # Active demyelinating lesion (enhancing)
    24: 0.03,   # Subacute infarct — BBB breakdown
    25: 0.01,   # Microhaemorrhage
    26: 0.28,   # Tumour — markedly leaky neovasculature
    27: 0.02,   # Abscess core
    28: 0.18,   # Abscess rim — enhancing capsule
}


def gamma_variate(
    t: "np.ndarray | float",
    t0: float = 10.0,
    alpha: float = 3.0,
    beta: float = 1.5,
    amp: float = 1.0,
) -> "np.ndarray | float":
    """DSC bolus concentration–time curve C(t) (gamma-variate, the standard first-pass fit
    with no recirculation): 0 before arrival ``t0``, then a single asymmetric peak.
    ``∫C(t)dt`` is proportional to CBV; the peak height tracks CBF."""
    tt = np.asarray(t, dtype=float) - t0
    c = np.where(tt > 0, amp * np.power(np.clip(tt, 0, None), alpha) * np.exp(-tt / beta), 0.0)
    return float(c) if np.isscalar(t) else c


def tofts_curve(
    t: "np.ndarray | float",
    ktrans: float,
    ve: float = 0.2,
    cp_amp: float = 1.0,
    cp_decay: float = 0.02,
) -> "np.ndarray | float":
    """DCE tissue concentration C_t(t) from the (extended) Tofts model with a
    mono-exponentially decaying plasma input C_p(t)=cp_amp·e^(−cp_decay·t):
    C_t = Ktrans·∫₀ᵗ C_p(τ)·e^(−(Ktrans/ve)(t−τ)) dτ. Higher Ktrans → faster, higher uptake;
    Ktrans=0 (intact BBB) → no enhancement."""
    tt = np.asarray(t, dtype=float)
    if ktrans <= 0:
        out = np.zeros_like(tt)
        return float(out) if np.isscalar(t) else out
    kep = ktrans / max(ve, 1e-3)                       # efflux rate constant
    # analytic convolution of two exponentials (kep ≠ cp_decay)
    if abs(kep - cp_decay) < 1e-6:
        conv = cp_amp * tt * np.exp(-kep * tt)
    else:
        conv = cp_amp * (np.exp(-cp_decay * tt) - np.exp(-kep * tt)) / (kep - cp_decay)
    ct = ktrans * np.clip(conv, 0, None)
    return float(ct) if np.isscalar(t) else ct


def _label_map(label_slice: np.ndarray, table: dict[int, float], seed: int,
               spread: float = 0.20, lo: float = 0.6, hi: float = 1.4) -> np.ndarray:
    """Per-label value map with smooth physiological spatial variation; 0 where the table
    value is 0 (avascular / background)."""
    out = np.zeros(label_slice.shape, dtype=float)
    rng = np.random.RandomState(seed)
    variation = gaussian_filter(rng.randn(*label_slice.shape) * 0.05, sigma=3)
    for label in np.unique(label_slice):
        base = table.get(int(label), 0.0)
        if base <= 0.0:
            continue
        mask = label_slice == label
        out[mask] = np.clip(base * (1.0 + variation[mask] * spread), base * lo, base * hi)
    return out


def compute_cbv_map(label_slice: np.ndarray) -> np.ndarray:
    """DSC cerebral blood volume map (mL/100 g) — grey > white, 0 where avascular."""
    return _label_map(label_slice, CBV_ML100G, seed=51)


def compute_cbf_map(label_slice: np.ndarray) -> np.ndarray:
    """DSC cerebral blood flow map (mL/100 g/min). Shares the ASL flow table so DSC and
    ASL agree on flow."""
    return perfusion.compute_cbf_map(label_slice)


def compute_mtt_map(label_slice: np.ndarray) -> np.ndarray:
    """Mean transit time map (s) via the central volume theorem MTT = CBV/CBF. Prolonged
    where flow falls faster than volume (e.g. an infarct / its penumbra)."""
    cbv = compute_cbv_map(label_slice)
    cbf = compute_cbf_map(label_slice)
    mtt = np.zeros(label_slice.shape, dtype=float)
    ok = cbf > 0
    mtt[ok] = 60.0 * cbv[ok] / cbf[ok]                 # min → s
    return mtt


def compute_ktrans_map(label_slice: np.ndarray) -> np.ndarray:
    """DCE permeability map Ktrans (min⁻¹) — ~0 behind an intact BBB, high in leaky
    tumour / active-lesion vasculature (and the BBB-free body organs)."""
    return _label_map(label_slice, KTRANS_PERMIN, seed=53, spread=0.25)
