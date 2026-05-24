"""
body_phantoms.py  —  synthetic anatomy + region registry for the MRI simulator.

Philosophy matches phantom3d.generate_synthetic_3d_brain: anatomically placed
shapes with noise-driven boundary irregularity, every voxel carrying a tissue
*label*. Labels map to T1/T2/PD/T2* in BODY_TISSUES, so the existing
phantom3d.simulate_slice renders them under any sequence with no engine changes.

Brain labels 0-5 are kept byte-identical to phantom3d.TISSUE_PROPERTIES_3D, so
the two tables merge cleanly (see merge_into_engine()).

Volume axis convention matches phantom3d.get_slice:
    axis 0 = axial index (superior->inferior, Z)
    axis 1 = coronal index (anterior->posterior, Y)
    axis 2 = sagittal index (left->right, X)
"""
import numpy as np
from scipy.ndimage import gaussian_filter

# Single source of truth: tissue_db.py. body_phantoms reuses its label vocabulary
# so the synthetic phantoms and the engine always agree. (apply_to_engine() at
# the chosen field strength is what actually drives rendering; this table is only
# used for the label set / names here.)
import tissue_db as _tdb
BODY_TISSUES = _tdb.properties("3T")

# Labels that belong to body anatomy (not in the brain table) — these get added
# to the engine's property dict; brain labels 0-5 are left untouched.
_BODY_ONLY = (6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17)


def merge_into_engine() -> None:
    """Add body tissue properties to phantom3d.TISSUE_PROPERTIES_3D in place."""
    import phantom3d
    for lab in _BODY_ONLY:
        phantom3d.TISSUE_PROPERTIES_3D.setdefault(lab, BODY_TISSUES[lab])


def _ellipse(
    gy: np.ndarray,
    gx: np.ndarray,
    cy: float,
    cx: float,
    ry: float,
    rx: float,
    angle: float = 0.0,
    pert: np.ndarray | None = None,
) -> np.ndarray:
    t = np.deg2rad(angle)
    yy = gy - cy; xx = gx - cx
    xr = xx * np.cos(t) + yy * np.sin(t)
    yr = -xx * np.sin(t) + yy * np.cos(t)
    rhs = 1.0 if pert is None else (1.0 + pert)
    return (xr / rx) ** 2 + (yr / ry) ** 2 <= rhs


def _win(f: float, lo: float, hi: float, edge: float = 0.10) -> float:
    """Smooth 0..1 raised-cosine window over [lo,hi] with soft edges of width `edge`."""
    if f <= lo or f >= hi:
        return 0.0
    d = min(f - lo, hi - f)
    if d >= edge:
        return 1.0
    return 0.5 - 0.5 * np.cos(np.pi * d / edge)


def _abdomen_slice(
    f: float,
    H: int,
    W: int,
    gy: np.ndarray,
    gx: np.ndarray,
    pert: np.ndarray | None,
    disc: bool = False,
) -> np.ndarray:
    """One axial abdomen label slice at superior->inferior fraction f in [0,1]."""
    cy, cx = H * 0.5, W * 0.5
    ph = np.zeros((H, W), dtype=np.uint8)

    taper = np.interp(f, [0.0, 0.08, 0.88, 1.0], [0.80, 1.0, 1.0, 0.78])
    body = _ellipse(gy, gx, cy, cx, H * 0.45 * taper, W * 0.47 * taper, pert=pert)
    skin = _ellipse(gy, gx, cy, cx, H * 0.40 * taper, W * 0.43 * taper, pert=pert)
    wall = _ellipse(gy, gx, cy, cx, H * 0.355 * taper, W * 0.39 * taper, pert=pert)
    ph[body] = 4         # subcutaneous fat
    ph[skin] = 6         # body-wall muscle
    ph[wall] = 4         # visceral/mesenteric fat (cavity baseline)
    cavity = wall

    # Liver — superior, patient-right (image left); fades out caudally
    wl = _win(f, 0.0, 0.64, edge=0.16)
    if wl > 0.05:
        s = (1.0 - f / 0.72) * wl
        liver = _ellipse(gy, gx, cy - H * 0.10, cx - W * 0.14,
                         H * (0.10 + 0.26 * s), W * (0.10 + 0.26 * s),
                         angle=12, pert=pert) & cavity
        ph[liver] = 7
    # Spleen — upper-mid, patient-left posterolateral
    ws = _win(f, 0.04, 0.46, edge=0.10)
    if ws > 0.05:
        ph[_ellipse(gy, gx, cy - H * 0.02, cx + W * 0.30,
                    H * 0.15 * ws, W * 0.085 * ws, angle=-28, pert=pert) & cavity] = 8
    # Stomach — fluid + gas, upper anterior-left
    wt = _win(f, 0.04, 0.40, edge=0.10)
    if wt > 0.05:
        stom = _ellipse(gy, gx, cy - H * 0.19, cx + W * 0.13, H * 0.12 * wt, W * 0.115 * wt, pert=pert) & cavity
        ph[stom] = 1
        ph[_ellipse(gy, gx, cy - H * 0.24, cx + W * 0.13, H * 0.06 * wt, W * 0.095 * wt) & stom] = 12
    # Kidneys — paravertebral, cortex + medulla + hilar fat; bean-tapered in z
    wk = _win(f, 0.30, 0.80, edge=0.14)
    if wk > 0.05:
        for side in (-1, 1):
            kx = cx + side * W * 0.29
            cortex = _ellipse(gy, gx, cy + H * 0.13, kx, H * 0.155 * wk, W * 0.085 * wk, angle=18 * side, pert=pert) & cavity
            medulla = _ellipse(gy, gx, cy + H * 0.13, kx, H * 0.105 * wk, W * 0.05 * wk, angle=18 * side)
            hilum = _ellipse(gy, gx, cy + H * 0.13, kx - side * W * 0.03, H * 0.06 * wk, W * 0.038 * wk)
            ph[cortex] = 9
            ph[medulla & cortex] = 10
            ph[hilum & cortex] = 4
    # Bowel — more loops inferiorly
    if f > 0.40:
        n = int(np.interp(f, [0.40, 1.0], [2, 5]))
        spots = [(cy + H * 0.01, cx - W * 0.03), (cy + H * 0.06, cx + W * 0.10),
                 (cy - H * 0.03, cx - W * 0.12), (cy + H * 0.12, cx + W * 0.02),
                 (cy + H * 0.02, cx + W * 0.21)]
        for i in range(min(n, len(spots))):
            ly, lx = spots[i]
            r = H * 0.075
            loop = _ellipse(gy, gx, ly, lx, r, r, pert=pert) & cavity
            ph[loop] = 17
            ph[_ellipse(gy, gx, ly, lx, r - 4, r - 4) & loop] = (12 if i % 2 == 0 else 1)

    # Great vessels — vertical, anterior to spine
    ph[_ellipse(gy, gx, cy + H * 0.20, cx - W * 0.04, H * 0.045, W * 0.035) & cavity] = 11   # aorta
    ph[_ellipse(gy, gx, cy + H * 0.21, cx + W * 0.05, H * 0.05, W * 0.047) & cavity] = 11    # IVC

    # Spine — vertebral body (or disc), canal/cord, processes
    vy = cy + H * 0.30
    vbody = _ellipse(gy, gx, vy, cx, H * 0.095, W * 0.085)
    if disc:
        ph[vbody] = 15                                   # intervertebral disc
    else:
        ph[vbody] = 13                                   # cortical rim
        ph[_ellipse(gy, gx, vy, cx, H * 0.065, W * 0.062)] = 14   # marrow
    canal = _ellipse(gy, gx, vy + H * 0.075, cx, H * 0.05, W * 0.04)
    ph[canal] = 1
    ph[_ellipse(gy, gx, vy + H * 0.075, cx, H * 0.028, W * 0.022)] = 16
    ph[_ellipse(gy, gx, vy + H * 0.13, cx, H * 0.06, W * 0.018)] = 13
    for side in (-1, 1):
        ph[_ellipse(gy, gx, vy + H * 0.04, cx + side * W * 0.10, H * 0.022, W * 0.06, angle=20 * side)] = 13

    ph[~body] = 0
    return ph


def generate_abdomen_3d(Z: int = 160, H: int = 200, W: int = 256, seed: int = 7) -> np.ndarray:
    """Z-varying axial abdomen volume, shape (Z, H, W)."""
    rng = np.random.default_rng(seed)
    gy, gx = np.ogrid[:H, :W]
    # Coherent boundary-irregularity field (small, smooth, correlated in z)
    noise = gaussian_filter(rng.standard_normal((Z, H, W)), sigma=(2.0, 3.0, 3.0))
    noise *= 0.06 / (np.abs(noise).max() + 1e-9)
    vol = np.zeros((Z, H, W), dtype=np.uint8)
    for z in range(Z):
        f = z / (Z - 1)
        disc = (z % 13) in (0, 1)        # intervertebral discs at intervals
        vol[z] = _abdomen_slice(f, H, W, gy, gx, noise[z], disc=disc)
    return vol


# ---- Region registry --------------------------------------------------------
REGION_NAMES = ["Brain", "Abdomen"]
# Sequences each region supports (brain has the specialised ones)
REGION_SEQUENCES = {
    "Brain":   ["Spin Echo", "FSE / TSE", "Gradient Echo", "Inversion Recovery",
                "Diffusion (DWI)", "MR Angiography", "fMRI (BOLD)"],
    "Abdomen": ["Spin Echo", "FSE / TSE", "Gradient Echo", "Inversion Recovery"],
}
_BUILDERS = {"Abdomen": generate_abdomen_3d}


def build_region(name: str) -> np.ndarray:
    """Return a labeled 3D volume for a non-brain region (Brain is supplied by app)."""
    if name in _BUILDERS:
        return _BUILDERS[name]()
    raise KeyError(f"No builder for region {name!r}")


# back-compat helper used by the earlier demo
def generate_abdomen_axial(H: int = 260, W: int = 320, seed: int = 7) -> np.ndarray:
    gy, gx = np.ogrid[:H, :W]
    return _abdomen_slice(0.34, H, W, gy, gx, pert=None, disc=False)


def render_slice(
    label_map: np.ndarray,
    TR: float,
    TE: float,
    sequence: str = "SE",
    TI: float = 150,
    flip_angle: float = 90,
    texture: float = 0.07,
    blur: float = 0.6,
    seed: int = 0,
) -> np.ndarray:
    from signal_engine import (spin_echo_signal, gradient_echo_signal,
                               inversion_recovery_signal)
    img = np.zeros(label_map.shape, dtype=float)
    for label, p in BODY_TISSUES.items():
        mask = label_map == label
        if not np.any(mask):
            continue
        if sequence == "GRE":
            sig = gradient_echo_signal(p["T1"], p["T2star"], p["PD"], TR, TE, flip_angle)
        elif sequence == "IR":
            sig = inversion_recovery_signal(p["T1"], p["T2"], p["PD"], TR, TE, TI)
        else:
            sig = spin_echo_signal(p["T1"], p["T2"], p["PD"], TR, TE)
        img[mask] = sig
    if texture > 0:
        rng = np.random.default_rng(seed)
        n = gaussian_filter(rng.standard_normal(img.shape), sigma=2.2)
        n /= (np.abs(n).max() + 1e-9)
        m = label_map > 0
        img[m] *= (1.0 + texture * n[m])
    if blur > 0:
        img = gaussian_filter(img, sigma=blur)
    return img
