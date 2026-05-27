"""Fast Spin Echo (FSE/TSE) signal simulation with Extended Phase Graph (EPG).

Functions
---------
epg_signal           — signal at effective TE using full EPG echo-train simulation
compute_fse_echo_train — signal at every echo in the train (EPG-based)
fse_scan_time        — scan-time formula for FSE
fse_blurring_factor  — PSF FWHM broadening from T2 decay across the echo train
simulate_fse_image   — per-tissue FSE image with Gaussian phase-blur approximation
"""

import numpy as np
from scipy.ndimage import gaussian_filter


# ---------------------------------------------------------------------------
# Internal EPG engine
# ---------------------------------------------------------------------------

def _epg_run(
    T1: float,
    T2: float,
    PD: float,
    TR: float,
    ETL: int,
    echo_spacing: float,
    refocus_angle_deg: float = 180.0,
) -> np.ndarray:
    """EPG simulation of an FSE/CPMG echo train.

    Uses a reduced-state representation (tracking only F⁺[k] and Z[k]) that
    is valid for CPMG-style sequences where the refocusing pulses all share
    the same phase axis.  The Hermitian conjugate F⁻[k] = (F⁺[k])* is
    maintained automatically by the shift boundary condition.

    Parameters
    ----------
    T1, T2      : float  tissue relaxation times (ms)
    PD          : float  proton density (0–1)
    TR          : float  repetition time (ms); sets initial longitudinal Mz
    ETL         : int    echo train length
    echo_spacing: float  time between consecutive echoes (ms)
    refocus_angle_deg : float  refocusing flip angle in degrees (default 180)

    Returns
    -------
    signals : (ETL,) float64  magnitude signal at each echo (TE_n = n × ESP)
    """
    alpha_ref = np.deg2rad(refocus_angle_deg)
    ca2 = float(np.cos(alpha_ref / 2) ** 2)
    sa2 = float(np.sin(alpha_ref / 2) ** 2)
    sa  = float(np.sin(alpha_ref))
    ca  = float(np.cos(alpha_ref))

    tau = echo_spacing / 2.0            # half echo-spacing
    T1  = max(float(T1), 1e-9)
    T2  = max(float(T2), 1e-9)

    N = ETL + 2                         # maximum EPG state order needed
    Fp = np.zeros(N, dtype=complex)
    Z  = np.zeros(N, dtype=float)

    # Initial Mz after TR recovery (T1 weighting)
    M0 = float(PD) * (1.0 - np.exp(-TR / T1))

    # 90° excitation (phase Y = π/2): F⁺[0] = −M0, Z[0] = 0
    Fp[0] = -M0
    Z[0]  = 0.0

    E1 = np.exp(-tau / T1)
    E2 = np.exp(-tau / T2)
    dZ = M0 * (1.0 - E1)               # T1 recovery increment per half-ESP

    signals = np.zeros(ETL)

    for _ in range(ETL):
        # ---- Relax ESP/2 ------------------------------------------------
        Fp *= E2
        Z  *= E1
        Z[0] += dZ

        # ---- Gradient shift (+1 dephasing order) -------------------------
        # Fp_new[k] = Fp_old[k−1] for k≥1; Fp_new[0] = conj(Fp_old[1])
        fp1 = complex(Fp[1])
        Fp[1:] = Fp[:-1].copy()
        Fp[0]  = np.conj(fp1)

        # ---- RF refocusing pulse -----------------------------------------
        # General rotation (phi = 0, i.e., pulse along X):
        #   F⁺_new = cos²(α/2)·F⁺ + sin²(α/2)·(F⁺)* − i·sin(α)·Z
        #   Z_new  = sin(α)·Im(F⁺) + cos(α)·Z
        Fp_new  = ca2 * Fp + sa2 * np.conj(Fp) - 1j * sa * Z
        Z[:]    = sa * np.imag(Fp) + ca * Z
        Fp[:]   = Fp_new

        # ---- Gradient shift (+1 dephasing order) -------------------------
        fp1    = complex(Fp[1])
        Fp[1:] = Fp[:-1].copy()
        Fp[0]  = np.conj(fp1)

        # ---- Relax ESP/2 ------------------------------------------------
        Fp *= E2
        Z  *= E1
        Z[0] += dZ

        signals[_] = abs(Fp[0])

    return signals


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def epg_signal(
    T1: float,
    T2: float,
    PD: float,
    TR: float,
    TE_eff: float,
    ETL: int,
    echo_spacing: float,
    refocus_angle_deg: float = 180.0,
) -> float:
    """FSE signal at the effective TE using EPG echo-train simulation.

    Unlike the simple SE formula PD·(1−e^{−TR/T1})·e^{−TE/T2}, EPG correctly
    accounts for stimulated-echo contributions when the refocusing flip angle
    deviates from 180°, producing the characteristic echo-amplitude modulation
    seen in clinical FSE sequences.

    Parameters
    ----------
    T1, T2         : float  relaxation times (ms)
    PD             : float  proton density (0–1)
    TR             : float  repetition time (ms)
    TE_eff         : float  effective TE (ms) — centre of k-space echo
    ETL            : int    echo train length
    echo_spacing   : float  inter-echo spacing (ms)
    refocus_angle_deg : float  refocusing flip angle in degrees (default 180)

    Returns
    -------
    signal : float  non-negative signal magnitude
    """
    if PD == 0.0:
        return 0.0

    signals = _epg_run(T1, T2, PD, TR, ETL, echo_spacing, refocus_angle_deg)

    # Map TE_eff → echo index (1-based → 0-based array index)
    echo_idx = max(0, min(ETL - 1, round(TE_eff / echo_spacing) - 1))
    return float(signals[echo_idx])


def compute_fse_echo_train(
    T1: float,
    T2: float,
    PD: float,
    TR: float,
    ETL: int,
    echo_spacing: float,
    refocus_angle_deg: float = 180.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Compute FSE signal at every echo in the train using EPG.

    Parameters
    ----------
    T1, T2         : float  relaxation times (ms)
    PD             : float  proton density (0–1)
    TR             : float  repetition time (ms)
    ETL            : int    echo train length
    echo_spacing   : float  inter-echo spacing (ms)
    refocus_angle_deg : float  refocusing flip angle in degrees (default 180)

    Returns
    -------
    TE_values : (ETL,) float64  TE at each echo (ms)
    signals   : (ETL,) float64  magnitude signal at each echo
    """
    TE_values = np.arange(1, ETL + 1, dtype=float) * echo_spacing
    signals   = _epg_run(T1, T2, PD, TR, ETL, echo_spacing, refocus_angle_deg)
    return TE_values, signals


def fse_scan_time(
    TR: float,
    matrix_size: int,
    NEX: int,
    ETL: int,
    acceleration: int = 1,
) -> float:
    """FSE scan time (seconds).

    FSE reduces phase-encode time by ETL relative to SE:
    time = TR × (phase_encodes / ETL) × NEX / acceleration

    Parameters
    ----------
    TR           : float  repetition time (ms)
    matrix_size  : int    phase-encode matrix dimension
    NEX          : int    number of signal averages
    ETL          : int    echo train length
    acceleration : int    parallel-imaging acceleration factor (default 1)

    Returns
    -------
    time : float  scan time in seconds
    """
    phase_encodes = matrix_size
    time_ms = TR * (phase_encodes / ETL) * NEX / acceleration
    return time_ms / 1000.0


def fse_blurring_factor(
    ETL: int,
    echo_spacing: float,
    T2: float,
    refocus_angle_deg: float = 180.0,
) -> float:
    """PSF FWHM broadening in the phase-encode direction due to T2 decay.

    The echo-train amplitude modulation acts as a k-space apodisation window.
    EPG echo amplitudes are used as the window, and the resulting PSF FWHM
    is compared to the ideal (rect-window) FWHM to give a blurring factor.

    Parameters
    ----------
    ETL           : int    echo train length
    echo_spacing  : float  inter-echo spacing (ms)
    T2            : float  tissue T2 (ms)
    refocus_angle_deg : float  refocusing flip angle (default 180)

    Returns
    -------
    factor : float  FWHM ratio (≥ 1.0; 1.0 = no blurring)
    """
    # Use infinite T1 / TR to isolate T2 modulation
    _, amplitudes = compute_fse_echo_train(
        T1=1e9, T2=T2, PD=1.0, TR=1e9,
        ETL=ETL, echo_spacing=echo_spacing,
        refocus_angle_deg=refocus_angle_deg,
    )
    if amplitudes.max() == 0.0:
        return float(ETL)

    window = amplitudes / amplitudes.max()

    def _fwhm(w: np.ndarray) -> float:
        psf = np.abs(np.fft.fftshift(np.fft.ifft(np.fft.ifftshift(w))))
        if psf.max() == 0.0:
            return 1.0
        psf /= psf.max()
        above = psf >= 0.5
        if not above.any():
            return float(len(w))
        first = int(np.argmax(above))
        last  = int(len(above) - 1 - np.argmax(above[::-1]))
        return float(last - first + 1)

    actual_fwhm = _fwhm(window)
    ideal_fwhm  = _fwhm(np.ones(ETL))
    return max(1.0, actual_fwhm / max(ideal_fwhm, 1.0))


def simulate_fse_image(
    phantom_slice: np.ndarray,
    TR: float,
    TE_eff: float,
    ETL: int,
    echo_spacing: float,
    tissue_properties: dict,
    refocus_angle_deg: float = 180.0,
) -> np.ndarray:
    """Simulate an FSE image with T2 blurring in the phase-encode direction.

    Each tissue is assigned its EPG signal at TE_eff, then blurred along the
    phase-encode (row) axis by its **own** T2-dependent PSF broadening. This is
    per-tissue on purpose: a single global blur keyed to the shortest T2 in the
    slice (e.g. cortical bone, ~3 ms) would smear the entire image, even though
    that tissue has essentially no FSE signal. Long-T2 tissue (brain, CSF) stays
    sharp; only short-T2 (thin, near-signal-less) tissue blurs.

    Parameters
    ----------
    phantom_slice     : (rows, cols) integer label array
    TR, TE_eff        : float  scan parameters (ms)
    ETL, echo_spacing : int, float  echo-train parameters
    tissue_properties : dict  {label: {"T1": …, "T2": …, "PD": …}}
    refocus_angle_deg : float  refocusing flip angle (default 180)

    Returns
    -------
    image : (rows, cols) float64  simulated FSE magnitude image
    """
    image = np.zeros_like(phantom_slice, dtype=float)

    for label, props in tissue_properties.items():
        mask = phantom_slice == label
        if not np.any(mask):
            continue

        T1, T2, PD = float(props["T1"]), float(props["T2"]), float(props["PD"])
        signal = epg_signal(T1, T2, PD, TR, TE_eff, ETL, echo_spacing, refocus_angle_deg)

        tissue_img = np.where(mask, signal, 0.0)
        factor = fse_blurring_factor(ETL, echo_spacing, T2, refocus_angle_deg)
        sigma = (factor - 1.0) / 2.355      # excess FWHM (voxels) → Gaussian σ
        if sigma > 0.1:
            tissue_img = gaussian_filter(tissue_img, sigma=[sigma, 0.0])
        image += tissue_img

    return image
