import numpy as np
import os

PHANTOM_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')


def add_air_sinuses(vol: np.ndarray) -> np.ndarray:
    """Carve synthetic paranasal + mastoid air cavities into the skull base.

    BrainWeb models no internal air, so air-tissue susceptibility interfaces
    (which drive GRE/EPI signal dropout and geometric distortion) are absent.
    This carves a few ellipsoidal air pockets into the lower-anterior head —
    anchored to the head bounding box and the base of the cerebrum, and only
    into face/skull tissue (never brain or CSF) — so susceptibility/EPI effects
    look realistic on skull-base slices. Returns a modified copy.

    Volume axes: 0=Z (inferior→superior), 1=Y (anterior→posterior), 2=X (L→R).
    """
    out = vol.copy()
    tissue = vol > 0
    if not tissue.any():
        return out
    Z, Y, X = vol.shape
    zs, ys, xs = np.where(tissue)
    z0, z1, y0, y1, x0, x1 = zs.min(), zs.max(), ys.min(), ys.max(), xs.min(), xs.max()
    hz, hy, hx = max(z1 - z0, 1), max(y1 - y0, 1), max(x1 - x0, 1)
    cx = (x0 + x1) / 2.0

    brain = np.isin(vol, (2, 3))
    bz = np.where(brain.reshape(Z, -1).mean(axis=1) > 0.10)[0]
    base_z = int(bz.min()) if bz.size else (z0 + z1) // 2

    zz, yy, xx = np.ogrid[:Z, :Y, :X]
    def ellipsoid(cz, cy, cxx, rz, ry, rx):
        return (((zz - cz) / rz) ** 2 + ((yy - cy) / ry) ** 2
                + ((xx - cxx) / rx) ** 2) <= 1.0

    # (centre_z, centre_y, centre_x, radii) as fractions of the head extent.
    # Cavities sit at and just above the cerebrum base (the skull-base / orbit
    # level), anterior for the paranasal group, posterolateral for the mastoids.
    cavities = [
        (base_z + 0.10 * hz, y0 + 0.16 * hy, cx,             0.06 * hz, 0.10 * hy, 0.11 * hx),  # frontal/ethmoid
        (base_z + 0.02 * hz, y0 + 0.40 * hy, cx,             0.05 * hz, 0.07 * hy, 0.08 * hx),  # sphenoid (central base)
        (base_z + 0.00 * hz, y0 + 0.18 * hy, cx - 0.15 * hx, 0.05 * hz, 0.08 * hy, 0.07 * hx),  # maxillary L
        (base_z + 0.00 * hz, y0 + 0.18 * hy, cx + 0.15 * hx, 0.05 * hz, 0.08 * hy, 0.07 * hx),  # maxillary R
        (base_z + 0.06 * hz, y0 + 0.68 * hy, cx - 0.28 * hx, 0.05 * hz, 0.06 * hy, 0.06 * hx),  # mastoid L
        (base_z + 0.06 * hz, y0 + 0.68 * hy, cx + 0.28 * hx, 0.05 * hz, 0.06 * hy, 0.06 * hx),  # mastoid R
    ]
    air = np.zeros(vol.shape, dtype=bool)
    for c in cavities:
        air |= ellipsoid(*c)

    carveable = tissue & ~np.isin(vol, (1, 2, 3))   # spare brain and CSF
    out[air & carveable] = 0
    return out


def load_brainweb_phantom(subject_num: int = 4) -> np.ndarray:
    """Load BrainWeb phantom and remap to our tissue labels."""
    os.makedirs(PHANTOM_DIR, exist_ok=True)
    
    # '_anat' tag: multi-class mapping + synthetic skull-base air sinuses.
    # Bumping the tag invalidates older caches automatically.
    cached_file = os.path.join(PHANTOM_DIR, f'brainweb_sub{subject_num:02d}_anat.npy')
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
    
    # Remap BrainWeb's 12 classes to the simulator's tissue_db labels, keeping
    # muscle / vessels / connective / dura / marrow distinct (previously these
    # were collapsed into fat/CSF/bone, discarding ~16% of the head as "fat").
    phantom = np.zeros_like(vol, dtype=np.uint8)

    phantom[vol == 16]  = 1    # CSF              -> Fluid/CSF
    phantom[vol == 32]  = 2    # Gray matter      -> Gray matter
    phantom[vol == 48]  = 3    # White matter     -> White matter
    phantom[vol == 64]  = 4    # Fat (subcut.)    -> Fat
    phantom[vol == 80]  = 6    # Muscle           -> Muscle
    phantom[vol == 96]  = 6    # Muscle / skin    -> Muscle (scalp soft tissue)
    phantom[vol == 112] = 5    # Skull            -> Bone (skull)
    phantom[vol == 128] = 11   # Vessels          -> Blood
    phantom[vol == 145] = 4    # Connective (peri-fat) -> Fat
    phantom[vol == 161] = 15   # Dura mater       -> Cartilage/Disc (fibrous, short T2)
    phantom[vol == 177] = 14   # Bone marrow      -> Marrow

    # Synthetic skull-base air sinuses (for realistic susceptibility / EPI).
    phantom = add_air_sinuses(phantom)

    # Cache
    np.save(cached_file, phantom)
    print(f"  Cached: {cached_file}")
    print(f"  Shape: {phantom.shape}")
    
    return phantom

def get_brainweb_or_synthetic() -> tuple[np.ndarray, str]:
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