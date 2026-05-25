"""Dixon fat-water separation, STIR fat suppression, and chemical shift.

Fat protons (-CH2-) resonate 3.5 ppm downfield from water.  At a given B0
the resulting frequency offset drives a sinusoidal phase difference between
fat and water signals as TE increases.  This module provides:

  • In-phase / opposed-phase GRE signal simulation
  • Two-point and three-point (B0-corrected) Dixon separation
  • STIR fat suppression
  • Chemical shift pixel displacement
"""

import numpy as np
from signal_engine import gradient_echo_signal, inversion_recovery_signal

try:
    from phantom3d import TISSUE_PROPERTIES_3D as _DEFAULT_PROPS
except ImportError:
    _DEFAULT_PROPS = {}

GAMMA_HZ_T  = 42.577e6   # proton gyromagnetic ratio / 2π  (Hz/T)
FAT_CS_PPM  = 3.5         # fat–water chemical shift (ppm)
FAT_LABELS  = frozenset({4, 19})   # labels treated as fat in the MR signal model


# ---------------------------------------------------------------------------
# Chemical shift frequency
# ---------------------------------------------------------------------------

def fat_water_shift_hz(field_strength_T: float) -> float:
    """Fat–water frequency offset Δf = 3.5 ppm × γ × B0  (Hz)."""
    return FAT_CS_PPM * 1e-6 * GAMMA_HZ_T * float(field_strength_T)


def inphase_te_ms(field_strength_T: float, n: int = 1) -> float:
    """n-th in-phase echo time in ms  (fat and water phases coincide).

    TE_ip = n / Δf  (n = 1, 2, 3, …)
    """
    return float(n) * 1000.0 / fat_water_shift_hz(field_strength_T)


def opposed_phase_te_ms(field_strength_T: float, n: int = 1) -> float:
    """n-th opposed-phase echo time in ms  (fat and water 180° apart).

    TE_op = (2n−1) / (2·Δf)  (n = 1, 2, 3, …)
    """
    return (2.0 * float(n) - 1.0) * 500.0 / fat_water_shift_hz(field_strength_T)


# ---------------------------------------------------------------------------
# Complex signal model
# ---------------------------------------------------------------------------

def combined_gre_signal(water_image: np.ndarray, fat_image: np.ndarray,
                         field_strength_T: float, TE_ms: float) -> np.ndarray:
    """Complex GRE voxel signal combining water and fat with CS phase.

    S(TE) = S_water + S_fat · exp(i · 2π · Δf · TE)

    Parameters
    ----------
    water_image : ndarray  real water-component signal
    fat_image   : ndarray  real fat-component signal (same shape)
    field_strength_T : float
    TE_ms : float

    Returns
    -------
    signal : ndarray complex128, same shape
    """
    df = fat_water_shift_hz(field_strength_T)
    fat_phase = 2.0 * np.pi * df * TE_ms * 1e-3
    return np.asarray(water_image, dtype=float) + np.asarray(fat_image, dtype=float) * np.exp(1j * fat_phase)


# ---------------------------------------------------------------------------
# Simulation helpers
# ---------------------------------------------------------------------------

def _get_props(tissue_props: dict | None) -> dict:
    return tissue_props if tissue_props is not None else _DEFAULT_PROPS


def _water_gre(label_map: np.ndarray, TR_ms: float, TE_ms: float,
               flip_angle_deg: float, tissue_props: dict | None,
               fat_labels: frozenset[int]) -> np.ndarray:
    """GRE signal from water-only labels (fat labels excluded)."""
    out = np.zeros(label_map.shape, dtype=np.float64)
    for lab, p in _get_props(tissue_props).items():
        if lab in fat_labels:
            continue
        mask = label_map == lab
        if mask.any():
            out[mask] = gradient_echo_signal(
                p["T1"], p.get("T2star", p["T2"]), p["PD"],
                TR_ms, TE_ms, flip_angle_deg)
    return out


def _fat_gre(label_map: np.ndarray, TR_ms: float, TE_ms: float,
             flip_angle_deg: float, tissue_props: dict | None,
             fat_labels: frozenset[int]) -> np.ndarray:
    """GRE signal from fat-only labels."""
    out = np.zeros(label_map.shape, dtype=np.float64)
    for lab, p in _get_props(tissue_props).items():
        if lab not in fat_labels:
            continue
        mask = label_map == lab
        if mask.any():
            out[mask] = gradient_echo_signal(
                p["T1"], p.get("T2star", p["T2"]), p["PD"],
                TR_ms, TE_ms, flip_angle_deg)
    return out


def simulate_inphase(label_map: np.ndarray, field_strength_T: float = 1.5,
                      TR_ms: float = 200., flip_angle_deg: float = 70.,
                      echo_n: int = 1, tissue_props: dict | None = None,
                      fat_labels: frozenset[int] | None = None) -> np.ndarray:
    """GRE magnitude image at an in-phase echo time.

    Fat and water signals add constructively: |S_water + S_fat|.

    Parameters
    ----------
    label_map : 2-D int array
    field_strength_T : float
    TR_ms, flip_angle_deg : float
    echo_n : int  selects the n-th in-phase TE (default 1)
    tissue_props, fat_labels : optional overrides

    Returns
    -------
    image : ndarray float64
    """
    fl  = fat_labels if fat_labels is not None else FAT_LABELS
    te  = inphase_te_ms(field_strength_T, echo_n)
    sw  = _water_gre(label_map, TR_ms, te, flip_angle_deg, tissue_props, fl)
    sf  = _fat_gre(label_map, TR_ms, te, flip_angle_deg, tissue_props, fl)
    return np.abs(combined_gre_signal(sw, sf, field_strength_T, te))


def simulate_opposed(label_map: np.ndarray, field_strength_T: float = 1.5,
                      TR_ms: float = 200., flip_angle_deg: float = 70.,
                      echo_n: int = 1, tissue_props: dict | None = None,
                      fat_labels: frozenset[int] | None = None) -> np.ndarray:
    """GRE magnitude image at an opposed-phase echo time.

    Fat and water signals cancel: |S_water − S_fat|.

    Returns
    -------
    image : ndarray float64
    """
    fl  = fat_labels if fat_labels is not None else FAT_LABELS
    te  = opposed_phase_te_ms(field_strength_T, echo_n)
    sw  = _water_gre(label_map, TR_ms, te, flip_angle_deg, tissue_props, fl)
    sf  = _fat_gre(label_map, TR_ms, te, flip_angle_deg, tissue_props, fl)
    return np.abs(combined_gre_signal(sw, sf, field_strength_T, te))


# ---------------------------------------------------------------------------
# Dixon separation
# ---------------------------------------------------------------------------

def two_point_dixon(inphase: np.ndarray,
                    opposed: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Fat–water separation from in-phase and opposed-phase magnitude images.

    Assumes S_ip = W + F and S_op = |W − F|.
    Valid when both W ≥ 0 and F ≥ 0 and W ≥ F (water dominant).

        W = (S_ip + S_op) / 2
        F = (S_ip − S_op) / 2

    Parameters
    ----------
    inphase  : ndarray  in-phase magnitude image
    opposed  : ndarray  opposed-phase magnitude image (same shape)

    Returns
    -------
    water, fat : ndarray pair, non-negative
    """
    ip = np.asarray(inphase,  dtype=float)
    op = np.asarray(opposed,  dtype=float)
    water = (ip + op) / 2.0
    fat   = np.maximum((ip - op) / 2.0, 0.0)
    return water, fat


def three_point_dixon(s_ip1: np.ndarray, s_op: np.ndarray,
                      s_ip2: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Fat–water separation from three complex GRE echoes with B0 correction.

    Echoes acquired at TE1 (in-phase), TE2 (opposed), TE3 (in-phase) so that
    the B0-driven phase accumulates linearly: φ, 0, −φ relative to TE2.

    Algorithm (Glover 1991, simplified):
      1. Estimate B0 phase from the ratio of the two in-phase echoes.
      2. Remove B0 phase from all echoes.
      3. Recover W and F from the corrected in-phase and opposed signals.

    Parameters
    ----------
    s_ip1 : ndarray complex  first in-phase echo
    s_op  : ndarray complex  opposed-phase echo
    s_ip2 : ndarray complex  second in-phase echo

    Returns
    -------
    water, fat : ndarray float64, non-negative
    """
    s1 = np.asarray(s_ip1, dtype=complex)
    sm = np.asarray(s_op,  dtype=complex)
    s2 = np.asarray(s_ip2, dtype=complex)

    # B0 phase between the two in-phase echoes: e^(i·2φ) = s2 / s1
    with np.errstate(invalid="ignore", divide="ignore"):
        ratio = np.where(np.abs(s1) > 1e-12, s2 / s1, 1. + 0j)
    phi = np.angle(ratio) / 2.0   # B0 phase increment from TE1 to midpoint echo

    # B0 phase at TE1; midpoint (opposed) echo phase = phi_1 + phi
    phi_1 = np.angle(s1)

    WpF = np.real(s1 * np.exp(-1j * phi_1))           # W + F
    WmF = np.real(sm * np.exp(-1j * (phi_1 + phi)))   # W − F

    water = np.maximum((WpF + WmF) / 2.0, 0.0)
    fat   = np.maximum((WpF - WmF) / 2.0, 0.0)
    return water, fat


def fat_fraction(fat_image: np.ndarray, water_image: np.ndarray) -> np.ndarray:
    """Fat fraction map: |F| / (|F| + |W|), clipped to [0, 1].

    Parameters
    ----------
    fat_image, water_image : ndarray  (any shape)

    Returns
    -------
    ff : ndarray float64, values in [0, 1]
    """
    f = np.abs(np.asarray(fat_image,   dtype=float))
    w = np.abs(np.asarray(water_image, dtype=float))
    total = f + w
    with np.errstate(invalid="ignore", divide="ignore"):
        ratio = f / total
    return np.where(total > 1e-12, ratio, 0.0)


# ---------------------------------------------------------------------------
# STIR fat suppression
# ---------------------------------------------------------------------------

def stir_ti_optimal(T1_fat_ms: float) -> float:
    """Inversion time that nulls fat signal: TI = T1_fat · ln 2."""
    return float(T1_fat_ms) * np.log(2.0)


def simulate_stir(label_map: np.ndarray, TR_ms: float = 4000.,
                  TE_ms: float = 30., TI_ms: float | None = None,
                  tissue_props: dict | None = None) -> np.ndarray:
    """STIR image: IR acquisition with TI chosen to null fat.

    If TI_ms is None, uses stir_ti_optimal for the T1 of label 4 (fat).

    Returns
    -------
    image : ndarray float64  (magnitude)
    """
    props = _get_props(tissue_props)

    if TI_ms is None:
        T1_fat = props.get(4, {}).get("T1", 370.)
        TI_ms = stir_ti_optimal(T1_fat)

    out = np.zeros(label_map.shape, dtype=np.float64)
    for lab, p in props.items():
        mask = label_map == lab
        if mask.any():
            out[mask] = inversion_recovery_signal(
                p["T1"], p["T2"], p["PD"], TR_ms, TE_ms, TI_ms)
    return out


# ---------------------------------------------------------------------------
# Chemical shift displacement
# ---------------------------------------------------------------------------

def chemical_shift_pixels(field_strength_T: float, bw_hz_per_pixel: float) -> float:
    """Fat pixel displacement in the frequency-encode direction.

    shift = Δf / BW_per_pixel  (pixels)

    Parameters
    ----------
    field_strength_T : float
    bw_hz_per_pixel : float  receiver bandwidth per pixel (Hz)

    Returns
    -------
    shift : float  positive = shift toward higher frequency
    """
    return fat_water_shift_hz(field_strength_T) / float(bw_hz_per_pixel)
