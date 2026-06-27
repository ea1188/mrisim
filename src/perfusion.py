"""Arterial Spin Labeling (ASL) perfusion.

ASL magnetically labels arterial blood water as a freely-diffusible tracer (no contrast
agent), then images after a post-label delay (PLD) lets the labelled blood reach the
tissue. The *perfusion-weighted* image is the **label − control** difference ΔM — only a
~1% modulation of the equilibrium signal, so it is intrinsically low-SNR and grey matter
(high flow) is brightest. Calibrating ΔM against the blood T1 kinetics yields a
quantitative **CBF map** in mL/100 g/min.

Modelled with the single-compartment pCASL kinetic model (Buxton 1998; Alsop 2015
consensus): ΔM/M0 = 2·α·f·T1b·exp(−PLD/T1b)·(1−exp(−τ/T1b)) / λ, with f the tissue blood
flow, τ the label duration, α the labelling efficiency and λ the blood–brain partition
coefficient.

Public API:
    asl_delta_fraction(cbf, pld_ms, label_dur_ms, t1_blood_ms)  — ΔM/M0 (label−control)
    compute_cbf_map(label_slice, field)                         — CBF map, mL/100 g/min
    simulate_asl_weighted(label_slice, field, pld_ms, ...)      — perfusion-weighted ΔM image
"""
from __future__ import annotations

import numpy as np
from scipy.ndimage import gaussian_filter

import tissue_db

# Resting tissue blood flow (mL / 100 g / min) per tissue_db label. Brain grey matter
# ~60, white matter ~22 (grey ≈ 2.5–3× white), CSF/fat/bone/air unperfused. Well-perfused
# organs are high (kidney cortex ~200, liver ~100, myocardium ~80). 0 = not perfused.
CBF_ML100G: dict[int, float] = {
    0: 0.0,      # Air / background
    1: 0.0,      # CSF / fluid
    2: 60.0,     # Grey matter
    3: 22.0,     # White matter
    4: 0.0,      # Fat
    5: 0.0,      # Bone
    6: 15.0,     # Muscle
    7: 100.0,    # Liver
    8: 80.0,     # Spleen
    9: 200.0,    # Kidney cortex (highly perfused)
    10: 100.0,   # Kidney medulla
    11: 0.0,     # Blood (intravascular — flow void, not parenchymal perfusion)
    12: 0.0,     # Gas
    13: 0.0,     # Cortical bone
    14: 5.0,     # Marrow
    15: 0.0,     # Cartilage / disc
    16: 25.0,    # Spinal cord (neural — white-matter-like)
    17: 30.0,    # Bowel wall
    18: 0.0,     # Lung (air)
    19: 60.0,    # Pancreas
    20: 80.0,    # Heart / myocardium
    21: 20.0,    # Soft tissue / gland
    22: 0.0,     # Ligament / meniscus
    # Demo brain pathologies: an infarct is oligaemic (low flow), a tumour neovascular
    # (high), so perfusion discriminates them where structural images may not.
    23: 30.0,    # WM lesion
    24: 8.0,     # Acute infarct — reduced perfusion
    25: 20.0,    # Microhaemorrhage
    26: 95.0,    # Tumour — neovascular hyperperfusion
    27: 12.0,    # Abscess core — avascular pus
    28: 45.0,    # Abscess rim (enhancing capsule)
}

# Arterial blood T1 (ms): longer at higher field. (Lu 2004; Alsop 2015 use 1650 ms @ 3T.)
T1_BLOOD_MS: dict[float, float] = {1.5: 1480.0, 3.0: 1650.0}

# Kinetic-model constants (Alsop 2015 consensus pCASL).
LABEL_EFFICIENCY = 0.85          # α — labelling efficiency (pCASL)
PARTITION_COEFF = 0.90           # λ — blood–brain partition coefficient (mL/g)


def _field_T(field: str | float) -> float:
    return 3.0 if "3" in str(field) else 1.5


def asl_delta_fraction(
    cbf: "float | np.ndarray",
    pld_ms: "float | np.ndarray",
    label_dur_ms: float,
    t1_blood_ms: float,
    alpha: float = LABEL_EFFICIENCY,
    lam: float = PARTITION_COEFF,
) -> "float | np.ndarray":
    """ΔM/M0 — the label−control perfusion signal as a fraction of equilibrium
    magnetization, for a tissue perfused at ``cbf`` mL/100 g/min (single-compartment
    pCASL). Returns ~0.01 for grey matter at a typical PLD — i.e. a ~1% modulation."""
    f = np.asarray(cbf, dtype=float) / 6000.0          # mL/100g/min → mL/g/s
    t1b, pld, tau = t1_blood_ms / 1000.0, pld_ms / 1000.0, label_dur_ms / 1000.0
    frac = (2.0 * alpha * f * t1b / lam
            * np.exp(-pld / t1b) * (1.0 - np.exp(-tau / t1b)))
    return float(frac) if np.isscalar(cbf) else frac


def compute_cbf_map(label_slice: np.ndarray, field: str | float = "3T") -> np.ndarray:
    """Quantitative CBF map (mL/100 g/min) for a labelled-tissue slice, with smooth
    physiological spatial variation; 0 where unperfused or background. `field` is
    accepted for API symmetry (CBF is field-independent in this model)."""
    del field
    cbf = np.zeros(label_slice.shape, dtype=float)
    rng = np.random.RandomState(47)
    variation = gaussian_filter(rng.randn(*label_slice.shape) * 0.05, sigma=3)
    for label in np.unique(label_slice):
        base = CBF_ML100G.get(int(label), 0.0)
        if base <= 0.0:
            continue
        mask = label_slice == label
        local = base * (1.0 + variation[mask] * 0.20)
        cbf[mask] = np.clip(local, base * 0.6, base * 1.4)
    return cbf


def simulate_asl_weighted(
    label_slice: np.ndarray,
    field: str | float = "3T",
    pld_ms: float = 1800.0,
    label_dur_ms: float = 1800.0,
) -> np.ndarray:
    """Perfusion-weighted image — the (noisy) label−control difference ΔM. It is ~1% of
    the equilibrium magnetization, so grey matter (high CBF) is brightest and the image
    carries the subtraction noise of two near-identical acquisitions. Non-negative."""
    fT = _field_T(field)
    t1b = T1_BLOOD_MS.get(fT, 1650.0)
    cbf = compute_cbf_map(label_slice, field)
    props = tissue_db.properties("3T" if fT == 3.0 else "1.5T")
    m0 = np.zeros(label_slice.shape, dtype=float)      # equilibrium magnetization ≈ PD
    for label in np.unique(label_slice):
        p = props.get(int(label))
        if p:
            m0[label_slice == label] = float(p.get("PD", 0.0))
    delta = m0 * asl_delta_fraction(cbf, pld_ms, label_dur_ms, t1b)
    # label−control is a small difference of two noisy images → its own subtraction noise,
    # scaled to a fraction of a grey-matter ΔM so the perfusion map stays readable.
    gm_delta = float(m0.max()) * asl_delta_fraction(60.0, pld_ms, label_dur_ms, t1b)
    rng = np.random.RandomState(48)
    noise = rng.randn(*label_slice.shape) * (0.12 * gm_delta)
    return np.clip(delta + noise, 0.0, None)
