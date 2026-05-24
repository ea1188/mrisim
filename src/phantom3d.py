from typing import Any

import numpy as np
from scipy.ndimage import gaussian_filter, binary_dilation, binary_erosion

def generate_synthetic_3d_brain(nx=181, ny=217, nz=181):
    """Generate a realistic 3D brain phantom with cortical folding and subcortical structures."""
    phantom = np.zeros((nx, ny, nz), dtype=np.uint8)
    
    cx, cy, cz = nx // 2, ny // 2, nz // 2
    z, y, x = np.ogrid[:nx, :ny, :nz]
    
    # --- Scalp ---
    scalp = ((x - cz)**2 / (cz * 0.92)**2 + 
             (y - cy)**2 / (cy * 0.87)**2 + 
             (z - cx)**2 / (cx * 0.90)**2) < 1
    phantom[scalp] = 4
    
    # --- Skull ---
    skull = ((x - cz)**2 / (cz * 0.86)**2 + 
             (y - cy)**2 / (cy * 0.81)**2 + 
             (z - cx)**2 / (cx * 0.84)**2) < 1
    phantom[skull] = 5
    
    # --- CSF (subarachnoid space) ---
    csf_outer = ((x - cz)**2 / (cz * 0.82)**2 + 
                 (y - cy)**2 / (cy * 0.77)**2 + 
                 (z - cx)**2 / (cx * 0.80)**2) < 1
    phantom[csf_outer] = 1
    
    # --- Cortical gray matter ---
    cortex = ((x - cz)**2 / (cz * 0.78)**2 + 
              (y - cy)**2 / (cy * 0.73)**2 + 
              (z - cx)**2 / (cx * 0.76)**2) < 1
    phantom[cortex] = 2
    
    # --- White matter ---
    wm = ((x - cz)**2 / (cz * 0.60)**2 + 
          (y - cy)**2 / (cy * 0.57)**2 + 
          (z - cx)**2 / (cx * 0.60)**2) < 1
    phantom[wm] = 3
    
    # --- Add cortical folding (sulci and gyri) ---
    np.random.seed(42)
    # Create 3D noise field for cortical folding
    fold_noise = np.random.randn(nx, ny, nz)
    fold_noise = gaussian_filter(fold_noise, sigma=4)
    
    # Second frequency for finer folds
    fine_folds = np.random.randn(nx, ny, nz)
    fine_folds = gaussian_filter(fine_folds, sigma=2.5)
    
    # Combined fold pattern
    fold_pattern = fold_noise * 0.6 + fine_folds * 0.4
    
    # Apply folds: where fold_pattern is high in gray matter, convert to CSF (sulci)
    gm_mask = phantom == 2
    sulci_threshold = 0.35
    sulci = gm_mask & (fold_pattern > sulci_threshold)
    phantom[sulci] = 1  # CSF in sulci
    
    # Where fold_pattern is low in CSF near cortex, convert to GM (gyri pushing out)
    csf_near_cortex = (phantom == 1) & csf_outer & ~skull
    gyri = csf_near_cortex & (fold_pattern < -0.3)
    phantom[gyri] = 2  # GM expanding into CSF
    
    # --- Lateral ventricles (more realistic shape) ---
    # Frontal horns
    for side in [-1, 1]:
        horn_x = cz + side * int(nz * 0.06)
        frontal_horn = (((x - horn_x)**2 / (nz*0.025)**2 + 
                        (y - (cy - ny*0.08))**2 / (ny*0.08)**2 + 
                        (z - cx)**2 / (nx*0.04)**2) < 1)
        phantom[frontal_horn] = 1
    
    # Body of ventricles
    for side in [-1, 1]:
        body_x = cz + side * int(nz * 0.05)
        vent_body = (((x - body_x)**2 / (nz*0.02)**2 + 
                     (y - cy)**2 / (ny*0.10)**2 + 
                     (z - (cx - nx*0.02))**2 / (nx*0.03)**2) < 1)
        phantom[vent_body] = 1
    
    # Occipital horns
    for side in [-1, 1]:
        occ_x = cz + side * int(nz * 0.04)
        occ_horn = (((x - occ_x)**2 / (nz*0.015)**2 + 
                    (y - (cy + ny*0.12))**2 / (ny*0.06)**2 + 
                    (z - cx)**2 / (nx*0.02)**2) < 1)
        phantom[occ_horn] = 1
    
    # Third ventricle
    third_v = (((x - cz)**2 / (nz*0.006)**2 + 
                (y - cy)**2 / (ny*0.04)**2 + 
                (z - cx)**2 / (nx*0.015)**2) < 1)
    phantom[third_v] = 1
    
    # Fourth ventricle
    fourth_v = (((x - cz)**2 / (nz*0.012)**2 + 
                 (y - (cy + ny*0.18))**2 / (ny*0.02)**2 + 
                 (z - (cx + nx*0.08))**2 / (nx*0.012)**2) < 1)
    phantom[fourth_v] = 1
    
    # --- Deep gray matter structures ---
    # Thalamus (bilateral)
    for side in [-1, 1]:
        thal_x = cz + side * int(nz * 0.055)
        thalamus = (((x - thal_x)**2 / (nz*0.04)**2 + 
                    (y - (cy + ny*0.01))**2 / (ny*0.035)**2 + 
                    (z - (cx - nx*0.02))**2 / (nx*0.03)**2) < 1)
        phantom[thalamus] = 2
    
    # Caudate nucleus (bilateral, C-shaped)
    for side in [-1, 1]:
        caud_x = cz + side * int(nz * 0.06)
        # Head of caudate
        caudate_head = (((x - caud_x)**2 / (nz*0.025)**2 + 
                        (y - (cy - ny*0.06))**2 / (ny*0.03)**2 + 
                        (z - (cx - nx*0.03))**2 / (nx*0.025)**2) < 1)
        phantom[caudate_head] = 2
        # Body
        caudate_body = (((x - caud_x)**2 / (nz*0.015)**2 + 
                        (y - (cy - ny*0.02))**2 / (ny*0.05)**2 + 
                        (z - (cx - nx*0.06))**2 / (nx*0.015)**2) < 1)
        phantom[caudate_body] = 2
    
    # Putamen (bilateral)
    for side in [-1, 1]:
        put_x = cz + side * int(nz * 0.10)
        putamen = (((x - put_x)**2 / (nz*0.025)**2 + 
                   (y - (cy - ny*0.02))**2 / (ny*0.04)**2 + 
                   (z - (cx - nx*0.02))**2 / (nx*0.03)**2) < 1)
        phantom[putamen] = 2
    
    # Globus pallidus (bilateral, medial to putamen)
    for side in [-1, 1]:
        gp_x = cz + side * int(nz * 0.07)
        gp = (((x - gp_x)**2 / (nz*0.015)**2 + 
              (y - (cy - ny*0.02))**2 / (ny*0.025)**2 + 
              (z - (cx - nx*0.02))**2 / (nx*0.02)**2) < 1)
        phantom[gp] = 2
    
    # Internal capsule (WM tracts between caudate and putamen)
    for side in [-1, 1]:
        ic_x = cz + side * int(nz * 0.08)
        ic = (((x - ic_x)**2 / (nz*0.008)**2 + 
              (y - (cy - ny*0.02))**2 / (ny*0.06)**2 + 
              (z - (cx - nx*0.02))**2 / (nx*0.04)**2) < 1)
        phantom[ic] = 3
    
    # --- Corpus callosum (midline WM structure) ---
    # Genu (anterior)
    cc_genu = (((x - cz)**2 / (nz*0.02)**2 + 
                (y - (cy - ny*0.12))**2 / (ny*0.03)**2 + 
                (z - (cx - nx*0.08))**2 / (nx*0.025)**2) < 1)
    phantom[cc_genu] = 3
    
    # Body
    cc_body = (((x - cz)**2 / (nz*0.25)**2 + 
                (y - cy)**2 / (ny*0.01)**2 + 
                (z - (cx - nx*0.12))**2 / (nx*0.012)**2) < 1)
    # Make it thin in z
    cc_body &= (np.abs(z - (cx - int(nx*0.12))) < nx*0.015)
    phantom[cc_body] = 3
    
    # Splenium (posterior)
    cc_splen = (((x - cz)**2 / (nz*0.025)**2 + 
                 (y - (cy + ny*0.08))**2 / (ny*0.03)**2 + 
                 (z - (cx - nx*0.08))**2 / (nx*0.025)**2) < 1)
    phantom[cc_splen] = 3
    
    # --- Cerebellum ---
    cerebellum_outer = (((x - cz)**2 / (nz*0.30)**2 + 
                         (y - (cy + ny*0.30))**2 / (ny*0.11)**2 + 
                         (z - (cx + nx*0.12))**2 / (nx*0.13)**2) < 1)
    
    # Cerebellar gray matter (with foliation pattern)
    cereb_noise = np.random.randn(nx, ny, nz)
    cereb_noise = gaussian_filter(cereb_noise, sigma=1.5)
    
    cereb_gm = cerebellum_outer & (phantom == 0)
    phantom[cereb_gm] = 2
    
    # Cerebellar white matter (arbor vitae)
    cereb_wm = (((x - cz)**2 / (nz*0.15)**2 + 
                 (y - (cy + ny*0.30))**2 / (ny*0.06)**2 + 
                 (z - (cx + nx*0.12))**2 / (nx*0.07)**2) < 1)
    cereb_wm_mask = cereb_wm & (phantom == 2) & cerebellum_outer
    phantom[cereb_wm_mask] = 3
    
    # Cerebellar folia (alternating GM/CSF)
    cereb_folia = cerebellum_outer & (phantom == 2) & (cereb_noise > 0.5)
    phantom[cereb_folia] = 1
    
    # --- Brainstem ---
    # Midbrain
    midbrain = (((x - cz)**2 / (nz*0.035)**2 + 
                 (y - (cy + ny*0.15))**2 / (ny*0.03)**2 + 
                 (z - (cx + nx*0.02))**2 / (nx*0.035)**2) < 1)
    phantom[midbrain] = 3
    
    # Pons
    pons = (((x - cz)**2 / (nz*0.045)**2 + 
             (y - (cy + ny*0.22))**2 / (ny*0.035)**2 + 
             (z - (cx + nx*0.05))**2 / (nx*0.035)**2) < 1)
    phantom[pons] = 3
    
    # Medulla
    medulla = (((x - cz)**2 / (nz*0.025)**2 + 
                (y - (cy + ny*0.28))**2 / (ny*0.04)**2 + 
                (z - (cx + nx*0.08))**2 / (nx*0.025)**2) < 1)
    phantom[medulla] = 3
    
    # --- Optic chiasm / nerves ---
    optic = (((x - cz)**2 / (nz*0.015)**2 + 
              (y - (cy + ny*0.10))**2 / (ny*0.015)**2 + 
              (z - (cx + nx*0.01))**2 / (nx*0.008)**2) < 1)
    phantom[optic] = 3
    
    # --- Eyes (for realistic axial appearance) ---
    for side in [-1, 1]:
        eye_x = cz + side * int(nz * 0.18)
        eye = (((x - eye_x)**2 + 
                (y - (cy - ny*0.30))**2 + 
                (z - (cx + nx*0.05))**2) < (nx*0.045)**2)
        eye_region = eye & (phantom == 4)  # only in scalp region
        phantom[eye_region] = 1  # vitreous = fluid
    
    return phantom

def get_slice(phantom_3d, orientation='axial', slice_idx=None):
    """Extract a 2D slice from the 3D phantom."""
    if orientation == 'axial':
        max_idx = phantom_3d.shape[0]
        if slice_idx is None:
            slice_idx = max_idx // 2
        slice_idx = np.clip(slice_idx, 0, max_idx - 1)
        return phantom_3d[slice_idx, :, :]
    elif orientation == 'sagittal':
        max_idx = phantom_3d.shape[2]
        if slice_idx is None:
            slice_idx = max_idx // 2
        slice_idx = np.clip(slice_idx, 0, max_idx - 1)
        return np.fliplr(phantom_3d[:, :, slice_idx])
    elif orientation == 'coronal':
        max_idx = phantom_3d.shape[1]
        if slice_idx is None:
            slice_idx = max_idx // 2
        slice_idx = np.clip(slice_idx, 0, max_idx - 1)
        return phantom_3d[:, slice_idx, :]

def simulate_slice(phantom_slice, TR, TE, sequence='SE', TI=None, flip_angle=90):
    """Apply signal equations to a 2D slice from the 3D phantom."""
    from signal_engine import spin_echo_signal, gradient_echo_signal, inversion_recovery_signal
    
    image = np.zeros_like(phantom_slice, dtype=float)
    
    for label, props in TISSUE_PROPERTIES_3D.items():
        mask = phantom_slice == label
        if not np.any(mask):
            continue
        
        if sequence == 'SE':
            sig = spin_echo_signal(props["T1"], props["T2"], props["PD"], TR, TE)
        elif sequence == 'GRE':
            sig = gradient_echo_signal(props["T1"], props["T2star"], props["PD"], TR, TE, flip_angle)
        elif sequence == 'IR':
            if TI is None:
                TI = 150
            sig = inversion_recovery_signal(props["T1"], props["T2"], props["PD"], TR, TE, TI)
        else:
            sig = spin_echo_signal(props["T1"], props["T2"], props["PD"], TR, TE)
        
        image[mask] = sig
    
    return image

TISSUE_PROPERTIES_3D: dict[int, dict[str, Any]] = {
    0: {"T1": 1, "T2": 1, "PD": 0.0, "T2star": 1, "name": "Background"},
    1: {"T1": 4500, "T2": 2200, "PD": 1.0, "T2star": 1500, "name": "CSF"},
    2: {"T1": 1330, "T2": 100, "PD": 0.8, "T2star": 60, "name": "Gray Matter"},
    3: {"T1": 830, "T2": 80, "PD": 0.65, "T2star": 48, "name": "White Matter"},
    4: {"T1": 370, "T2": 60, "PD": 0.95, "T2star": 40, "name": "Fat/Scalp"},
    5: {"T1": 200, "T2": 5, "PD": 0.1, "T2star": 3, "name": "Bone"},
}

if __name__ == "__main__":
    print("Generating realistic 3D brain phantom...")
    phantom = generate_synthetic_3d_brain()
    print(f"Shape: {phantom.shape}")
    print(f"Labels: {np.unique(phantom)}")
    for label, props in TISSUE_PROPERTIES_3D.items():
        count = np.sum(phantom == label)
        pct = count / phantom.size * 100
        print(f"  {label} ({props['name']:15s}): {count:>8} voxels ({pct:.1f}%)")
    
    print("\n3D phantom module working.")