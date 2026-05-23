import numpy as np

# Diffusion properties per tissue (10^-3 mm^2/s)
DIFFUSION_PROPERTIES = {
    0: {"ADC": 0.0, "FA": 0.0},
    1: {"ADC": 3.0, "FA": 0.0},
    2: {"ADC": 0.8, "FA": 0.15},
    3: {"ADC": 0.7, "FA": 0.45},
    4: {"ADC": 3.0, "FA": 0.0},
}

FIBER_ORIENTATIONS = {
    3: np.array([1.0, 0.3]),
}

def diffusion_signal(S0, b_value, ADC):
    D = ADC * 1e-3
    signal = S0 * np.exp(-b_value * D)
    return signal

def diffusion_tensor_signal(S0, b_value, tensor, gradient_direction):
    g = np.array(gradient_direction, dtype=float)
    g = g / np.linalg.norm(g)
    apparent_D = g @ tensor @ g
    signal = S0 * np.exp(-b_value * apparent_D)
    return signal

def create_diffusion_tensor(ADC, FA, orientation):
    MD = ADC * 1e-3
    if FA == 0:
        return np.eye(2) * MD
    
    diff_sq = 2 * MD**2 * FA**2 / (1 - FA**2 / 2)
    diff = np.sqrt(diff_sq)
    lambda1 = MD + diff / 2
    lambda2 = MD - diff / 2
    
    if lambda2 < 0:
        lambda2 = 0.01 * 1e-3
        lambda1 = 2 * MD - lambda2
    
    orientation = np.array(orientation, dtype=float)
    orientation = orientation / np.linalg.norm(orientation)
    cos_a = orientation[0]
    sin_a = orientation[1]
    R = np.array([[cos_a, -sin_a], [sin_a, cos_a]])
    D_diag = np.diag([lambda1, lambda2])
    tensor = R @ D_diag @ R.T
    return tensor

def simulate_diffusion_image(phantom, tissue_properties, b_value, gradient_direction=[1, 0], TR=8000, TE=80):
    from signal_engine import spin_echo_signal
    image = np.zeros_like(phantom, dtype=float)
    
    for label, props in tissue_properties.items():
        mask = phantom == label
        S0 = spin_echo_signal(props["T1"], props["T2"], props["PD"], TR, TE)
        diff_props = DIFFUSION_PROPERTIES.get(label, {"ADC": 0, "FA": 0})
        
        if diff_props["FA"] > 0 and label in FIBER_ORIENTATIONS:
            tensor = create_diffusion_tensor(
                diff_props["ADC"], diff_props["FA"], FIBER_ORIENTATIONS[label])
            sig = diffusion_tensor_signal(S0, b_value, tensor, gradient_direction)
        else:
            sig = diffusion_signal(S0, b_value, diff_props["ADC"])
        
        image[mask] = sig
    return image

def compute_adc_map(phantom, tissue_properties, b_value, TR=8000, TE=80):
    """Compute ADC map with spatial variation for realism."""
    from signal_engine import spin_echo_signal
    
    size = phantom.shape[0]
    adc_map = np.zeros_like(phantom, dtype=float)
    
    # Add realistic spatial variation to ADC values
    np.random.seed(42)  # reproducible
    variation = np.random.normal(0, 0.05, (size, size))
    # Smooth the variation to look realistic
    from scipy.ndimage import gaussian_filter
    variation = gaussian_filter(variation, sigma=8)
    
    for label, diff_props in DIFFUSION_PROPERTIES.items():
        mask = phantom == label
        base_adc = diff_props["ADC"]
        if base_adc > 0:
            # Add spatial variation (percentage of base value)
            local_adc = base_adc * (1 + variation[mask] * 0.3)
            local_adc = np.clip(local_adc, base_adc * 0.5, base_adc * 1.5)
            adc_map[mask] = local_adc
        else:
            adc_map[mask] = 0
    
    return adc_map

def compute_fa_map(phantom):
    """Generate FA map with spatial variation and fiber structure."""
    size = phantom.shape[0]
    fa_map = np.zeros_like(phantom, dtype=float)
    
    # Create spatial variation
    np.random.seed(43)
    variation = np.random.normal(0, 0.08, (size, size))
    from scipy.ndimage import gaussian_filter
    variation = gaussian_filter(variation, sigma=5)
    
    # Create tract structure patterns
    center = size // 2
    y, x = np.mgrid[:size, :size]
    
    # Distance-based pattern
    dist_from_center = np.sqrt((x - center)**2 + (y - center)**2) / center
    tract_pattern = 0.3 * np.cos(4 * np.pi * dist_from_center) + 0.7
    
    # Corpus callosum band (high FA)
    cc_band = np.exp(-((y - int(center * 0.85))**2) / (2 * (size * 0.03)**2))
    
    for label, diff_props in DIFFUSION_PROPERTIES.items():
        mask = phantom == label
        base_fa = diff_props["FA"]
        
        if label == 3:  # White matter
            local_fa = base_fa * tract_pattern[mask] + 0.2 * cc_band[mask]
            local_fa = local_fa + variation[mask] * 0.15
            local_fa = np.clip(local_fa, 0.1, 0.9)
            fa_map[mask] = local_fa
        elif base_fa > 0:
            local_fa = base_fa + variation[mask] * 0.1
            local_fa = np.clip(local_fa, 0.0, 1.0)
            fa_map[mask] = local_fa
    
    return fa_map

def compute_direction_map(phantom):
    """Generate a color-coded direction map (simplified RGB DTI)."""
    size = phantom.shape[0]
    direction_map = np.zeros((size, size, 3), dtype=float)
    center = size // 2
    y, x = np.mgrid[:size, :size]
    
    # White matter gets directional color
    wm_mask = phantom == 3
    
    # Primary direction varies with position (simulates real fiber architecture)
    # Red = left-right, Green = anterior-posterior, Blue = superior-inferior
    angle = np.arctan2(y - center, x - center)
    
    # Dominant left-right (red) with some variation
    fa_map = compute_fa_map(phantom)
    
    direction_map[wm_mask, 0] = np.abs(np.cos(angle[wm_mask])) * fa_map[wm_mask]  # Red (L-R)
    direction_map[wm_mask, 1] = np.abs(np.sin(angle[wm_mask])) * fa_map[wm_mask]  # Green (A-P)
    direction_map[wm_mask, 2] = 0.3 * fa_map[wm_mask]  # Blue (S-I, constant in 2D)
    
    # Normalize
    max_val = direction_map.max()
    if max_val > 0:
        direction_map = direction_map / max_val
    
    return direction_map

if __name__ == "__main__":
    from phantom import create_brain_phantom, TISSUE_PROPERTIES
    
    phantom = create_brain_phantom(256)
    
    for b in [0, 500, 1000, 2000]:
        img = simulate_diffusion_image(phantom, TISSUE_PROPERTIES, b)
        print(f"b={b}: max={img.max():.4f}, WM={img[phantom==3].mean():.4f}, CSF={img[phantom==1].mean():.4f}")
    
    adc = compute_adc_map(phantom, TISSUE_PROPERTIES, 1000)
    print(f"\nADC map range: {adc[adc>0].min():.3f} - {adc.max():.3f}")
    print(f"ADC WM mean={adc[phantom==3].mean():.3f}, std={adc[phantom==3].std():.3f}")
    
    fa = compute_fa_map(phantom)
    print(f"\nFA map range: {fa[fa>0].min():.3f} - {fa.max():.3f}")
    print(f"FA WM mean={fa[phantom==3].mean():.3f}, std={fa[phantom==3].std():.3f}")
    
    print("\nDiffusion module working.")