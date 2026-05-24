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
    signal = PD * np.sin(alpha) * (1 - E1) / (1 - np.cos(alpha) * E1) * np.exp(-TE / T2star)
    return signal

def inversion_recovery_signal(T1: float, T2: float, PD: float, TR: float, TE: float,
                               TI: float) -> float:
    """Calculate inversion recovery signal intensity."""
    signal = PD * abs(1 - 2 * np.exp(-TI / T1) + np.exp(-TR / T1)) * np.exp(-TE / T2)
    return signal

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
