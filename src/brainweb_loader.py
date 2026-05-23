import numpy as np
import os

PHANTOM_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')

def load_brainweb_phantom(subject_num=4):
    """Load BrainWeb phantom and remap to our tissue labels."""
    os.makedirs(PHANTOM_DIR, exist_ok=True)
    
    cached_file = os.path.join(PHANTOM_DIR, f'brainweb_sub{subject_num:02d}.npy')
    if os.path.exists(cached_file):
        print("Loading cached BrainWeb phantom...")
        return np.load(cached_file)
    
    import brainweb
    
    # Load subject file
    subject_file = os.path.expanduser(f'~/.brainweb/subject_{subject_num:02d}.bin.gz')
    if not os.path.exists(subject_file):
        print("Downloading BrainWeb data...")
        brainweb.get_files()
    
    print(f"Loading BrainWeb subject {subject_num:02d}...")
    raw = brainweb.load_file(subject_file)
    
    # BrainWeb labels (values are label * 16 or similar encoding):
    # 0=Background, 16=CSF, 32=Grey Matter, 48=White Matter,
    # 64=Fat, 80=Muscle, 96=Muscle/Skin, 112=Skull,
    # 128=Vessels, 145=Around fat, 161=Dura, 177=Bone Marrow
    
    # Downsample from 0.5mm (362x434x362) to 1mm (181x217x181)
    vol = raw[::2, ::2, ::2]
    print(f"  Downsampled: {raw.shape} -> {vol.shape}")
    
    # Remap to our convention:
    # 0=Background, 1=CSF, 2=Gray Matter, 3=White Matter, 4=Fat/Scalp, 5=Bone
    phantom = np.zeros_like(vol, dtype=np.uint8)
    
    phantom[vol == 16] = 1    # CSF
    phantom[vol == 32] = 2    # Gray Matter
    phantom[vol == 48] = 3    # White Matter
    phantom[vol == 64] = 4    # Fat
    phantom[vol == 80] = 4    # Muscle -> Fat/Scalp
    phantom[vol == 96] = 4    # Muscle/Skin -> Fat/Scalp
    phantom[vol == 112] = 5   # Skull -> Bone
    phantom[vol == 128] = 1   # Vessels -> CSF (fluid-like)
    phantom[vol == 145] = 4   # Around fat -> Fat/Scalp
    phantom[vol == 161] = 1   # Dura -> CSF
    phantom[vol == 177] = 5   # Bone marrow -> Bone
    
    # Cache
    np.save(cached_file, phantom)
    print(f"  Cached: {cached_file}")
    print(f"  Shape: {phantom.shape}")
    
    return phantom

def get_brainweb_or_synthetic():
    """Try BrainWeb, fall back to synthetic."""
    try:
        phantom = load_brainweb_phantom(subject_num=4)
        if phantom is not None and np.sum(phantom > 0) > 10000:
            return phantom, "BrainWeb"
    except Exception as e:
        print(f"BrainWeb failed: {e}")
    
    print("Using synthetic phantom.")
    from phantom3d import generate_synthetic_3d_brain
    return generate_synthetic_3d_brain(), "Synthetic"

if __name__ == "__main__":
    phantom, source = get_brainweb_or_synthetic()
    print(f"\nSource: {source}")
    print(f"Shape: {phantom.shape}")
    for label in np.unique(phantom):
        count = np.sum(phantom == label)
        pct = count / phantom.size * 100
        names = {0: "Background", 1: "CSF", 2: "Gray Matter", 3: "White Matter", 4: "Fat/Scalp", 5: "Bone"}
        print(f"  {label} ({names.get(label, '?'):15s}): {count:>8} voxels ({pct:.1f}%)")