import numpy as np

def create_brain_phantom(size=256):
    """Create a 2D brain phantom with labeled tissue regions."""
    phantom = np.zeros((size, size), dtype=int)
    center = size // 2
    y, x = np.ogrid[:size, :size]
    
    # Skull/background = 0
    # 1 = CSF (outer ring)
    # 2 = Gray matter
    # 3 = White matter
    # 4 = CSF (ventricles)
    
    # Outer skull boundary (ellipse)
    skull_mask = ((x - center)**2 / (center * 0.85)**2 + 
                  (y - center)**2 / (center * 0.75)**2) < 1
    phantom[skull_mask] = 1  # CSF layer
    
    # Brain parenchyma (gray matter outer)
    brain_mask = ((x - center)**2 / (center * 0.78)**2 + 
                  (y - center)**2 / (center * 0.68)**2) < 1
    phantom[brain_mask] = 2  # Gray matter
    
    # White matter (inner)
    wm_mask = ((x - center)**2 / (center * 0.55)**2 + 
               (y - center)**2 / (center * 0.50)**2) < 1
    phantom[wm_mask] = 3  # White matter
    
    # Lateral ventricles (CSF)
    # Left ventricle
    lv_mask = ((x - (center - size*0.12))**2 / (size*0.06)**2 + 
               (y - center)**2 / (size*0.15)**2) < 1
    phantom[lv_mask] = 4  # CSF
    
    # Right ventricle
    rv_mask = ((x - (center + size*0.12))**2 / (size*0.06)**2 + 
               (y - center)**2 / (size*0.15)**2) < 1
    phantom[rv_mask] = 4  # CSF
    
    # Gray matter nuclei (thalamus/caudate)
    ln_mask = ((x - (center - size*0.08))**2 + (y - (center - size*0.02))**2) < (size*0.04)**2
    phantom[ln_mask] = 2
    rn_mask = ((x - (center + size*0.08))**2 + (y - (center - size*0.02))**2) < (size*0.04)**2
    phantom[rn_mask] = 2
    
    return phantom

# Tissue label mapping
TISSUE_LABELS = {
    0: "background",
    1: "csf",
    2: "gray_matter",
    3: "white_matter",
    4: "csf",
}

TISSUE_PROPERTIES = {
    0: {"T1": 1, "T2": 1, "PD": 0.0},       # background (no signal)
    1: {"T1": 4500, "T2": 2200, "PD": 1.0},  # CSF
    2: {"T1": 1330, "T2": 100, "PD": 0.8},   # Gray matter
    3: {"T1": 830, "T2": 80, "PD": 0.65},    # White matter
    4: {"T1": 4500, "T2": 2200, "PD": 1.0},  # CSF (ventricles)
}

if __name__ == "__main__":
    phantom = create_brain_phantom()
    print(f"Phantom shape: {phantom.shape}")
    print(f"Tissue labels present: {np.unique(phantom)}")
    for label in np.unique(phantom):
        count = np.sum(phantom == label)
        print(f"  Label {label} ({TISSUE_LABELS[label]:15s}): {count} voxels")
