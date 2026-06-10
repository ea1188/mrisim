import numpy as np

# Brain activation regions (simplified)
def create_fmri_phantom(size: int = 256) -> tuple[np.ndarray, np.ndarray]:
    """Create phantom with activation regions for fMRI simulation."""
    from phantom import create_brain_phantom
    
    phantom = create_brain_phantom(size)
    center = size // 2
    y, x = np.mgrid[:size, :size]
    
    # Activation map (0 = no activation, values = BOLD signal change %)
    activation = np.zeros((size, size), dtype=float)
    
    # Visual cortex activation (posterior)
    visual = np.exp(-((x - center)**2 + (y - (center + int(size*0.25)))**2) / (2 * (size*0.06)**2))
    
    # Motor cortex activation (superior)
    motor_left = np.exp(-((x - (center - int(size*0.12)))**2 + (y - (center - int(size*0.22)))**2) / (2 * (size*0.04)**2))
    motor_right = np.exp(-((x - (center + int(size*0.12)))**2 + (y - (center - int(size*0.22)))**2) / (2 * (size*0.04)**2))
    
    # Language area (left lateralized)
    language = np.exp(-((x - (center - int(size*0.2)))**2 + (y - (center - int(size*0.05)))**2) / (2 * (size*0.05)**2))
    
    # Combine activations (only in gray matter)
    gm_mask = phantom == 2
    activation[gm_mask] = (visual[gm_mask] * 3.0 + 
                           motor_left[gm_mask] * 2.5 + 
                           motor_right[gm_mask] * 2.5 + 
                           language[gm_mask] * 2.0)
    
    # Clip to realistic BOLD signal change range (0-5%)
    activation = np.clip(activation, 0, 5.0)
    
    return phantom, activation

def simulate_bold_signal(
    T2star_rest: float | np.ndarray,
    bold_change_percent: float | np.ndarray,
) -> float | np.ndarray:
    """Calculate T2* change due to BOLD effect.
    
    BOLD effect: neural activation → increased blood flow → 
    decreased deoxyhemoglobin → increased T2* → increased signal on T2*-weighted images
    """
    # T2* increases with activation (less deoxyHb = less susceptibility)
    # Approximate: delta_T2star/T2star ≈ bold_change/100 * scaling_factor
    delta_R2star = -bold_change_percent / 100.0 * (1.0 / T2star_rest) * 0.5
    T2star_active = 1.0 / (1.0/T2star_rest + delta_R2star)
    return T2star_active

def simulate_fmri_image(
    phantom: np.ndarray,
    activation: np.ndarray,
    TR: float = 2000,
    TE: float = 30,
    flip_angle: float = 90,
    is_active: bool = True,
) -> np.ndarray:
    """Simulate an fMRI EPI image.

    Parameters:
    - is_active: if True, show activated state; if False, show rest state
    """
    from signal_engine import gradient_echo_signal
    from phantom import TISSUE_PROPERTIES

    image = np.zeros_like(phantom, dtype=float)

    T2star_values = {
        0: 1,
        1: 2000 * 0.6,
        2: 100 * 0.6,
        3: 80 * 0.6,
        4: 2000 * 0.6,
    }

    for label, props in TISSUE_PROPERTIES.items():
        mask = phantom == label
        T2star = float(T2star_values.get(label, props["T2"] * 0.6))

        if is_active and label == 2:
            act_values = activation[mask]
            T2star_local = np.where(
                act_values > 0,
                simulate_bold_signal(T2star, act_values),
                T2star,
            )
            alpha = np.radians(flip_angle)
            E1 = np.exp(-TR / props["T1"])
            denom = 1.0 - np.cos(alpha) * E1
            if abs(denom) < 1e-12:
                image[mask] = 0.0
            else:
                image[mask] = (props["PD"] * np.sin(alpha) * (1.0 - E1) / denom
                               * np.exp(-TE / T2star_local))
        else:
            sig = gradient_echo_signal(props["T1"], T2star, props["PD"], TR, TE, flip_angle)
            image[mask] = sig

    return image

def simulate_fmri_fast(
    phantom: np.ndarray,
    activation: np.ndarray,
    TR: float = 2000,
    TE: float = 30,
    flip_angle: float = 90,
    is_active: bool = True,
) -> np.ndarray:
    """Fast vectorized fMRI simulation."""
    from signal_engine import gradient_echo_signal
    from phantom import TISSUE_PROPERTIES
    
    image = np.zeros_like(phantom, dtype=float)
    
    T2star_base = {
        0: 1,
        1: 1200,    # CSF T2*
        2: 60,      # GM T2* at 3T
        3: 48,      # WM T2* at 3T
        4: 1200,    # CSF
    }
    
    for label, props in TISSUE_PROPERTIES.items():
        mask = phantom == label
        T2star = T2star_base.get(label, 50)
        
        if is_active and label == 2:
            # T2* increases with BOLD (less deoxyHb), per active voxel; the spoiled
            # GRE signal then comes from the shared engine helper (which carries the
            # 0÷0 flip-angle guard) with the per-voxel T2*.
            act_values = activation[mask]
            T2star_modified = T2star * (1 + act_values / 100.0 * 0.3)
            image[mask] = gradient_echo_signal(props["T1"], T2star_modified, props["PD"],
                                               TR, TE, flip_angle)
        else:
            sig = gradient_echo_signal(props["T1"], T2star, props["PD"], TR, TE, flip_angle)
            image[mask] = sig
    
    return image

def compute_activation_map(
    phantom: np.ndarray,
    activation: np.ndarray,
    TR: float = 2000,
    TE: float = 30,
    flip_angle: float = 90,
) -> np.ndarray:
    """Compute the difference (activation) map between rest and active states."""
    rest = simulate_fmri_fast(phantom, activation, TR, TE, flip_angle, is_active=False)
    active = simulate_fmri_fast(phantom, activation, TR, TE, flip_angle, is_active=True)
    
    # Percent signal change
    with np.errstate(divide='ignore', invalid='ignore'):
        pct_change = np.where(rest > 0, (active - rest) / rest * 100, 0)
    
    return pct_change

def compute_t_statistic_map(
    phantom: np.ndarray,
    activation: np.ndarray,
    TR: float = 2000,
    TE: float = 30,
    flip_angle: float = 90,
    num_volumes: int = 100,
    noise_level: float = 0.5,
) -> np.ndarray:
    """Simulate a t-statistic map from a block design fMRI experiment.
    
    Simulates alternating rest/active blocks and computes per-voxel t-test.
    """
    rest_image = simulate_fmri_fast(phantom, activation, TR, TE, flip_angle, is_active=False)
    active_image = simulate_fmri_fast(phantom, activation, TR, TE, flip_angle, is_active=True)
    
    # Simulate time series with noise — split the run into rest/active volumes.
    n_rest = num_volumes // 2
    n_active = num_volumes - n_rest

    # Add temporal noise
    sigma = np.max(rest_image) * noise_level / 100
    
    rest_mean = rest_image
    active_mean = active_image
    
    # T-statistic: (mean_active - mean_rest) / sqrt(var_rest/n_rest + var_active/n_active)
    # With assumed equal variance = sigma^2 (equal groups → sqrt(2/n)).
    pooled_se = sigma * np.sqrt(1.0 / n_rest + 1.0 / n_active)
    
    with np.errstate(divide='ignore', invalid='ignore'):
        t_map = np.where(pooled_se > 0, (active_mean - rest_mean) / pooled_se, 0)
    
    # Only show in brain
    brain_mask = phantom > 0
    t_map[~brain_mask] = 0
    
    return t_map

def compute_temporal_snr(TR: float, TE: float, flip_angle: float, num_volumes: int) -> float:
    """Estimate temporal SNR for fMRI experiment."""
    # tSNR decreases with fewer volumes, increases with longer experiments
    # Typical tSNR at 3T: 50-150 for GRE-EPI
    base_tsnr = 80  # typical 3T value
    
    # TE effect: optimal TE ~ T2* for maximum BOLD sensitivity
    T2star_gm = 60  # ms at 3T
    te_efficiency = (TE / T2star_gm) * np.exp(-TE / T2star_gm) / (1/np.e)  # normalized
    
    # Volume averaging effect
    volume_factor = np.sqrt(num_volumes / 100)
    
    tsnr = base_tsnr * te_efficiency * volume_factor
    return tsnr

if __name__ == "__main__":
    
    phantom, activation = create_fmri_phantom(256)
    print(f"Activation range: {activation[activation>0].min():.2f} - {activation.max():.2f}%")
    print(f"Activated voxels: {np.sum(activation > 0.5)}")
    
    # Test fMRI simulation
    rest = simulate_fmri_fast(phantom, activation, TR=2000, TE=30, is_active=False)
    active = simulate_fmri_fast(phantom, activation, TR=2000, TE=30, is_active=True)
    print(f"\nRest GM signal: {rest[phantom==2].mean():.4f}")
    print(f"Active GM signal: {active[phantom==2].mean():.4f}")
    print(f"Max BOLD change: {((active-rest)/rest * 100)[activation > 1].max():.2f}%")
    
    # Test t-map
    t_map = compute_t_statistic_map(phantom, activation)
    print(f"\nT-map range: {t_map[t_map>0].min():.1f} - {t_map.max():.1f}")
    print(f"Voxels above t=3: {np.sum(t_map > 3)}")
    
    # Test tSNR
    tsnr = compute_temporal_snr(TR=2000, TE=30, flip_angle=90, num_volumes=100)
    print(f"\nEstimated tSNR: {tsnr:.1f}")
    
    print("\nfMRI module working.")