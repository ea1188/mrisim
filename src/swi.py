"""Susceptibility-Weighted Imaging (SWI).

A long-TE gradient-echo **magnitude** image is multiplied by a **phase mask**
derived from the local field, so that paramagnetic sources — venous (deoxy)
blood, microbleeds, iron, calcium — accumulate negative phase and are darkened.
The phase is first high-pass filtered (homodyne) to strip the smooth background
field, leaving only the local susceptibility phase. A minimum-intensity
projection over a slab gives the SWI venogram.

References: Haacke et al., MRM 2004;52:612 (SWI); Reichenbach et al. 1997.
All functions are pure (numpy/scipy); the Simulator builds the magnitude and the
field, then calls :func:`swi_combine`.
"""
import numpy as np
from scipy.ndimage import gaussian_filter, minimum_filter1d


def field_to_phase(field_hz: np.ndarray, te_ms: float) -> np.ndarray:
    """Accumulated GRE phase (radians, wrapped to (−π, π]) from an off-resonance
    field at echo time ``te_ms``:  φ = 2π·Δf·TE."""
    ph = 2.0 * np.pi * np.asarray(field_hz, dtype=float) * (te_ms * 1e-3)
    return (ph + np.pi) % (2.0 * np.pi) - np.pi


def homodyne_highpass(phase: np.ndarray, sigma: float = 8.0) -> np.ndarray:
    """High-pass the phase to remove the smooth background field, keeping the
    local susceptibility phase. Operates on the complex signal e^{iφ} (divided by
    its low-pass) to avoid phase-wrap artefacts, then takes the angle."""
    if sigma <= 0:
        return np.asarray(phase, dtype=float)
    c = np.exp(1j * np.asarray(phase, dtype=float))
    lp = gaussian_filter(c.real, sigma) + 1j * gaussian_filter(c.imag, sigma)
    lp = lp / np.maximum(np.abs(lp), 1e-6)
    return np.angle(c * np.conj(lp))


def phase_mask(phase: np.ndarray, power: int = 4) -> np.ndarray:
    """Negative-phase mask in [0, 1], raised to ``power``.

    f(φ) = (π + φ)/π for φ ∈ [−π, 0)  (1 at φ=0, 0 at φ=−π), and 1 for φ ≥ 0.
    Multiplying the magnitude by f^power darkens negative-phase (paramagnetic)
    voxels while leaving the rest untouched — the standard negative SWI mask."""
    phase = np.asarray(phase, dtype=float)
    m = np.clip((np.pi + phase) / np.pi, 0.0, 1.0)
    m = np.where(phase >= 0.0, 1.0, m)
    return m ** int(power)


def swi_combine(magnitude: np.ndarray, phase: np.ndarray, power: int = 4,
                hp_sigma: float = 8.0) -> np.ndarray:
    """SWI image = magnitude × phase_mask(high-pass(phase))^power."""
    hp = homodyne_highpass(phase, hp_sigma)
    return np.asarray(magnitude, dtype=float) * phase_mask(hp, power)


def min_ip(volume: np.ndarray, axis: int = 0, slab: int = 8) -> np.ndarray:
    """Minimum-intensity projection over a moving slab (the SWI venogram): each
    voxel becomes the minimum over ``slab`` neighbours along ``axis``. Returns a
    volume of the same shape."""
    return minimum_filter1d(np.asarray(volume, dtype=float),
                            size=max(1, int(slab)), axis=int(axis), mode="nearest")
