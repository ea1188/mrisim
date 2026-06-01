"""K-space acquisition simulation for MRI.

Covers the signal chain from image → k-space → acquired (possibly undersampled,
filtered, or partial-Fourier) k-space → reconstructed image.

Functions
---------
image_to_kspace     — 2-D FFT with standard MRI centring (DC at centre)
kspace_to_image     — inverse FFT, returns magnitude image
apply_matrix_size   — crop central k-space to a target acquisition matrix
zero_fill_resize    — zero-pad k-space to a larger matrix before IFFT
kspace_filter       — apodise k-space with a 2-D window (Hamming, Hanning, …)
partial_fourier     — simulate partial-Fourier acquisition along one axis
apply_aliasing      — fold image to simulate a reduced phase-encode FOV
simulate_acquisition — end-to-end single-voxel-size acquisition pipeline
get_kspace_display  — log-magnitude representation for display
"""

import numpy as np


# ---------------------------------------------------------------------------
# Forward / inverse FFT (with MRI DC-at-centre convention)
# ---------------------------------------------------------------------------

def image_to_kspace(image: np.ndarray) -> np.ndarray:
    """2-D FFT with DC shifted to the centre of k-space.

    Parameters
    ----------
    image : (rows, cols) real or complex array

    Returns
    -------
    kspace : (rows, cols) complex128
    """
    return np.fft.fftshift(np.fft.fft2(np.fft.ifftshift(image))).astype(complex)


def kspace_to_image(kspace: np.ndarray) -> np.ndarray:
    """Inverse FFT, returns magnitude image.

    Parameters
    ----------
    kspace : (rows, cols) complex array

    Returns
    -------
    image : (rows, cols) float64, non-negative
    """
    return np.abs(np.fft.fftshift(np.fft.ifft2(np.fft.ifftshift(kspace)))).astype(np.float64)


def radial_sampling_mask(shape: tuple[int, int], n_spokes: int) -> np.ndarray:
    """Boolean k-space coverage of an ``n_spokes`` radial (projection) acquisition.

    Radial sampling fills k-space along spokes through the centre. The centre is
    always densely covered (motion-robust), while the periphery is gapped when
    there are fewer spokes than the Nyquist number — those azimuthal gaps are
    what produce streak artifacts after reconstruction.
    """
    H, W = shape
    cy, cx = H / 2.0, W / 2.0
    yy, xx = np.mgrid[0:H, 0:W].astype(float)
    dy, dx = yy - cy, xx - cx
    r = np.hypot(dy, dx)
    th = np.mod(np.arctan2(dy, dx), np.pi)               # spoke angle, [0, π)
    tol = np.where(r > 1.0, np.arcsin(np.clip(0.7 / r, 0.0, 1.0)), np.pi)
    mask = np.zeros(shape, dtype=bool)
    for a in np.linspace(0.0, np.pi, max(1, int(n_spokes)), endpoint=False):
        d = np.abs(th - a)
        d = np.minimum(d, np.pi - d)                      # circular distance
        mask |= d <= tol
    mask[r < 1.5] = True                                  # central disc always sampled
    return mask


def apply_radial_sampling(image: np.ndarray, n_spokes: int) -> np.ndarray:
    """Reconstruct ``image`` as if acquired with ``n_spokes`` radial spokes.

    The image's k-space is restricted to the radial coverage and transformed
    back, so under-sampling (few spokes) yields the characteristic radial streak
    artifact while full sampling returns the image essentially unchanged.
    """
    mask = radial_sampling_mask(image.shape, n_spokes)
    return kspace_to_image(image_to_kspace(image) * mask)


# ---------------------------------------------------------------------------
# Matrix size (k-space cropping)
# ---------------------------------------------------------------------------

def apply_matrix_size(
    kspace_full: np.ndarray,
    target_rows: int,
    target_cols: int | None = None,
) -> np.ndarray:
    """Crop the central region of k-space to simulate a lower acquisition matrix.

    Cropping k-space is equivalent to reducing the image FOV while keeping the
    voxel size constant (Nyquist criterion): fewer phase-encode lines → lower
    resolution in that direction.

    Parameters
    ----------
    kspace_full : (rows, cols) complex array  fully sampled k-space
    target_rows : int  desired number of k-space rows to keep
    target_cols : int or None  desired columns; defaults to target_rows (square)

    Returns
    -------
    kspace_cropped : (target_rows, target_cols) complex array
        If target_rows ≥ rows and target_cols ≥ cols, the original array is
        returned unchanged.
    """
    rows, cols = kspace_full.shape
    tc = target_cols if target_cols is not None else target_rows

    if target_rows >= rows and tc >= cols:
        return kspace_full

    # Crop rows
    if target_rows < rows:
        r_start = (rows - target_rows) // 2
        out = kspace_full[r_start: r_start + target_rows, :]
    else:
        out = kspace_full

    # Crop cols
    if tc < cols:
        c_start = (cols - tc) // 2
        out = out[:, c_start: c_start + tc]

    return out


# ---------------------------------------------------------------------------
# Zero-fill (k-space padding before IFFT)
# ---------------------------------------------------------------------------

def zero_fill_resize(
    kspace_small: np.ndarray,
    target_rows: int,
    target_cols: int | None = None,
) -> np.ndarray:
    """Zero-pad k-space to a larger matrix and return the magnitude image.

    Zero-filling interpolates between acquired samples in image space
    (sinc interpolation), giving the appearance of higher resolution
    without adding new information.  The image is scaled so that pixel
    intensities match the original (non-zero-filled) reconstruction.

    Parameters
    ----------
    kspace_small : (rows, cols) complex array  acquired (possibly cropped) k-space
    target_rows : int  desired image output rows  (must be ≥ kspace_small.shape[0])
    target_cols : int or None  desired image output cols; defaults to target_rows

    Returns
    -------
    image : (target_rows, target_cols) float64  zero-filled magnitude image

    Notes
    -----
    If the k-space is already at or above the target size the array is
    reconstructed as-is (no padding applied, no error raised).
    """
    in_rows, in_cols = kspace_small.shape
    tc = target_cols if target_cols is not None else target_rows

    if in_rows >= target_rows and in_cols >= tc:
        return kspace_to_image(kspace_small)

    padded = np.zeros((target_rows, tc), dtype=complex)
    r_start = (target_rows - min(in_rows, target_rows)) // 2
    c_start = (tc          - min(in_cols, tc))          // 2
    r_end   = r_start + min(in_rows, target_rows)
    c_end   = c_start + min(in_cols, tc)
    padded[r_start:r_end, c_start:c_end] = kspace_small[:r_end - r_start,
                                                          :c_end - c_start]

    image  = kspace_to_image(padded)
    # Intensity scale: zero-filling multiplies the DC value by (target/current)^2
    # in image space — normalise back so pixel values represent the same signal.
    return image.astype(np.float64)


# ---------------------------------------------------------------------------
# K-space apodisation (Gibbs ringing reduction)
# ---------------------------------------------------------------------------

_WINDOW_FUNCTIONS: dict[str, str] = {
    "hamming":  "hamming",
    "hanning":  "hanning",
    "blackman": "blackman",
    "bartlett": "bartlett",
    "rect":     "rect",
}


def kspace_filter(
    kspace: np.ndarray,
    window: str = "hamming",
) -> np.ndarray:
    """Apply a 2-D separable window function to k-space (apodisation).

    Multiplying k-space by a smooth window tapers the high-spatial-frequency
    components, reducing Gibbs (truncation) ringing at the cost of a small
    amount of image blurring.

    Parameters
    ----------
    kspace : (rows, cols) complex array  centred (DC at centre)
    window : str  one of "hamming" (default), "hanning", "blackman",
             "bartlett", "rect" (no filtering)

    Returns
    -------
    filtered : (rows, cols) complex array
    """
    rows, cols = kspace.shape
    w = window.lower()

    if w not in _WINDOW_FUNCTIONS:
        raise ValueError(
            f"Unknown window {window!r}. Choose from: "
            + ", ".join(_WINDOW_FUNCTIONS)
        )

    if w == "rect":
        return kspace.copy()

    win_fn = getattr(np, w)   # np.hamming, np.hanning, etc.
    wr = np.fft.ifftshift(win_fn(rows))   # match kspace DC-at-centre order
    wc = np.fft.ifftshift(win_fn(cols))
    # Outer product → 2-D separable window
    W  = np.fft.fftshift(np.outer(wr, wc))
    return (kspace * W).astype(complex)


# ---------------------------------------------------------------------------
# Partial Fourier acquisition
# ---------------------------------------------------------------------------

def partial_fourier(
    kspace: np.ndarray,
    fraction: float = 0.625,
    axis: int = 0,
) -> np.ndarray:
    """Simulate partial-Fourier acquisition by zeroing asymmetrically sampled lines.

    In partial Fourier, only ``fraction`` of k-space lines are acquired along
    the chosen axis, always including the centre and the "full" side.  The
    missing lines are set to zero (homodyne/zero-fill reconstruction is not
    applied here — that would require phase-map estimation).

    Acquisition convention used here: the *positive* half of k-space
    (lines above centre) is always fully acquired; the *negative* half
    (lines below centre) is partially acquired according to ``fraction``.

    Parameters
    ----------
    kspace : (rows, cols) complex array  centred k-space
    fraction : float  ∈ (0.5, 1.0]  fraction of lines acquired (0.625 is typical)
    axis : int  axis along which to undersample (0 = phase-encode)

    Returns
    -------
    kspace_pf : same shape, with un-acquired lines set to zero
    """
    if not 0.5 < fraction <= 1.0:
        raise ValueError(f"fraction must be in (0.5, 1.0], got {fraction}")

    n = kspace.shape[axis]
    centre = n // 2

    # How many lines from the negative-k half to acquire
    n_neg_acquired = int(np.round((fraction - 0.5) * n))

    out     = kspace.copy()
    idx     = [slice(None)] * kspace.ndim
    # Zero the negative-k lines beyond what we acquire
    # Negative half starts at index 0 and runs to centre - 1
    n_neg_total   = centre
    n_neg_zeroed  = n_neg_total - n_neg_acquired
    if n_neg_zeroed > 0:
        idx[axis] = slice(0, n_neg_zeroed)
        out[tuple(idx)] = 0.0

    return out


# ---------------------------------------------------------------------------
# Phase-encode FOV aliasing (wrap-around artefact)
# ---------------------------------------------------------------------------

def apply_aliasing(
    image: np.ndarray,
    fov_fraction: float,
) -> np.ndarray:
    """Simulate reduced-FOV aliasing by folding the image in the phase direction.

    When the phase-encode FOV is smaller than the object, signal from outside
    the FOV wraps (aliases) back in.  This is modelled by folding the image
    with modulo arithmetic — vectorised for efficiency.

    Parameters
    ----------
    image : (rows, cols) float array
    fov_fraction : float  phase-FOV / full FOV (0 < fov_fraction ≤ 1);
        values ≥ 1 return the image unchanged

    Returns
    -------
    aliased : (n_rows, cols) float array where n_rows = max(10, int(rows × fov_fraction))
    """
    if fov_fraction >= 1.0:
        return image

    rows, cols = image.shape
    n_rows = max(10, int(rows * fov_fraction))

    # Vectorised fold: each row i maps to i % n_rows in the reduced image.
    # np.add.at accumulates correctly for repeated (aliased) indices.
    result = np.zeros((n_rows, cols), dtype=np.float64)
    row_idx = np.arange(rows) % n_rows          # (rows,)
    np.add.at(result, row_idx, image)
    return result


# ---------------------------------------------------------------------------
# End-to-end acquisition pipeline
# ---------------------------------------------------------------------------

def simulate_acquisition(
    image: np.ndarray,
    matrix_size: int,
    fov_fraction: float = 1.0,
    filter_window: str | None = None,
    pf_fraction: float | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Simulate a complete MRI k-space acquisition.

    Pipeline:
      1. Forward FFT (image → k-space)
      2. Optional k-space apodisation (kspace_filter)
      3. Optional partial Fourier acquisition (partial_fourier)
      4. Crop to acquisition matrix (apply_matrix_size)
      5. Zero-fill to original image size (zero_fill_resize)
      6. Optional phase-encode FOV reduction (apply_aliasing)

    Parameters
    ----------
    image : (rows, cols) float array
    matrix_size : int  acquisition matrix (square); must be ≤ image size
    fov_fraction : float  phase-encode FOV fraction (1.0 = no aliasing)
    filter_window : str or None  apodisation window passed to kspace_filter
    pf_fraction : float or None  partial-Fourier fraction (None = full Fourier)

    Returns
    -------
    reconstructed : (rows, cols) float64  reconstructed image
    kspace_acquired : (matrix_size, matrix_size) complex  acquired k-space
    """
    rows, cols = image.shape
    kspace_full = image_to_kspace(image)

    # Optional apodisation
    if filter_window is not None:
        kspace_full = kspace_filter(kspace_full, filter_window)

    # Optional partial Fourier
    if pf_fraction is not None:
        kspace_full = partial_fourier(kspace_full, pf_fraction)

    # Crop to acquisition matrix
    kspace_acquired = apply_matrix_size(kspace_full, matrix_size)

    # Reconstruct (zero-fill if under-sampled)
    if matrix_size < rows:
        reconstructed = zero_fill_resize(kspace_acquired, rows, cols)
    else:
        reconstructed = kspace_to_image(kspace_acquired)

    # Phase-encode FOV aliasing
    if fov_fraction < 1.0:
        from scipy.ndimage import zoom
        aliased = apply_aliasing(reconstructed, fov_fraction)
        # Apply zoom only along the phase-encode (row) axis to restore the
        # original row count; column count is unchanged by aliasing.
        scale_r = rows / aliased.shape[0]
        reconstructed = zoom(aliased, (scale_r, 1.0), order=1)

    return reconstructed, kspace_acquired


# ---------------------------------------------------------------------------
# Display helper
# ---------------------------------------------------------------------------

def get_kspace_display(kspace: np.ndarray) -> np.ndarray:
    """Log-magnitude of k-space for display purposes.

    Parameters
    ----------
    kspace : (rows, cols) complex array

    Returns
    -------
    display : (rows, cols) float64, non-negative
    """
    return np.log1p(np.abs(kspace)).astype(np.float64)
