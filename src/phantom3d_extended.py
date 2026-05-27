import numpy as np
from scipy.ndimage import gaussian_filter

def add_vessels_3d(phantom: np.ndarray) -> np.ndarray:
    """Add a dense vascular network to the 3D phantom. Label 11 = vessels (Blood)."""
    nx, ny, nz = phantom.shape
    cx, cy, cz = nx // 2, ny // 2, nz // 2
    x, y, z = np.mgrid[:nx, :ny, :nz]
    
    vessels = np.zeros_like(phantom, dtype=bool)
    rng = np.random.default_rng(12345)   # deterministic organic meander

    # Helper to add a vessel segment between two 3D points
    def add_vessel_segment(p1: tuple, p2: tuple, radius: float, taper: float = 0) -> None:
        """Draw a vessel between two points, with a smooth random meander and
        distal tapering so it reads as an organic vessel rather than a drawn line."""
        p1 = np.array(p1, dtype=float); p2 = np.array(p2, dtype=float)
        num_steps = int(np.linalg.norm(p2 - p1) * 2) + 5
        # low-frequency sinusoidal wobble (amplitude ~1-2 voxels, random phase/freq)
        amp = rng.uniform(0.6, 1.8, size=3)
        phase = rng.uniform(0, 2 * np.pi, size=3)
        freq = rng.uniform(0.7, 2.2)
        for i in range(num_steps):
            t = i / max(num_steps - 1, 1)
            wobble = amp * np.sin(2 * np.pi * freq * t + phase) * np.sin(np.pi * t)  # taper wobble at ends
            pos = p1 * (1 - t) + p2 * t + wobble
            r = radius * (1 - taper * t)
            if r < 1:
                r = 1
            dist = np.sqrt((x - pos[0])**2 + (y - pos[1])**2 + (z - pos[2])**2)
            vessels.__ior__(dist < r)
    
    # Helper for curved vessel
    def add_curved_vessel(points: list, radius: float, taper: float = 0) -> None:
        """Draw vessel through list of control points."""
        for i in range(len(points) - 1):
            r = radius * (1 - taper * i / len(points))
            add_vessel_segment(points[i], points[i+1], max(r, 1))
    
    r_large = 3.0   # major arteries
    r_medium = 2.2  # medium branches  
    r_small = 1.5   # small branches
    
    # --- Circle of Willis region ---
    # Internal carotid arteries (bilateral, vertical)
    for side in [-1, 1]:
        z_off = int(cz + side * nz * 0.06)
        points = [(cx + int(nx*0.1), cy + int(ny*0.1), z_off),
                  (cx, cy, z_off),
                  (cx - int(nx*0.05), cy - int(ny*0.05), z_off)]
        add_curved_vessel(points, r_large)
    
    # Anterior communicating / ACA
    add_vessel_segment((cx - int(nx*0.05), cy - int(ny*0.05), cz - int(nz*0.06)),
                       (cx - int(nx*0.05), cy - int(ny*0.05), cz + int(nz*0.06)), r_medium)
    
    # ACA going anterior
    for side in [-1, 1]:
        z_off = int(cz + side * nz * 0.03)
        points = [(cx - int(nx*0.05), cy - int(ny*0.05), z_off)]
        for step in range(8):
            points.append((cx - int(nx*0.05) - step * int(nx*0.02),
                          cy - int(ny*0.05) - step * int(ny*0.02),
                          z_off + side * step * int(nz*0.005)))
        add_curved_vessel(points, r_medium, taper=0.3)
    
    # MCAs (bilateral, major lateral branches)
    for side in [-1, 1]:
        # Main MCA trunk
        z_start = int(cz + side * nz * 0.06)
        z_end = int(cz + side * nz * 0.35)
        
        trunk_points = []
        for step in range(12):
            t = step / 11
            vz = z_start + (z_end - z_start) * t
            vx = cx - int(nx * 0.03) + int(nx * 0.02 * np.sin(t * 2))
            vy = cy - int(ny * 0.02) + int(ny * 0.01 * np.cos(t * 3))
            trunk_points.append((int(vx), int(vy), int(vz)))
        add_curved_vessel(trunk_points, r_large, taper=0.4)
        
        # MCA branches (superior and inferior)
        for branch_offset in [-1, 0, 1]:
            branch_points = []
            start_idx = 4 + branch_offset
            if start_idx < len(trunk_points):
                start = trunk_points[start_idx]
                for step in range(8):
                    t = step / 7
                    vz = start[2] + side * int(nz * 0.06 * t)
                    vx = start[0] - int(nx * 0.08 * t) + int(nx * 0.02 * np.sin(t * 3 + branch_offset))
                    vy = start[1] + branch_offset * int(ny * 0.04 * t)
                    branch_points.append((int(vx), int(vy), int(vz)))
                add_curved_vessel(branch_points, r_small, taper=0.5)
    
    # PCAs (bilateral, posterior)
    for side in [-1, 1]:
        z_off = int(cz + side * nz * 0.04)
        points = [(cx, cy + int(ny*0.08), cz)]
        for step in range(10):
            t = step / 9
            points.append((cx + int(nx*0.01 * np.sin(t*2)),
                          cy + int(ny*0.08) + int(ny*0.12*t),
                          z_off + side * int(nz*0.08*t)))
        add_curved_vessel(points, r_medium, taper=0.4)
    
    # Basilar artery
    points = [(cx + int(nx*0.02), cy + int(ny*0.25), cz),
              (cx + int(nx*0.02), cy + int(ny*0.18), cz),
              (cx, cy + int(ny*0.08), cz)]
    add_curved_vessel(points, r_large)
    
    # Vertebral arteries
    for side in [-1, 1]:
        z_off = int(cz + side * nz * 0.04)
        points = [(cx + int(nx*0.05), cy + int(ny*0.35), z_off),
                  (cx + int(nx*0.03), cy + int(ny*0.28), z_off),
                  (cx + int(nx*0.02), cy + int(ny*0.22), int(cz + side * nz * 0.02))]
        add_curved_vessel(points, r_medium)
    
    # Superior sagittal sinus (midline, large)
    points = [(cx - int(nx*0.25), cy - int(ny*0.15), cz),
              (cx - int(nx*0.15), cy, cz),
              (cx - int(nx*0.05), cy + int(ny*0.1), cz)]
    add_curved_vessel(points, r_large)
    
    # Only inside brain
    brain_mask = (phantom >= 1) & (phantom <= 4)
    vessels &= brain_mask
    
    phantom_with_vessels = phantom.copy()
    phantom_with_vessels[vessels] = 11   # Blood (tissue_db); was 6, which is now Muscle
    
    return phantom_with_vessels

def add_activation_3d(phantom: np.ndarray) -> np.ndarray:
    """Create 3D activation map for fMRI simulation."""
    nx, ny, nz = phantom.shape
    cx, cy, cz = nx // 2, ny // 2, nz // 2
    
    activation = np.zeros((nx, ny, nz), dtype=float)
    x, y, z = np.mgrid[:nx, :ny, :nz]
    
    # Visual cortex (posterior, large bilateral region)
    visual = np.exp(-((z - cz)**2/(nz*0.12)**2 + (y - (cy + int(ny*0.22)))**2/(ny*0.06)**2 + (x - cx)**2/(nx*0.08)**2))
    
    # Motor cortex (superior strip, bilateral)
    motor = np.exp(-((y - cy)**2/(ny*0.04)**2 + (x - (cx - int(nx*0.2)))**2/(nx*0.03)**2)) * \
            np.exp(-(z - cz)**2/(nz*0.2)**2)
    
    # Broca's area (left frontal)
    broca = np.exp(-((z - (cz - int(nz*0.2)))**2 + (y - (cy - int(ny*0.1)))**2 + (x - cx)**2) / (2*(nx*0.04)**2))
    
    # Wernicke's area (left temporal/parietal)
    wernicke = np.exp(-((z - (cz - int(nz*0.22)))**2 + (y - (cy + int(ny*0.08)))**2 + (x - cx)**2) / (2*(nx*0.05)**2))
    
    # Auditory cortex (bilateral temporal)
    for side in [-1, 1]:
        auditory = np.exp(-((z - (cz + side*int(nz*0.25)))**2 + (y - (cy + int(ny*0.03)))**2 + (x - (cx + int(nx*0.02)))**2) / (2*(nx*0.03)**2))
        activation += auditory * 1.8
    
    # Combine
    activation += visual * 3.5 + motor * 2.8 + broca * 2.2 + wernicke * 2.0
    
    # Only in gray matter
    gm_mask = phantom == 2
    activation[~gm_mask] = 0
    activation = np.clip(activation, 0, 5.0)
    
    return activation

def add_tissue_texture(phantom: np.ndarray, sigma_coarse: float = 10, sigma_fine: float = 3) -> np.ndarray:
    """Create tissue inhomogeneity texture for more realistic images.
    Returns a multiplicative texture map (values around 1.0)."""
    nx, ny, nz = phantom.shape
    np.random.seed(42)
    
    # B1 inhomogeneity (smooth, affects whole image)
    b1_field = np.random.randn(nx, ny, nz) * 0.04
    b1_field = gaussian_filter(b1_field, sigma=sigma_coarse)
    
    # Biological tissue variation (finer)
    bio_variation = np.random.randn(nx, ny, nz) * 0.02
    bio_variation = gaussian_filter(bio_variation, sigma=sigma_fine)
    
    texture = 1.0 + b1_field + bio_variation
    
    # Additional per-tissue variation
    for label in [2, 3]:  # GM and WM have more internal variation
        mask = phantom == label
        tissue_var = np.random.randn(nx, ny, nz) * 0.03
        tissue_var = gaussian_filter(tissue_var, sigma=2)
        texture[mask] += tissue_var[mask]
    
    return texture

def get_diffusion_properties_3d(phantom: np.ndarray | None) -> dict[int, dict[str, float]]:
    """Return per-label diffusion properties."""
    return {
        0: {"ADC": 0.0, "FA": 0.0},
        1: {"ADC": 3.0, "FA": 0.0},
        2: {"ADC": 0.8, "FA": 0.15},
        3: {"ADC": 0.7, "FA": 0.45},
        4: {"ADC": 0.05, "FA": 0.0},
        5: {"ADC": 0.0, "FA": 0.0},
        6: {"ADC": 1.0, "FA": 0.0},
    }

def simulate_diffusion_3d_slice(
    phantom_slice: np.ndarray,
    b_value: float,
    direction: list[float] | np.ndarray,
    TR: float = 8000,
    TE: float = 80,
) -> np.ndarray:
    """Simulate diffusion-weighted image with anisotropy effects."""
    from signal_engine import spin_echo_signal
    from phantom3d import TISSUE_PROPERTIES_3D
    
    diff_props = get_diffusion_properties_3d(None)
    image = np.zeros_like(phantom_slice, dtype=float)
    
    # Add directional variation for white matter
    np.random.seed(45)
    size = phantom_slice.shape
    # Fiber orientation field (smooth, varies across WM)
    fiber_angle = gaussian_filter(np.random.randn(*size), sigma=8) * np.pi
    
    dir_vec = np.array(direction[:2] if len(direction) >= 2 else [direction[0], 0], dtype=float)
    dir_vec = dir_vec / (np.linalg.norm(dir_vec) + 1e-10)
    
    for label, props in TISSUE_PROPERTIES_3D.items():
        mask = phantom_slice == label
        if not np.any(mask):
            continue
        
        S0 = spin_echo_signal(props["T1"], props["T2"], props["PD"], TR, TE)
        dp = diff_props.get(label, {"ADC": 0, "FA": 0})
        
        if label == 3 and dp["FA"] > 0:
            # Anisotropic diffusion in white matter
            FA = dp["FA"]
            ADC = dp["ADC"]
            MD = ADC * 1e-3
            
            # Eigenvalue decomposition based on FA
            diff_sq = 2 * MD**2 * FA**2 / max(1 - FA**2/2, 0.01)
            diff = np.sqrt(diff_sq)
            lambda1 = MD + diff/2
            lambda2 = MD - diff/2
            lambda2 = max(lambda2, 0.01e-3)
            
            # Per-voxel apparent diffusion based on fiber orientation vs gradient direction
            angles = fiber_angle[mask]
            fiber_dirs = np.stack([np.cos(angles), np.sin(angles)], axis=1)
            dot_products = np.abs(fiber_dirs @ dir_vec)
            
            # Apparent D = lambda1*cos^2(theta) + lambda2*sin^2(theta)
            apparent_D = lambda1 * dot_products**2 + lambda2 * (1 - dot_products**2)
            signal = S0 * np.exp(-b_value * apparent_D)
            image[mask] = signal
        else:
            D = dp["ADC"] * 1e-3
            signal = S0 * np.exp(-b_value * D)
            image[mask] = signal
    
    # Add tissue texture
    texture = gaussian_filter(np.random.randn(*size) * 0.03, sigma=3) + 1.0
    image *= texture
    image = np.clip(image, 0, None)
    
    return image

def simulate_adc_map_3d(phantom_slice: np.ndarray) -> np.ndarray:
    """Generate ADC map with spatial variation."""
    diff_props = get_diffusion_properties_3d(None)
    adc_map = np.zeros_like(phantom_slice, dtype=float)
    
    np.random.seed(42)
    size = phantom_slice.shape
    variation = gaussian_filter(np.random.randn(*size) * 0.05, sigma=3)
    
    for label, dp in diff_props.items():
        mask = phantom_slice == label
        if not np.any(mask) or dp["ADC"] == 0:
            continue
        base_adc = dp["ADC"]
        local_adc = base_adc * (1 + variation[mask] * 0.25)
        local_adc = np.clip(local_adc, base_adc * 0.5, base_adc * 1.5)
        adc_map[mask] = local_adc
    
    return adc_map

def simulate_fa_map_3d(phantom_slice: np.ndarray) -> np.ndarray:
    """Generate FA map with fiber structure variation."""
    diff_props = get_diffusion_properties_3d(None)
    fa_map = np.zeros_like(phantom_slice, dtype=float)
    
    np.random.seed(43)
    size = phantom_slice.shape
    # Tract-like structure
    tract_pattern = gaussian_filter(np.random.randn(*size), sigma=5)
    fine_detail = gaussian_filter(np.random.randn(*size), sigma=2)
    
    for label, dp in diff_props.items():
        mask = phantom_slice == label
        if not np.any(mask) or dp["FA"] == 0:
            continue
        base_fa = dp["FA"]
        
        if label == 3:  # White matter
            local_fa = base_fa + tract_pattern[mask] * 0.15 + fine_detail[mask] * 0.05
            local_fa = np.clip(local_fa, 0.1, 0.9)
        else:
            local_fa = base_fa + fine_detail[mask] * 0.05
            local_fa = np.clip(local_fa, 0.0, 0.5)
        
        fa_map[mask] = local_fa
    
    return fa_map

def simulate_tof_3d_slice(
    phantom_slice: np.ndarray,
    TR: float = 25,
    TE: float = 4,
    flip_angle: float = 60,
) -> np.ndarray:
    """Simulate TOF MRA with better vessel-to-background contrast.

    Blood (label 11) is fresh, unsaturated inflow → bright; all other tissue is
    saturated by the short TR + large flip angle → dark. Take a MIP over a slab
    of these slices for the angiogram.
    """
    from signal_engine import gradient_echo_signal
    import tissue_db

    props_extended = tissue_db.properties("3T")
    image = np.zeros_like(phantom_slice, dtype=float)
    alpha_rad = np.radians(flip_angle)

    for label, props in props_extended.items():
        mask = phantom_slice == label
        if not np.any(mask):
            continue

        T2star = props.get("T2star", props["T2"] * 0.6)

        if label == 11:  # Blood / vessels - full inflow enhancement
            # Fresh unsaturated blood signal (much brighter than static tissue)
            image[mask] = props["PD"] * np.sin(alpha_rad) * np.exp(-TE / T2star)
        elif label == 0:
            image[mask] = 0
        else:
            # Static tissue - heavily saturated by short TR + large flip angle
            image[mask] = gradient_echo_signal(props["T1"], T2star, props["PD"], TR, TE, flip_angle)
    
    # Add subtle texture
    np.random.seed(46)
    texture = gaussian_filter(np.random.randn(*phantom_slice.shape) * 0.02, sigma=2) + 1.0
    image *= texture
    image = np.clip(image, 0, None)
    
    return image

def simulate_fmri_3d_slice(
    phantom_slice: np.ndarray,
    activation_slice: np.ndarray,
    TR: float = 2000,
    TE: float = 30,
    flip_angle: float = 90,
    is_active: bool = True,
) -> np.ndarray:
    """Simulate fMRI with tissue texture."""
    from signal_engine import gradient_echo_signal
    from phantom3d import TISSUE_PROPERTIES_3D
    
    image = np.zeros_like(phantom_slice, dtype=float)
    T2star_base = {0: 1, 1: 1200, 2: 60, 3: 48, 4: 40, 5: 3, 6: 50}
    
    for label, props in TISSUE_PROPERTIES_3D.items():
        mask = phantom_slice == label
        if not np.any(mask):
            continue
        
        T2star = T2star_base.get(label, 50)
        
        if is_active and label == 2:
            act_values = activation_slice[mask]
            T2star_modified = T2star * (1 + act_values / 100.0 * 0.3)
            alpha = np.radians(flip_angle)
            E1 = np.exp(-TR / props["T1"])
            base_signal = props["PD"] * np.sin(alpha) * (1 - E1) / (1 - np.cos(alpha) * E1)
            signals = base_signal * np.exp(-TE / T2star_modified)
            image[mask] = signals
        else:
            sig = gradient_echo_signal(props["T1"], T2star, props["PD"], TR, TE, flip_angle)
            image[mask] = sig
    
    # Add tissue texture
    np.random.seed(47)
    texture = gaussian_filter(np.random.randn(*phantom_slice.shape) * 0.025, sigma=2) + 1.0
    image *= texture
    image = np.clip(image, 0, None)
    
    return image

def compute_activation_map_3d(
    phantom_slice: np.ndarray,
    activation_slice: np.ndarray,
    TR: float = 2000,
    TE: float = 30,
    flip_angle: float = 90,
) -> np.ndarray:
    """Compute BOLD percent signal change map."""
    rest = simulate_fmri_3d_slice(phantom_slice, activation_slice, TR, TE, flip_angle, is_active=False)
    active = simulate_fmri_3d_slice(phantom_slice, activation_slice, TR, TE, flip_angle, is_active=True)
    
    with np.errstate(divide='ignore', invalid='ignore'):
        pct_change = np.where(rest > 0, (active - rest) / rest * 100, 0)
    
    return pct_change

def compute_tstat_map_3d(
    phantom_slice: np.ndarray,
    activation_slice: np.ndarray,
    TR: float = 2000,
    TE: float = 30,
    flip_angle: float = 90,
    num_volumes: int = 100,
) -> np.ndarray:
    """Compute t-statistic map."""
    rest = simulate_fmri_3d_slice(phantom_slice, activation_slice, TR, TE, flip_angle, is_active=False)
    active = simulate_fmri_3d_slice(phantom_slice, activation_slice, TR, TE, flip_angle, is_active=True)
    
    sigma = np.max(rest) * 0.5 / 100
    n_per_condition = num_volumes // 2
    pooled_se = sigma * np.sqrt(2.0 / n_per_condition)
    
    with np.errstate(divide='ignore', invalid='ignore'):
        t_map = np.where(pooled_se > 0, (active - rest) / pooled_se, 0)
    
    brain_mask = phantom_slice > 0
    t_map[~brain_mask] = 0
    
    return t_map

def load_real_tof_mra() -> np.ndarray | None:
    """Load the real TOF MRA dataset."""
    import os
    path = os.path.expanduser('~/mrisim/data/tof_mra_real.npy')
    if os.path.exists(path):
        return np.load(path)
    return None

def simulate_tof_with_real_data(
    real_mra: np.ndarray,
    orientation: str,
    slice_idx: int,
    TR: float = 25,
    TE: float = 4,
    flip_angle: float = 60,
    mip_slab: int = 20,
) -> np.ndarray:
    """Use real MRA data with parameter-dependent contrast modulation.
    
    The real data provides anatomy; parameters modulate contrast.
    Higher flip angle -> more inflow enhancement -> brighter vessels
    Shorter TR -> more background suppression -> better vessel contrast
    """
    from phantom3d import get_slice as get_slice_raw
    
    max_idx = {"axial": real_mra.shape[2], "sagittal": real_mra.shape[0], "coronal": real_mra.shape[1]}
    max_sl = max_idx[orientation] - 1
    
    # MIP over slab
    start_sl = max(0, slice_idx - mip_slab // 2)
    end_sl = min(max_sl, slice_idx + mip_slab // 2)
    
    mip_image: np.ndarray | None = None
    for s in range(start_sl, end_sl + 1):
        if orientation == 'axial':
            sl = np.rot90(real_mra[:, :, s], k=3)
        elif orientation == 'sagittal':
            sl = np.rot90(real_mra[s, :, :], k=3)
        else:  # coronal
            sl = np.rot90(real_mra[:, s, :], k=-1)

        if mip_image is None:
            mip_image = sl.copy()
        else:
            mip_image = np.maximum(mip_image, sl)

    if mip_image is None:
        return np.zeros_like(real_mra[:, :, 0])
    
    # Parameter-dependent contrast modulation
    # Optimal TOF: short TR (20-30ms), high FA (60-70°), short TE (3-5ms)
    # Vessel signal: proportional to sin(FA) for unsaturated blood
    # Background suppression: better with short TR + high FA
    
    alpha = np.radians(flip_angle)
    
    # Vessel enhancement factor (peaks around FA=60-70°)
    vessel_factor = np.sin(alpha) / np.sin(np.radians(60))  # normalized to optimal
    
    # Background suppression (better with short TR, high FA)
    # At very long TR, background recovers and vessels lose contrast
    suppression_factor = np.exp(-TR / 50) * 2  # peaks at short TR
    suppression_factor = np.clip(suppression_factor, 0.1, 1.5)
    
    # TE effect (signal decay)
    te_factor = np.exp(-TE / 50)
    
    # Apply modulation
    # Separate "vessels" (bright voxels) from "background" (dim voxels)
    threshold = 0.15
    vessel_mask = mip_image > threshold
    background_mask = ~vessel_mask & (mip_image > 0)
    
    result = mip_image.copy()
    result[vessel_mask] *= vessel_factor * te_factor
    result[background_mask] *= (1 - suppression_factor * 0.5) * te_factor
    result = np.clip(result, 0, 1)
    
    return result

if __name__ == "__main__":
    from brainweb_loader import get_brainweb_or_synthetic
    from phantom3d import get_slice
    
    phantom, source = get_brainweb_or_synthetic()
    print(f"Source: {source}, Shape: {phantom.shape}")
    
    phantom_v = add_vessels_3d(phantom)
    print(f"Vessel voxels: {np.sum(phantom_v == 6)}")
    
    activation = add_activation_3d(phantom)
    print(f"Activated voxels (>0.5): {np.sum(activation > 0.5)}")
    
    # Test
    ax_slice = get_slice(phantom_v, 'axial', 90)
    act_slice = get_slice(activation, 'axial', 90)
    
    dwi = simulate_diffusion_3d_slice(ax_slice, b_value=1000, direction=[1,0])
    print(f"DWI max={dwi.max():.4f}, WM={dwi[ax_slice==3].mean():.4f}, GM={dwi[ax_slice==2].mean():.4f}")
    
    tof = simulate_tof_3d_slice(ax_slice)
    vessel_sig = tof[ax_slice==6].mean() if np.any(ax_slice==6) else 0
    brain_sig = tof[ax_slice==2].mean() if np.any(ax_slice==2) else 0
    print(f"TOF vessel={vessel_sig:.4f}, brain={brain_sig:.4f}, ratio={vessel_sig/(brain_sig+1e-10):.1f}x")
    
    fmri = simulate_fmri_3d_slice(ax_slice, act_slice, is_active=True)
    print(f"fMRI max={fmri.max():.4f}")
    
    print("\n3D extended module working.")