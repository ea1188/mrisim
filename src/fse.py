import numpy as np

def epg_signal(T1, T2, PD, TR, TE_eff, ETL, echo_spacing):
    """Simplified Extended Phase Graph signal for FSE/TSE.
    
    In FSE, multiple echoes are collected per TR using 180° refocusing pulses.
    Each echo has different T2 weighting. The echo at TE_eff determines contrast.
    
    ETL: Echo Train Length (number of echoes per TR)
    echo_spacing: time between echoes (ms)
    TE_eff: effective TE (which echo fills center of k-space)
    
    The key tradeoff: longer ETL = faster scan but more T2 blurring.
    """
    # Signal at effective TE
    signal = PD * (1 - np.exp(-TR / T1)) * np.exp(-TE_eff / T2)
    return signal

def fse_scan_time(TR, matrix_size, NEX, ETL, acceleration=1):
    """Calculate FSE scan time.
    
    FSE is faster than SE by factor of ETL:
    Time = TR * (phase_encodes / ETL) * NEX / acceleration
    """
    phase_encodes = matrix_size
    time_ms = TR * (phase_encodes / ETL) * NEX / acceleration
    return time_ms / 1000  # seconds

def fse_blurring_factor(ETL, echo_spacing, T2):
    """Estimate T2 blurring in FSE.
    
    Later echoes in the train have more T2 decay.
    This causes blurring in the phase encode direction.
    Worse with: long ETL, long echo spacing, short T2.
    
    Returns a blurring factor (1.0 = no blurring, higher = more blur)
    """
    # Total readout time for the echo train
    train_duration = ETL * echo_spacing
    
    # Signal decay across the echo train
    decay_ratio = np.exp(-train_duration / T2)
    
    # Blurring factor: ratio of signal at end vs start of train
    # More decay = more blurring (PSF broadening)
    blurring = 1.0 + (1.0 - decay_ratio) * 0.5
    
    return blurring

def simulate_fse_image(phantom_slice, TR, TE_eff, ETL, echo_spacing, tissue_properties):
    """Simulate FSE image with T2 blurring effect.
    
    Returns the simulated image with ETL-dependent blurring.
    """
    from scipy.ndimage import gaussian_filter
    
    image = np.zeros_like(phantom_slice, dtype=float)
    max_blur = 0
    
    for label, props in tissue_properties.items():
        mask = phantom_slice == label
        if not np.any(mask):
            continue
        
        T1, T2, PD = props["T1"], props["T2"], props["PD"]
        
        # Signal at effective TE
        signal = epg_signal(T1, T2, PD, TR, TE_eff, ETL, echo_spacing)
        image[mask] = signal
        
        # Track blurring for short-T2 tissues
        blur = fse_blurring_factor(ETL, echo_spacing, T2)
        if blur > max_blur:
            max_blur = blur
    
    # Apply T2 blurring (affects phase encode direction = vertical)
    # Blurring is proportional to ETL and echo spacing
    train_duration = ETL * echo_spacing
    blur_sigma = train_duration / 500.0  # empirical scaling
    
    if blur_sigma > 0.5:
        # Apply directional blur (phase encode = vertical)
        kernel_size = int(blur_sigma * 3)
        if kernel_size > 0:
            # Blur only in vertical direction (phase encode)
            image = gaussian_filter(image, sigma=[blur_sigma, 0])
    
    return image

def compute_fse_echo_train(T1, T2, PD, TR, ETL, echo_spacing):
    """Compute signal at each echo in the train.
    
    Returns array of signal values for each echo.
    """
    echoes = np.arange(1, ETL + 1)
    TE_values = echoes * echo_spacing
    
    # Signal at each echo
    signals = PD * (1 - np.exp(-TR / T1)) * np.exp(-TE_values / T2)
    
    return TE_values, signals

if __name__ == "__main__":
    from phantom3d import TISSUE_PROPERTIES_3D
    
    # Test FSE signal
    print("FSE Signal Test:")
    print("-" * 50)
    
    TR, TE_eff, ETL, ESP = 4000, 80, 16, 10
    print(f"Parameters: TR={TR}, TE_eff={TE_eff}, ETL={ETL}, ESP={ESP}ms")
    print()
    
    for label, props in TISSUE_PROPERTIES_3D.items():
        if props["PD"] == 0:
            continue
        sig = epg_signal(props["T1"], props["T2"], props["PD"], TR, TE_eff, ETL, ESP)
        blur = fse_blurring_factor(ETL, ESP, props["T2"])
        print(f"  {props['name']:15s}: signal={sig:.4f}, blur_factor={blur:.2f}")
    
    # Scan time comparison
    print()
    print("Scan Time Comparison (256 matrix, NEX=1):")
    print("-" * 50)
    se_time = TR * 256 / 1000
    for etl in [1, 4, 8, 16, 32]:
        fse_time = fse_scan_time(TR, 256, 1, etl)
        speedup = se_time / fse_time
        print(f"  ETL={etl:2d}: time={fse_time:.0f}s ({fse_time/60:.1f}min), speedup={speedup:.1f}x")
    
    # Echo train decay
    print()
    print("Echo Train Signal Decay (WM vs CSF):")
    print("-" * 50)
    for tissue, T1, T2, PD in [("WM", 830, 80, 0.65), ("CSF", 4500, 2200, 1.0)]:
        te_vals, sigs = compute_fse_echo_train(T1, T2, PD, TR, 16, 10)
        print(f"  {tissue}: echo1={sigs[0]:.4f}, echo8={sigs[7]:.4f}, echo16={sigs[15]:.4f}")
    
    print("\nFSE module working.")