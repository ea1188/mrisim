import numpy as np

def create_vascular_phantom(size=256):
    """Create a brain phantom with blood vessels."""
    from phantom import create_brain_phantom
    
    # Start with base brain phantom
    phantom = create_brain_phantom(size)
    center = size // 2
    y, x = np.mgrid[:size, :size]
    
    # Add vessels (label = 5)
    # Internal carotid arteries (two vertical vessels)
    left_carotid = ((x - (center - size*0.08))**2 + (y - center)**2*0.01) < (size*0.015)**2
    right_carotid = ((x - (center + size*0.08))**2 + (y - center)**2*0.01) < (size*0.015)**2
    
    # Middle cerebral arteries (horizontal branches)
    left_mca = np.zeros((size, size), dtype=bool)
    right_mca = np.zeros((size, size), dtype=bool)
    
    # Left MCA - curves laterally
    for i in range(center - int(size*0.08), center + int(size*0.15)):
        cy = center - int(size*0.05) + int(size*0.03 * np.sin((i - center) * 0.05))
        radius = int(size * 0.012)
        mask = (x - i)**2 + (y - cy)**2 < radius**2
        left_mca |= mask
    
    # Right MCA
    for i in range(center - int(size*0.15), center + int(size*0.08)):
        cy = center - int(size*0.05) + int(size*0.03 * np.sin((i - center) * 0.05))
        radius = int(size * 0.012)
        mask = (x - i)**2 + (y - cy)**2 < radius**2
        right_mca |= mask
    
    # Anterior cerebral artery (midline, going up)
    aca = ((x - center)**2) < (size*0.01)**2
    aca &= (y > center - int(size*0.3)) & (y < center - int(size*0.05))
    
    # Basilar artery (midline, below)
    basilar = ((x - center)**2) < (size*0.012)**2
    basilar &= (y > center + int(size*0.05)) & (y < center + int(size*0.25))
    
    # Combine all vessels
    vessels = left_carotid | right_carotid | left_mca | right_mca | aca | basilar
    
    # Only place vessels where there's brain tissue
    brain_mask = phantom > 0
    vessels &= brain_mask
    phantom[vessels] = 5
    
    return phantom

# Extended tissue properties including blood
ANGIO_TISSUE_PROPERTIES = {
    0: {"T1": 1, "T2": 1, "PD": 0.0},
    1: {"T1": 4500, "T2": 2200, "PD": 1.0},   # CSF
    2: {"T1": 1330, "T2": 100, "PD": 0.8},     # Gray matter
    3: {"T1": 830, "T2": 80, "PD": 0.65},      # White matter
    4: {"T1": 4500, "T2": 2200, "PD": 1.0},    # CSF ventricles
    5: {"T1": 1930, "T2": 275, "PD": 0.9},     # Arterial blood at 3T
}

def simulate_tof_mra(phantom, TR=25, TE=4, flip_angle=60, slice_thickness=1.5):
    """Simulate Time-of-Flight MR Angiography.
    
    TOF exploits inflow enhancement: fresh blood entering the slice
    has full magnetization (not saturated), so it appears bright
    relative to stationary tissue that is partially saturated.
    """
    from signal_engine import gradient_echo_signal
    
    image = np.zeros_like(phantom, dtype=float)
    alpha = flip_angle
    
    for label, props in ANGIO_TISSUE_PROPERTIES.items():
        mask = phantom == label
        T2star = props["T2"] * 0.5  # T2* approximation
        
        if label == 5:  # Blood vessels - inflow enhancement
            # Fresh blood hasn't experienced prior RF pulses
            # Signal is as if first excitation (no saturation)
            # Inflow enhancement factor depends on velocity and slice thickness
            # For fully refreshed blood: signal = PD * sin(alpha) * exp(-TE/T2*)
            # This is much higher than saturated stationary tissue
            
            alpha_rad = np.radians(alpha)
            inflow_signal = props["PD"] * np.sin(alpha_rad) * np.exp(-TE / T2star)
            image[mask] = inflow_signal
        else:
            # Stationary tissue - experiences repeated RF pulses (saturated)
            sig = gradient_echo_signal(props["T1"], T2star, props["PD"], TR, TE, alpha)
            image[mask] = sig
    
    return image

def simulate_phase_contrast(phantom, venc=80, flow_velocity=60, flow_direction="up"):
    """Simulate Phase Contrast MR Angiography.
    
    PC-MRA encodes velocity as phase shift.
    venc: velocity encoding value (cm/s) - sets sensitivity
    flow_velocity: actual blood velocity (cm/s)
    
    Returns: magnitude image, phase image, speed image
    """
    from signal_engine import gradient_echo_signal
    
    size = phantom.shape[0]
    magnitude = np.zeros((size, size), dtype=float)
    phase = np.zeros((size, size), dtype=float)
    
    TR, TE, FA = 30, 5, 30
    
    for label, props in ANGIO_TISSUE_PROPERTIES.items():
        mask = phantom == label
        T2star = props["T2"] * 0.5
        sig = gradient_echo_signal(props["T1"], T2star, props["PD"], TR, TE, FA)
        magnitude[mask] = sig
        
        if label == 5:  # Blood - has velocity
            # Phase shift proportional to velocity
            # phase = pi * v / venc
            velocity = flow_velocity
            phase_shift = np.pi * velocity / venc
            # Clip to avoid aliasing (velocity > venc causes wrap)
            if abs(phase_shift) > np.pi:
                phase_shift = phase_shift % (2 * np.pi) - np.pi  # velocity aliasing
            phase[mask] = phase_shift
    
    # Speed image (magnitude of velocity)
    speed = np.abs(phase / np.pi * venc)
    
    return magnitude, phase, speed

def compute_mip(volume_slices):
    """Maximum Intensity Projection across slices."""
    return np.max(volume_slices, axis=0)

if __name__ == "__main__":
    phantom = create_vascular_phantom(256)
    print(f"Vascular phantom: {np.unique(phantom)} labels")
    print(f"Vessel voxels: {np.sum(phantom == 5)}")
    
    # Test TOF
    tof = simulate_tof_mra(phantom, TR=25, TE=4, flip_angle=60)
    print(f"\nTOF MRA:")
    print(f"  Blood signal: {tof[phantom==5].mean():.4f}")
    print(f"  Brain signal: {tof[phantom==2].mean():.4f}")
    print(f"  Vessel/Brain ratio: {tof[phantom==5].mean()/tof[phantom==2].mean():.1f}x")
    
    # Test Phase Contrast
    mag, phase, speed = simulate_phase_contrast(phantom, venc=80, flow_velocity=60)
    print(f"\nPhase Contrast:")
    print(f"  Blood phase: {phase[phantom==5].mean():.3f} rad")
    print(f"  Static phase: {phase[phantom==2].mean():.3f} rad")
    print(f"  Speed in vessels: {speed[phantom==5].mean():.1f} cm/s")
    
    print("\nAngiography module working.")