"""B0 field map generation and off-resonance effects for MRI simulation."""

import numpy as np
from scipy.ndimage import map_coordinates

GAMMA_HZ_T = 42.577e6  # proton gyromagnetic ratio / 2π  (Hz/T)

# Bulk susceptibility values in ppm (SI convention, relative to water).
# Labels follow the current tissue_db / atlas scheme (0–21); air-filled structures
# (background, gas, bowel lumen, lungs) are paramagnetic vs tissue (~+0.36 ppm) and
# are the dominant off-resonance source (sinuses, chest, abdomen).
SUSCEPTIBILITY_PPM = {
    0:  0.00,   # background / air (no tissue)
    1: -9.05,   # CSF
    2: -9.05,   # gray matter
    3: -9.05,   # white matter
    4: -8.86,   # fat
    5: -9.05,   # bone (synthetic-brain skull)
    6: -9.05,   # muscle / soft tissue generic
    7: -9.05,   # liver
    8: -9.05,   # spleen
    9: -9.05,   # kidney cortex
    10: -9.05,  # kidney medulla
    11: -9.05,  # blood / vessel
    12: +0.36,  # gas — air-like
    13: -11.1,  # cortical bone
    14: -9.05,  # marrow
    15: -9.05,  # cartilage / intervertebral disc
    16: -9.05,  # spinal cord
    17: +0.36,  # bowel (luminal gas) — air-like
    18: +0.36,  # lung — air-filled
    19: -9.05,  # pancreas
    20: -9.05,  # heart / myocardium
    21: -9.05,  # soft tissue / gland (prostate, adrenal, thyroid)
    # Demo pathologies (brain-only). The microhaemorrhage is strongly paramagnetic
    # (blood-breakdown products) → a large susceptibility jump from tissue that
    # blooms dark on SWI / gradient echo. The others are tissue-like so they don't
    # spuriously bloom (an absent label would default to χ=0, ~9 ppm off tissue).
    23: -9.05,  # WM lesion
    24: -9.05,  # acute infarct
    25: -8.40,  # microhaemorrhage — paramagnetic (hemosiderin ~+0.65 ppm vs tissue), blooms dark on SWI
    26: -9.05,  # tumour
    27: -9.05,  # abscess core
    28: -9.05,  # abscess rim
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _chi_vol(label_vol: np.ndarray) -> np.ndarray:
    """Convert integer label volume to susceptibility map (ppm)."""
    out = np.zeros(label_vol.shape, dtype=np.float64)
    for lab, chi in SUSCEPTIBILITY_PPM.items():
        out[label_vol == lab] = chi
    return out


def _dipole_kernel(
    shape: tuple[int, ...],
    voxel_size: tuple[float, ...] = (1., 1., 1.),
) -> np.ndarray:
    """Dipole kernel K(k) = 1/3 - kz² / |k|² in k-space.

    DC component is set to 0 (mean susceptibility does not shift the
    reference frequency).  Axes follow volume convention: axis 0 = Z (S/I),
    axis 1 = Y (A/P), axis 2 = X (L/R).

    Parameters
    ----------
    shape : tuple of int  (nz, ny, nx)
    voxel_size : (sz, sy, sx) in mm

    Returns
    -------
    K : ndarray, shape == shape, float64
    """
    nz, ny, nx = shape
    sz, sy, sx = voxel_size

    # Frequency axes in cycles/mm (numpy rfft convention via fftfreq)
    kz = np.fft.fftfreq(nz, d=sz).reshape(-1, 1, 1)
    ky = np.fft.fftfreq(ny, d=sy).reshape(1, -1, 1)
    kx = np.fft.fftfreq(nx, d=sx).reshape(1, 1, -1)

    k2 = kz**2 + ky**2 + kx**2
    with np.errstate(invalid="ignore", divide="ignore"):
        K = 1.0 / 3.0 - kz**2 / k2
    K[k2 == 0] = 0.0  # DC = 0
    return K


# ---------------------------------------------------------------------------
# Public: B0 map generators
# ---------------------------------------------------------------------------

def susceptibility_b0_map(
    label_vol: np.ndarray,
    voxel_size: tuple[float, ...] = (1., 1., 1.),
    field_strength_T: float = 1.5,
) -> np.ndarray:
    """Compute B0 field map from a label volume via dipole convolution.

    Uses the standard MRI susceptibility forward model:
        ΔB0 = B0 · IFFT( FFT(χ) · K )
    where K is the dipole kernel and χ is the susceptibility in ppm (scaled
    to dimensionless by 1e-6).

    Parameters
    ----------
    label_vol : ndarray int, shape (nz, ny, nx)
    voxel_size : (sz, sy, sx) mm
    field_strength_T : float  (e.g. 1.5 or 3.0)

    Returns
    -------
    b0_hz : ndarray float64, shape (nz, ny, nx)  [Hz]
    """
    return field_from_chi(_chi_vol(label_vol), voxel_size, field_strength_T)


def field_from_chi(
    chi_ppm: np.ndarray,
    voxel_size: tuple[float, ...] = (1., 1., 1.),
    field_strength_T: float = 1.5,
) -> np.ndarray:
    """B0 field map (Hz) from a susceptibility map (ppm) via the dipole forward
    model ΔB0 = B0·IFFT(FFT(χ)·K). Exposed so callers can build a custom χ — e.g.
    SWI adding paramagnetic venous blood on top of the tissue susceptibility."""
    chi = np.asarray(chi_ppm, dtype=np.float64) * 1e-6   # ppm → dimensionless
    K = _dipole_kernel(chi.shape, voxel_size)
    db0_T = field_strength_T * np.real(np.fft.ifftn(np.fft.fftn(chi) * K))
    return db0_T * GAMMA_HZ_T


def polynomial_b0_map(
    shape: tuple[int, ...],
    voxel_size: tuple[float, ...] = (1., 1., 1.),
    linear: float | np.ndarray = 0.,
    quadratic: float | np.ndarray = 0.,
) -> np.ndarray:
    """Smooth polynomial B0 variation (shimming residuals).

    Models a first + second-order shim residual:
        ΔB0(z,y,x) = Σ_i (L_i · p_i) + Σ_i (Q_i · p_i²)
    where p_i is the physical coordinate in mm along each axis.

    Parameters
    ----------
    shape : (nz, ny, nx) or any n-D shape
    voxel_size : same length as shape, mm per voxel per axis
    linear : Hz/mm per axis (same order as shape)
    quadratic : Hz/mm² per axis

    Returns
    -------
    b0_hz : ndarray float64, shape == shape
    """
    ndim = len(shape)
    vox = np.broadcast_to(voxel_size, (ndim,))
    lin = np.broadcast_to(linear,    (ndim,))
    quad = np.broadcast_to(quadratic, (ndim,))

    coords = [np.arange(s, dtype=float) * v - (s - 1) / 2.0 * v
              for s, v in zip(shape, vox, strict=False)]
    grids = np.meshgrid(*coords, indexing="ij")

    b0 = np.zeros(shape, dtype=np.float64)
    for g, L, Q in zip(grids, lin, quad, strict=False):
        b0 += L * g + Q * g**2
    return b0


def gaussian_b0_map(
    shape: tuple[int, ...],
    voxel_size: tuple[float, ...] = (1., 1., 1.),
    center: list[float] | np.ndarray | None = None,
    amplitude_hz: float = 100.0,
    fwhm_mm: float = 30.0,
) -> np.ndarray:
    """Localised Gaussian B0 distortion (e.g. metallic implant).

    Parameters
    ----------
    shape : tuple of int
    voxel_size : mm per voxel, same length as shape
    center : physical center in mm (defaults to volume centre)
    amplitude_hz : peak off-resonance in Hz
    fwhm_mm : full-width at half-maximum of the Gaussian

    Returns
    -------
    b0_hz : ndarray float64, shape == shape
    """
    ndim = len(shape)
    vox = np.broadcast_to(voxel_size, (ndim,))
    sigma2 = (fwhm_mm / (2.0 * np.sqrt(2.0 * np.log(2.0))))**2

    if center is None:
        center = [(s - 1) / 2.0 * v for s, v in zip(shape, vox, strict=False)]
    center = np.asarray(center, dtype=float)

    coords = [np.arange(s, dtype=float) * v for s, v in zip(shape, vox, strict=False)]
    grids = np.meshgrid(*coords, indexing="ij")

    r2 = sum((g - c)**2 for g, c in zip(grids, center, strict=False))
    return amplitude_hz * np.exp(-r2 / (2.0 * sigma2))


# ---------------------------------------------------------------------------
# Public: off-resonance effects on signal
# ---------------------------------------------------------------------------

def b0_lineshape_factor(
    b0_slice_hz: np.ndarray,
    TE_ms: float,
    voxel_size_2d: tuple[float, float] = (1., 1.),
) -> np.ndarray:
    """Intravoxel dephasing factor [0, 1] per pixel.

    Estimates the B0 gradient across each voxel using finite differences,
    converts to frequency spread ΔF (Hz), then:
        factor = |sinc(ΔF · TE)|
    where sinc(x) = sin(πx)/(πx) (numpy convention).

    Parameters
    ----------
    b0_slice_hz : 2-D ndarray  (rows, cols)  in Hz
    TE_ms : float  echo time in ms
    voxel_size_2d : (row_mm, col_mm)

    Returns
    -------
    factor : ndarray float64, shape == b0_slice_hz.shape, values in [0, 1]
    """
    TE_s = TE_ms * 1e-3
    gy, gx = np.gradient(b0_slice_hz,
                         voxel_size_2d[0], voxel_size_2d[1])
    sy, sx = voxel_size_2d
    # frequency spread across one voxel along each axis
    delta_f = np.sqrt((gy * sy)**2 + (gx * sx)**2)
    return np.abs(np.sinc(delta_f * TE_s))  # numpy sinc = sin(πx)/(πx)


def apply_offresonance(
    signal_image: np.ndarray,
    b0_slice_hz: np.ndarray,
    TE_ms: float,
    sequence: str = "GRE",
    voxel_size_2d: tuple[float, float] = (1., 1.),
) -> np.ndarray:
    """Apply intravoxel dephasing to a 2-D MR signal image.

    Spin echo (SE, IR) refocuses static field inhomogeneity → image unchanged.
    Gradient echo (GRE) multiplies by the intravoxel dephasing factor.

    Parameters
    ----------
    signal_image : 2-D ndarray
    b0_slice_hz : 2-D ndarray  (same shape)  in Hz
    TE_ms : float
    sequence : "SE" | "IR" | "GRE"
    voxel_size_2d : (row_mm, col_mm)

    Returns
    -------
    modulated : ndarray, same shape and dtype as signal_image
    """
    seq = sequence.upper()
    if seq in ("SE", "IR"):
        return signal_image.copy()
    factor = b0_lineshape_factor(b0_slice_hz, TE_ms, voxel_size_2d)
    return signal_image * factor


# ---------------------------------------------------------------------------
# Public: readout geometric distortion
# ---------------------------------------------------------------------------

def readout_pixel_shift(b0_slice_hz: np.ndarray, bandwidth_hz_per_pixel: float) -> np.ndarray:
    """Pixel shift map along the frequency-encode direction.

    Parameters
    ----------
    b0_slice_hz : ndarray  in Hz
    bandwidth_hz_per_pixel : float  (receiver bandwidth / matrix size)

    Returns
    -------
    shift : ndarray, same shape, in pixels
    """
    return b0_slice_hz / bandwidth_hz_per_pixel


def apply_readout_shift(
    image: np.ndarray,
    b0_slice_hz: np.ndarray,
    bandwidth_hz_per_pixel: float,
    freq_encode_axis: int = 1,
) -> np.ndarray:
    """Geometrically distort an image by the readout pixel shift.

    Uses nearest-neighbour interpolation (order=0) to preserve label
    integer values; pass a float image to get smooth output.

    Parameters
    ----------
    image : 2-D ndarray
    b0_slice_hz : 2-D ndarray  same shape
    bandwidth_hz_per_pixel : float
    freq_encode_axis : 0 (rows) or 1 (cols)

    Returns
    -------
    distorted : ndarray, same shape
    """
    shift = readout_pixel_shift(b0_slice_hz, bandwidth_hz_per_pixel)
    rows, cols = np.indices(image.shape, dtype=float)
    if freq_encode_axis == 1:
        cols = cols + shift
    else:
        rows = rows + shift
    coords = np.array([rows.ravel(), cols.ravel()])
    distorted = map_coordinates(image.astype(float), coords,
                                order=1, mode="constant", cval=0.0)
    return distorted.reshape(image.shape)
