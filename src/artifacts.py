import numpy as np
from scipy.ndimage import gaussian_filter

def add_motion_artifact(
    image: np.ndarray,
    motion_type: str = "periodic",
    amplitude: float = 5,
    frequency: float = 3,
    phase_direction: str = "vertical",
    rng: np.random.Generator | None = None,
) -> np.ndarray:
    """Simulate motion artifact (ghosting) in the phase encode direction.
    
    In real MRI, motion during acquisition causes phase errors in k-space,
    resulting in ghost images displaced in the phase encode direction.
    
    Parameters:
    - image: input image (already reconstructed or signal image)
    - motion_type: 'periodic' (breathing), 'random' (sudden movement), 'linear' (drift)
    - amplitude: motion amplitude in pixels
    - frequency: number of motion cycles during acquisition (for periodic)
    - phase_direction: 'vertical' or 'horizontal' (phase encode direction)
    """
    # Work in k-space
    kspace = np.fft.fftshift(np.fft.fft2(np.fft.ifftshift(image)))
    
    rows, cols = kspace.shape
    
    if phase_direction == "vertical":
        num_lines = rows
    else:
        num_lines = cols
    
    if rng is None:
        rng = np.random.default_rng()

    # Generate motion trajectory (displacement per k-space line)
    if motion_type == "periodic":
        # Simulates breathing or pulsation
        t = np.arange(num_lines)
        displacement = amplitude * np.sin(2 * np.pi * frequency * t / num_lines)
    elif motion_type == "random":
        # Sudden jerky movements
        displacement = np.zeros(num_lines)
        num_events = max(1, int(frequency))
        event_positions = rng.integers(0, num_lines, num_events)
        for pos in event_positions:
            # Each event causes a shift that persists briefly
            duration = num_lines // 10
            end = min(int(pos) + duration, num_lines)
            displacement[int(pos):end] = amplitude * (rng.random() * 2 - 1)
    elif motion_type == "linear":
        # Gradual drift during scan
        displacement = np.linspace(0, amplitude, num_lines)
    else:
        displacement = np.zeros(num_lines)
    
    # Apply phase shifts to k-space lines
    # Motion in image space causes phase ramp in k-space
    corrupted_kspace = kspace.copy()
    
    if phase_direction == "vertical":
        for line_idx in range(rows):
            # Phase shift = 2*pi * displacement * k_position / FOV
            phase_shift = np.zeros(cols)
            k_positions = np.arange(cols) - cols // 2
            phase_shift = 2 * np.pi * displacement[line_idx] * k_positions / cols
            corrupted_kspace[line_idx, :] *= np.exp(1j * phase_shift)
    else:
        for line_idx in range(cols):
            phase_shift = np.zeros(rows)
            k_positions = np.arange(rows) - rows // 2
            phase_shift = 2 * np.pi * displacement[line_idx] * k_positions / rows
            corrupted_kspace[:, line_idx] *= np.exp(1j * phase_shift)
    
    # Reconstruct
    result = np.abs(np.fft.fftshift(np.fft.ifft2(np.fft.ifftshift(corrupted_kspace))))
    
    return result

def add_chemical_shift_artifact(
    image: np.ndarray,
    phantom_slice: np.ndarray,
    shift_pixels: float = 3,
    fat_label: int = 4,
) -> np.ndarray:
    """Simulate chemical shift artifact.
    
    Fat resonates at a different frequency than water (~3.5 ppm).
    This causes fat signal to be shifted in the readout (frequency encode) direction.
    
    shift_pixels: displacement in pixels (depends on bandwidth)
        At 125 Hz/pixel bandwidth: shift = 3.5ppm * 128MHz / 125Hz = ~3.6 pixels at 3T
    """
    result = image.copy()
    
    # Find fat voxels
    fat_mask = phantom_slice == fat_label
    if not np.any(fat_mask):
        return result
    
    # Get fat signal values
    fat_signal = np.zeros_like(image)
    fat_signal[fat_mask] = image[fat_mask]
    
    # Remove fat from original position
    result[fat_mask] = 0
    
    # Shift fat signal in readout direction (horizontal)
    shift = int(shift_pixels)
    if shift > 0:
        shifted_fat = np.zeros_like(fat_signal)
        shifted_fat[:, shift:] = fat_signal[:, :-shift]
    elif shift < 0:
        shifted_fat = np.zeros_like(fat_signal)
        shifted_fat[:, :shift] = fat_signal[:, -shift:]
    else:
        shifted_fat = fat_signal
    
    # Add shifted fat back (bright edge on one side, dark on other)
    result += shifted_fat
    
    # Create the characteristic bright/dark band at fat-water interface
    # Where shifted fat overlaps with water: bright band
    # Where fat was removed: dark band
    
    return result

def add_susceptibility_artifact(
    image: np.ndarray,
    phantom_slice: np.ndarray,
    strength: float = 0.3,
    air_labels: list[int] | None = None,
) -> np.ndarray:
    """Simulate susceptibility artifact (signal dropout and distortion).
    
    Occurs at air-tissue interfaces (sinuses, ear canals).
    Causes local field inhomogeneity -> signal dephasing -> signal loss.
    """
    if air_labels is None:
        air_labels = [0]
    rows, cols = image.shape

    # Create susceptibility field map
    # Signal dropout near air-tissue boundaries
    boundary_map = np.zeros_like(image, dtype=float)

    for air_label in air_labels:
        air_mask = phantom_slice == air_label
        if not np.any(air_mask):
            continue
        
        # Distance from air-tissue boundary
        from scipy.ndimage import distance_transform_edt, binary_dilation
        
        # Find boundary pixels (air adjacent to tissue)
        dilated = binary_dilation(air_mask, iterations=2)
        boundary = dilated & ~air_mask
        
        # Distance from boundary (in tissue)
        tissue_mask = phantom_slice > 0
        if np.any(boundary & tissue_mask):
            # Create a field perturbation that decays with distance from boundary
            dist = distance_transform_edt(~boundary)
            # Field perturbation decays as 1/r^2
            field_perturbation = np.where(dist > 0, 1.0 / (1 + dist**2 * 0.1), 1.0)
            boundary_map += field_perturbation
    
    # Apply signal loss based on field perturbation
    # T2* shortening causes signal dropout
    signal_loss = np.exp(-boundary_map * strength * 10)
    signal_loss = np.clip(signal_loss, 0.1, 1.0)
    
    result = image * signal_loss
    
    return result

def add_zipper_artifact(
    image: np.ndarray,
    frequency_offset: float = 0.3,
    amplitude: float = 0.1,
) -> np.ndarray:
    """Simulate zipper artifact (RF interference line).
    
    Caused by RF leakage or equipment interference.
    Appears as a bright line at a specific frequency in the image.
    """
    rows, cols = image.shape
    result = image.copy()
    
    # Add a bright line at the interference frequency position
    line_position = int(cols * frequency_offset)
    line_position = np.clip(line_position, 0, cols - 1)
    
    max_signal = np.max(image)
    interference = max_signal * amplitude
    
    # Zipper is a vertical bright line
    result[:, line_position] += interference
    # With some spread
    if line_position > 0:
        result[:, line_position - 1] += interference * 0.3
    if line_position < cols - 1:
        result[:, line_position + 1] += interference * 0.3
    
    return result

def calculate_chemical_shift_pixels(bandwidth_per_pixel: float, field_strength: float = 3.0) -> float:
    """Calculate chemical shift displacement in pixels.
    
    Chemical shift of fat: 3.5 ppm
    At 3T: frequency difference = 3.5e-6 * 128e6 = 448 Hz
    Shift in pixels = frequency_difference / bandwidth_per_pixel
    """
    fat_water_shift_hz = 3.5e-6 * field_strength * 42.576e6  # Hz
    shift_pixels = fat_water_shift_hz / bandwidth_per_pixel
    return shift_pixels

if __name__ == "__main__":
    from phantom3d import get_slice, simulate_slice
    from brainweb_loader import get_brainweb_or_synthetic
    
    phantom, source = get_brainweb_or_synthetic()
    print(f"Source: {source}")
    
    # Get a slice and simulate
    sl = get_slice(phantom, 'axial', 90)
    image = simulate_slice(sl, TR=500, TE=15, sequence='SE')
    print(f"Original image: {image.shape}, max={image.max():.4f}")
    
    # Test motion artifact
    motion_img = add_motion_artifact(image, motion_type="periodic", amplitude=3, frequency=4)
    print(f"Motion artifact: max={motion_img.max():.4f}")
    
    # Test chemical shift
    chem_img = add_chemical_shift_artifact(image, sl, shift_pixels=4)
    print(f"Chemical shift: max={chem_img.max():.4f}")
    
    # Test susceptibility
    susc_img = add_susceptibility_artifact(image, sl, strength=0.5)
    print(f"Susceptibility: max={susc_img.max():.4f}")
    
    # Test zipper
    zip_img = add_zipper_artifact(image, frequency_offset=0.3, amplitude=0.15)
    print(f"Zipper: max={zip_img.max():.4f}")
    
    # Chemical shift calculation
    for bw in [50, 125, 250, 500]:
        shift = calculate_chemical_shift_pixels(bw)
        print(f"  BW={bw} Hz/px -> chemical shift = {shift:.1f} pixels")
    
    print("\nArtifacts module working.")