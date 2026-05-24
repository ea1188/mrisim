"""B1+ transmit field inhomogeneity simulation.

At 3T and above, the RF wavelength (~12 cm in tissue) is comparable to the
FOV, producing spatially varying flip angles.  This module models B1+ maps,
their effect on SE/GRE/IR signal, and flip-angle mapping sequences.
"""

import numpy as np
from signal_engine import spin_echo_signal, gradient_echo_signal, inversion_recovery_signal


# ---------------------------------------------------------------------------
# B1+ map generators
# ---------------------------------------------------------------------------

def gaussian_b1_map(shape: tuple[int, int],
                    voxel_size: tuple[float, float] = (1., 1.),
                    center: tuple[float, float] | None = None,
                    nominal: float = 1.0, variation: float = 0.3,
                    fwhm_mm: float = 150.) -> np.ndarray:
    """Smooth Gaussian B1+ map modelling centre-brightening at 3T.

    The transmit field is brighter at the isocentre and falls off toward
    the periphery.  Returns a relative map (1.0 = nominal flip angle).

    Parameters
    ----------
    shape : (rows, cols)
    voxel_size : (row_mm, col_mm)
    center : physical centre of the bright region in mm; defaults to FOV centre
    nominal : float  mean field value (1.0 = perfect)
    variation : float  peak–trough variation as fraction of nominal
    fwhm_mm : float  full-width at half-maximum of the Gaussian

    Returns
    -------
    b1_map : (rows, cols) float64  relative B1+ (1.0 = nominal)
    """
    rows, cols = shape
    sy, sx = voxel_size
    sigma2 = (fwhm_mm / (2.0 * np.sqrt(2.0 * np.log(2.0))))**2

    y = (np.arange(rows) - (rows - 1) / 2.) * sy
    x = (np.arange(cols) - (cols - 1) / 2.) * sx
    Y, X = np.meshgrid(y, x, indexing="ij")

    if center is not None:
        cy, cx = center
    else:
        cy, cx = 0., 0.

    r2 = (Y - cy)**2 + (X - cx)**2
    # Centre-brightening: peak at centre, falls off to (nominal - variation)
    b1 = nominal + variation * np.exp(-r2 / (2. * sigma2)) - variation
    return b1.astype(np.float64)


def sinusoidal_b1_map(shape: tuple[int, int],
                       voxel_size: tuple[float, float] = (1., 1.),
                       period_mm: float = 200., axis: int = 1,
                       nominal: float = 1.0, amplitude: float = 0.2) -> np.ndarray:
    """Sinusoidal standing-wave B1+ pattern.

    Models the constructive/destructive interference pattern seen in large
    FOV body imaging at 3T.

    Parameters
    ----------
    shape : (rows, cols)
    voxel_size : (row_mm, col_mm)
    period_mm : float  spatial period of the modulation
    axis : 0 (row direction) or 1 (col direction)
    nominal : float  mean field value
    amplitude : float  peak-to-mean variation

    Returns
    -------
    b1_map : (rows, cols) float64
    """
    rows, cols = shape
    sy, sx = voxel_size

    if axis == 0:
        coords = (np.arange(rows) - (rows - 1) / 2.) * sy
        pattern = np.cos(2. * np.pi * coords / period_mm)
        b1 = nominal + amplitude * pattern[:, np.newaxis]
    else:
        coords = (np.arange(cols) - (cols - 1) / 2.) * sx
        pattern = np.cos(2. * np.pi * coords / period_mm)
        b1 = nominal + amplitude * pattern[np.newaxis, :]

    return np.broadcast_to(b1, shape).astype(np.float64).copy()


def uniform_b1_map(shape: tuple[int, int], value: float = 1.0) -> np.ndarray:
    """Uniform B1+ map — baseline / ideal transmitter."""
    return np.full(shape, float(value), dtype=np.float64)


# ---------------------------------------------------------------------------
# Effective flip angle
# ---------------------------------------------------------------------------

def effective_flip_angle(nominal_deg: float, b1_map: np.ndarray) -> np.ndarray:
    """Pointwise effective flip angle after B1+ scaling.

    Parameters
    ----------
    nominal_deg : float  prescribed flip angle in degrees
    b1_map : ndarray  relative B1+ map (1.0 = perfect)

    Returns
    -------
    alpha_eff : ndarray float64, same shape as b1_map, in degrees
    """
    return float(nominal_deg) * np.asarray(b1_map, dtype=float)


# ---------------------------------------------------------------------------
# Signal modulation
# ---------------------------------------------------------------------------

def apply_b1_to_gre(signal_image: np.ndarray, b1_map: np.ndarray,
                    nominal_deg: float, T1_map: np.ndarray, T2star_map: np.ndarray,
                    PD_map: np.ndarray, TR_ms: float, TE_ms: float) -> np.ndarray:
    """Re-compute GRE signal using effective (B1-corrected) flip angles.

    Parameters
    ----------
    signal_image : (rows, cols)  original GRE image (not used in recompute
        path, kept for API symmetry)
    b1_map : (rows, cols) relative B1+
    nominal_deg : float  prescribed flip angle
    T1_map, T2star_map, PD_map : (rows, cols) parameter maps
    TR_ms, TE_ms : float

    Returns
    -------
    corrected : (rows, cols) float64
    """
    alpha_eff = np.radians(effective_flip_angle(nominal_deg, b1_map))
    T1  = np.asarray(T1_map, dtype=float)
    T2s = np.asarray(T2star_map, dtype=float)
    PD  = np.asarray(PD_map, dtype=float)

    T1s  = np.where(T1  > 0, T1,  1.)
    T2ss = np.where(T2s > 0, T2s, 1.)

    E1 = np.exp(-TR_ms / T1s)
    denom = 1. - np.cos(alpha_eff) * E1
    with np.errstate(invalid="ignore", divide="ignore"):
        img = (PD * np.sin(alpha_eff) * (1. - E1)
               / np.where(np.abs(denom) > 1e-12, denom, 1e-12)
               * np.exp(-TE_ms / T2ss))
    return np.where(T1 > 0, img, 0.).astype(np.float64)


def apply_b1_to_se(signal_image: np.ndarray, b1_map: np.ndarray,
                   nominal_deg: float) -> np.ndarray:
    """Scale SE signal by sin(α_eff) / sin(α_nominal) approximation.

    For a perfectly-slice-selective 180° refocusing pulse the SE signal
    is proportional to sin(α_exc) × sin²(α_ref/2).  As a practical
    first-order correction this function scales by (B1)³ when
    both excitation and refocusing share the same B1 map.

    Parameters
    ----------
    signal_image : ndarray
    b1_map : ndarray  relative B1+
    nominal_deg : float  nominal excitation flip (typically 90°)

    Returns
    -------
    corrected : ndarray float64
    """
    b1 = np.asarray(b1_map, dtype=float)
    alpha_nom = np.radians(float(nominal_deg))
    alpha_eff = alpha_nom * b1
    alpha_ref = 2. * alpha_nom * b1    # refocusing nominally 2× excitation

    scale = (np.sin(alpha_eff) * np.sin(alpha_ref / 2.)**2
             / (np.sin(alpha_nom) * np.sin(alpha_nom)**2 + 1e-12))
    return np.asarray(signal_image, dtype=float) * scale


# ---------------------------------------------------------------------------
# B1 mapping sequences
# ---------------------------------------------------------------------------

def double_angle_b1_map(signal_alpha: np.ndarray,
                         signal_2alpha: np.ndarray) -> np.ndarray:
    """Estimate relative B1+ from the double-angle method (Insko 1993).

    B1_rel = arccos(S(2α) / (2 · S(α))) / α_nominal

    This cancels T1 and PD dependence when TR >> T1.

    Parameters
    ----------
    signal_alpha : ndarray  GRE image at flip angle α
    signal_2alpha : ndarray  GRE image at flip angle 2α

    Returns
    -------
    b1_rel : ndarray  relative B1+ map (1.0 = nominal)
    """
    s1 = np.asarray(signal_alpha,  dtype=float)
    s2 = np.asarray(signal_2alpha, dtype=float)
    with np.errstate(invalid="ignore", divide="ignore"):
        ratio = np.where(np.abs(s1) > 1e-12, s2 / (2. * s1), 1.)
    ratio = np.clip(ratio, -1., 1.)
    return np.arccos(ratio) / (np.pi / 3.)   # α_nominal = 60° → π/3


def actual_flip_angle_b1_map(signal_tr1: np.ndarray, signal_tr2: np.ndarray,
                              TR1_ms: float, TR2_ms: float) -> np.ndarray:
    """Estimate B1+ via the AFI (Actual Flip Angle Imaging) method.

    Uses two interleaved acquisitions at the same flip angle but two TRs.
    B1_rel = arccos((n·r - 1)/(n - r)) / α_nominal  where r = S2/S1, n = TR2/TR1.

    Parameters
    ----------
    signal_tr1 : ndarray  image acquired at TR1
    signal_tr2 : ndarray  image acquired at TR2
    TR1_ms, TR2_ms : float

    Returns
    -------
    b1_rel : ndarray  relative B1+ map
    """
    s1 = np.asarray(signal_tr1, dtype=float)
    s2 = np.asarray(signal_tr2, dtype=float)
    n  = float(TR2_ms) / float(TR1_ms)
    with np.errstate(invalid="ignore", divide="ignore"):
        r = np.where(np.abs(s1) > 1e-12, s2 / s1, 1.)
    with np.errstate(invalid="ignore"):
        cos_alpha = np.clip((n * r - 1.) / np.where(np.abs(n - r) > 1e-12,
                                                      n - r, 1e-12), -1., 1.)
    alpha_eff_rad = np.arccos(cos_alpha)
    nominal_rad = np.radians(60.)   # standard AFI uses 60° nominal
    return alpha_eff_rad / nominal_rad


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

def b1_uniformity(b1_map: np.ndarray,
                  mask: np.ndarray | None = None) -> float:
    """Transmit field uniformity metric: std / mean over the masked region.

    Lower is better; 0 = perfectly uniform.

    Parameters
    ----------
    b1_map : ndarray
    mask : bool array or None  (None → all pixels)

    Returns
    -------
    cv : float  coefficient of variation
    """
    b1 = np.asarray(b1_map, dtype=float)
    region = b1[mask] if mask is not None else b1.ravel()
    m = region.mean()
    if m < 1e-12:
        return 0.
    return float(region.std() / m)
