"""Magnetization Transfer (MT) simulation — two-pool binary spin-bath model.

A semi-solid macromolecular pool (pool B, very short T2) exchanges
magnetisation with the free water pool (pool A).  Off-resonance RF pulses
preferentially saturate pool B via its broad Gaussian lineshape; the
subsequent exchange reduces the observable free-pool signal.

Key references:
  Henkelman et al. (1993) MRM 29:759-766  — two-pool model
  Graham & Henkelman (1997) MRM 37:866-875 — pulsed MT
  Sled & Pike (2001) MRM 46:923-931
"""

import numpy as np
from signal_engine import spin_echo_signal, gradient_echo_signal, inversion_recovery_signal

try:
    from phantom3d import TISSUE_PROPERTIES_3D as _DEFAULT_TISSUE
except ImportError:
    _DEFAULT_TISSUE = {}

GAMMA_RAD_T = 2.0 * np.pi * 42.577e6   # rad s⁻¹ T⁻¹

# ---------------------------------------------------------------------------
# Bound-pool MT parameters per tissue label  (labels 0-21, nifti_region scheme)
# f    : bound pool fraction  M0B / (M0A + M0B)
# k_ab : free→bound exchange rate  (s⁻¹)
# T2b_us : bound pool T2  (μs) — determines lineshape width
# T1b_ms : bound pool T1  (ms) — typically long; often fixed at 1 s
# ---------------------------------------------------------------------------
MT_PARAMS = {
    0:  {"f": 0.000, "k_ab":  0.,  "T2b_us": 10., "T1b_ms": 1000., "name": "background"},
    1:  {"f": 0.005, "k_ab":  5.,  "T2b_us": 10., "T1b_ms": 1000., "name": "CSF"},
    2:  {"f": 0.100, "k_ab": 25.,  "T2b_us": 12., "T1b_ms": 1000., "name": "gray matter"},
    3:  {"f": 0.160, "k_ab": 45.,  "T2b_us": 12., "T1b_ms": 1000., "name": "white matter"},
    4:  {"f": 0.015, "k_ab":  5.,  "T2b_us": 15., "T1b_ms": 1000., "name": "fat"},
    5:  {"f": 0.040, "k_ab": 12.,  "T2b_us": 10., "T1b_ms": 1000., "name": "bone (skull)"},
    6:  {"f": 0.060, "k_ab": 18.,  "T2b_us": 12., "T1b_ms": 1000., "name": "muscle"},
    7:  {"f": 0.045, "k_ab": 14.,  "T2b_us": 12., "T1b_ms": 1000., "name": "liver"},
    8:  {"f": 0.040, "k_ab": 12.,  "T2b_us": 12., "T1b_ms": 1000., "name": "spleen"},
    9:  {"f": 0.040, "k_ab": 13.,  "T2b_us": 12., "T1b_ms": 1000., "name": "kidney"},
    10: {"f": 0.035, "k_ab": 11.,  "T2b_us": 12., "T1b_ms": 1000., "name": "pancreas"},
    11: {"f": 0.010, "k_ab":  5.,  "T2b_us": 12., "T1b_ms": 1000., "name": "gallbladder"},
    12: {"f": 0.010, "k_ab":  4.,  "T2b_us": 12., "T1b_ms": 1000., "name": "bladder"},
    13: {"f": 0.120, "k_ab": 30.,  "T2b_us": 10., "T1b_ms": 1000., "name": "cortical bone"},
    14: {"f": 0.020, "k_ab":  8.,  "T2b_us": 12., "T1b_ms": 1000., "name": "vessels"},
    15: {"f": 0.090, "k_ab": 22.,  "T2b_us": 12., "T1b_ms": 1000., "name": "intervertebral disc"},
    16: {"f": 0.130, "k_ab": 35.,  "T2b_us": 12., "T1b_ms": 1000., "name": "spinal cord"},
    17: {"f": 0.000, "k_ab":  0.,  "T2b_us": 10., "T1b_ms": 1000., "name": "air"},
    18: {"f": 0.110, "k_ab": 28.,  "T2b_us": 12., "T1b_ms": 1000., "name": "cartilage"},
    19: {"f": 0.015, "k_ab":  5.,  "T2b_us": 15., "T1b_ms": 1000., "name": "subcutaneous fat"},
    20: {"f": 0.055, "k_ab": 17.,  "T2b_us": 12., "T1b_ms": 1000., "name": "heart"},
    21: {"f": 0.010, "k_ab":  4.,  "T2b_us": 12., "T1b_ms": 1000., "name": "trachea"},
}


def _get_mt(mt_params):
    return mt_params if mt_params is not None else MT_PARAMS


def _get_tissue(tissue_props):
    return tissue_props if tissue_props is not None else _DEFAULT_TISSUE


# ---------------------------------------------------------------------------
# Lineshape functions
# ---------------------------------------------------------------------------

def gaussian_lineshape(offset_hz, T2b_us):
    """Gaussian spectral lineshape of the immobile (bound) pool.

    g(Δf) = T2b / √(2π) · exp(−2π²·Δf²·T2b²)   [s]

    Parameters
    ----------
    offset_hz : float or array  frequency offset from water resonance (Hz)
    T2b_us : float  bound pool T2 (μs)

    Returns
    -------
    g : same shape as offset_hz, in seconds
    """
    T2b_s = float(T2b_us) * 1e-6
    return (T2b_s / np.sqrt(2.0 * np.pi)
            * np.exp(-2.0 * np.pi**2 * np.asarray(offset_hz, float)**2 * T2b_s**2))


def lorentzian_lineshape(offset_hz, T2a_ms):
    """Lorentzian spectral lineshape of the free water pool.

    g(Δf) = T2a / π · 1 / (1 + (2π·Δf·T2a)²)   [s]

    Used for direct saturation of free water (relevant near 0 Hz offset).

    Parameters
    ----------
    offset_hz : float or array
    T2a_ms : float  free pool T2 (ms)
    """
    T2a_s = float(T2a_ms) * 1e-3
    return (T2a_s / np.pi
            / (1.0 + (2.0 * np.pi * np.asarray(offset_hz, float) * T2a_s)**2))


# ---------------------------------------------------------------------------
# RF saturation rates
# ---------------------------------------------------------------------------

def saturation_rate_bound(B1_sat_uT, offset_hz, T2b_us):
    """CW RF saturation rate of the bound pool  W_b = π·ω₁²·g(Δf)  [s⁻¹].

    Parameters
    ----------
    B1_sat_uT : float  saturation pulse amplitude (μT)
    offset_hz : float or array  frequency offset (Hz)
    T2b_us : float  bound pool T2 (μs)
    """
    omega1 = GAMMA_RAD_T * float(B1_sat_uT) * 1e-6   # rad/s
    return np.pi * omega1**2 * gaussian_lineshape(offset_hz, T2b_us)


def saturation_rate_free(B1_sat_uT, offset_hz, T2a_ms):
    """CW RF saturation rate of the free pool  W_a = π·ω₁²·g_L(Δf)  [s⁻¹].

    Significant only near 0 Hz offset (direct water saturation).
    """
    omega1 = GAMMA_RAD_T * float(B1_sat_uT) * 1e-6
    return np.pi * omega1**2 * lorentzian_lineshape(offset_hz, T2a_ms)


# ---------------------------------------------------------------------------
# Core steady-state two-pool model
# ---------------------------------------------------------------------------

def mt_steady_state(f, k_ab, T1a_ms, T1b_ms, W_b, W_a=0.0):
    """Normalised free-pool steady-state magnetisation under CW MT saturation.

    Solves the binary spin-bath equations at steady state
    (Henkelman 1993, eq. 4):

        (R1A + k_AB + W_A) · MzA = R1A · M0A + k_BA · MzB
        (R1B + k_BA + W_B) · MzB = R1B · M0B + k_AB · MzA

    Returns MzA / M0A ∈ [0, 1].

    Parameters
    ----------
    f : float  bound pool fraction M0B / (M0A + M0B)
    k_ab : float  exchange rate A→B  (s⁻¹)
    T1a_ms, T1b_ms : float  longitudinal relaxation times (ms)
    W_b : float or array  bound pool saturation rate  (s⁻¹)
    W_a : float or array  free pool saturation rate  (s⁻¹)  [default 0]

    Returns
    -------
    mza_norm : float or array  MzA / M0A
    """
    if f == 0.0:
        return np.ones_like(np.asarray(W_b, float))

    R1a = 1e3 / float(T1a_ms)          # s⁻¹
    R1b = 1e3 / float(T1b_ms)          # s⁻¹
    k_ba = k_ab * (1.0 - f) / f        # detailed balance: k_ab·M0A = k_ba·M0B

    W_b = np.asarray(W_b, dtype=float)
    W_a = np.asarray(W_a, dtype=float) * np.ones_like(W_b)

    D  = R1b + k_ba + W_b
    RA = R1a + k_ab + W_a

    # Numerator and denominator of MzA/M0A (see derivation in module docstring)
    numer = R1a * D + k_ba * R1b * (f / (1.0 - f))
    denom = RA * D - k_ba * k_ab

    with np.errstate(divide="ignore", invalid="ignore"):
        result = np.where(np.abs(denom) > 1e-20, numer / denom, 1.0)
    return np.clip(result, 0.0, 1.0)


# ---------------------------------------------------------------------------
# MTR and weighted images
# ---------------------------------------------------------------------------

def mt_ratio(signal_sat, signal_unsat):
    """Magnetisation Transfer Ratio: MTR = (M0 − Msat) / M0.

    Commonly expressed as a percentage (× 100).

    Parameters
    ----------
    signal_sat   : ndarray  image acquired with MT saturation pulse
    signal_unsat : ndarray  reference image without MT pulse

    Returns
    -------
    mtr : ndarray float64  MTR in percent [0, 100]
    """
    s0  = np.asarray(signal_unsat, dtype=float)
    sat = np.asarray(signal_sat,   dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        mtr = np.where(s0 > 1e-12, (s0 - sat) / s0, 0.0)
    return np.clip(mtr * 100.0, 0.0, 100.0)


def _render_signal(label_map, signal_fn, tissue_props):
    """Apply signal_fn(props) per label to produce a float image."""
    out = np.zeros(label_map.shape, dtype=np.float64)
    for lab, p in _get_tissue(tissue_props).items():
        mask = label_map == lab
        if mask.any():
            out[mask] = signal_fn(p)
    return out


def simulate_mt_weighted(label_map, B1_sat_uT=3.0, offset_hz=2000.,
                          TR_ms=500., TE_ms=10., flip_angle_deg=30.,
                          sequence="GRE", tissue_props=None, mt_params=None):
    """Simulate an MT-weighted image.

    For each voxel, computes the free-pool steady-state fraction under CW
    saturation, then multiplies by the unperturbed GRE/SE signal.

    Parameters
    ----------
    label_map : 2-D int array
    B1_sat_uT : float  saturation pulse amplitude (μT)
    offset_hz : float  saturation frequency offset (Hz); ≥ 500 Hz recommended
    TR_ms, TE_ms, flip_angle_deg : float  readout parameters
    sequence : "GRE" | "SE" | "IR"
    tissue_props, mt_params : optional override dicts

    Returns
    -------
    image : ndarray float64
    """
    mtp = _get_mt(mt_params)
    seq = sequence.upper()

    def _sig(p, lab):
        if seq == "SE":
            s0 = spin_echo_signal(p["T1"], p["T2"], p["PD"], TR_ms, TE_ms)
        else:
            s0 = gradient_echo_signal(
                p["T1"], p.get("T2star", p["T2"]), p["PD"],
                TR_ms, TE_ms, flip_angle_deg)
        mp = mtp.get(lab, mtp[0])
        T1a = p["T1"]
        Wb = saturation_rate_bound(B1_sat_uT, offset_hz, mp["T2b_us"])
        frac = mt_steady_state(mp["f"], mp["k_ab"], T1a, mp["T1b_ms"], Wb)
        return float(s0 * frac)

    out = np.zeros(label_map.shape, dtype=np.float64)
    for lab, p in _get_tissue(tissue_props).items():
        mask = label_map == lab
        if mask.any():
            out[mask] = _sig(p, lab)
    return out


def simulate_no_mt(label_map, TR_ms=500., TE_ms=10., flip_angle_deg=30.,
                   sequence="GRE", tissue_props=None):
    """Simulate the reference (no MT saturation) image."""
    seq = sequence.upper()

    def _sig(p):
        if seq == "SE":
            return spin_echo_signal(p["T1"], p["T2"], p["PD"], TR_ms, TE_ms)
        return gradient_echo_signal(
            p["T1"], p.get("T2star", p["T2"]), p["PD"],
            TR_ms, TE_ms, flip_angle_deg)

    return _render_signal(label_map, _sig, tissue_props)


def simulate_mtr_map(label_map, B1_sat_uT=3.0, offset_hz=2000.,
                      TR_ms=500., TE_ms=10., flip_angle_deg=30.,
                      sequence="GRE", tissue_props=None, mt_params=None):
    """MTR map from a label volume.

    Returns
    -------
    mtr : ndarray float64  MTR in percent
    """
    s_sat   = simulate_mt_weighted(label_map, B1_sat_uT, offset_hz,
                                    TR_ms, TE_ms, flip_angle_deg,
                                    sequence, tissue_props, mt_params)
    s_unsat = simulate_no_mt(label_map, TR_ms, TE_ms, flip_angle_deg,
                              sequence, tissue_props)
    return mt_ratio(s_sat, s_unsat)


# ---------------------------------------------------------------------------
# Z-spectrum
# ---------------------------------------------------------------------------

def z_spectrum(f, k_ab, T1a_ms, T1b_ms, T2b_us, T2a_ms,
               offset_hz_list, B1_sat_uT=1.0):
    """Z-spectrum (magnetisation vs frequency offset) for a single tissue.

    Includes both MT from bound pool and direct saturation of free water.

    Parameters
    ----------
    f, k_ab : bound pool fraction and exchange rate
    T1a_ms, T1b_ms : relaxation times (ms)
    T2b_us : bound pool T2 (μs)
    T2a_ms : free pool T2 (ms) for direct saturation lineshape
    offset_hz_list : array-like  frequency offsets (Hz)
    B1_sat_uT : float  saturation amplitude (μT)

    Returns
    -------
    z : ndarray  MzA/M0A ∈ [0, 1], shape == len(offset_hz_list)
    """
    offsets = np.asarray(offset_hz_list, dtype=float)
    Wb = saturation_rate_bound(B1_sat_uT, offsets, T2b_us)
    Wa = saturation_rate_free(B1_sat_uT, offsets, T2a_ms)
    return mt_steady_state(f, k_ab, T1a_ms, T1b_ms, Wb, W_a=Wa)


def simulate_z_spectrum_map(label_map, offset_hz_list, B1_sat_uT=1.0,
                              tissue_props=None, mt_params=None):
    """Z-spectrum per pixel: full (n_offsets, H, W) stack.

    Parameters
    ----------
    label_map : 2-D int array
    offset_hz_list : sequence of floats
    B1_sat_uT : float
    tissue_props, mt_params : optional overrides

    Returns
    -------
    z_stack : (n_offsets, H, W) float64  MzA/M0A
    """
    offsets = np.asarray(offset_hz_list, dtype=float)
    n = len(offsets)
    stack = np.ones((n,) + label_map.shape, dtype=np.float64)

    tp  = _get_tissue(tissue_props)
    mtp = _get_mt(mt_params)

    for lab, p in tp.items():
        mask = label_map == lab
        if not mask.any():
            continue
        mp  = mtp.get(lab, mtp[0])
        T2a = p["T2"]   # free pool T2 (ms)
        z   = z_spectrum(mp["f"], mp["k_ab"], p["T1"], mp["T1b_ms"],
                          mp["T2b_us"], T2a, offsets, B1_sat_uT)
        stack[:, mask] = z[:, np.newaxis]

    return stack
