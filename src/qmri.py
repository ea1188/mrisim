"""Quantitative MRI: parameter mapping and synthetic contrast generation."""

import numpy as np
from scipy.optimize import curve_fit
from signal_engine import (
    spin_echo_signal,
    gradient_echo_signal,
    inversion_recovery_signal,
)

try:
    from phantom3d import TISSUE_PROPERTIES_3D as _DEFAULT_PROPS
except ImportError:
    _DEFAULT_PROPS = {}

_T1_MIN_MS = 10.0
_T1_MAX_MS = 10000.0
_T2_MAX_MS = 5000.0


def _get_props(tissue_props):
    return tissue_props if tissue_props is not None else _DEFAULT_PROPS


def _render_label_map(label_map, signal_fn, tissue_props):
    """Apply signal_fn(props_dict) per label, return float image."""
    out = np.zeros(label_map.shape, dtype=np.float64)
    for lab, p in _get_props(tissue_props).items():
        mask = label_map == lab
        if mask.any():
            out[mask] = signal_fn(p)
    return out


# ---------------------------------------------------------------------------
# Simulation helpers  (label map → signal series)
# ---------------------------------------------------------------------------

def simulate_vfa_series(label_map, flip_angles_deg, TR_ms, TE_ms=5.0,
                        tissue_props=None):
    """GRE images at multiple flip angles for VFA T1 mapping.

    Parameters
    ----------
    label_map : 2-D int array
    flip_angles_deg : sequence of float
    TR_ms, TE_ms : float

    Returns
    -------
    series : (n_angles, H, W) float64
    """
    return np.stack(
        [_render_label_map(
            label_map,
            lambda p, a=a: gradient_echo_signal(
                p["T1"], p.get("T2star", p["T2"]), p["PD"], TR_ms, TE_ms, a),
            tissue_props,
        ) for a in flip_angles_deg],
        axis=0,
    )


def simulate_ir_series(label_map, TI_ms_list, TR_ms=3000., TE_ms=10.,
                       tissue_props=None):
    """IR magnitude images at multiple inversion times.

    Returns
    -------
    series : (n_TI, H, W) float64
    """
    return np.stack(
        [_render_label_map(
            label_map,
            lambda p, ti=ti: inversion_recovery_signal(
                p["T1"], p["T2"], p["PD"], TR_ms, TE_ms, ti),
            tissue_props,
        ) for ti in TI_ms_list],
        axis=0,
    )


def simulate_multi_echo_series(label_map, TE_ms_list, TR_ms=2000.,
                               flip_angle_deg=90., sequence="SE",
                               tissue_props=None):
    """Multi-echo images for T2 (SE) or T2* (GRE) mapping.

    Returns
    -------
    series : (n_TE, H, W) float64
    """
    seq = sequence.upper()
    frames = []
    for te in TE_ms_list:
        if seq == "SE":
            fn = lambda p, te=te: spin_echo_signal(
                p["T1"], p["T2"], p["PD"], TR_ms, te)
        else:
            fn = lambda p, te=te: gradient_echo_signal(
                p["T1"], p.get("T2star", p["T2"]), p["PD"],
                TR_ms, te, flip_angle_deg)
        frames.append(_render_label_map(label_map, fn, tissue_props))
    return np.stack(frames, axis=0)


# ---------------------------------------------------------------------------
# Quantitative maps  (signal series → parameter maps)
# ---------------------------------------------------------------------------

def vfa_t1_map(signal_series, flip_angles_deg, TR_ms):
    """T1 map from a VFA GRE series via the Fram linearisation.

    Uses S/sin(α) = E1 · S/tan(α) + S0·(1−E1) — fully vectorised
    closed-form least squares with no per-pixel loop.

    Parameters
    ----------
    signal_series : (n_angles, H, W) float
    flip_angles_deg : sequence of float, length n_angles
    TR_ms : float

    Returns
    -------
    T1_ms : (H, W) float64, clipped to [10, 10 000] ms
    """
    alpha = np.radians(np.asarray(flip_angles_deg, dtype=float))
    eps = 1e-12
    sin_a = np.sin(alpha)[:, None, None]
    tan_a = np.tan(alpha)[:, None, None]

    y = signal_series / np.where(np.abs(sin_a) > eps, sin_a, eps)
    x = signal_series / np.where(np.abs(tan_a) > eps, tan_a, eps)

    n = len(flip_angles_deg)
    Sx  = x.sum(axis=0)
    Sy  = y.sum(axis=0)
    Sxx = (x * x).sum(axis=0)
    Sxy = (x * y).sum(axis=0)
    denom = n * Sxx - Sx**2

    with np.errstate(invalid="ignore", divide="ignore"):
        raw_E1 = (n * Sxy - Sx * Sy) / denom
    E1 = np.where(np.abs(denom) > eps, raw_E1, np.exp(-TR_ms / 1000.))
    E1 = np.clip(E1, 1e-10, 1.0 - 1e-10)
    T1 = -TR_ms / np.log(E1)
    return np.clip(T1, _T1_MIN_MS, _T1_MAX_MS)


def multi_echo_t2_map(signal_series, TE_ms_list):
    """T2 map from a multi-echo SE series via log-linear regression.

    ln S(TE) = ln S0 − TE / T2

    Parameters
    ----------
    signal_series : (n_TE, H, W) float
    TE_ms_list : sequence of float

    Returns
    -------
    T2_ms : (H, W) float64, 0 where signal is absent
    """
    TE = np.asarray(TE_ms_list, dtype=float)
    n_te = len(TE)
    H, W = signal_series.shape[1:]

    log_s = np.log(np.maximum(signal_series, 1e-12))   # (n_TE, H, W)
    A = np.column_stack([np.ones(n_te), TE])            # (n_TE, 2)
    b = log_s.reshape(n_te, -1)                         # (n_TE, N)
    result, _, _, _ = np.linalg.lstsq(A, b, rcond=None) # (2, N)

    inv_T2 = -result[1].reshape(H, W)                   # 1/T2  (ms⁻¹)
    T2 = np.where(inv_T2 > 1e-10,
                  1.0 / np.maximum(inv_T2, 1.0 / _T2_MAX_MS),
                  0.0)
    return np.clip(T2, 0., _T2_MAX_MS)


def t2star_map(signal_series, TE_ms_list):
    """T2* map from a multi-echo GRE series.

    Identical fitting algorithm to multi_echo_t2_map; named separately
    to document the GRE / T2* use case.
    """
    return multi_echo_t2_map(signal_series, TE_ms_list)


def ir_t1_map(signal_series, TI_ms_list, TR_ms=3000.):
    """T1 map from an inversion recovery magnitude series.

    Fits S(TI) = S0 · |1 − 2·exp(−TI/T1) + exp(−TR/T1)| pixelwise via
    scipy.optimize.curve_fit.  O(n_pixels) — suitable for 2-D slices.

    Parameters
    ----------
    signal_series : (n_TI, H, W) float, magnitude
    TI_ms_list : sequence of float
    TR_ms : float

    Returns
    -------
    T1_ms : (H, W) float64, 0 for background pixels
    """
    TI = np.asarray(TI_ms_list, dtype=float)
    n_ti = len(TI)
    H, W = signal_series.shape[1:]
    T1_map = np.zeros((H, W), dtype=np.float64)

    def _model(ti, T1, S0):
        return S0 * np.abs(1.0 - 2.0 * np.exp(-ti / T1)
                           + np.exp(-TR_ms / T1))

    flat = signal_series.reshape(n_ti, -1)
    for idx in range(flat.shape[1]):
        s = flat[:, idx]
        if s.max() < 1e-10:
            continue
        try:
            popt, _ = curve_fit(
                _model, TI, s,
                p0=[1000., s.max()],
                bounds=([_T1_MIN_MS, 0.], [_T1_MAX_MS, np.inf]),
                maxfev=400,
            )
            T1_map.flat[idx] = popt[0]
        except Exception:
            pass

    return T1_map


# ---------------------------------------------------------------------------
# Synthetic MRI
# ---------------------------------------------------------------------------

def synthetic_contrast(t1_map, t2_map, pd_map, TR_ms, TE_ms,
                       sequence="SE", TI_ms=None, flip_angle_deg=90.):
    """Synthesise any MR contrast from quantitative parameter maps.

    Parameters
    ----------
    t1_map, t2_map, pd_map : 2-D ndarray  (ms, ms, a.u.)
    TR_ms, TE_ms : float
    sequence : "SE" | "GRE" | "IR"
    TI_ms : float, required for "IR"
    flip_angle_deg : float, used for "GRE"

    Returns
    -------
    image : ndarray float64, same shape; 0 where T1 == 0
    """
    T1 = np.asarray(t1_map, dtype=float)
    T2 = np.asarray(t2_map, dtype=float)
    PD = np.asarray(pd_map, dtype=float)

    T1s = np.where(T1 > 0, T1, 1.0)   # avoid ÷0 in background
    T2s = np.where(T2 > 0, T2, 1.0)
    seq = sequence.upper()

    if seq == "SE":
        img = PD * (1.0 - np.exp(-TR_ms / T1s)) * np.exp(-TE_ms / T2s)
    elif seq == "GRE":
        alpha = np.radians(float(flip_angle_deg))
        E1 = np.exp(-TR_ms / T1s)
        denom = 1.0 - np.cos(alpha) * E1
        img = (PD * np.sin(alpha) * (1.0 - E1)
               / np.where(np.abs(denom) > 1e-12, denom, 1e-12)
               * np.exp(-TE_ms / T2s))
    elif seq == "IR":
        if TI_ms is None:
            raise ValueError("TI_ms is required for sequence='IR'")
        img = (PD
               * np.abs(1.0 - 2.0 * np.exp(-TI_ms / T1s)
                        + np.exp(-TR_ms / T1s))
               * np.exp(-TE_ms / T2s))
    else:
        raise ValueError(
            f"Unknown sequence {sequence!r}. Choose 'SE', 'GRE', or 'IR'.")

    return np.where(T1 > 0, img, 0.0)
