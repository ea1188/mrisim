import numpy as np

# Blood-label convention (foot-gun warning): the standalone *prototype* functions
# in this module — create_vascular_phantom / simulate_tof_mra / simulate_phase_contrast
# — paint and key off blood as label **5** (their own self-contained phantom). The
# production engine path (flow.py BLOOD_LABEL=11, tof_intensity_volume below, and the
# tissue_db scheme) uses label **11**. Don't mix a label-5 prototype phantom with the
# label-11 engine functions, or blood will be invisible to one of them.


def create_vascular_phantom(size: int = 256) -> np.ndarray:
    """Create a brain phantom with blood vessels (prototype; blood = label 5)."""
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

def simulate_tof_mra(
    phantom: np.ndarray,
    TR: float = 25,
    TE: float = 4,
    flip_angle: float = 60,
    slice_thickness: float = 1.5,
) -> np.ndarray:
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

def simulate_phase_contrast(
    phantom: np.ndarray,
    venc: float = 80,
    flow_velocity: float = 60,
    flow_direction: str = "up",
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
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
            # Velocity above venc wraps the phase into (−π, π] (velocity aliasing).
            if abs(phase_shift) > np.pi:
                phase_shift = (phase_shift + np.pi) % (2 * np.pi) - np.pi
            phase[mask] = phase_shift
    
    # Speed image (magnitude of velocity)
    speed = np.abs(phase / np.pi * venc)
    
    return magnitude, phase, speed

def compute_mip(volume_slices: np.ndarray) -> np.ndarray:
    """Maximum Intensity Projection across slices."""
    return np.max(volume_slices, axis=0)


def tof_intensity_volume(vessel_vol: np.ndarray, TR: float = 25.0, TE: float = 4.0,
                         flip_angle: float = 60.0,
                         static_suppression: float = 0.10) -> np.ndarray:
    """3D Time-of-Flight intensity volume from a labelled vessel phantom.

    Fresh inflowing blood (label 11) is unsaturated → bright; stationary tissue
    is saturated by the short TR + large flip angle and further attenuated by
    ``static_suppression`` so a MIP is vessel-dominated rather than picking up
    the brightest stationary voxel along each ray.

    Returns a float volume the same shape as ``vessel_vol``.
    """
    from signal_engine import gradient_echo_signal
    import tissue_db
    tp = tissue_db.properties("3T")
    a = np.radians(flip_angle)
    out = np.zeros(vessel_vol.shape, dtype=float)
    for lab, p in tp.items():
        mask = vessel_vol == lab
        if not mask.any():
            continue
        t2s = p.get("T2star", p["T2"] * 0.6)
        if lab == 11:        # blood / vessels — bright inflow
            out[mask] = p["PD"] * np.sin(a) * np.exp(-TE / t2s)
        elif lab == 0:       # background air
            out[mask] = 0.0
        else:                # stationary tissue — saturated and suppressed
            out[mask] = gradient_echo_signal(p["T1"], t2s, p["PD"], TR, TE, flip_angle) * static_suppression
    return out


def pc_intensity_volume(vessel_vol: np.ndarray, venc: float = 80.0,
                        flow_velocity: float = 60.0, display: str = "Speed") -> np.ndarray:
    """3D phase-contrast intensity volume from a labelled vessel phantom.

    PC-MRA encodes velocity as a phase shift φ = π·v/venc; spins faster than the
    velocity-encoding ``venc`` wrap into (−π, π] (velocity aliasing). Blood
    (label 11) carries ``flow_velocity`` (cm/s); stationary tissue has none.

    The returned float volume — MIP'd the same way as the TOF volume — depends on
    ``display``:

    * ``"Speed"`` / ``"Phase"`` (flow displays): vessels bright ∝ the apparent
      speed |φ|/π (so a venc below the true velocity *dims/wraps* fast flow — the
      key venc teaching point); stationary tissue is dark, so the vessel tree
      pops. This is the PC angiogram.
    * ``"Magnitude"``: a gradient-echo anatomical magnitude (vessels are *not*
      flow-weighted), so you can see why magnitude alone isn't an angiogram.
    """
    from signal_engine import gradient_echo_signal
    import tissue_db
    tp = tissue_db.properties("3T")
    tr, te, fa = 30.0, 5.0, 30.0
    phi = np.pi * float(flow_velocity) / max(float(venc), 1e-6)
    phi = (phi + np.pi) % (2 * np.pi) - np.pi          # wrap to (−π, π]
    flow_brightness = abs(phi) / np.pi                 # ∈ [0, 1]; peaks at v = venc
    out = np.zeros(vessel_vol.shape, dtype=float)
    for lab, p in tp.items():
        mask = vessel_vol == lab
        if not mask.any():
            continue
        if lab == 0:                                   # background air
            continue
        t2s = p.get("T2star", p["T2"] * 0.6)
        if display == "Magnitude":
            sig = gradient_echo_signal(p["T1"], t2s, p["PD"], tr, te, fa)
            out[mask] = sig if lab == 11 else sig * 0.5
        elif lab == 11:                                # blood — flow-weighted
            out[mask] = flow_brightness
        # stationary tissue stays 0 on the flow displays
    return out


def prep_realtof_volume(volume: np.ndarray, threshold: float = 0.5,
                        gamma: float = 2.0) -> np.ndarray:
    """Background-suppress a real TOF MRA volume so a MIP shows the vessels.

    Real (non-fat-suppressed) TOF data has bright fat/tissue as well as vessels,
    so a raw MIP is washed out. Normalise to [0,1], clip away everything below
    ``threshold``, and apply ``gamma`` to emphasise the brightest (vessel)
    voxels — leaving an organic vessel tree to project.
    """
    v = np.asarray(volume, dtype=float)
    v = v / max(float(v.max()), 1e-9)
    return np.clip((v - threshold) / (1.0 - threshold), 0.0, 1.0) ** gamma


def rotating_mip(tof_volume: np.ndarray, azimuth_deg: float = 0.0,
                 elevation_deg: float = 0.0) -> np.ndarray:
    """Maximum-intensity projection of a TOF volume from a viewing angle.

    The volume axes are (Z=superior/inferior, Y=anterior/posterior, X=left/right).
    ``azimuth`` rotates about the S/I axis (spin the angiogram), ``elevation``
    tilts about the L/R axis; the projection is along the (rotated) A/P axis, so
    azimuth=elevation=0 gives a coronal front view — the classic MRA MIP that a
    radiologist rotates to inspect the vessel tree in 3D.

    Returns a 2-D (Z, X) projection image.
    """
    from scipy.ndimage import rotate
    v = tof_volume
    if abs(azimuth_deg) > 0.01:
        v = rotate(v, azimuth_deg, axes=(1, 2), reshape=False, order=1)
    if abs(elevation_deg) > 0.01:
        v = rotate(v, elevation_deg, axes=(0, 1), reshape=False, order=1)
    return v.max(axis=1)

if __name__ == "__main__":
    phantom = create_vascular_phantom(256)
    print(f"Vascular phantom: {np.unique(phantom)} labels")
    print(f"Vessel voxels: {np.sum(phantom == 5)}")
    
    # Test TOF
    tof = simulate_tof_mra(phantom, TR=25, TE=4, flip_angle=60)
    print("\nTOF MRA:")
    print(f"  Blood signal: {tof[phantom==5].mean():.4f}")
    print(f"  Brain signal: {tof[phantom==2].mean():.4f}")
    print(f"  Vessel/Brain ratio: {tof[phantom==5].mean()/tof[phantom==2].mean():.1f}x")
    
    # Test Phase Contrast
    mag, phase, speed = simulate_phase_contrast(phantom, venc=80, flow_velocity=60)
    print("\nPhase Contrast:")
    print(f"  Blood phase: {phase[phantom==5].mean():.3f} rad")
    print(f"  Static phase: {phase[phantom==2].mean():.3f} rad")
    print(f"  Speed in vessels: {speed[phantom==5].mean():.1f} cm/s")
    
    print("\nAngiography module working.")