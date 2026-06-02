"""Partial Volume Effects (PVE) simulation.

When a voxel spans a tissue boundary its measured signal is a weighted
average of the signals from each contributing tissue.  Two complementary
models are provided:

  1. Gaussian PSF model — smooths binary tissue masks to produce
     continuously-varying tissue fraction maps, then applies linear
     signal mixing.  Models in-plane blurring due to the voxel PSF.

  2. Through-plane slab averaging — integrates signal across multiple
     thin slabs with a rect or Gaussian slice-selection profile.
     Models the dominant PVE source in 2-D multi-slice acquisitions.
"""

import numpy as np
from scipy.ndimage import gaussian_filter, binary_dilation
from signal_engine import (
    spin_echo_signal,
    gradient_echo_signal,
    inversion_recovery_signal,
)

try:
    from phantom3d import TISSUE_PROPERTIES_3D as _DEFAULT_TISSUE
except ImportError:
    _DEFAULT_TISSUE = {}


def _get_tissue(tissue_props: dict | None) -> dict:
    return tissue_props if tissue_props is not None else _DEFAULT_TISSUE


def _signal_per_label(tissue_props: dict, TR_ms: float, TE_ms: float,
                       sequence: str, TI_ms: float | None,
                       flip_angle_deg: float) -> dict[int, float]:
    """Return {label: pure-tissue signal} for the given scan parameters."""
    seq = sequence.upper()
    result: dict[int, float] = {}
    for lab, p in tissue_props.items():
        if seq == "SE":
            result[lab] = spin_echo_signal(
                p["T1"], p["T2"], p["PD"], TR_ms, TE_ms)
        elif seq == "GRE":
            result[lab] = gradient_echo_signal(
                p["T1"], p.get("T2star", p["T2"]), p["PD"],
                TR_ms, TE_ms, flip_angle_deg)
        elif seq == "IR":
            result[lab] = inversion_recovery_signal(
                p["T1"], p["T2"], p["PD"], TR_ms, TE_ms,
                TI_ms if TI_ms is not None else 500.)
        else:
            raise ValueError(f"Unknown sequence {sequence!r}")
    return result


# ---------------------------------------------------------------------------
# Tissue fraction maps
# ---------------------------------------------------------------------------

def tissue_fraction_maps(label_map: np.ndarray,
                          smooth_sigma_vox: float = 1.0) -> dict[int, np.ndarray]:
    """Gaussian-PSF tissue fraction maps from a hard-label map.

    Each binary tissue mask is convolved with a Gaussian of width
    ``smooth_sigma_vox`` (voxels) to simulate the finite voxel PSF.
    Fractions are normalised to sum to 1 at every pixel.

    Parameters
    ----------
    label_map : ndarray int  (any shape)
    smooth_sigma_vox : float  Gaussian σ in voxels (0 = hard labels)

    Returns
    -------
    fractions : dict {label: ndarray float64}
        Values ∈ [0, 1], sum to 1 at every location.
    """
    labels = np.unique(label_map)
    if smooth_sigma_vox <= 0:
        return {lab: (label_map == lab).astype(np.float64) for lab in labels}

    raw = {lab: gaussian_filter((label_map == lab).astype(float),
                                 sigma=smooth_sigma_vox)
           for lab in labels}
    total = sum(raw.values())
    safe  = np.where(total > 1e-12, total, 1.0)
    return {lab: v / safe for lab, v in raw.items()}


# ---------------------------------------------------------------------------
# Linear signal mixing
# ---------------------------------------------------------------------------

def pv_signal_linear(fractions: dict[int, np.ndarray],
                     signal_per_label: dict[int, float]) -> np.ndarray:
    """Linear partial-volume signal:  S_pv = Σ_i  f_i · S_i.

    Parameters
    ----------
    fractions : dict {label: ndarray}  tissue fraction maps
    signal_per_label : dict {label: float}  pure-tissue signals

    Returns
    -------
    signal : ndarray float64, same shape as the fraction arrays
    """
    first = next(iter(fractions.values()))
    out = np.zeros(first.shape, dtype=np.float64)
    for lab, frac in fractions.items():
        out += frac * float(signal_per_label.get(lab, 0.))
    return out


# ---------------------------------------------------------------------------
# In-plane PVE simulation
# ---------------------------------------------------------------------------

def simulate_pv_slice(label_map: np.ndarray, TR_ms: float = 500.,
                       TE_ms: float = 15., sequence: str = "SE",
                       smooth_sigma_vox: float = 1.0,
                       TI_ms: float | None = None, flip_angle_deg: float = 90.,
                       tissue_props: dict | None = None) -> np.ndarray:
    """Simulate a 2-D slice with in-plane Gaussian PSF partial-volume effects.

    Parameters
    ----------
    label_map : 2-D int array
    TR_ms, TE_ms : float
    sequence : "SE" | "GRE" | "IR"
    smooth_sigma_vox : float  Gaussian σ (voxels); 0 = no PVE
    TI_ms : float or None  inversion time, for "IR"
    flip_angle_deg : float  for "GRE"
    tissue_props : dict or None

    Returns
    -------
    image : ndarray float64, same shape as label_map
    """
    props    = _get_tissue(tissue_props)
    fracs    = tissue_fraction_maps(label_map, smooth_sigma_vox)
    sig_dict = _signal_per_label(props, TR_ms, TE_ms, sequence, TI_ms, flip_angle_deg)
    return pv_signal_linear(fracs, sig_dict)


# ---------------------------------------------------------------------------
# Through-plane PVE simulation
# ---------------------------------------------------------------------------

def simulate_thick_slice(vol_3d: np.ndarray, center_z: int,
                          slice_thickness_vox: int = 5,
                          TR_ms: float = 500., TE_ms: float = 15.,
                          sequence: str = "SE", TI_ms: float | None = None,
                          flip_angle_deg: float = 90., slice_profile: str = "rect",
                          tissue_props: dict | None = None) -> np.ndarray:
    """2-D image with through-plane PVE from slab averaging.

    Averages the signal from ``slice_thickness_vox`` consecutive planes
    centred on ``center_z``, weighted by the chosen slice-selection profile.

    Parameters
    ----------
    vol_3d : (nz, ny, nx) int array  3-D label volume
    center_z : int  z-index of the slice centre
    slice_thickness_vox : int  number of z-planes to integrate
    TR_ms, TE_ms, sequence, TI_ms, flip_angle_deg : scan parameters
    slice_profile : "rect" | "gauss"
        "rect"  — uniform weights (hard slice boundary)
        "gauss" — Gaussian weights (σ = thickness / 2.35)
    tissue_props : dict or None

    Returns
    -------
    image : (ny, nx) float64
    """
    nz  = vol_3d.shape[0]
    half = slice_thickness_vox // 2
    z_indices = np.arange(center_z - half,
                           center_z - half + slice_thickness_vox)
    z_indices = np.clip(z_indices, 0, nz - 1)

    if slice_profile == "gauss":
        sigma   = slice_thickness_vox / (2.0 * np.sqrt(2.0 * np.log(2.0)))
        weights = np.exp(-0.5 * ((z_indices - center_z) / sigma)**2)
        weights = weights / weights.sum()
    else:
        weights = np.ones(len(z_indices)) / len(z_indices)

    props    = _get_tissue(tissue_props)
    sig_dict = _signal_per_label(props, TR_ms, TE_ms, sequence, TI_ms, flip_angle_deg)

    out = np.zeros(vol_3d.shape[1:], dtype=np.float64)
    for z, w in zip(z_indices, weights, strict=False):
        plane = vol_3d[int(z)]
        for lab, sig in sig_dict.items():
            out += w * (plane == lab).astype(float) * sig
    return out


# ---------------------------------------------------------------------------
# Boundary analysis
# ---------------------------------------------------------------------------

def boundary_mask(label_map: np.ndarray, label_a: int, label_b: int,
                  dilation_vox: int = 1) -> np.ndarray:
    """Voxels at the interface between two tissue labels.

    Returns a boolean mask of voxels that are within ``dilation_vox``
    of both label_a and label_b but are not purely either tissue.
    These are the voxels most affected by PVE.

    Parameters
    ----------
    label_map : ndarray int
    label_a, label_b : int
    dilation_vox : int  dilation radius in voxels

    Returns
    -------
    mask : bool array, same shape
    """
    struct  = np.ones((2 * dilation_vox + 1,) * label_map.ndim, dtype=bool)
    pure_a  = label_map == label_a
    pure_b  = label_map == label_b
    near_a  = binary_dilation(pure_a, structure=struct)
    near_b  = binary_dilation(pure_b, structure=struct)
    return near_a & near_b & ~pure_a & ~pure_b


def fraction_at_boundary(label_map: np.ndarray, label_a: int, label_b: int,
                           smooth_sigma_vox: float = 1.0,
                           dilation_vox: int = 1) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Tissue fractions of label_a and label_b at their shared boundary.

    Parameters
    ----------
    label_map : ndarray int
    label_a, label_b : int
    smooth_sigma_vox : float
    dilation_vox : int  boundary detection radius

    Returns
    -------
    f_a, f_b : ndarray float64  fraction maps for the two labels (full shape)
    bnd_mask : bool array  where the boundary was detected
    """
    fracs    = tissue_fraction_maps(label_map, smooth_sigma_vox)
    bnd      = boundary_mask(label_map, label_a, label_b, dilation_vox)
    f_a = fracs.get(label_a, np.zeros(label_map.shape))
    f_b = fracs.get(label_b, np.zeros(label_map.shape))
    return f_a, f_b, bnd


# ---------------------------------------------------------------------------
# PVE correction
# ---------------------------------------------------------------------------

def pv_correction(measured_signal: np.ndarray,
                   tissue_fractions: dict[int, np.ndarray],
                   signal_per_label: dict[int, float],
                   target_label: int) -> np.ndarray:
    """Remove partial-volume contamination from a measured signal.

    Solves:  S_target = (S_measured − Σ_{j≠target} f_j · S_j) / f_target

    Valid only where f_target > 0.  Returns measured_signal unchanged
    where f_target is negligible.

    Parameters
    ----------
    measured_signal : ndarray
    tissue_fractions : dict {label: ndarray}
    signal_per_label : dict {label: float}
    target_label : int

    Returns
    -------
    corrected : ndarray float64, same shape as measured_signal
    """
    f_t  = tissue_fractions.get(target_label,
                                  np.zeros_like(measured_signal, dtype=float))
    contamination = np.zeros_like(measured_signal, dtype=float)
    for lab, frac in tissue_fractions.items():
        if lab != target_label:
            contamination += frac * float(signal_per_label.get(lab, 0.))

    valid = f_t > 1e-6
    with np.errstate(divide="ignore", invalid="ignore"):
        corrected = np.where(valid,
                             (measured_signal - contamination) / np.where(valid, f_t, 1.),
                             measured_signal)
    return corrected.astype(np.float64)


# ---------------------------------------------------------------------------
# ROI statistics
# ---------------------------------------------------------------------------

def mean_signal_in_roi(signal_map: np.ndarray, label_map: np.ndarray,
                        label: int, fractions: dict | None = None,
                        min_fraction: float = 0.9) -> float:
    """Mean signal within a tissue ROI, with optional PV-weighting.

    Parameters
    ----------
    signal_map : ndarray  2-D or 3-D signal image
    label_map : ndarray int  same shape
    label : int
    fractions : dict or None
        If provided, includes only voxels where ``fractions[label] ≥
        min_fraction`` (high-purity voxels).
    min_fraction : float  purity threshold when fractions are supplied

    Returns
    -------
    mean : float  (0 if the ROI is empty)
    """
    if fractions is not None:
        f = fractions.get(label, np.zeros_like(signal_map))
        mask = f >= min_fraction
    else:
        mask = label_map == label

    if not mask.any():
        return 0.
    return float(signal_map[mask].mean())
