"""Parallel imaging acceleration and compressed sensing for MRI simulation.

SENSE reconstruction delegates to the physics-correct sensitivity models and
g-factor computation in coil.py rather than the heuristic noise models that
were here before.

Functions
---------
sense_reconstruction        — full Cartesian SENSE: coil-image → undersample → unfold
apply_parallel_imaging      — high-level wrapper (SENSE or approximate GRAPPA)
compute_acceleration_metrics — scan-time / SNR metrics derived from a real g-factor map
vd_poisson_mask             — variable-density random undersampling mask
apply_compressed_sensing    — CS acquisition with zero-filled reconstruction
"""

import numpy as np

from coil import (
    apply_coil_sensitivities,
    combine_sos,
    g_factor_map,
    head_coil_array,
)


# ---------------------------------------------------------------------------
# SENSE reconstruction
# ---------------------------------------------------------------------------

def sense_reconstruction(
    image: np.ndarray,
    sensitivity_maps: np.ndarray,
    acceleration: int,
    noise_sigma: float = 0.0,
    noise_cov: np.ndarray | None = None,
    rng: np.random.Generator | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Full Cartesian SENSE pipeline: acquire → undersample → unfold.

    Pipeline
    --------
    1. Apply coil sensitivities to create per-coil complex images.
    2. Add complex Gaussian noise (σ = noise_sigma per coil, per channel).
    3. Forward FFT along the phase-encode axis (axis 0), keep every R-th
       line (regular Cartesian undersampling), inverse FFT → aliased coil images.
    4. SENSE unfolding: at each reduced-FOV row, solve
       ``(S†Ψ⁻¹S) x = S†Ψ⁻¹ b`` for the R aliased pixels — vectorised
       over all columns simultaneously.

    Parameters
    ----------
    image : (rows, cols) float array  ideal (noise-free) MR image
    sensitivity_maps : (n_coils, rows, cols) real or complex array
    acceleration : int  SENSE factor R; must divide rows evenly
    noise_sigma : float  per-coil Gaussian noise σ (0 = noise-free)
    noise_cov : (n_coils, n_coils) or None  coil noise covariance (identity if None)
    rng : np.random.Generator or None  seed source for reproducible noise

    Returns
    -------
    image_recon : (rows, cols) float64  SENSE-reconstructed magnitude image
    g_factor : (rows, cols) float64  local noise amplification (≥ 1)
    """
    img = np.asarray(image, dtype=np.float64)
    sm  = np.asarray(sensitivity_maps, dtype=complex)
    n_coils, rows, cols = sm.shape
    R = int(acceleration)

    if R < 1:
        raise ValueError(f"acceleration must be >= 1, got {R}")
    if rows % R != 0:
        raise ValueError(
            f"rows ({rows}) must be divisible by acceleration ({R}); "
            "pad the image before calling or use apply_parallel_imaging which "
            "handles this automatically"
        )

    if R == 1:
        coil_imgs = apply_coil_sensitivities(img, np.abs(sm).real.astype(np.float64))
        return combine_sos(coil_imgs), np.ones((rows, cols), dtype=np.float64)

    if rng is None:
        rng = np.random.default_rng()

    # Step 1: coil images (complex; sensitivities are real-valued in our model)
    coil_imgs = apply_coil_sensitivities(img, np.abs(sm).real.astype(np.float64)).astype(complex)

    # Step 2: add per-coil complex Gaussian noise
    if noise_sigma > 0.0:
        sigma = float(noise_sigma)
        noise = (rng.standard_normal(coil_imgs.shape)
                 + 1j * rng.standard_normal(coil_imgs.shape)) * (sigma / np.sqrt(2.0))
        coil_imgs = coil_imgs + noise

    # Step 3: forward FFT, regular R-fold undersampling, inverse FFT
    kspace       = np.fft.fft(coil_imgs, axis=1, norm="ortho")  # (n_coils, rows, cols)
    undersampled = kspace[:, ::R, :]                              # (n_coils, rows//R, cols)
    aliased      = np.fft.ifft(undersampled, axis=1, norm="ortho")  # (n_coils, rows//R, cols)

    # Step 4: SENSE unfolding, vectorised over columns
    n_reduced = rows // R
    psi_inv = (np.linalg.inv(np.asarray(noise_cov, dtype=complex))
               if noise_cov is not None
               else np.eye(n_coils, dtype=complex))

    recon = np.zeros((rows, cols), dtype=complex)
    for row_r in range(n_reduced):
        aliased_rows = [row_r + k * n_reduced for k in range(R)]

        # S: (cols, n_coils, R)
        S      = sm[:, aliased_rows, :].transpose(2, 0, 1)
        SH_Psi = S.conj().transpose(0, 2, 1) @ psi_inv      # (cols, R, n_coils)
        A      = SH_Psi @ S                                   # (cols, R, R)
        b      = aliased[:, row_r, :].T[:, :, np.newaxis]    # (cols, n_coils, 1)
        rhs    = SH_Psi @ b                                   # (cols, R, 1)

        try:
            x = np.linalg.solve(A, rhs)[..., 0]              # (cols, R)
        except np.linalg.LinAlgError:
            x = np.zeros((cols, R), dtype=complex)

        for k, row_full in enumerate(aliased_rows):
            recon[row_full, :] = x[:, k]

    gfactor = g_factor_map(sm, R, noise_cov)
    return np.abs(recon).astype(np.float64), gfactor


# ---------------------------------------------------------------------------
# High-level wrapper (backward-compatible)
# ---------------------------------------------------------------------------

def apply_parallel_imaging(
    image: np.ndarray,
    acceleration_factor: int = 2,
    method: str = "SENSE",
    n_coils: int = 8,
    noise_sigma: float = 0.01,
    sensitivity_maps: np.ndarray | None = None,
    noise_cov: np.ndarray | None = None,
    rng: np.random.Generator | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Simulate accelerated parallel imaging acquisition and reconstruction.

    Uses physics-correct coil sensitivity models from coil.py.

    Parameters
    ----------
    image : (rows, cols) float array
    acceleration_factor : int  SENSE/GRAPPA factor R (≥ 1)
    method : "SENSE" | "GRAPPA"
        SENSE: full Cartesian SENSE unfolding via sense_reconstruction.
        GRAPPA: SoS combination after regular Cartesian undersampling —
        a simplified approximation (no kernel calibration) that captures
        the residual aliasing; g-factor scaled 20 % below SENSE as a
        crude model of GRAPPA's lower geometric noise factor.
    n_coils : int  coil elements for the auto-generated head array
    noise_sigma : float  per-coil noise σ expressed as a fraction of the
        image maximum (default 0.01 → 1 % noise)
    sensitivity_maps : (n_coils, rows, cols) or None — auto-generated if None
    noise_cov : (n_coils, n_coils) or None  coil noise covariance
    rng : np.random.Generator or None

    Returns
    -------
    image_recon : (rows, cols) float64
    g_factor : (rows, cols) float64  g ≥ 1 everywhere
    """
    img = np.asarray(image, dtype=np.float64)
    R   = int(acceleration_factor)

    if R <= 1:
        return img.copy(), np.ones(img.shape, dtype=np.float64)

    rows, cols = img.shape
    if rng is None:
        rng = np.random.default_rng()

    if sensitivity_maps is None:
        sm = head_coil_array(shape=(rows, cols), n_coils=n_coils,
                             voxel_size_mm=(1.0, 1.0)).astype(complex)
    else:
        sm = np.asarray(sensitivity_maps, dtype=complex)
        n_coils = sm.shape[0]

    sigma = float(noise_sigma) * float(img.max()) if img.max() > 0.0 else float(noise_sigma)

    if method.upper() == "SENSE":
        # Pad rows to the next multiple of R if needed
        pad = (-rows % R) % R
        if pad:
            img_work = np.pad(img, ((0, pad), (0, 0)))
            sm_work  = np.pad(sm,  ((0, 0), (0, pad), (0, 0)))
        else:
            img_work, sm_work = img, sm

        recon, gfactor = sense_reconstruction(
            img_work, sm_work, R, sigma, noise_cov, rng)

        if pad:
            recon   = recon[:rows, :]
            gfactor = gfactor[:rows, :]
        return recon, gfactor

    else:  # GRAPPA approximation
        coil_imgs = apply_coil_sensitivities(img, np.abs(sm).real.astype(np.float64)).astype(complex)
        if sigma > 0.0:
            coil_imgs += (rng.standard_normal(coil_imgs.shape)
                          + 1j * rng.standard_normal(coil_imgs.shape)) * (sigma / np.sqrt(2.0))

        # Undersample k-space (zero-fill missing lines) and reconstruct via SoS
        kspace         = np.fft.fft(coil_imgs, axis=1, norm="ortho")
        line_mask      = np.zeros(rows, dtype=bool)
        line_mask[::R] = True
        kspace[:, ~line_mask, :] = 0.0
        imgs  = np.abs(np.fft.ifft(kspace, axis=1, norm="ortho"))
        recon = combine_sos(imgs)

        # Preserve mean intensity
        ref_mean = float(img[img > 0].mean()) if (img > 0).any() else 1.0
        rec_mean = float(recon[recon > 0].mean()) if (recon > 0).any() else 1.0
        recon = recon * (ref_mean / rec_mean)

        # GRAPPA g-factor reference: SENSE g × 0.8 (GRAPPA typically lower)
        gfactor = np.clip(g_factor_map(sm, R, noise_cov) * 0.8, 1.0, None)
        return recon, gfactor


# ---------------------------------------------------------------------------
# Acceleration metrics
# ---------------------------------------------------------------------------

def compute_acceleration_metrics(
    acceleration_factor: int,
    base_snr: float,
    base_scan_time: float,
    g_factor: np.ndarray | None = None,
) -> dict[str, float]:
    """Compute SNR and scan-time metrics for an accelerated acquisition.

    When a g-factor map is supplied (from sense_reconstruction or
    g_factor_map), the mean g drives the SNR estimate.  Without one,
    g = 1 (the ideal lower bound) is assumed.

    Parameters
    ----------
    acceleration_factor : int
    base_snr : float  unaccelerated SNR
    base_scan_time : float  unaccelerated scan time (any consistent unit)
    g_factor : (rows, cols) float array or None

    Returns
    -------
    dict with keys:
        snr_factor    — SNR_{accel} / SNR_{base}
        adjusted_snr  — base_snr × snr_factor
        adjusted_time — base_scan_time / R
        g_factor_mean — mean g (1.0 if no map supplied)
        g_factor_max  — max g
        g_factor_p95  — 95th-percentile g
    """
    R = int(acceleration_factor)
    adjusted_time = base_scan_time / R

    if g_factor is not None:
        g_arr  = np.asarray(g_factor, dtype=float)
        g_mean = float(g_arr.mean())
        g_max  = float(g_arr.max())
        g_p95  = float(np.percentile(g_arr, 95))
    else:
        g_mean = g_max = g_p95 = 1.0

    snr_factor   = 1.0 / (np.sqrt(float(R)) * g_mean)
    adjusted_snr = base_snr * snr_factor

    return {
        "snr_factor":    snr_factor,
        "adjusted_snr":  adjusted_snr,
        "adjusted_time": adjusted_time,
        "g_factor_mean": g_mean,
        "g_factor_max":  g_max,
        "g_factor_p95":  g_p95,
    }


# ---------------------------------------------------------------------------
# Variable-density undersampling mask
# ---------------------------------------------------------------------------

def vd_poisson_mask(
    rows: int,
    cols: int,
    acceleration: int,
    center_fraction: float = 0.08,
    rng: np.random.Generator | None = None,
) -> np.ndarray:
    """Variable-density random undersampling mask for compressed sensing.

    The sampling density falls off as 1 / (1 + r²) from the k-space centre,
    which approximates the Poisson-disc distribution commonly used in
    clinical CS protocols.  The ACS (auto-calibration signal) region at the
    centre is always fully sampled.

    Parameters
    ----------
    rows, cols : int  k-space matrix dimensions
    acceleration : int  target acceleration factor
    center_fraction : float  fraction of k-space rows fully sampled at centre
    rng : np.random.Generator or None

    Returns
    -------
    mask : (rows, cols) bool  True = line acquired
    """
    if rng is None:
        rng = np.random.default_rng()

    ky = np.arange(rows) - rows / 2.0
    kx = np.arange(cols) - cols / 2.0
    KY, KX = np.meshgrid(ky, kx, indexing="ij")
    r2 = (KY / (rows / 2.0)) ** 2 + (KX / (cols / 2.0)) ** 2

    # Always sample the ACS centre block
    acs_half = max(1, int(rows * center_fraction / 2))
    mask = np.zeros((rows, cols), dtype=bool)
    mask[rows // 2 - acs_half: rows // 2 + acs_half, :] = True

    # Outside ACS: variable-density probability proportional to 1 / (1 + r²)
    outside      = ~mask
    density      = np.where(outside, 1.0 / (1.0 + r2), 0.0)
    density_sum  = density.sum()

    target_outer = max(0, int(rows * cols / acceleration) - int(mask.sum()))
    outer_total  = int(outside.sum())

    if target_outer > 0 and outer_total > 0 and density_sum > 0:
        prob    = density[outside] / density_sum
        chosen  = rng.choice(outer_total,
                             size=min(target_outer, outer_total),
                             replace=False, p=prob)
        idx     = np.where(outside)
        mask[idx[0][chosen], idx[1][chosen]] = True

    return mask


# ---------------------------------------------------------------------------
# Compressed sensing
# ---------------------------------------------------------------------------

def apply_compressed_sensing(
    image: np.ndarray,
    acceleration_factor: int = 4,
    center_fraction: float = 0.08,
    rng: np.random.Generator | None = None,
) -> np.ndarray:
    """Simulate CS acquisition with variable-density undersampling.

    Applies a vd_poisson_mask to k-space, then returns the zero-filled
    reconstruction.  This models the incoherent aliasing before iterative
    reconstruction — the noise-like artefact pattern is the property CS
    exploits.  For a full CS pipeline, pass this output to a total-variation
    or wavelet-based iterative solver.

    Parameters
    ----------
    image : (rows, cols) float array
    acceleration_factor : int  target acceleration (1 = fully sampled)
    center_fraction : float  fraction of k-space always acquired at centre
    rng : np.random.Generator or None

    Returns
    -------
    image_recon : (rows, cols) float64  zero-filled reconstruction
    """
    if acceleration_factor <= 1:
        return np.asarray(image, dtype=np.float64)

    img = np.asarray(image, dtype=np.float64)
    if rng is None:
        rng = np.random.default_rng()

    rows, cols = img.shape
    kspace = np.fft.fftshift(np.fft.fft2(np.fft.ifftshift(img)))
    mask   = vd_poisson_mask(rows, cols, acceleration_factor, center_fraction, rng)
    recon  = np.abs(np.fft.fftshift(np.fft.ifft2(np.fft.ifftshift(kspace * mask))))
    return recon.astype(np.float64)
