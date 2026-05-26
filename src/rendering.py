"""
rendering.py — pure (Qt-free) signal-rendering helpers for the MRI simulator.

These functions turn a tissue-label slice plus a property table into a rendered
image under a given sequence, and apply per-effect physics (Gadolinium contrast,
magnetization transfer, B1+ inhomogeneity, fat-water chemical shift) by
delegating to the dedicated physics modules (signal_engine, mt, b1, dixon).

There is no GUI/Qt/matplotlib code here, so every function can be unit tested
directly. app_qt.py imports this module and calls these functions.
"""

import numpy as np
from scipy.ndimage import gaussian_filter
from signal_engine import (
    spin_echo_signal,
    gradient_echo_signal,
    inversion_recovery_signal,
)
import dixon
import mt
import b1


# Gadolinium relaxivity constants (3T, Gd-DTPA)
GD_R1_MS: float = 4.5e-3        # (mmol/kg)^-1 · ms^-1
# Per-label fractional Gd concentration relative to administered dose.
# Reflects BBB integrity: scalp/CSF enhance more than brain parenchyma.
GD_TISSUE_FRACTION: dict[int, float] = {
    1: 0.30,   # CSF — modest (choroid plexus leak)
    2: 0.05,   # Gray matter — intact BBB
    3: 0.05,   # White matter — intact BBB
    4: 0.60,   # Fat/Scalp — no BBB, vascularised
    5: 0.10,   # Bone
}


def apply_gd(base_props: dict, dose: float) -> dict:
    """Return a copy of tissue_props with T1 shortened by Gd at the given dose (mmol/kg)."""
    modified = {k: dict(v) for k, v in base_props.items()}
    for label, frac in GD_TISSUE_FRACTION.items():
        if label in modified:
            T1 = modified[label]["T1"]
            modified[label]["T1"] = 1.0 / (1.0 / T1 + GD_R1_MS * dose * frac)
    return modified


def param_maps(phantom_slice: np.ndarray, tprops: dict,
               keys: tuple[str, ...]) -> list[np.ndarray]:
    """Per-pixel parameter maps (one per key) built from a label slice + props."""
    maps = [np.zeros(phantom_slice.shape, dtype=float) for _ in keys]
    for lab, p in tprops.items():
        mask = phantom_slice == lab
        if mask.any():
            for m, k in zip(maps, keys):
                m[mask] = float(p.get(k, p.get("T2", 0.0)))
    return maps


def simulate_slice_props(phantom_slice: np.ndarray, TR: float, TE: float,
                         sequence: str, TI: float, FA: float,
                         tissue_props: dict) -> np.ndarray:
    """Like phantom3d.simulate_slice but uses caller-supplied tissue properties."""
    image = np.zeros_like(phantom_slice, dtype=float)
    for label, props in tissue_props.items():
        mask = phantom_slice == label
        if not np.any(mask):
            continue
        if sequence == "SE":
            sig = spin_echo_signal(props["T1"], props["T2"], props["PD"], TR, TE)
        elif sequence == "GRE":
            sig = gradient_echo_signal(props["T1"], props.get("T2star", props["T2"]),
                                       props["PD"], TR, TE, FA)
        elif sequence == "IR":
            sig = inversion_recovery_signal(props["T1"], props["T2"], props["PD"], TR, TE, TI)
        else:
            sig = spin_echo_signal(props["T1"], props["T2"], props["PD"], TR, TE)
        image[mask] = sig
    return image


def apply_mt(image: np.ndarray, phantom_slice: np.ndarray, tprops: dict,
             mt_power: float, seq: str, TR: float, TE: float, FA: float) -> np.ndarray:
    """Suppress signal via the two-pool MT model (mt.simulate_mt_weighted).

    The free-pool steady-state fraction under off-resonance saturation is
    computed per tissue from the binary spin-bath model and applied as a
    multiplicative map, so the rendered texture is preserved.  mt_power
    (0-100 %) scales the saturation-pulse B1 amplitude (0-2.5 µT).
    """
    if mt_power <= 0 or phantom_slice.shape != image.shape:
        return image
    B1_sat = mt_power / 100.0 * 2.5          # 0-2.5 µT → up to ~45% WM MTR
    seq_mt = "SE" if seq in ("Spin Echo", "Inversion Recovery", "FSE / TSE") else "GRE"
    s_sat = mt.simulate_mt_weighted(phantom_slice, B1_sat_uT=B1_sat, offset_hz=1500.0,
                                    TR_ms=TR, TE_ms=TE, flip_angle_deg=FA,
                                    sequence=seq_mt, tissue_props=tprops)
    s_ref = mt.simulate_no_mt(phantom_slice, TR_ms=TR, TE_ms=TE,
                              flip_angle_deg=FA, sequence=seq_mt, tissue_props=tprops)
    with np.errstate(invalid="ignore", divide="ignore"):
        factor = np.where(s_ref > 1e-9, s_sat / s_ref, 1.0)
    return image * factor


def apply_b1(image: np.ndarray, phantom_slice: np.ndarray, tprops: dict,
             seq: str, FA: float, TR: float, TE: float, B0: float) -> np.ndarray:
    """Apply B1+ transmit inhomogeneity using the b1 module.

    A centre-bright Gaussian B1+ map (stronger variation at 3T than 1.5T)
    modulates the signal through the correct flip-angle physics — the GRE
    Ernst-curve response (b1.apply_b1_to_gre) or the SE sin·sin² refocusing
    law (b1.apply_b1_to_se) — applied as a ratio so texture is preserved.
    """
    if phantom_slice.shape != image.shape:
        return image
    variation = 0.30 if B0 >= 2.5 else 0.12   # 3T more inhomogeneous than 1.5T
    b1_map = b1.gaussian_b1_map(image.shape, variation=variation)
    if seq == "Gradient Echo":
        T1m, T2sm, PDm = param_maps(phantom_slice, tprops, ("T1", "T2star", "PD"))
        eff = b1.apply_b1_to_gre(image, b1_map, FA, T1m, T2sm, PDm, TR, TE)
        nom = b1.apply_b1_to_gre(image, b1.uniform_b1_map(image.shape), FA,
                                 T1m, T2sm, PDm, TR, TE)
        with np.errstate(invalid="ignore", divide="ignore"):
            ratio = np.where(nom > 1e-9, eff / nom, 1.0)
        return image * ratio
    return b1.apply_b1_to_se(image, b1_map, 90.0)


def gre_fatwater_phase(image: np.ndarray, phantom_slice: np.ndarray,
                       TE_ms: float, B0: float) -> np.ndarray:
    """Apply fat-water chemical-shift phase cycling for GRE sequences.

    SE refocuses the fat-water phase; GRE does not, so the relative phase
    accumulates over TE producing in-phase / opposed-phase (India-ink) borders.
    The chemical-shift phase model lives in dixon.combined_gre_signal — here we
    only split the rendered image into water/fat components and blur them to
    model the partial-volume mixing that makes the boundary effect visible.
    """
    fat_mask    = phantom_slice == 4   # Fat/Scalp label
    tissue_mask = phantom_slice > 0

    if not np.any(fat_mask) or not np.any(tissue_mask & ~fat_mask):
        return image

    water_blur = gaussian_filter(np.where(tissue_mask & ~fat_mask, image, 0.0), sigma=1.5)
    fat_blur   = gaussian_filter(np.where(fat_mask, image, 0.0), sigma=1.5)

    combined = np.abs(dixon.combined_gre_signal(water_blur, fat_blur, B0, TE_ms))

    result              = image.copy()
    result[tissue_mask] = combined[tissue_mask]
    return result


def gre_fw_phase_label(TE_ms: float, B0: float) -> str:
    """Short label describing the current fat-water phase (for metrics display)."""
    phi     = 2.0 * np.pi * dixon.fat_water_shift_hz(B0) * TE_ms / 1000.0
    cos_phi = float(np.cos(phi))
    if cos_phi > 0.70:
        return "In-phase"
    if cos_phi < -0.70:
        return "Opposed"
    return f"Partial ({np.degrees(phi) % 360:.0f}°)"
