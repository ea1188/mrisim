import numpy as np

# Tissue properties: T1 (ms), T2 (ms), proton density (0-1)
TISSUES = {
    "white_matter": {"T1": 830, "T2": 80, "PD": 0.65},
    "gray_matter":  {"T1": 1330, "T2": 100, "PD": 0.80},
    "csf":          {"T1": 4500, "T2": 2200, "PD": 1.00},
    "fat":          {"T1": 370, "T2": 60, "PD": 0.95},
    "muscle":       {"T1": 1400, "T2": 35, "PD": 0.75},
}

def spin_echo_signal(T1: float, T2: float, PD: float, TR: float, TE: float) -> float:
    """Calculate spin echo signal intensity."""
    signal = PD * (1 - np.exp(-TR / T1)) * np.exp(-TE / T2)
    return signal

def gradient_echo_signal(T1: float, T2star: float, PD: float, TR: float, TE: float,
                          flip_angle_deg: float) -> float:
    """Calculate spoiled gradient echo signal intensity."""
    alpha = np.radians(flip_angle_deg)
    E1 = np.exp(-TR / T1)
    denom = 1.0 - np.cos(alpha) * E1
    numer = PD * np.sin(alpha) * (1.0 - E1) * np.exp(-TE / T2star)
    # Guard against 0/0 (flip_angle=0 and TR→0): replace near-zero denom with 1 so
    # the division is safe, then force the result to 0 via np.where.
    safe_denom = np.where(np.abs(denom) < 1e-12, 1.0, denom)
    signal = np.where(np.abs(denom) < 1e-12, 0.0, numer / safe_denom)
    return float(signal) if np.ndim(signal) == 0 else signal  # type: ignore[return-value]

def inversion_recovery_signal(T1: float, T2: float, PD: float, TR: float, TE: float,
                               TI: float) -> float:
    """Calculate inversion recovery signal intensity."""
    signal = PD * abs(1 - 2 * np.exp(-TI / T1) + np.exp(-TR / T1)) * np.exp(-TE / T2)
    return signal

def balanced_ssfp_signal(T1: float, T2: float, PD: float, TR: float, TE: float,
                         flip_angle_deg: float) -> float:
    """On-resonance balanced SSFP (bSSFP / TrueFISP / FIESTA) steady-state signal.

    Unlike spoiled GRE, the transverse magnetization is refocused every TR, giving
    the characteristic high signal wherever T2/T1 is large — fluid, fat and blood
    are all bright. (Banding from off-resonance is applied separately.)
    """
    a = np.radians(flip_angle_deg)
    E1 = np.exp(-TR / np.maximum(T1, 1e-6))
    E2 = np.exp(-TR / np.maximum(T2, 1e-6))
    denom = 1.0 - (E1 - E2) * np.cos(a) - E1 * E2
    safe = np.where(np.abs(denom) < 1e-9, 1.0, denom)
    sig = PD * np.sin(a) * (1.0 - E1) / safe * np.exp(-TE / np.maximum(T2, 1e-6))
    sig = np.where(np.abs(denom) < 1e-9, 0.0, sig)
    return float(sig) if np.ndim(sig) == 0 else sig  # type: ignore[return-value]


def ssfp_banding(off_resonance_hz: "float | np.ndarray", TR_ms: float,
                 E2: "float | np.ndarray", null_width: float = 0.6) -> "np.ndarray":
    """bSSFP off-resonance banding factor (0–1).

    The balanced steady state has a broad, flat passband (factor ≈ 1) with narrow
    dark signal nulls where the per-TR phase β = 2π·Δf·TR passes through ±π
    (Δf ≈ ±1/2TR). Long-T2 tissue (E2 → 1) bands deepest. Longer TR packs more
    bands across a given off-resonance range.
    """
    beta = 2.0 * np.pi * np.asarray(off_resonance_hz, dtype=float) * (TR_ms / 1000.0)
    phi = np.mod(beta, 2.0 * np.pi)          # [0, 2π)
    d = np.abs(phi - np.pi)                   # angular distance to the null at π
    return 1.0 - E2 * np.exp(-(d / null_width) ** 2)


def calculate_snr(signal: float, bandwidth: float, voxel_volume: float, NEX: float) -> float:
    """Estimate relative SNR."""
    noise = np.sqrt(bandwidth)
    snr = signal * voxel_volume * np.sqrt(NEX) / noise
    return snr

def calculate_scan_time(TR: float, phase_encodes: int, NEX: float,
                         ETL: int = 1, acceleration: int = 1) -> float:
    """Calculate scan time in seconds."""
    time_ms = TR * phase_encodes * NEX / (ETL * acceleration)
    return time_ms / 1000

# Quick test
if __name__ == "__main__":
    TR, TE = 500, 20
    print(f"Spin Echo | TR={TR}ms, TE={TE}ms")
    print("-" * 40)
    for name, props in TISSUES.items():
        sig = spin_echo_signal(props["T1"], props["T2"], props["PD"], TR, TE)
        print(f"  {name:15s}: signal = {sig:.4f}")
