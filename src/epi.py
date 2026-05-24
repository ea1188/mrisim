"""EPI (Echo Planar Imaging) k-space trajectory and artifact simulation."""

import numpy as np
from scipy.ndimage import map_coordinates

# ---------------------------------------------------------------------------
# k-space trajectory
# ---------------------------------------------------------------------------

def epi_trajectory(n_freq, n_phase, esp_ms=0.5):
    """Generate a Cartesian EPI k-space trajectory.

    Odd phase-encode lines are acquired right-to-left (reversed readout),
    producing the alternating sign pattern that causes Nyquist ghosting
    when there is a constant phase error between even and odd lines.

    Parameters
    ----------
    n_freq : int  number of frequency-encode samples per line
    n_phase : int  number of phase-encode lines (= EPI factor)
    esp_ms : float  echo spacing in ms

    Returns
    -------
    kx : (n_phase, n_freq) float  k-space x-coordinate in units of 1/FOV
    ky : (n_phase, n_freq) float  k-space y-coordinate
    t  : (n_phase, n_freq) float  acquisition time in ms of each sample
    """
    kx_line = np.linspace(-n_freq / 2, n_freq / 2 - 1, n_freq)
    ky_vals = np.linspace(-n_phase / 2, n_phase / 2 - 1, n_phase)

    kx = np.empty((n_phase, n_freq))
    ky = np.empty((n_phase, n_freq))
    t  = np.empty((n_phase, n_freq))

    for i in range(n_phase):
        kx[i] = kx_line if (i % 2 == 0) else kx_line[::-1]
        ky[i] = ky_vals[i]
        t[i]  = i * esp_ms + np.linspace(0., esp_ms, n_freq, endpoint=False)

    return kx, ky, t


def epi_phase_correction(kspace, n_ref_lines=3):
    """Estimate and remove linear phase error between even and odd EPI lines.

    Uses reference lines (acquired without phase encoding) to estimate
    the zeroth- and first-order phase offsets between polarity groups,
    then applies the correction to all lines.

    Parameters
    ----------
    kspace : (n_phase, n_freq) complex  raw EPI k-space
    n_ref_lines : int  number of reference lines used for estimation

    Returns
    -------
    corrected : (n_phase, n_freq) complex
    """
    n_phase, n_freq = kspace.shape
    # Use the first few even and odd lines as references
    even_lines = kspace[0:2 * n_ref_lines:2]
    odd_lines  = kspace[1:2 * n_ref_lines:2]

    # Average phase difference between reversed odd and even lines
    odd_rev = odd_lines[:, ::-1]
    phase_diff = np.angle(
        np.mean(odd_rev * np.conj(even_lines), axis=0))  # (n_freq,)

    # Fit zeroth + first order to the phase difference
    x = np.arange(n_freq, dtype=float) - n_freq / 2.
    coeffs = np.polyfit(x, phase_diff, 1)
    linear_phase = np.polyval(coeffs, x)

    corrected = kspace.copy()
    for i in range(n_phase):
        if i % 2 == 1:
            corrected[i] = kspace[i] * np.exp(-1j * linear_phase)
    return corrected


# ---------------------------------------------------------------------------
# Nyquist (N/2) ghost
# ---------------------------------------------------------------------------

def add_nyquist_ghost(kspace, phase_offset_rad=0.1, linear_phase_rad_per_sample=0.0):
    """Introduce a constant and/or linear phase error on odd EPI lines.

    This creates the N/2 (Nyquist) ghost: a shifted copy of the object
    displaced by FOV/2 in the phase-encode direction.

    Parameters
    ----------
    kspace : (n_phase, n_freq) complex
    phase_offset_rad : float  constant phase added to odd lines
    linear_phase_rad_per_sample : float  linear phase ramp on odd lines

    Returns
    -------
    ghosted : (n_phase, n_freq) complex
    """
    n_phase, n_freq = kspace.shape
    x = np.arange(n_freq, dtype=float)
    phase_ramp = phase_offset_rad + linear_phase_rad_per_sample * x
    ghosted = kspace.copy()
    for i in range(1, n_phase, 2):   # odd lines only
        ghosted[i] = kspace[i] * np.exp(1j * phase_ramp)
    return ghosted


def ghost_ratio(image):
    """Ghost-to-signal ratio: mean ghost intensity / mean object intensity.

    Assumes the ghost occupies the opposite half of the image in the
    phase-encode direction (axis 0).

    Parameters
    ----------
    image : (rows, cols) float or complex  magnitude image

    Returns
    -------
    gsr : float  in [0, 1]
    """
    mag = np.abs(image)
    rows = mag.shape[0]
    half = rows // 2
    signal_half = mag[:half]
    ghost_half  = mag[half:]
    s = signal_half.mean()
    g = ghost_half.mean()
    if s < 1e-12:
        return 0.0
    return float(g / s)


# ---------------------------------------------------------------------------
# B0-driven phase-encode distortion
# ---------------------------------------------------------------------------

def epi_b0_phase_error(b0_slice_hz, t_pe_ms):
    """Phase accrual map due to B0 at a given time along the EPI train.

    Each phase-encode line is acquired at a different time and thus
    accumulates a different B0 phase.

    Parameters
    ----------
    b0_slice_hz : (rows, cols) float  B0 map in Hz
    t_pe_ms : float  acquisition time of this phase-encode line in ms

    Returns
    -------
    phase_rad : (rows, cols) float
    """
    return 2.0 * np.pi * b0_slice_hz * t_pe_ms * 1e-3


def epi_distortion_map(b0_slice_hz, esp_ms, n_phase, bw_hz_per_pixel=None):
    """Pixel-shift map in the phase-encode direction due to B0 off-resonance.

    In EPI the effective bandwidth per pixel in phase is very small:
        BW_eff = 1 / (n_phase · esp)
    so even modest B0 offsets produce large shifts.

    Parameters
    ----------
    b0_slice_hz : (rows, cols) float  B0 map in Hz
    esp_ms : float  echo spacing in ms
    n_phase : int  number of phase-encode lines (EPI factor)
    bw_hz_per_pixel : float or None
        Override effective bandwidth. Defaults to 1 / (n_phase · esp_s).

    Returns
    -------
    shift_pixels : (rows, cols) float  positive = shift toward +PE direction
    """
    if bw_hz_per_pixel is None:
        bw_hz_per_pixel = 1.0 / (n_phase * esp_ms * 1e-3)
    return b0_slice_hz / bw_hz_per_pixel


def apply_epi_distortion(image, b0_slice_hz, esp_ms, n_phase,
                          bw_hz_per_pixel=None, phase_encode_axis=0):
    """Geometrically distort an image by the EPI B0 pixel-shift map.

    Parameters
    ----------
    image : 2-D ndarray
    b0_slice_hz : 2-D ndarray  same shape
    esp_ms : float
    n_phase : int
    bw_hz_per_pixel : float or None
    phase_encode_axis : 0 (rows, default) or 1 (cols)

    Returns
    -------
    distorted : ndarray, same shape as image, float64
    """
    shift = epi_distortion_map(b0_slice_hz, esp_ms, n_phase, bw_hz_per_pixel)
    rows, cols = np.indices(image.shape, dtype=float)
    if phase_encode_axis == 0:
        rows = rows + shift
    else:
        cols = cols + shift
    coords = np.array([rows.ravel(), cols.ravel()])
    distorted = map_coordinates(image.astype(float), coords,
                                order=1, mode="constant", cval=0.0)
    return distorted.reshape(image.shape)


# ---------------------------------------------------------------------------
# Simulate full EPI acquisition
# ---------------------------------------------------------------------------

def simulate_epi(signal_image, b0_slice_hz=None, esp_ms=0.5,
                 phase_offset_rad=0.0, linear_phase_rad_per_sample=0.0,
                 correct_ghost=False):
    """Simulate an EPI acquisition with optional B0 distortion and ghosting.

    Procedure:
      1. FFT the input image to k-space.
      2. Re-order lines according to the EPI alternating pattern.
      3. Apply B0 phase (one phase per line, accumulating over esp).
      4. Optionally add Nyquist phase error (odd-line phase offset).
      5. Optionally run epi_phase_correction to remove ghost.
      6. Reorder back, IFFT → reconstructed image.

    Parameters
    ----------
    signal_image : (rows, cols) float  ground-truth MR image
    b0_slice_hz : (rows, cols) float or None  B0 map in Hz
    esp_ms : float  echo spacing in ms
    phase_offset_rad : float  constant phase error on odd lines
    linear_phase_rad_per_sample : float  linear phase ramp on odd lines
    correct_ghost : bool  apply epi_phase_correction before recon

    Returns
    -------
    recon : (rows, cols) complex  reconstructed EPI image (take |·| for magnitude)
    kspace_epi : (rows, cols) complex  raw EPI k-space (before correction)
    """
    rows, cols = signal_image.shape

    # Ideal k-space via FFT (row = phase encode, col = frequency encode)
    kspace_ideal = np.fft.fftshift(np.fft.fft2(np.fft.ifftshift(signal_image)))

    # EPI reordering: odd lines are acquired reversed
    kspace_epi = kspace_ideal.copy()
    for i in range(1, rows, 2):
        kspace_epi[i] = kspace_ideal[i, ::-1]

    # B0 phase: each line acquired at time i * esp_ms
    if b0_slice_hz is not None:
        b0_kspace = np.fft.fftshift(np.fft.fft2(
            np.fft.ifftshift(signal_image * np.exp(
                2j * np.pi * b0_slice_hz * 0.0))))  # placeholder
        for i in range(rows):
            t_ms = i * esp_ms
            phase_map = epi_b0_phase_error(b0_slice_hz, t_ms)
            # Modulate image-space signal, then add to k-space via linearity
            b0_mod = signal_image * np.exp(1j * phase_map)
            ks_line = np.fft.fftshift(
                np.fft.fft(np.fft.ifftshift(b0_mod[i % rows])))
            if i % 2 == 1:
                kspace_epi[i] = ks_line[::-1]
            else:
                kspace_epi[i] = ks_line

    # Nyquist ghost
    if phase_offset_rad != 0.0 or linear_phase_rad_per_sample != 0.0:
        kspace_epi = add_nyquist_ghost(kspace_epi, phase_offset_rad,
                                        linear_phase_rad_per_sample)

    # Optional ghost correction
    kspace_recon = epi_phase_correction(kspace_epi) if correct_ghost else kspace_epi

    # Undo odd-line reversal before IFFT
    kspace_ordered = kspace_recon.copy()
    for i in range(1, rows, 2):
        kspace_ordered[i] = kspace_recon[i, ::-1]

    recon = np.fft.fftshift(np.fft.ifft2(np.fft.ifftshift(kspace_ordered)))
    return recon, kspace_epi


# ---------------------------------------------------------------------------
# T2* signal decay along echo train
# ---------------------------------------------------------------------------

def epi_t2star_decay(signal_image, T2star_map_ms, esp_ms, n_phase):
    """Apply T2* blurring along the phase-encode direction of EPI.

    Each phase-encode line is acquired at a different effective TE
    (i·esp_ms from the centre of k-space outward), causing T2*-driven
    signal decay that blurs the image in the phase-encode direction.

    Parameters
    ----------
    signal_image : (rows, cols) float  ground-truth image at TE_eff=0
    T2star_map_ms : (rows, cols) float  T2* map in ms
    esp_ms : float  echo spacing in ms
    n_phase : int  number of phase-encode lines

    Returns
    -------
    blurred : (rows, cols) float  T2*-blurred image in image space
    """
    kspace = np.fft.fftshift(np.fft.fft2(np.fft.ifftshift(signal_image)))
    # Decay weight for each phase-encode line (distance from centre of k-space)
    pe_indices = np.arange(n_phase)
    centre = n_phase / 2.0
    delta_te_ms = np.abs(pe_indices - centre) * esp_ms   # (n_phase,)

    # Reshape for broadcast: (n_phase, 1)
    decay_weights = np.exp(-delta_te_ms[:, np.newaxis]
                           / np.maximum(T2star_map_ms.mean(), 1.0))

    kspace_blurred = kspace * decay_weights
    blurred = np.abs(np.fft.fftshift(np.fft.ifft2(np.fft.ifftshift(kspace_blurred))))
    return blurred
