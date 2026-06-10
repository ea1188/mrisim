"""Rician noise model for MRI magnitude images.

Magnitude MRI images follow a Rician distribution, not Gaussian.
This produces a noise floor bias and is especially significant at low SNR.
"""

import numpy as np
from scipy.special import i0e, i1e   # scaled modified Bessel functions (orders 0, 1)


# ---------------------------------------------------------------------------
# Core distribution
# ---------------------------------------------------------------------------

def rician_pdf(x: np.ndarray, nu: float, sigma: float) -> np.ndarray:
    """Rician probability density function.

    p(x; ν, σ) = (x/σ²) · exp(−(x²+ν²)/(2σ²)) · I₀(xν/σ²)

    Parameters
    ----------
    x : array-like  magnitude values (≥ 0)
    nu : float  non-centrality parameter (true signal amplitude)
    sigma : float  noise standard deviation (per channel)

    Returns
    -------
    pdf : ndarray, same shape as x
    """
    x = np.asarray(x, dtype=float)
    nu = float(nu)
    sigma = float(sigma)
    s2 = sigma**2
    # Use scaled Bessel (i0e) to avoid overflow: I0(z) = i0e(z)*exp(z)
    # p = (x/s2)*exp(-(x2+nu2)/(2s2))*I0(x*nu/s2)
    #   = (x/s2)*exp(-(x2+nu2)/(2s2))*i0e(x*nu/s2)*exp(x*nu/s2)
    #   = (x/s2)*i0e(x*nu/s2)*exp(-(x2+nu2-2*x*nu)/(2s2))   [complete square]
    #   = (x/s2)*i0e(x*nu/s2)*exp(-(x-nu)^2/(2s2))
    with np.errstate(invalid="ignore"):
        z = x * nu / s2
        pdf = (x / s2) * i0e(z) * np.exp(-(x - nu)**2 / (2.0 * s2))
    return np.where(x >= 0, pdf, 0.0)


def rician_mean(nu: float | np.ndarray, sigma: float | np.ndarray) -> np.ndarray:
    """Expected value of a Rician-distributed magnitude.

    E[M] = σ · sqrt(π/2) · L_{1/2}(−ν²/(2σ²))
    where L_{1/2} is a Laguerre polynomial.  Computed via the closed form:
    E[M] = σ · sqrt(π/2) · exp(−ν²/(4σ²)) · [(1 + ν²/(2σ²))·I₀(ν²/(4σ²))
                                                + (ν²/(2σ²))·I₁(ν²/(4σ²))]

    Computed exactly via scaled Bessel functions (i0e/i1e), which makes the
    Laguerre form overflow-safe: with z = ν²/(4σ²),

        exp(−z)·Iₙ(z) = i_ne(z),  so
        E[M] = σ·sqrt(π/2)·[(1+2z)·i0e(z) + 2z·i1e(z)].

    The exact form matters at low SNR (it is ~25% above the √(ν²+σ²) high-SNR
    approximation at ν=0, where E[M] = σ·sqrt(π/2) ≈ 1.2533σ). For ν=0 with σ=0
    the magnitude is deterministic, E[M] = |ν|.

    Parameters
    ----------
    nu, sigma : float or array-like

    Returns
    -------
    mean : same shape as broadcast(nu, sigma)
    """
    nu = np.asarray(nu, dtype=float)
    sigma = np.asarray(sigma, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        z = np.where(sigma > 0, nu**2 / (4.0 * sigma**2), 0.0)
        laguerre = (1.0 + 2.0 * z) * i0e(z) + 2.0 * z * i1e(z)
        mean = sigma * np.sqrt(np.pi / 2.0) * laguerre
    # σ → 0 is the noise-free limit where the magnitude equals |ν| exactly.
    return np.where(sigma > 0, mean, np.abs(nu))


def rician_variance(nu: float | np.ndarray,
                    sigma: float | np.ndarray) -> np.ndarray:
    """Variance of a Rician distribution: Var = 2σ² + ν² − E[M]²."""
    nu    = np.asarray(nu, dtype=float)
    sigma = np.asarray(sigma, dtype=float)
    return 2.0 * sigma**2 + nu**2 - rician_mean(nu, sigma)**2


def rician_snr_bias(nu: float | np.ndarray,
                    sigma: float | np.ndarray) -> np.ndarray:
    """Signal-to-noise ratio bias in Rician magnitude images.

    Returns the fractional noise floor: (E[M] − ν) / ν.
    Positive → magnitude image over-estimates true signal.

    Parameters
    ----------
    nu : float or array-like  true signal (0 = background)
    sigma : float or array-like  noise std per channel

    Returns
    -------
    bias : fractional bias (dimensionless)
    """
    nu = np.asarray(nu, dtype=float)
    sigma = np.asarray(sigma, dtype=float)
    with np.errstate(invalid="ignore", divide="ignore"):
        bias = np.where(nu > 0,
                        (rician_mean(nu, sigma) - nu) / nu,
                        np.inf)
    return bias


# ---------------------------------------------------------------------------
# Noise addition
# ---------------------------------------------------------------------------

def add_rician_noise(
    signal_image: np.ndarray,
    sigma: float | np.ndarray,
    rng: np.random.Generator | None = None,
) -> np.ndarray:
    """Add Rician noise to a real-valued MR signal image.

    Procedure: add independent Gaussian noise to real and imaginary channels,
    then take the magnitude.

    Parameters
    ----------
    signal_image : ndarray  real-valued, non-negative  (any shape)
    sigma : float or ndarray  noise standard deviation per channel
        If ndarray, must broadcast to signal_image.shape.
    rng : np.random.Generator or None  reproducible noise source

    Returns
    -------
    noisy : ndarray, same shape, float64, non-negative
    """
    if rng is None:
        rng = np.random.default_rng()
    signal_image = np.asarray(signal_image, dtype=float)
    real_part = signal_image + rng.normal(0., sigma, signal_image.shape)
    imag_part = rng.normal(0., sigma, signal_image.shape)
    return np.sqrt(real_part**2 + imag_part**2)


def add_rician_noise_seeded(
    signal_image: np.ndarray,
    sigma: float,
    seed: int | None = None,
) -> np.ndarray:
    """Reproducible Rician noise using an integer seed (thin wrapper)."""
    return add_rician_noise(signal_image, sigma, rng=np.random.default_rng(seed))


# ---------------------------------------------------------------------------
# SNR estimation
# ---------------------------------------------------------------------------

def estimate_snr_background(image: np.ndarray, signal_mask: np.ndarray,
                             background_mask: np.ndarray | None = None) -> float:
    """Estimate SNR from signal and background regions.

    SNR = mean(signal_region) / std(background_region)

    If background_mask is None, uses a 10×10 corner patch.

    Parameters
    ----------
    image : 2-D ndarray
    signal_mask : bool array, same shape  (True where tissue signal is)
    background_mask : bool array or None

    Returns
    -------
    snr : float
    """
    if background_mask is None:
        bg = np.zeros(image.shape, dtype=bool)
        bg[:10, :10] = True
    else:
        bg = background_mask

    sig = image[signal_mask].mean()
    noise_std = image[bg].std()
    if noise_std < 1e-12:
        return np.inf
    return float(sig / noise_std)


def noise_sigma_from_snr(signal_level: float, target_snr: float) -> float:
    """Return the per-channel noise sigma that achieves a target SNR.

    Accounts for the Rician noise floor using rician_mean.

    Parameters
    ----------
    signal_level : float  expected signal amplitude in tissue
    target_snr : float  desired SNR = signal / sigma

    Returns
    -------
    sigma : float
    """
    return float(signal_level / target_snr)


# ---------------------------------------------------------------------------
# Correction
# ---------------------------------------------------------------------------

def rician_bias_correction(image: np.ndarray, sigma: float) -> np.ndarray:
    """Remove the Rician noise floor bias from a magnitude image.

    Applies: corrected = sqrt(max(image² − σ², 0))

    This is the standard first-order correction (Gudbjartsson & Patz 1995).
    Accurate for SNR > 2; clips negative values to zero.

    Parameters
    ----------
    image : ndarray  magnitude MRI image
    sigma : float  noise standard deviation per channel

    Returns
    -------
    corrected : ndarray, same shape, non-negative float64
    """
    image = np.asarray(image, dtype=float)
    return np.sqrt(np.maximum(image**2 - sigma**2, 0.0))
