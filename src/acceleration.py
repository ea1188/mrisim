import numpy as np
from scipy.ndimage import gaussian_filter

def apply_parallel_imaging(image, acceleration_factor=2, method="SENSE"):
    """Simulate parallel imaging (GRAPPA/SENSE) effect.
    
    Parallel imaging undersamples k-space by the acceleration factor,
    then reconstructs using coil sensitivity information.
    
    Effects:
    - Scan time reduced by acceleration factor
    - SNR reduced by sqrt(acceleration) * g-factor
    - g-factor causes spatially varying noise amplification
    
    Parameters:
    - acceleration_factor: R (2, 3, or 4 typical)
    - method: 'SENSE' or 'GRAPPA'
    """
    if acceleration_factor <= 1:
        return image, np.ones_like(image)
    
    rows, cols = image.shape
    
    # Generate g-factor map (geometry factor)
    # g-factor >= 1, higher at center, depends on coil geometry
    # Simplified model: g increases toward center of image
    y, x = np.mgrid[:rows, :cols]
    cy, cx = rows // 2, cols // 2
    
    # Distance from center (normalized)
    dist = np.sqrt((y - cy)**2 / (rows/2)**2 + (x - cx)**2 / (cols/2)**2)
    
    # g-factor model: higher acceleration = higher g-factor, worse at center
    if method == "SENSE":
        # SENSE g-factor pattern (depends on coil geometry)
        g_factor = 1.0 + (acceleration_factor - 1) * 0.3 * np.exp(-dist**2 * 2)
        # Add some coil-dependent variation
        g_factor += 0.1 * np.sin(np.pi * y / rows) * (acceleration_factor - 1)
    else:
        # GRAPPA has slightly different noise pattern (more uniform but kernel artifacts)
        g_factor = 1.0 + (acceleration_factor - 1) * 0.2
        # GRAPPA can have residual aliasing at high R
        if acceleration_factor >= 3:
            # Add subtle residual aliasing
            shift = rows // acceleration_factor
            g_factor += 0.05 * acceleration_factor
    
    g_factor = np.clip(g_factor, 1.0, acceleration_factor * 1.5)
    
    # Apply SNR penalty: noise amplified by sqrt(R) * g_factor
    snr_penalty = np.sqrt(acceleration_factor) * g_factor
    
    # Add spatially varying noise based on g-factor
    noise_sigma = np.max(image) * 0.02 * snr_penalty
    noise = np.random.normal(0, 1, image.shape) * noise_sigma
    
    result = image + noise
    result = np.clip(result, 0, None)
    
    return result, g_factor

def compute_acceleration_metrics(acceleration_factor, base_snr, base_scan_time):
    """Compute metrics for accelerated acquisition.
    
    Returns dict with adjusted values.
    """
    # SNR penalty
    snr_factor = 1.0 / np.sqrt(acceleration_factor)
    adjusted_snr = base_snr * snr_factor
    
    # Scan time reduction
    adjusted_time = base_scan_time / acceleration_factor
    
    return {
        "snr_factor": snr_factor,
        "adjusted_snr": adjusted_snr,
        "adjusted_time": adjusted_time,
        "g_factor_mean": 1.0 + (acceleration_factor - 1) * 0.25,
    }

def apply_compressed_sensing(image, acceleration_factor=4, sparsity=0.3):
    """Simulate compressed sensing reconstruction.
    
    CS uses random undersampling + iterative reconstruction.
    Higher acceleration possible but with potential blurring/staircasing artifacts.
    """
    if acceleration_factor <= 1:
        return image
    
    rows, cols = image.shape
    
    # Simulate undersampled k-space (variable density random sampling)
    kspace = np.fft.fftshift(np.fft.fft2(np.fft.ifftshift(image)))
    
    # Variable density sampling mask (more samples at center)
    mask = np.zeros((rows, cols), dtype=bool)
    center_fraction = 0.1  # Always sample central 10%
    center_start = int(rows * (0.5 - center_fraction/2))
    center_end = int(rows * (0.5 + center_fraction/2))
    mask[center_start:center_end, :] = True
    
    # Random samples outside center
    remaining_fraction = (1.0 / acceleration_factor) - center_fraction
    if remaining_fraction > 0:
        outer_mask = ~mask
        outer_indices = np.where(outer_mask)
        num_samples = int(remaining_fraction * rows * cols)
        if num_samples > 0 and len(outer_indices[0]) > 0:
            selected = np.random.choice(len(outer_indices[0]), 
                                       min(num_samples, len(outer_indices[0])), replace=False)
            mask[outer_indices[0][selected], outer_indices[1][selected]] = True
    
    # Apply mask
    undersampled = kspace * mask
    
    # Simple reconstruction (in real CS, this would be iterative)
    # Simulate the slight blurring/artifact of CS reconstruction
    reconstructed = np.abs(np.fft.fftshift(np.fft.ifft2(np.fft.ifftshift(undersampled))))
    
    # Scale to preserve mean intensity
    if np.max(reconstructed) > 0:
        reconstructed = reconstructed * (np.mean(image[image > 0]) / np.mean(reconstructed[reconstructed > 0]))
    
    # Add slight smoothing to simulate iterative reconstruction effect
    from scipy.ndimage import gaussian_filter
    reconstructed = gaussian_filter(reconstructed, sigma=0.3 * np.sqrt(acceleration_factor))
    
    return reconstructed

if __name__ == "__main__":
    from phantom3d import get_slice, simulate_slice
    from brainweb_loader import get_brainweb_or_synthetic
    
    phantom, source = get_brainweb_or_synthetic()
    sl = get_slice(phantom, 'axial', 90)
    image = simulate_slice(sl, TR=500, TE=15, sequence='SE')
    
    print("Parallel Imaging Test:")
    print("-" * 50)
    
    for R in [1, 2, 3, 4]:
        result, gfactor = apply_parallel_imaging(image, R, "SENSE")
        metrics = compute_acceleration_metrics(R, 30, 128)
        print(f"  R={R}: SNR factor={metrics['snr_factor']:.2f}, "
              f"g-factor mean={gfactor.mean():.2f}, "
              f"time={metrics['adjusted_time']:.0f}s")
    
    print()
    print("Compressed Sensing Test:")
    print("-" * 50)
    for R in [2, 4, 6, 8]:
        cs_img = apply_compressed_sensing(image, R)
        print(f"  R={R}: max={cs_img.max():.4f}, mean_ratio={cs_img.mean()/image.mean():.2f}")
    
    print("\nAcceleration module working.")