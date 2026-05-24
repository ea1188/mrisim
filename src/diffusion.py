"""Diffusion MRI simulation: DWI signal, DTI tensors, and parametric maps.

Functions
---------
diffusion_signal         — mono-exponential DWI signal S = S0·exp(−b·ADC)
diffusion_tensor_signal  — direction-dependent DWI signal from a 2-D tensor
create_diffusion_tensor  — construct 2-D DTI tensor from ADC, FA, orientation
simulate_diffusion_image — per-tissue DWI image (scalar or tensor)
compute_adc_map          — ADC map with realistic spatial noise
compute_fa_map           — FA map with tract structure and spatial noise
compute_direction_map    — colour-coded FA-weighted direction map (RGB)
"""

import numpy as np
from scipy.ndimage import gaussian_filter


# Tissue diffusion properties (ADC in 10⁻³ mm²/s)
DIFFUSION_PROPERTIES: dict[int, dict[str, float]] = {
    0: {"ADC": 0.0, "FA": 0.0},   # background
    1: {"ADC": 3.0, "FA": 0.0},   # CSF
    2: {"ADC": 0.8, "FA": 0.15},  # grey matter
    3: {"ADC": 0.7, "FA": 0.45},  # white matter
    4: {"ADC": 3.0, "FA": 0.0},   # ventricles
}

FIBER_ORIENTATIONS: dict[int, np.ndarray] = {
    3: np.array([1.0, 0.3]),
}


# ---------------------------------------------------------------------------
# Signal models
# ---------------------------------------------------------------------------

def diffusion_signal(S0: float, b_value: float, ADC: float) -> float:
    """Mono-exponential diffusion signal: S = S0·exp(−b·D).

    Parameters
    ----------
    S0      : float  baseline (b=0) signal magnitude
    b_value : float  b-value (s/mm²)
    ADC     : float  apparent diffusion coefficient (10⁻³ mm²/s)

    Returns
    -------
    signal : float  diffusion-weighted signal magnitude
    """
    return float(S0 * np.exp(-b_value * ADC * 1e-3))


def diffusion_tensor_signal(
    S0: float,
    b_value: float,
    tensor: np.ndarray,
    gradient_direction: np.ndarray | list[float],
) -> float:
    """Direction-dependent DWI signal using a 2-D diffusion tensor.

    S = S0·exp(−b · gᵀ·D·g) where g is the normalised gradient direction.

    Parameters
    ----------
    S0                 : float  baseline signal
    b_value            : float  b-value (s/mm²)
    tensor             : (2, 2) symmetric positive-definite diffusion tensor (mm²/s)
    gradient_direction : (2,) array-like  diffusion-encoding direction (need not be unit)

    Returns
    -------
    signal : float
    """
    g = np.asarray(gradient_direction, dtype=float)
    g = g / np.linalg.norm(g)
    apparent_D = float(g @ tensor @ g)
    return float(S0 * np.exp(-b_value * apparent_D))


# ---------------------------------------------------------------------------
# Tensor construction
# ---------------------------------------------------------------------------

def create_diffusion_tensor(
    ADC: float,
    FA: float,
    orientation: np.ndarray | list[float],
) -> np.ndarray:
    """Build a 2-D diffusion tensor from mean diffusivity, FA and orientation.

    The two eigenvalues λ₁ ≥ λ₂ are derived from:
        MD  = (λ₁ + λ₂) / 2
        FA² = δ² / (2·MD² + δ²/2)   where δ = λ₁ − λ₂

    Parameters
    ----------
    ADC         : float  mean diffusivity (10⁻³ mm²/s); ½·trace of the tensor
    FA          : float  fractional anisotropy ∈ [0, 1)
    orientation : (2,) array-like  principal eigenvector direction

    Returns
    -------
    tensor : (2, 2) float64  symmetric positive-definite tensor (mm²/s)
    """
    MD = float(ADC) * 1e-3
    if FA == 0.0:
        return np.eye(2) * MD

    # Solve for eigenvalue spread δ = λ₁ − λ₂
    denom = 1.0 - FA ** 2 / 2.0
    if denom <= 0:
        denom = 1e-9
    delta = np.sqrt(2.0 * MD ** 2 * FA ** 2 / denom)
    lambda1 = MD + delta / 2.0
    lambda2 = MD - delta / 2.0

    if lambda2 < 0:
        lambda2 = 0.01e-3
        lambda1 = 2.0 * MD - lambda2

    v = np.asarray(orientation, dtype=float)
    v = v / np.linalg.norm(v)
    cos_a, sin_a = float(v[0]), float(v[1])
    R = np.array([[cos_a, -sin_a], [sin_a, cos_a]])
    return R @ np.diag([lambda1, lambda2]) @ R.T


# ---------------------------------------------------------------------------
# DWI image synthesis
# ---------------------------------------------------------------------------

def simulate_diffusion_image(
    phantom: np.ndarray,
    tissue_properties: dict,  # type: ignore[type-arg]
    b_value: float,
    gradient_direction: np.ndarray | list[float] | None = None,
    TR: float = 8000,
    TE: float = 80,
) -> np.ndarray:
    """Simulate a diffusion-weighted image from a labelled phantom.

    Each tissue receives its S0 from the spin-echo signal model, then the
    DWI attenuation is applied: scalar (isotropic tissues) or tensor-based
    (anisotropic tissues with an entry in FIBER_ORIENTATIONS).

    Parameters
    ----------
    phantom           : (rows, cols) integer label array
    tissue_properties : dict  {label: {"T1": …, "T2": …, "PD": …}}
    b_value           : float  b-value (s/mm²)
    gradient_direction: (2,) array-like or None  encoding direction (default [1, 0])
    TR, TE            : float  scan parameters (ms)

    Returns
    -------
    image : (rows, cols) float64
    """
    from signal_engine import spin_echo_signal

    if gradient_direction is None:
        gradient_direction = [1.0, 0.0]
    gdir = np.asarray(gradient_direction, dtype=float)

    image = np.zeros_like(phantom, dtype=float)

    for label, props in tissue_properties.items():
        mask = phantom == label
        if not np.any(mask):
            continue

        S0 = spin_echo_signal(props["T1"], props["T2"], props["PD"], TR, TE)
        diff_props = DIFFUSION_PROPERTIES.get(int(label), {"ADC": 0.0, "FA": 0.0})

        if diff_props["FA"] > 0 and int(label) in FIBER_ORIENTATIONS:
            tensor = create_diffusion_tensor(
                diff_props["ADC"], diff_props["FA"],
                FIBER_ORIENTATIONS[int(label)],
            )
            sig = diffusion_tensor_signal(S0, b_value, tensor, gdir)
        else:
            sig = diffusion_signal(S0, b_value, diff_props["ADC"])

        image[mask] = sig

    return image


# ---------------------------------------------------------------------------
# Parametric maps
# ---------------------------------------------------------------------------

def compute_adc_map(
    phantom: np.ndarray,
    rng: np.random.Generator | None = None,
) -> np.ndarray:
    """ADC map with smooth spatial noise overlaid on tissue base values.

    Parameters
    ----------
    phantom : (rows, cols) integer label array
    rng     : np.random.Generator or None  source of reproducible noise

    Returns
    -------
    adc_map : (rows, cols) float64  ADC in 10⁻³ mm²/s; 0 for background
    """
    if rng is None:
        rng = np.random.default_rng()

    size = phantom.shape[0]
    adc_map = np.zeros_like(phantom, dtype=float)

    # Smooth noise field (percentage perturbation)
    raw = rng.standard_normal((size, size))
    variation = gaussian_filter(raw, sigma=8)

    for label, diff_props in DIFFUSION_PROPERTIES.items():
        mask = phantom == label
        base_adc = diff_props["ADC"]
        if base_adc > 0:
            local_adc = base_adc * (1.0 + variation[mask] * 0.3)
            adc_map[mask] = np.clip(local_adc, base_adc * 0.5, base_adc * 1.5)
        else:
            adc_map[mask] = 0.0

    return adc_map


def compute_fa_map(
    phantom: np.ndarray,
    rng: np.random.Generator | None = None,
) -> np.ndarray:
    """FA map with simulated tract structure and spatial noise.

    White-matter (label 3) FA is modulated by a cosine radial pattern that
    mimics the alternating high/low FA of gyri/sulci, plus a narrow corpus-
    callosum band of elevated FA near the midline.

    Parameters
    ----------
    phantom : (rows, cols) integer label array
    rng     : np.random.Generator or None

    Returns
    -------
    fa_map : (rows, cols) float64  FA ∈ [0, 1]; 0 for background
    """
    if rng is None:
        rng = np.random.default_rng()

    size = phantom.shape[0]
    fa_map = np.zeros_like(phantom, dtype=float)
    center = size // 2

    # Smooth noise field
    raw = rng.standard_normal((size, size))
    variation = gaussian_filter(raw, sigma=5)

    # Spatial patterns for white matter
    y, x = np.mgrid[:size, :size]
    dist_from_center = np.sqrt((x - center) ** 2 + (y - center) ** 2) / center
    tract_pattern = 0.3 * np.cos(4.0 * np.pi * dist_from_center) + 0.7
    cc_band = np.exp(-((y - int(center * 0.85)) ** 2) / (2.0 * (size * 0.03) ** 2))

    for label, diff_props in DIFFUSION_PROPERTIES.items():
        mask = phantom == label
        base_fa = diff_props["FA"]

        if label == 3:  # white matter
            local_fa = base_fa * tract_pattern[mask] + 0.2 * cc_band[mask]
            local_fa = local_fa + variation[mask] * 0.15
            fa_map[mask] = np.clip(local_fa, 0.1, 0.9)
        elif base_fa > 0:
            local_fa = base_fa + variation[mask] * 0.1
            fa_map[mask] = np.clip(local_fa, 0.0, 1.0)

    return fa_map


def compute_direction_map(
    phantom: np.ndarray,
    rng: np.random.Generator | None = None,
) -> np.ndarray:
    """Colour-coded FA-weighted direction map (simplified RGB DTI).

    Channels: R = left–right, G = anterior–posterior, B = superior–inferior
    (constant in 2-D).  All channels are scaled by the local FA.

    Parameters
    ----------
    phantom : (rows, cols) integer label array
    rng     : np.random.Generator or None  passed through to compute_fa_map

    Returns
    -------
    direction_map : (rows, cols, 3) float64  values ∈ [0, 1]
    """
    size = phantom.shape[0]
    direction_map = np.zeros((size, size, 3), dtype=float)
    center = size // 2

    fa_map = compute_fa_map(phantom, rng)
    wm_mask = phantom == 3

    y, x = np.mgrid[:size, :size]
    angle = np.arctan2(y - center, x - center)

    direction_map[wm_mask, 0] = np.abs(np.cos(angle[wm_mask])) * fa_map[wm_mask]
    direction_map[wm_mask, 1] = np.abs(np.sin(angle[wm_mask])) * fa_map[wm_mask]
    direction_map[wm_mask, 2] = 0.3 * fa_map[wm_mask]

    max_val = direction_map.max()
    if max_val > 0:
        direction_map /= max_val

    return direction_map
