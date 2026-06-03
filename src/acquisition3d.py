"""True 3-D (slab) acquisition — kz phase-encoding and 3-D FFT reconstruction.

The 2-D pipeline (``kspace.simulate_acquisition``) acquires one slice at a time,
and the simulator's "slice thickness" merely *averages* adjacent slices. This
models a genuine 3-D acquisition: a slab is excited and phase-encoded along the
slice (kz) direction as well as the in-plane (kx, ky) directions, then
reconstructed with a 3-D FFT into thin contiguous partitions. That yields true
through-plane resolution, kz partial Fourier, the imperfect-slab edge profile,
and the √Nz SNR advantage a 3-D encode has over a single 2-D slice — none of
which the 2-D path can represent.

All transforms keep DC centred (``fftshift(fftn(ifftshift(.)))``), matching the
2-D conventions in ``kspace.py``.
"""
import numpy as np

from kspace import partial_fourier   # ndim-agnostic; reused for the ky / kz axes


def volume_to_kspace(volume: np.ndarray) -> np.ndarray:
    """3-D FFT with DC shifted to the centre of k-space."""
    return np.fft.fftshift(np.fft.fftn(np.fft.ifftshift(volume))).astype(complex)


def kspace_to_volume(kspace: np.ndarray) -> np.ndarray:
    """Inverse 3-D FFT; returns a non-negative magnitude volume."""
    return np.abs(np.fft.fftshift(np.fft.ifftn(np.fft.ifftshift(kspace)))).astype(np.float64)


def slab_excitation_profile(n_partitions: int, sharpness: float = 0.85) -> np.ndarray:
    """Through-plane RF slab-excitation weighting (1-D, length ``n_partitions``).

    A real 3-D slab is not excited uniformly: the profile is a flat-ish top with
    soft, attenuated edges, so the outermost partitions are darker. ``sharpness``
    in (0, 1] sets how square the profile is — 1 ≈ flat top with a thin roll-off,
    lower values give a rounder, more gaussian profile. Always normalised to a
    peak of 1.
    """
    n = int(n_partitions)
    if n <= 1:
        return np.ones(max(1, n), dtype=float)
    x = np.linspace(-1.0, 1.0, n)                       # normalised slab position
    s = float(np.clip(sharpness, 0.05, 1.0))
    order = 2.0 + 16.0 * s                              # super-gaussian exponent
    width = 0.70 + 0.18 * s                             # flat-top half-width
    prof = np.exp(-(np.abs(x) / width) ** order)
    return (prof / prof.max()).astype(float)


def snr_3d_gain(n_kz: int, nex: int = 1) -> float:
    """SNR advantage of a 3-D encode over one 2-D slice of equal in-plane
    resolution: every partition-encode samples the whole slab, so noise averages
    as √(n_kz · NEX)."""
    return float(np.sqrt(max(1, int(n_kz)) * max(1, int(nex))))


def _hamming_window_3d(shape: tuple[int, int, int]) -> np.ndarray:
    """Separable 3-D Hamming apodisation window centred on k-space."""
    w = [np.hamming(max(1, n)) if n > 1 else np.ones(1) for n in shape]
    return np.einsum("i,j,k->ijk", w[0], w[1], w[2])


def _center_crop_3d(kspace: np.ndarray, shape: tuple[int, int, int]) -> np.ndarray:
    """Central crop of a DC-centred k-space to ``shape`` (per-axis ≤ current)."""
    sl = []
    for full, want in zip(kspace.shape, shape, strict=True):
        want = min(want, full)
        start = (full - want) // 2
        sl.append(slice(start, start + want))
    return kspace[tuple(sl)]


def _zero_fill_3d(kspace: np.ndarray, shape: tuple[int, int, int]) -> np.ndarray:
    """Zero-fill a DC-centred k-space back up to ``shape`` (interpolating recon)."""
    out = np.zeros(shape, dtype=complex)
    out_sl, in_sl = [], []
    for full_out, cur in zip(shape, kspace.shape, strict=True):
        take = min(full_out, cur)
        out_sl.append(slice((full_out - take) // 2, (full_out - take) // 2 + take))
        in_sl.append(slice((cur - take) // 2, (cur - take) // 2 + take))
    out[tuple(out_sl)] = kspace[tuple(in_sl)]
    return out


def acquire_3d(
    signal_slab: np.ndarray,
    matrix_xy: int,
    n_kz: int,
    pf_ky: float | None = None,
    pf_kz: float | None = None,
    filter_window: str | None = None,
    profile: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Acquire and reconstruct a 3-D slab.

    Pipeline (mirrors the 2-D ``simulate_acquisition`` but in 3-D):
      0. Optional slab-excitation weighting along the partition (kz) axis.
      1. Forward 3-D FFT (slab → k-space).
      2. Optional separable apodisation.
      3. Optional partial Fourier in ky (axis 1) and kz (axis 0).
      4. Crop to the acquisition matrix ``(n_kz, matrix_xy, matrix_xy)`` — this
         sets the in-plane and **through-plane** resolution.
      5. Zero-fill back to the slab shape and inverse 3-D FFT.

    Parameters
    ----------
    signal_slab : (Nz, H, W) float  rendered signal slab (Nz partitions)
    matrix_xy : int  in-plane acquisition matrix (square)
    n_kz : int  number of kz partition-encodes (through-plane resolution)
    pf_ky, pf_kz : float or None  partial-Fourier fraction in ky / kz
    filter_window : 'hamming' or None  k-space apodisation
    profile : (Nz,) or None  slab-excitation weighting applied before encoding

    Returns
    -------
    recon : (Nz, H, W) float64  reconstructed slab (magnitude)
    kspace_acquired : (n_kz, matrix_xy, matrix_xy) complex  acquired samples
    """
    slab = np.asarray(signal_slab, dtype=float)
    if slab.ndim != 3:
        raise ValueError(f"signal_slab must be 3-D, got shape {slab.shape}")
    Nz, H, W = slab.shape
    if profile is not None:
        slab = slab * np.asarray(profile, dtype=float)[:, None, None]

    kspace = volume_to_kspace(slab)
    if filter_window == "hamming":
        kspace = kspace * _hamming_window_3d(kspace.shape)
    if pf_ky is not None:
        kspace = partial_fourier(kspace, pf_ky, axis=1)
    if pf_kz is not None:
        kspace = partial_fourier(kspace, pf_kz, axis=0)

    target = (min(int(n_kz), Nz), min(int(matrix_xy), H), min(int(matrix_xy), W))
    kspace_acquired = _center_crop_3d(kspace, target)
    recon = kspace_to_volume(_zero_fill_3d(kspace_acquired, (Nz, H, W)))
    return recon, kspace_acquired
