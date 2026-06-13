"""Receive coil sensitivity maps and parallel-imaging utilities.

Provides physics-based and analytical models for MR receiver coil arrays,
signal combination strategies (SoS, SENSE), and figures of merit (g-factor,
SNR efficiency).

Coil models
-----------
  biot_savart_sensitivity  — circular loop coil approximation (falls as R²/(r²+R²)^3/2)
  gaussian_sensitivity     — analytic Gaussian profile
  cylindrical_array        — N coils uniformly arranged around a cylinder
  head_coil_array          — coils distributed over an elliptical FOV (head geometry)

Signal combination
------------------
  apply_coil_sensitivities — multiply image by each coil map  →  coil images
  combine_sos              — Sum-of-Squares magnitude combination
  combine_sense            — optimal (pseudo-inverse) SENSE combination
  coil_snr_weights         — noise-optimal combination weights per voxel

Figures of merit
----------------
  g_factor_map             — local noise amplification in undersampled SENSE
  snr_map                  — voxel-wise intrinsic SNR proxy
  coil_uniformity          — coefficient-of-variation of the SoS sensitivity
"""

import numpy as np
from scipy.ndimage import gaussian_filter


# ---------------------------------------------------------------------------
# Single-coil sensitivity models
# ---------------------------------------------------------------------------

def biot_savart_sensitivity(
    shape: tuple[int, int],
    coil_center: tuple[float, float],
    coil_radius_mm: float,
    voxel_size_mm: tuple[float, float] = (1.0, 1.0),
    peak: float = 1.0,
) -> np.ndarray:
    """Approximate receive sensitivity of a circular surface coil.

    Uses the on-axis Biot-Savart solution for a loop coil evaluated at the
    image plane, then extended off-axis by replacing the axial distance with
    the in-plane Euclidean distance from the coil centre:

        S(r) = peak × R² / (r² + R²)^(3/2)

    where R is the coil radius and r is the distance from the coil centre.
    The map is normalised so that the maximum over the FOV equals *peak*.

    Parameters
    ----------
    shape : (rows, cols) output array shape
    coil_center : (row, col) in pixels
    coil_radius_mm : float  loop radius in mm
    voxel_size_mm : (row_spacing, col_spacing) in mm
    peak : float  maximum sensitivity (1.0 = normalised)

    Returns
    -------
    sensitivity : (rows, cols) float64, values in (0, peak]
    """
    rows, cols = shape
    r0, c0 = coil_center
    dr, dc = voxel_size_mm

    row_idx = np.arange(rows, dtype=np.float64)
    col_idx = np.arange(cols, dtype=np.float64)
    rr, cc  = np.meshgrid(row_idx, col_idx, indexing="ij")

    dist_mm  = np.sqrt(((rr - r0) * dr) ** 2 + ((cc - c0) * dc) ** 2)
    R = float(coil_radius_mm)
    raw = R ** 2 / (dist_mm ** 2 + R ** 2) ** 1.5

    mx = raw.max()
    if mx > 1e-30:
        raw = raw / mx

    return (raw * float(peak)).astype(np.float64)


def gaussian_sensitivity(
    shape: tuple[int, int],
    center: tuple[float, float],
    sigma_mm: float,
    voxel_size_mm: tuple[float, float] = (1.0, 1.0),
    peak: float = 1.0,
) -> np.ndarray:
    """Gaussian receive sensitivity profile.

    S(r) = peak × exp(−r² / (2 σ²))

    Parameters
    ----------
    shape : (rows, cols)
    center : (row, col) in pixels
    sigma_mm : float  Gaussian width in mm
    voxel_size_mm : (dr, dc) in mm
    peak : float  peak value

    Returns
    -------
    sensitivity : (rows, cols) float64
    """
    rows, cols = shape
    r0, c0 = center
    dr, dc = voxel_size_mm

    row_idx = np.arange(rows, dtype=np.float64)
    col_idx = np.arange(cols, dtype=np.float64)
    rr, cc  = np.meshgrid(row_idx, col_idx, indexing="ij")

    dist2 = ((rr - r0) * dr) ** 2 + ((cc - c0) * dc) ** 2
    return (float(peak) * np.exp(-dist2 / (2.0 * float(sigma_mm) ** 2))).astype(np.float64)


# ---------------------------------------------------------------------------
# Coil arrays
# ---------------------------------------------------------------------------

def cylindrical_array(
    shape: tuple[int, int],
    n_coils: int,
    radius_mm: float,
    coil_radius_mm: float | None = None,
    voxel_size_mm: tuple[float, float] = (1.0, 1.0),
    center: tuple[float, float] | None = None,
) -> np.ndarray:
    """N receive coils uniformly distributed on a cylinder around the FOV.

    Coil centres are placed on a circle of ``radius_mm`` (in mm) centred at
    ``center`` (defaults to the image centre).  Each coil's sensitivity is
    modelled with :func:`biot_savart_sensitivity`.

    Parameters
    ----------
    shape : (rows, cols) image shape
    n_coils : int  number of coil elements
    radius_mm : float  radius of the coil-centre ring in mm
    coil_radius_mm : float or None  loop radius; defaults to radius_mm / 2
    voxel_size_mm : (dr, dc) in mm
    center : (row, col) array centre; defaults to image centre

    Returns
    -------
    maps : (n_coils, rows, cols) float64, each map normalised to peak = 1
    """
    rows, cols = shape
    dr, dc = voxel_size_mm
    rc = center[0] if center is not None else (rows - 1) / 2.0
    cc_ctr = center[1] if center is not None else (cols - 1) / 2.0

    if coil_radius_mm is None:
        coil_radius_mm = radius_mm / 2.0

    maps = np.zeros((n_coils, rows, cols), dtype=np.float64)
    for i in range(n_coils):
        angle = 2.0 * np.pi * i / n_coils
        # Convert mm offset to pixel offset
        row_center = rc   + (radius_mm * np.sin(angle)) / dr
        col_center = cc_ctr + (radius_mm * np.cos(angle)) / dc
        maps[i] = biot_savart_sensitivity(
            shape,
            coil_center=(row_center, col_center),
            coil_radius_mm=coil_radius_mm,
            voxel_size_mm=voxel_size_mm,
        )
    return maps


def head_coil_array(
    shape: tuple[int, int],
    n_coils: int = 8,
    radius_fraction: float = 0.55,
    voxel_size_mm: tuple[float, float] = (1.0, 1.0),
) -> np.ndarray:
    """Simplified head coil array on an ellipse fitting the FOV.

    Coils are evenly distributed on an ellipse whose semi-axes are
    ``radius_fraction × (rows/2, cols/2)`` converted to mm.

    Returns
    -------
    maps : (n_coils, rows, cols) float64
    """
    rows, cols = shape
    dr, dc = voxel_size_mm
    rc = (rows - 1) / 2.0
    cc = (cols - 1) / 2.0

    semi_r_mm = radius_fraction * rows / 2.0 * dr
    semi_c_mm = radius_fraction * cols / 2.0 * dc
    coil_r_mm = min(semi_r_mm, semi_c_mm) * 0.5

    maps = np.zeros((n_coils, rows, cols), dtype=np.float64)
    for i in range(n_coils):
        angle = 2.0 * np.pi * i / n_coils
        row_center = rc + (semi_r_mm * np.sin(angle)) / dr
        col_center = cc + (semi_c_mm * np.cos(angle)) / dc
        maps[i] = biot_savart_sensitivity(
            shape,
            coil_center=(row_center, col_center),
            coil_radius_mm=coil_r_mm,
            voxel_size_mm=voxel_size_mm,
        )
    return maps


# ---------------------------------------------------------------------------
# Signal combination
# ---------------------------------------------------------------------------

def apply_coil_sensitivities(
    image: np.ndarray,
    sensitivity_maps: np.ndarray,
) -> np.ndarray:
    """Multiply a single image by each element of a coil sensitivity array.

    Parameters
    ----------
    image : (rows, cols) float array  ideal (noise-free) MR image
    sensitivity_maps : (n_coils, rows, cols) float array

    Returns
    -------
    coil_images : (n_coils, rows, cols) float64
    """
    img  = np.asarray(image,            dtype=np.float64)
    maps = np.asarray(sensitivity_maps, dtype=np.float64)
    if img.shape != maps.shape[1:]:
        raise ValueError(
            f"image shape {img.shape} does not match sensitivity map "
            f"spatial shape {maps.shape[1:]}"
        )
    return (maps * img[np.newaxis, :, :]).astype(np.float64)


def combine_sos(coil_images: np.ndarray) -> np.ndarray:
    """Sum-of-Squares magnitude combination.

    I_SoS = sqrt( Σ_i |coil_images_i|² )

    Parameters
    ----------
    coil_images : (n_coils, rows, cols) real or complex array

    Returns
    -------
    image : (rows, cols) float64, non-negative
    """
    ci = np.asarray(coil_images)
    return np.sqrt(np.sum(np.abs(ci) ** 2, axis=0)).astype(np.float64)


def combine_sense(
    coil_images: np.ndarray,
    sensitivity_maps: np.ndarray,
    noise_cov: np.ndarray | None = None,
) -> np.ndarray:
    """Optimal (noise-weighted) SENSE image combination.

    For fully-sampled data the SENSE combination reduces to the matched filter:

        I(r) = Σ_i S_i*(r) × coil_image_i(r)  /  Σ_i |S_i(r)|²

    With a noise covariance matrix Ψ (n_coils × n_coils) the weights become:
        w = (S† Ψ⁻¹ S)⁻¹ S† Ψ⁻¹

    where S is the sensitivity vector at each voxel.

    Parameters
    ----------
    coil_images : (n_coils, rows, cols) real or complex
    sensitivity_maps : (n_coils, rows, cols) real or complex
    noise_cov : (n_coils, n_coils) float or complex, or None (→ identity)

    Returns
    -------
    image : (rows, cols) float64 (magnitude of complex-valued combination)
    """
    ci = np.asarray(coil_images,      dtype=complex)
    sm = np.asarray(sensitivity_maps, dtype=complex)
    n_coils, rows, cols = ci.shape

    if noise_cov is None:
        psi_inv = np.eye(n_coils, dtype=complex)
    else:
        psi_inv = np.linalg.inv(np.asarray(noise_cov, dtype=complex))

    np.zeros((rows, cols), dtype=complex)
    # (n_coils, rows*cols)
    S = sm.reshape(n_coils, -1)
    M = ci.reshape(n_coils, -1)

    # w = S† Ψ⁻¹; denominator = S† Ψ⁻¹ S per voxel
    SH  = S.conj()                         # (n_coils, npix)
    PSI_S = psi_inv @ S                    # (n_coils, npix)
    numer = np.sum(SH * (psi_inv @ M), axis=0)   # (npix,)
    denom = np.sum(SH * PSI_S, axis=0)            # (npix,)

    with np.errstate(invalid="ignore", divide="ignore"):
        combined = np.where(np.abs(denom) > 1e-30, numer / denom, 0.0)

    return np.abs(combined.reshape(rows, cols)).astype(np.float64)


def coil_snr_weights(
    sensitivity_maps: np.ndarray,
    noise_cov: np.ndarray | None = None,
) -> np.ndarray:
    """Noise-optimal combination weights w_i(r) = S_i*(r) / Σ_j |S_j(r)|².

    For white noise (noise_cov = I) these are the matched-filter weights.
    With noise_cov Ψ the weights are the rows of (S† Ψ⁻¹ S)⁻¹ S† Ψ⁻¹.

    Parameters
    ----------
    sensitivity_maps : (n_coils, rows, cols)
    noise_cov : (n_coils, n_coils) or None

    Returns
    -------
    weights : (n_coils, rows, cols) complex128
    """
    sm = np.asarray(sensitivity_maps, dtype=complex)
    n_coils, rows, cols = sm.shape

    if noise_cov is None:
        psi_inv = np.eye(n_coils, dtype=complex)
    else:
        psi_inv = np.linalg.inv(np.asarray(noise_cov, dtype=complex))

    S   = sm.reshape(n_coils, -1)           # (n_coils, npix)
    SH  = S.conj()
    PSI_S = psi_inv @ S                     # (n_coils, npix)
    denom = np.sum(SH * PSI_S, axis=0)      # (npix,)
    with np.errstate(invalid="ignore", divide="ignore"):
        w = np.where(np.abs(denom) > 1e-30, PSI_S / denom[np.newaxis, :], 0.0)
    return w.reshape(n_coils, rows, cols)


# ---------------------------------------------------------------------------
# Figures of merit
# ---------------------------------------------------------------------------

def snr_map(
    sensitivity_maps: np.ndarray,
    noise_sigma: float = 1.0,
) -> np.ndarray:
    """Intrinsic receive SNR proxy for a coil array.

    SNR(r) ∝ sqrt( Σ_i |S_i(r)|² ) / σ

    Parameters
    ----------
    sensitivity_maps : (n_coils, rows, cols)
    noise_sigma : float  assumed equal noise standard deviation per coil

    Returns
    -------
    snr : (rows, cols) float64, non-negative
    """
    maps = np.asarray(sensitivity_maps, dtype=complex)
    return (np.sqrt(np.sum(np.abs(maps) ** 2, axis=0)) / float(noise_sigma)
            ).astype(np.float64)


def g_factor_map(
    sensitivity_maps: np.ndarray,
    acceleration: int,
    noise_cov: np.ndarray | None = None,
) -> np.ndarray:
    """Voxel-wise g-factor for regular Cartesian SENSE undersampling.

    For an acceleration factor R, the aliased voxel set at each position
    contains R voxels separated by FOV/R in the phase-encode direction.
    The g-factor quantifies local noise amplification:

        g(r) = sqrt( [(S†Ψ⁻¹S)⁻¹]_{rr}  ×  [S†Ψ⁻¹S]_{rr} )

    where the index rr refers to the target voxel in the reduced FOV system.

    This implementation uses the direct R×R matrix inversion at each
    phase-encode position, following the Pruessmann 1999 SENSE formulation.

    Parameters
    ----------
    sensitivity_maps : (n_coils, rows, cols) — rows = phase-encode direction
    acceleration : int  SENSE acceleration factor R (≥ 1); must divide rows
    noise_cov : (n_coils, n_coils) or None

    Returns
    -------
    g : (rows, cols) float64  g ≥ 1 everywhere (1.0 = no amplification)
    """
    sm = np.asarray(sensitivity_maps, dtype=complex)
    n_coils, rows, cols = sm.shape
    R = int(acceleration)

    if R < 1:
        raise ValueError(f"acceleration must be ≥ 1, got {R}")
    if rows % R != 0:
        raise ValueError(
            f"rows ({rows}) must be divisible by acceleration ({R})"
        )

    if noise_cov is None:
        psi_inv = np.eye(n_coils, dtype=complex)
    else:
        psi_inv = np.linalg.inv(np.asarray(noise_cov, dtype=complex))

    n_reduced = rows // R       # rows in reduced FOV
    g = np.ones((rows, cols), dtype=np.float64)

    for col in range(cols):
        for row_r in range(n_reduced):
            # Aliased rows in full FOV for this reduced-FOV row
            aliased = [row_r + k * n_reduced for k in range(R)]

            # Sensitivity matrix: (n_coils, R)
            S_block = sm[:, aliased, col]  # (n_coils, R)

            # A = S† Ψ⁻¹ S  (R × R)
            A = S_block.conj().T @ psi_inv @ S_block

            try:
                A_inv = np.linalg.inv(A)
            except np.linalg.LinAlgError:
                # Singular: undefined g-factor, leave as 1
                continue

            for k, row_full in enumerate(aliased):
                diag_inv = float(np.real(A_inv[k, k]))
                diag_fwd = float(np.real(A[k, k]))
                g[row_full, col] = float(np.sqrt(max(diag_inv * diag_fwd, 1.0)))

    return g


def coil_uniformity(
    sensitivity_maps: np.ndarray,
    mask: np.ndarray | None = None,
) -> float:
    """Coefficient of variation of the SoS sensitivity within a mask.

    A value close to 0 indicates uniform sensitivity; higher values
    mean the array has significant spatial variation.

    Parameters
    ----------
    sensitivity_maps : (n_coils, rows, cols)
    mask : (rows, cols) bool or None  region to evaluate (all voxels if None)

    Returns
    -------
    cv : float  std / mean of the SoS map within the mask
    """
    sos = combine_sos(sensitivity_maps)
    region = sos[mask] if mask is not None else sos.ravel()
    if region.size == 0 or float(region.mean()) == 0.0:
        return 0.0
    return float(region.std() / region.mean())


# ---------------------------------------------------------------------------
# Convenience: smoothed sensitivity estimate from coil images
# ---------------------------------------------------------------------------

def estimate_sensitivity(
    coil_images: np.ndarray,
    smooth_sigma: float = 5.0,
) -> np.ndarray:
    """Estimate sensitivity maps from coil images by low-pass filtering.

    A crude but standard body-coil-reference–free approach: normalise each
    coil image by the SoS combination and apply a Gaussian smoothing filter.

    Parameters
    ----------
    coil_images : (n_coils, rows, cols) real array (magnitude images)
    smooth_sigma : float  Gaussian σ in voxels for the sensitivity estimate

    Returns
    -------
    sensitivity_est : (n_coils, rows, cols) float64, non-negative
    """
    ci   = np.asarray(coil_images, dtype=np.float64)
    sos  = combine_sos(ci)
    safe = np.where(sos > 1e-12, sos, 1.0)

    est = np.zeros_like(ci)
    for i in range(ci.shape[0]):
        ratio = ci[i] / safe
        est[i] = gaussian_filter(ratio, sigma=smooth_sigma)

    return np.maximum(est, 0.0)


# ---------------------------------------------------------------------------
# Display: receive-coil shading envelope (shared by the browser and desktop apps)
# ---------------------------------------------------------------------------

def receive_coil_envelope(
    shape: tuple[int, int],
    coil: str,
) -> "np.ndarray | None":
    """Normalised spatial receive-sensitivity envelope for shading an image.

    Returns a (rows, cols) array with bright regions ≈ 1 (clipped), or ``None`` for
    the ideal uniform coil. ``coil`` is one of ``"surface"`` (a single loop at the
    bottom edge — strong falloff), ``"quad"`` (2-channel), ``"head8"`` (8-channel
    array), or anything else / ``"uniform"`` → ``None``.
    """
    rows, cols = shape
    if coil == "surface":
        env = biot_savart_sensitivity(
            shape, coil_center=(rows - 1.0, (cols - 1) / 2.0),
            coil_radius_mm=max(cols, rows) * 0.18)
    elif coil == "quad":
        env = combine_sos(head_coil_array(shape, n_coils=2))
    elif coil == "head8":
        env = combine_sos(head_coil_array(shape, n_coils=8))
    else:
        return None
    p95 = float(np.percentile(env, 95))
    if p95 > 1e-9:
        env = env / p95
    return np.clip(env, 0.0, 1.25).astype(np.float64)
