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
    balanced_ssfp_signal,
)
import dixon
import mt
import b1
import coil
import epi
import pv


# Gadolinium relaxivity constants (3T, Gd-DTPA)
GD_R1_MS: float = 4.5e-3        # (mmol/kg)^-1 · ms^-1
# Per-label fractional Gd concentration relative to administered dose, i.e. how
# much each tissue enhances. Driven by perfusion + extracellular distribution:
# blood (intravascular) enhances most, the kidneys filter and concentrate Gd,
# vascular organs/glands enhance moderately, and barrier tissues (intact BBB,
# avascular cartilage, cortical bone, gas) barely change.
GD_TISSUE_FRACTION: dict[int, float] = {
    # Neuro (unchanged — brain contrast is separately calibrated)
    1: 0.30,   # CSF — modest (choroid plexus leak)
    2: 0.05,   # Gray matter — intact BBB
    3: 0.05,   # White matter — intact BBB
    4: 0.60,   # Fat/Scalp — no BBB, vascularised
    5: 0.10,   # Bone (skull)
    # Body tissues
    6: 0.25,   # Muscle — moderate perfusion
    7: 0.45,   # Liver — arterial + portal supply
    8: 0.55,   # Spleen — highly vascular
    9: 0.80,   # Kidney cortex — strongly perfused, filters Gd
    10: 0.65,  # Kidney medulla — enhances then excretes
    11: 0.95,  # Blood — intravascular, maximal enhancement
    12: 0.00,  # Gas
    13: 0.05,  # Cortical bone
    14: 0.20,  # Marrow
    15: 0.05,  # Cartilage / disc — avascular
    16: 0.05,  # Spinal cord — blood–cord barrier
    17: 0.30,  # Bowel / GI — wall enhances
    18: 0.15,  # Lung — mostly air, low parenchymal enhancement
    19: 0.55,  # Pancreas — well-perfused gland
    20: 0.40,  # Heart / myocardium — perfused
    21: 0.45,  # Soft tissue / gland (prostate, adrenal, thyroid)
    # Demo pathologies (brain-only): the enhancing tumour breaks the blood–brain
    # barrier and takes up Gd strongly → bright on T1-post-contrast. The WM lesion
    # / infarct / haemorrhage don't appreciably enhance (omitted → unchanged).
    26: 0.85,  # Tumour (enhancing)
    # Abscess: the capsule (rim) enhances avidly with Gd → a bright ring; the
    # necrotic pus core does not enhance (omitted → unchanged).
    28: 0.85,  # Abscess rim (enhancing capsule)
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
            for m, k in zip(maps, keys, strict=False):
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
        elif sequence == "bSSFP":
            sig = balanced_ssfp_signal(props["T1"], props["T2"], props["PD"], TR, TE, FA)
        else:
            sig = spin_echo_signal(props["T1"], props["T2"], props["PD"], TR, TE)
        image[mask] = sig
    return image


def apply_fat_sat(image: np.ndarray, phantom_slice: np.ndarray,
                  off_resonance_hz: "np.ndarray | None" = None,
                  residual: float = 0.1, fat_label: int = 4) -> np.ndarray:
    """Spectral (CHESS) fat saturation: null the fat resonance before imaging.

    A frequency-selective pulse saturates fat, so its signal drops to a small
    ``residual``. Unlike STIR this leaves water untouched — but it is sensitive
    to B0: where off-resonance moves fat out of the (~±100 Hz) saturation band
    the suppression fails and fat signal returns, the classic "failed fat-sat"
    seen near air interfaces and field-of-view edges.
    """
    fat = phantom_slice == fat_label
    if not np.any(fat) or phantom_slice.shape != image.shape:
        return image
    out = image.copy()
    if off_resonance_hz is not None and off_resonance_hz.shape == image.shape:
        # Suppression fails only where off-resonance is worst (air interfaces);
        # use a percentile threshold so it's robust to the field's absolute scale.
        a = np.abs(off_resonance_hz)
        ref = a[fat] if int(fat.sum()) > 10 else a
        lo = float(np.percentile(ref, 85))
        hi = float(np.percentile(ref, 97))
        fail = np.clip((a - lo) / max(hi - lo, 1.0), 0.0, 1.0)
        factor = residual + (1.0 - residual) * fail
        out[fat] = image[fat] * factor[fat]
    else:
        out[fat] = image[fat] * residual
    return out


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


_GFACTOR_CACHE: dict[tuple, float] = {}


def g_factor(acceleration: int, n_coils: int = 8) -> float:
    """Representative SENSE g-factor for an R-fold accelerated acquisition.

    Builds a head-coil sensitivity array and evaluates the Pruessmann
    voxel-wise g-factor map (coil.g_factor_map), then returns the **median**
    over the FOV. The median is used instead of the mean because near-singular
    peripheral voxels send the mean (and max) to extreme values that don't
    reflect the typical noise amplification over the anatomy.

    The g-factor depends on coil geometry and R, not image resolution, so it is
    evaluated on a fixed 96×96 grid (divisible by R∈{2,3,4}) and cached.
    Returns 1.0 for R ≤ 1 (no acceleration penalty).
    """
    R = int(acceleration)
    if R <= 1:
        return 1.0
    key = (R, int(n_coils))
    if key not in _GFACTOR_CACHE:
        n = (96 // R) * R                      # square grid divisible by R
        sens = coil.head_coil_array((n, n), n_coils=n_coils)
        g = coil.g_factor_map(sens, R)
        _GFACTOR_CACHE[key] = float(np.median(g))
    return _GFACTOR_CACHE[key]


def partial_volume(image: np.ndarray, phantom_slice: np.ndarray,
                   sigma_vox: float) -> np.ndarray:
    """In-plane partial-volume mixing via pv tissue-fraction maps.

    Boundary voxels become fraction-weighted blends of the adjacent tissues'
    signals (pv.tissue_fraction_maps + pv.pv_signal_linear), modelling the finite
    voxel PSF. Pure interiors keep their rendered texture: the fraction mix is
    blended in by (1 − max tissue fraction), which is ~0 inside a tissue and
    rises only at boundaries. sigma_vox ≤ 0 (or a shape mismatch) is a no-op.
    """
    if sigma_vox <= 0 or phantom_slice.shape != image.shape:
        return image
    fracs = pv.tissue_fraction_maps(phantom_slice, sigma_vox)
    means = {lab: (float(image[phantom_slice == lab].mean())
                   if np.any(phantom_slice == lab) else 0.0)
             for lab in fracs}
    mixed = pv.pv_signal_linear(fracs, means)
    max_frac = np.maximum.reduce(list(fracs.values()))
    w = np.clip(1.0 - max_frac, 0.0, 1.0)        # 0 in pure interiors, >0 at edges
    return image * (1.0 - w) + mixed * w


def gre_fw_phase_label(TE_ms: float, B0: float) -> str:
    """Short label describing the current fat-water phase (for metrics display)."""
    phi     = 2.0 * np.pi * dixon.fat_water_shift_hz(B0) * TE_ms / 1000.0
    cos_phi = float(np.cos(phi))
    if cos_phi > 0.70:
        return "In-phase"
    if cos_phi < -0.70:
        return "Opposed"
    return f"Partial ({np.degrees(phi) % 360:.0f}°)"


def scale_to_peak(field: np.ndarray, peak_hz: float) -> np.ndarray:
    """Rescale a B0 field (Hz) so its 95th-percentile magnitude equals peak_hz.

    Preserves the spatial pattern (e.g. a dipole field from b0.susceptibility_b0_map)
    while letting a single control set the off-resonance magnitude. Returns zeros
    if peak_hz ≤ 0 or the field is essentially flat. The 95th percentile (rather
    than the max) avoids a single hot voxel dominating the scale.
    """
    field = np.asarray(field, dtype=float)
    if peak_hz <= 0:
        return np.zeros_like(field)
    ref = float(np.percentile(np.abs(field), 95))
    if ref < 1e-9:
        return np.zeros_like(field)
    return field * (float(peak_hz) / ref)


def epi_b0_field(shape: tuple[int, int], strength_hz: float) -> np.ndarray:
    """Synthetic off-resonance B0 map (Hz) — fallback when the real dipole-field
    slice (b0.susceptibility_b0_map) is unavailable (e.g. oblique geometry).

    A localised frontal off-resonance region (sinus-like) plus a mild
    through-FOV gradient, scaled so the peak magnitude ≈ strength_hz.
    """
    H, W = shape
    y, x = np.ogrid[:H, :W]
    cy, cx = H * 0.72, W * 0.5
    r2 = ((y - cy) / (H * 0.22)) ** 2 + ((x - cx) / (W * 0.28)) ** 2
    blob = np.exp(-r2)
    grad = (y / max(H - 1, 1)) - 0.5
    return (float(strength_hz) * (blob + 0.2 * grad)).astype(float)


def simulate_epi_slice(image: np.ndarray, t2star_map: np.ndarray,
                       b0_map: np.ndarray, esp_ms: float,
                       ghost_phase: float, correct_ghost: bool) -> np.ndarray:
    """Apply EPI readout artifacts to a rendered image (image-space in/out).

    Two effects, both from the long single-shot echo train:
      * T2* blur along the phase-encode direction (epi.epi_t2star_decay), and
      * the EPI acquisition itself (epi.simulate_epi): B0-driven geometric
        distortion in the phase-encode direction and a Nyquist (N/2) ghost from
        even/odd line phase errors, with optional phase correction.

    Returns the magnitude image. The phase-encode direction is the row axis.
    """
    n_phase = image.shape[0]
    blurred = epi.epi_t2star_decay(image, t2star_map, esp_ms, n_phase)
    # Pass None (not a zero array) when there is no off-resonance, so simulate_epi
    # uses the exact reorder→recon path instead of its per-line B0 approximation.
    b0_arg = b0_map if (b0_map is not None and np.any(np.abs(b0_map) > 1e-9)) else None
    recon, _ = epi.simulate_epi(blurred, b0_slice_hz=b0_arg, esp_ms=esp_ms,
                                phase_offset_rad=ghost_phase,
                                correct_ghost=correct_ghost)
    return np.abs(recon)
