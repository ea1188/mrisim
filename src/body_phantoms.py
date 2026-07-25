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
import os

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
_BODY_ONLY = (6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22)


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
    disc: bool = False,  # kept for back-compat (generate_abdomen_axial)
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
    """Abdomen phantom: diaphragm (superior) to iliac crest (inferior).
    Axis0=S→I, Axis1=A→P, Axis2=R→L.  Full 3D volumetric generation.
    """
    rng = np.random.default_rng(seed)
    phantom = np.zeros((Z, H, W), dtype=np.uint8)
    gz, gy, gx = np.ogrid[:Z, :H, :W]
    cz, cy, cx = Z // 2, H // 2, W // 2

    n1 = gaussian_filter(rng.standard_normal((Z, H, W)), sigma=[3, 4, 4])
    n2 = gaussian_filter(rng.standard_normal((Z, H, W)), sigma=[1.5, 2, 2])
    pert = n1 * 0.050 + n2 * 0.025

    def E(z0: float, y0: float, x0: float,
          sz: float, sy: float, sx: float, ps: float = 1.0) -> np.ndarray:
        dist = (gz - z0) ** 2 / sz ** 2 + (gy - y0) ** 2 / sy ** 2 + (gx - x0) ** 2 / sx ** 2
        return dist <= 1.0 + pert * ps

    # Body outline
    body = E(cz, cy, cx, Z * 0.52, H * 0.44, W * 0.47)
    phantom[body] = 4                                           # subcutaneous fat
    wall = E(cz, cy, cx, Z * 0.52, H * 0.395, W * 0.425, 0.6)
    phantom[wall] = 6                                           # body-wall muscle
    cavity = E(cz, cy, cx, Z * 0.52, H * 0.33, W * 0.36, 0.5)
    phantom[cavity] = 4                                         # visceral fat baseline

    # Liver — right lobe (D-shape) + left lobe wedge
    lz_r = Z * 0.28; ly_r = cy - H * 0.11; lx_r = cx - W * 0.16
    liver_r = E(lz_r, ly_r, lx_r, Z * 0.28, H * 0.19, W * 0.22, 0.6) & cavity
    liver_l = E(Z * 0.33, cy - H * 0.14, cx + W * 0.03, Z * 0.22, H * 0.15, W * 0.11, 0.5) & cavity
    liver = liver_r | liver_l
    phantom[liver] = 7
    # Hepatic veins (3 trunks toward IVC)
    for dx in (-W * 0.10, 0.0, W * 0.10):
        phantom[E(lz_r - Z * 0.05, ly_r, lx_r + dx, Z * 0.18, H * 0.022, W * 0.016, 0) & liver] = 11
    # Portal vein
    phantom[E(lz_r + Z * 0.08, ly_r + H * 0.08, lx_r, Z * 0.06, H * 0.026, W * 0.028, 0) & liver] = 11
    # Gallbladder (pear-shaped, inferior liver fossa)
    phantom[E(lz_r + Z * 0.12, ly_r - H * 0.10, lx_r + W * 0.09, Z * 0.08, H * 0.060, W * 0.040, 0.3) & cavity] = 1

    # Spleen — left upper posterior
    phantom[E(Z * 0.30, cy - H * 0.05, cx + W * 0.29, Z * 0.16, H * 0.13, W * 0.09, 0.55) & cavity] = 8

    # Adrenal glands (small, above kidneys)
    for sign in (-1, 1):
        phantom[E(Z * 0.38, cy + H * 0.05, cx + sign * W * 0.24, Z * 0.04, H * 0.035, W * 0.025, 0) & cavity] = 21

    # Kidneys — bean-shaped with medial hilum notch
    for sign in (-1, 1):
        kz = Z * (0.50 + 0.04 * (1 if sign > 0 else 0))
        ky = cy + H * 0.11; kx = cx + sign * W * 0.27
        cortex = E(kz, ky, kx, Z * 0.16, H * 0.145, W * 0.082, 0.55) & cavity
        medulla = E(kz, ky, kx, Z * 0.11, H * 0.100, W * 0.055, 0)
        hilum = E(kz, ky, kx - sign * W * 0.055, Z * 0.09, H * 0.07, W * 0.040, 0)
        phantom[cortex & ~hilum] = 9
        phantom[medulla & cortex & ~hilum] = 10
        phantom[hilum & cortex] = 4                             # renal sinus fat

    # Pancreas — head (right) + body/tail (horizontal to left)
    phantom[E(Z * 0.50, cy + H * 0.03, cx - W * 0.10, Z * 0.09, H * 0.07, W * 0.07, 0.5) & cavity] = 19
    phantom[E(Z * 0.47, cy - H * 0.04, cx + W * 0.05, Z * 0.08, H * 0.05, W * 0.18, 0.4) & cavity] = 19

    # Aorta + IVC (posterior, run full length)
    phantom[E(cz, cy + H * 0.19, cx - W * 0.040, Z * 0.52, H * 0.040, W * 0.032, 0) & cavity] = 11
    phantom[E(cz, cy + H * 0.21, cx + W * 0.055, Z * 0.52, H * 0.050, W * 0.040, 0) & cavity] = 11

    # Bowel — noise-based distribution in inferior cavity
    bn = gaussian_filter(rng.standard_normal((Z, H, W)), sigma=[3, 3.5, 3.5])
    inf_cavity = cavity & (gz > int(cz * 0.80)) & (phantom == 4)
    phantom[(bn > 0.70) & inf_cavity] = 17                     # bowel wall
    phantom[(bn > 1.20) & (phantom == 17)] = 1                 # luminal fluid
    # Ascending + descending colon (lateral, full height)
    for sign in (-1, 1):
        col = E(cz, cy + H * 0.10, cx + sign * W * 0.31, Z * 0.44, H * 0.060, W * 0.055, 0.5) & cavity
        phantom[col] = 17
        phantom[E(cz, cy + H * 0.10, cx + sign * W * 0.31, Z * 0.44, H * 0.028, W * 0.025, 0) & col] = 12  # gas

    # Lumbar spine (posterior) — vertebral chain + canal
    for i in range(12):
        zi = int(Z * (0.04 + 0.86 * i / 12))
        vy = cy + H * 0.30
        vbz = Z * 0.034
        if (i % 3) == 2:                                        # disc
            phantom[E(zi, vy, cx, vbz, H * 0.090, W * 0.085, 0.3)] = 15
        else:
            phantom[E(zi, vy, cx, vbz, H * 0.090, W * 0.090, 0.3)] = 13
            phantom[E(zi, vy, cx, vbz * 0.7, H * 0.062, W * 0.062, 0)] = 14
        cay = vy + H * 0.110
        phantom[E(zi, cay, cx, vbz * 1.1, H * 0.048, W * 0.044, 0)] = 1   # CSF
        phantom[E(zi, cay, cx, vbz * 1.1, H * 0.028, W * 0.025, 0)] = 16  # cord
        for sign in (-1, 1):                                    # pedicles
            phantom[E(zi, cay, cx + sign * W * 0.055, vbz * 0.9, H * 0.040, W * 0.028, 0)] = 13
        phantom[E(zi, cay + H * 0.16, cx, vbz * 0.7, H * 0.038, W * 0.015, 0)] = 13  # spinous

    phantom[~body] = 0
    return phantom


# ---- Knee ------------------------------------------------------------------- #
def generate_knee_3d(Z: int = 120, H: int = 160, W: int = 150, seed: int = 17) -> np.ndarray:
    """Detailed knee MRI phantom. Axis0 = S→I (femur→tibia), Axis1 = A→P,
    Axis2 = M→L. Built with the :mod:`anatomy` toolkit so structures are
    anatomically shaped (cortical-shell bones, cartilage coats, crescent menisci,
    cord-like cruciates/tendons/vessels) rather than ellipsoid blobs.

    Structures: distal femur (bean-shaped condyles, intercondylar notch),
    patella, proximal tibia & fibula (cortex + marrow); femoral/tibial articular
    cartilage; medial (C) and lateral (O) menisci; ACL + PCL; patellar and
    quadriceps tendons; Hoffa's fat pad; joint fluid; popliteal artery, vein and
    tibial nerve; anterior (extensor) and posterior (flexor) muscle compartments
    separated by an intermuscular fat septum, under subcutaneous fat + skin.
    """
    import anatomy
    b = anatomy.Builder(Z, H, W, seed=seed)
    cz, cy, cx = Z // 2, H // 2, W // 2
    FAT, MUSCLE, FLUID, CART = 4, 6, 1, 15
    SKIN = 5

    # Subcutaneous fat envelope + skin rind + muscle core (fat rim between = SC fat)
    body = b.ellipsoid((cz, cy, cx), (Z * 0.52, H * 0.47, W * 0.46))
    b.paint(body, FAT)
    b.coat(body, 1.5, SKIN)                                          # thin skin rind
    muscle = b.ellipsoid((cz, cy, cx), (Z * 0.52, H * 0.42, W * 0.41), ps=0.6)
    b.paint(muscle, MUSCLE)
    # Short, curved intermuscular fat planes between the posterior flexor heads
    # (kept subtle and off-axis so they don't read as a geometric grid).
    for sx, sgn in ((cx - W * 0.16, -1), (cx + W * 0.16, 1)):
        sep = b.tube((cz, cy + H * 0.34, sx), (cz, cy + H * 0.10, sx + sgn * W * 0.06),
                     W * 0.012, ps=0.8)
        b.paint(sep & muscle, FAT)

    INF = b.gz > int(Z * 0.54)                                      # tibia half

    # ---- Distal femur: two bean-shaped condyles (medial larger) + notch ---- #
    cond = np.zeros((Z, H, W), bool)
    for cx_c, ry, rx, big in [(cx - W * 0.15, 0.22, 0.17, 1.0), (cx + W * 0.14, 0.20, 0.15, 0.9)]:
        e1 = b.ellipsoid((Z * 0.22, cy - H * 0.02, cx_c), (Z * 0.30 * big, H * ry, W * rx), ps=0.4)
        e2 = b.ellipsoid((Z * 0.30, cy + H * 0.06, cx_c), (Z * 0.18 * big, H * ry * 0.7, W * rx * 0.8), ps=0.4)
        cond |= (e1 | e2)
    cond &= b.gz < int(Z * 0.52)
    b.bone(cond, rim=2.0)
    # femoral articular cartilage on the inferior (joint-facing) condyle surface
    b.coat(cond, 2.2, CART, where=(b.gz > int(Z * 0.30)))

    # Patella (anterior) + quadriceps tendon above it
    pat = b.ellipsoid((Z * 0.12, cy - H * 0.30, cx), (Z * 0.10, H * 0.11, W * 0.10), ps=0.2)
    b.bone(pat, rim=1.6)
    b.coat(pat, 1.6, CART, where=(b.gy > cy - H * 0.30))            # retropatellar cartilage
    b.paint(b.tube((0, cy - H * 0.34, cx), (Z * 0.10, cy - H * 0.31, cx), W * 0.07, taper=0.2), MUSCLE)

    # ---- Proximal tibia + fibula (cortex + marrow) ------------------------- #
    tib = b.ellipsoid((Z * 0.80, cy, cx - W * 0.02), (Z * 0.40, H * 0.22, W * 0.20), ps=0.3) & INF
    b.bone(tib, rim=2.2)
    b.coat(tib, 2.0, CART, where=(b.gz < int(Z * 0.66)))           # tibial plateau cartilage
    fib = b.tube((Z * 0.55, cy + H * 0.06, cx + W * 0.31), (Z, cy + H * 0.06, cx + W * 0.30), W * 0.05, ps=0.3) & INF
    b.bone(fib, rim=1.4)

    # ---- Joint: fluid film, menisci, cruciates ----------------------------- #
    joint = (b.gz >= int(Z * 0.48)) & (b.gz <= int(Z * 0.54))
    articular = b.ellipsoid((Z * 0.51, cy, cx), (Z * 0.10, H * 0.26, W * 0.34))
    b.paint(joint & articular & (b.vol == MUSCLE), FLUID)           # thin synovial film
    # menisci — wedges between femur and tibia; medial C-shape, lateral fuller O
    mz = Z * 0.51
    b.paint(b.tube((mz, cy - H * 0.10, cx - W * 0.22), (mz, cy + H * 0.12, cx - W * 0.10), W * 0.05, ps=0.5), CART)
    lat = b.ellipsoid((mz, cy, cx + W * 0.14), (Z * 0.05, H * 0.10, W * 0.09))
    b.paint(lat, CART)
    b.paint(b.ellipsoid((mz, cy, cx + W * 0.14), (Z * 0.06, H * 0.05, W * 0.05)) & (b.vol == CART), FLUID)
    # ACL (anterolateral → posteromedial) and PCL (crossing) in the notch
    b.paint(b.tube((Z * 0.40, cy - H * 0.10, cx + W * 0.06), (Z * 0.58, cy + H * 0.12, cx - W * 0.05), W * 0.030, ps=0.4), MUSCLE)
    b.paint(b.tube((Z * 0.40, cy + H * 0.10, cx - W * 0.05), (Z * 0.58, cy - H * 0.06, cx + W * 0.05), W * 0.034, ps=0.4), MUSCLE)

    # Hoffa's infrapatellar fat pad (anterior to the notch, below patella)
    b.paint(b.ellipsoid((Z * 0.46, cy - H * 0.22, cx), (Z * 0.12, H * 0.10, W * 0.20), ps=0.5) & (b.vol == MUSCLE), FAT)
    # Patellar tendon (patella → tibial tuberosity)
    b.paint(b.tube((Z * 0.20, cy - H * 0.33, cx), (Z * 0.60, cy - H * 0.28, cx), W * 0.06, taper=0.1), MUSCLE)

    # Popliteal artery + vein and tibial nerve (posterior)
    for dx, r, lab in [(-W * 0.05, W * 0.035, 11), (W * 0.02, W * 0.045, 11), (W * 0.09, W * 0.030, 6)]:
        b.paint(b.tube((0, cy + H * 0.34, cx + dx), (Z, cy + H * 0.36, cx + dx), r, ps=0.4) & body, lab)

    b.vol[~body] = 0
    return b.vol


# ---- Spine ------------------------------------------------------------------ #
def generate_spine_3d(Z: int = 160, H: int = 200, W: int = 180, seed: int = 23) -> np.ndarray:
    """Spine phantom (C1-L5).  Axis0=S->I, Axis1=A->P, Axis2=L->R.

    Each spinal level: vertebral body (cortical + marrow, posterior concavity);
    complete posterior arch (pedicles + laminae + spinous + transverse processes);
    facet joints; IVD (nucleus pulposus + annulus fibrosus); spinal canal
    (CSF + cord); epidural fat; erector spinae (bilateral) + psoas (lumbar).
    """
    rng = np.random.default_rng(seed)
    phantom = np.zeros((Z, H, W), dtype=np.uint8)
    gz, gy, gx = np.ogrid[:Z, :H, :W]
    cz, cy, cx = Z // 2, H // 2, W // 2

    n1 = gaussian_filter(rng.standard_normal((Z, H, W)), sigma=[3, 4, 4])
    n2 = gaussian_filter(rng.standard_normal((Z, H, W)), sigma=[1.5, 2, 2])
    pert = n1 * 0.048 + n2 * 0.022

    def E(z0: float, y0: float, x0: float, sz: float, sy: float, sx: float, ps: float = 1.0) -> np.ndarray:
        dist = (gz - z0) ** 2 / sz ** 2 + (gy - y0) ** 2 / sy ** 2 + (gx - x0) ** 2 / sx ** 2
        return dist <= 1.0 + pert * ps

    # Graded body outline: narrows superiorly, widens in lumbar
    tz = gz.astype(float) / Z
    body_graded = ((gz - cz) ** 2 / (Z * 0.52) ** 2 +
                   (gy - cy) ** 2 / ((H * (0.35 + 0.10 * tz)) ** 2) +
                   (gx - cx) ** 2 / ((W * (0.41 + 0.06 * tz)) ** 2)) <= 1 + pert
    phantom[body_graded] = 4

    # Erector spinae (bilateral, posterior)
    for sign in (-1, 1):
        es = ((gz - cz) ** 2 / (Z * 0.52) ** 2 +
              (gy - (cy + H * 0.11)) ** 2 / ((H * (0.17 + 0.05 * tz)) ** 2) +
              (gx - (cx + sign * W * (0.16 + 0.07 * tz))) ** 2 / ((W * (0.16 + 0.06 * tz)) ** 2)) <= 1 + pert * 0.5
        phantom[es & body_graded] = 6

    # Psoas (anterior, lower half only)
    for sign in (-1, 1):
        ps_m = ((gz - cz * 1.3) ** 2 / (Z * 0.30) ** 2 +
                (gy - (cy - H * 0.10)) ** 2 / ((H * (0.10 + 0.04 * tz)) ** 2) +
                (gx - (cx + sign * W * 0.14)) ** 2 / (W * 0.09) ** 2) <= 1 + pert * 0.4
        phantom[ps_m & body_graded & (gz > int(Z * 0.50))] = 6

    # Vertebral chain (24 levels)
    for i in range(24):
        f = i / 24.0
        zi = int(Z * (0.03 + 0.90 * f))
        vbz = Z * 0.032
        vy = cy + H * (0.09 + 0.05 * f)
        vbw_y = H * (0.085 + 0.040 * f)
        vbw_x = W * (0.130 + 0.055 * f)
        is_disc = (i % 3) == 2

        if is_disc:
            phantom[E(zi, vy, cx, vbz, vbw_y, vbw_x, 0.3)] = 15          # annulus
            phantom[E(zi, vy, cx, vbz * 0.70, vbw_y * 0.55, vbw_x * 0.55, 0)] = 1  # nucleus
        else:
            phantom[E(zi, vy, cx, vbz, vbw_y, vbw_x, 0.3)] = 13
            phantom[E(zi, vy, cx, vbz * 0.75, vbw_y * 0.66, vbw_x * 0.66, 0)] = 14
            # Posterior concavity (flattened back of vertebral body)
            phantom[E(zi, vy + vbw_y * 0.90, cx, vbz * 0.6, vbw_y * 0.28, vbw_x * 0.50, 0) & (phantom == 14)] = 13

        # Pedicles
        ped_y = vy + vbw_y * 1.05
        for sign in (-1, 1):
            phantom[E(zi, ped_y, cx + sign * vbw_x * 0.85, vbz * 0.85, vbw_y * 0.42, vbw_x * 0.28, 0)] = 13

        # Spinal canal: CSF + cord
        cay = vy + vbw_y * 1.20
        can_h = H * (0.055 - 0.012 * f); can_w = W * (0.060 - 0.010 * f)
        phantom[E(zi, cay, cx, vbz * 1.05, can_h, can_w, 0)] = 1
        phantom[E(zi, cay, cx, vbz * 1.05, can_h * 0.54, can_w * 0.54, 0)] = 16

        # Epidural fat (dorsal)
        phantom[E(zi, cay + can_h * 1.55, cx, vbz * 0.8, can_h * 0.40, can_w * 0.90, 0)] = 4

        # Laminae (bilateral, posterior arch)
        for sign in (-1, 1):
            phantom[E(zi, cay + can_h * 1.10, cx + sign * can_w * 1.10, vbz * 0.75, can_h * 0.55, can_w * 0.38, 0)] = 13

        # Spinous process
        phantom[E(zi, cay + can_h * 2.05, cx, vbz * 0.65, H * 0.040, W * 0.015, 0)] = 13

        # Facet joints
        for sign in (-1, 1):
            phantom[E(zi, ped_y, cx + sign * can_w * 1.65, vbz * 0.50, vbw_y * 0.30, vbw_x * 0.20, 0)] = 13
            phantom[E(zi, ped_y, cx + sign * can_w * 1.65, vbz * 0.30, vbw_y * 0.14, vbw_x * 0.10, 0)] = 1

        # Transverse processes (thoracic+lumbar only)
        if f > 0.30:
            for sign in (-1, 1):
                phantom[E(zi, vy, cx + sign * W * (0.185 + 0.04 * f), vbz * 0.55, vbw_y * 0.22, vbw_x * 0.062, 0) & body_graded] = 13

    phantom[~body_graded] = 0
    return phantom


# ---- Pelvis ----------------------------------------------------------------- #
def generate_pelvis_3d(Z: int = 120, H: int = 220, W: int = 280, seed: int = 31) -> np.ndarray:
    """Pelvis phantom.  Axis0=S->I (iliac crest->perineum), Axis1=A->P, Axis2=R->L.

    Structures: iliac wings; sacrum; acetabulum + femoral head + labrum +
    articular cartilage; obturator internus; levator ani; bladder; prostate/
    uterus + adnexa; rectum; iliac vessels; pubic symphysis; femoral shafts.
    """
    rng = np.random.default_rng(seed)
    phantom = np.zeros((Z, H, W), dtype=np.uint8)
    gz, gy, gx = np.ogrid[:Z, :H, :W]
    cz, cy, cx = Z // 2, H // 2, W // 2

    n1 = gaussian_filter(rng.standard_normal((Z, H, W)), sigma=[3, 4, 4])
    n2 = gaussian_filter(rng.standard_normal((Z, H, W)), sigma=[1.5, 2.2, 2.2])
    pert = n1 * 0.050 + n2 * 0.022

    def E(z0: float, y0: float, x0: float, sz: float, sy: float, sx: float, ps: float = 1.0) -> np.ndarray:
        dist = (gz - z0) ** 2 / sz ** 2 + (gy - y0) ** 2 / sy ** 2 + (gx - x0) ** 2 / sx ** 2
        return dist <= 1.0 + pert * ps

    tz = gz.astype(float) / Z
    body_mask = ((gz - cz) ** 2 / (Z * 0.52) ** 2 +
                 (gy - cy) ** 2 / ((H * (0.43 + 0.04 * tz)) ** 2) +
                 (gx - cx) ** 2 / ((W * (0.46 + 0.03 * tz)) ** 2)) <= 1 + pert
    phantom[body_mask] = 4
    muscle_mask = ((gz - cz) ** 2 / (Z * 0.52) ** 2 +
                   (gy - cy) ** 2 / ((H * (0.38 + 0.04 * tz)) ** 2) +
                   (gx - cx) ** 2 / ((W * (0.40 + 0.03 * tz)) ** 2)) <= 1 + pert * 0.5
    phantom[muscle_mask] = 6

    # Sacrum (posterior midline, tapers inferiorly)
    phantom[E(Z * 0.35, cy + H * 0.28, cx, Z * 0.38, H * 0.13, W * 0.12, 0.4)] = 13
    phantom[E(Z * 0.35, cy + H * 0.28, cx, Z * 0.30, H * 0.09, W * 0.085, 0)] = 14
    phantom[E(Z * 0.35, cy + H * 0.20, cx, Z * 0.38, H * 0.05, W * 0.035, 0)] = 1   # sacral canal

    # Iliac wings (bilateral, superior 40%)
    for sign in (-1, 1):
        il_x = cx + sign * W * 0.30
        phantom[E(Z * 0.20, cy, il_x, Z * 0.22, H * 0.32, W * 0.12, 0.5)] = 13
        phantom[E(Z * 0.20, cy, il_x, Z * 0.18, H * 0.26, W * 0.08, 0)] = 14
        phantom[E(Z * 0.27, cy - H * 0.22, cx + sign * W * 0.30, Z * 0.06, H * 0.06, W * 0.06, 0.2)] = 13

    # Acetabulum + femoral head (hip joint, mid-pelvis)
    hip_z = Z * 0.52
    for sign in (-1, 1):
        ac_x = cx + sign * W * 0.31; ac_y = cy + H * 0.04
        phantom[E(hip_z, ac_y, ac_x, Z * 0.15, H * 0.135, W * 0.13, 0.35)] = 13
        phantom[E(hip_z, ac_y, ac_x, Z * 0.11, H * 0.095, W * 0.09, 0)] = 14
        phantom[E(hip_z, ac_y - H * 0.10, ac_x, Z * 0.15, H * 0.030, W * 0.030, 0)] = 15  # labrum
        fh_x = ac_x + sign * W * 0.04
        phantom[E(hip_z, ac_y, fh_x, Z * 0.125, H * 0.105, W * 0.100, 0.25)] = 13
        phantom[E(hip_z, ac_y, fh_x, Z * 0.090, H * 0.073, W * 0.070, 0)] = 14
        phantom[E(hip_z, ac_y, fh_x - sign * W * 0.07, Z * 0.12, H * 0.025, W * 0.025, 0)] = 15
        phantom[E(hip_z, ac_y, ac_x + sign * W * 0.02, Z * 0.12, H * 0.020, W * 0.020, 0)] = 1

    # Femoral shafts (inferior third)
    for sign in (-1, 1):
        fs_x = cx + sign * W * 0.27
        phantom[E(Z * 0.76, cy + H * 0.04, fs_x, Z * 0.28, H * 0.17, W * 0.15, 0.3) & (gz > int(Z * 0.60))] = 13
        phantom[E(Z * 0.76, cy + H * 0.04, fs_x, Z * 0.28, H * 0.11, W * 0.09, 0) & (gz > int(Z * 0.60))] = 14

    # Pubic symphysis + ischial rami
    phantom[E(Z * 0.72, cy, cx, Z * 0.12, H * 0.060, W * 0.090, 0.2)] = 13
    phantom[E(Z * 0.72, cy, cx, Z * 0.08, H * 0.030, W * 0.030, 0)] = 15
    for sign in (-1, 1):
        phantom[E(Z * 0.72, cy + H * 0.08, cx + sign * W * 0.14, Z * 0.10, H * 0.045, W * 0.090, 0.3)] = 13

    # Obturator internus + levator ani
    for sign in (-1, 1):
        phantom[E(Z * 0.65, cy + H * 0.08, cx + sign * W * 0.22, Z * 0.22, H * 0.080, W * 0.060, 0.4) & muscle_mask] = 6
    phantom[E(Z * 0.80, cy + H * 0.12, cx, Z * 0.12, H * 0.042, W * 0.28, 0.3) & body_mask] = 6

    # Bladder (dome-shaped, fluid)
    phantom[E(Z * 0.38, cy - H * 0.20, cx, Z * 0.18, H * 0.135, W * 0.130, 0.35)] = 1
    phantom[E(Z * 0.38, cy - H * 0.20, cx, Z * 0.22, H * 0.158, W * 0.155, 0.3) & (phantom == 6)] = 21

    # Prostate/uterus + adnexa
    phantom[E(Z * 0.58, cy - H * 0.04, cx, Z * 0.16, H * 0.070, W * 0.085, 0.4)] = 21
    for sign in (-1, 1):
        phantom[E(Z * 0.50, cy + H * 0.02, cx + sign * W * 0.07, Z * 0.08, H * 0.045, W * 0.060, 0.3)] = 21

    # Rectum (posterior)
    phantom[E(Z * 0.50, cy + H * 0.22, cx, Z * 0.38, H * 0.080, W * 0.070, 0.5)] = 17
    phantom[E(Z * 0.50, cy + H * 0.22, cx, Z * 0.38, H * 0.040, W * 0.040, 0)] = 1

    # Iliac vessels
    for sign in (-1, 1):
        phantom[E(Z * 0.25, cy - H * 0.07, cx + sign * W * 0.085, Z * 0.18, H * 0.040, W * 0.032, 0) & body_mask] = 11
        phantom[E(Z * 0.25, cy - H * 0.015, cx + sign * W * 0.085, Z * 0.18, H * 0.050, W * 0.042, 0) & body_mask] = 11

    phantom[~body_mask] = 0
    return phantom




# ---- Region registry --------------------------------------------------------
REGION_NAMES = ["Brain", "Abdomen", "Knee", "Spine", "Pelvis", "Torso"]
_MSK_SEQS = ["Spin Echo", "FSE / TSE", "Gradient Echo", "Inversion Recovery", "Balanced SSFP"]
REGION_SEQUENCES = {
    "Brain":   ["Spin Echo", "FSE / TSE", "Gradient Echo", "Inversion Recovery",
                "Balanced SSFP", "Echo Planar (EPI)", "Diffusion (DWI)",
                "MR Angiography", "Susceptibility (SWI)", "fMRI (BOLD)"],
    "Abdomen": _MSK_SEQS,
    "Knee":    _MSK_SEQS,
    "Spine":   _MSK_SEQS,
    "Pelvis":  _MSK_SEQS,
    "Torso":   _MSK_SEQS,
}
_BUILDERS = {
    "Abdomen": generate_abdomen_3d,
    "Knee":    generate_knee_3d,
    "Spine":   generate_spine_3d,
    "Pelvis":  generate_pelvis_3d,
    # Torso has no bespoke synthetic generator: it is a real-data-only region
    # (TotalSegMRI s0250). Fall back to the abdomen phantom so the dropdown
    # entry still renders something if the dataset is absent.
    "Torso":   generate_abdomen_3d,
}


def build_region(name: str) -> np.ndarray:
    """Return a labeled 3D volume for a non-brain region (Brain is supplied by app).

    Tries to load a real TotalSegmentator segmentation from data/ first (the
    body equivalent of BrainWeb).  Falls back to the synthetic generator if the
    data file is absent or nibabel is unavailable.
    """
    # Processed real atlases that take precedence over the TotalSegmentator atlas:
    # the Knee (KneeBones3Dify) and the SPIDER lumbar Spine.
    cached = _load_cache(_CACHE_SUBDIR.get(name), "atlas")
    if cached is not None:
        return cached
    # Real NIfTI path (TotalSegmentator MRI body atlases)
    try:
        from nifti_region import load_region_nifti
        from brainweb_loader import data_dir
        vol = load_region_nifti(name, data_dir())
        if vol is not None:
            return vol
    except Exception:
        pass
    # Synthetic fallback
    if name in _BUILDERS:
        return _BUILDERS[name]()
    raise KeyError(f"No builder for region {name!r}")


# Regions backed by a processed real cache under data/<subdir>/{atlas,texture}.npy.
_CACHE_SUBDIR = {"Knee": "knee_kb3d", "Spine": "spider_spine"}


def _load_cache(subdir: "str | None", which: str) -> "np.ndarray | None":
    """Load a processed real atlas/texture cache (data/<subdir>/<which>.npy)."""
    if not subdir:
        return None
    try:
        from brainweb_loader import data_dir
        path = os.path.join(data_dir(), subdir, f"{which}.npy")
        if not os.path.exists(path):
            return None
        arr = np.load(path)
        # Correct the atlas's known base tilt (e.g. the spine column leans 16.8° in
        # coronal) — the same rotation the browser applies in web_adapter.
        import region_orient
        region = {"spider_spine": "Spine", "knee_kb3d": "Knee"}.get(subdir)
        if region is not None:
            arr = region_orient.straighten(region, arr, 0 if which == "atlas" else 1)
        return arr
    except Exception:
        return None


# Per-tissue texture amplitude (multiplicative ± fraction) for the synthetic
# texture field — how heterogeneous each tissue looks. Fluid/bone are smooth;
# parenchyma, marrow, bowel and fat are mottled.
_TEXTURE_AMP = {
    1: 0.025,  4: 0.11,  5: 0.04,  6: 0.09,  7: 0.12,  8: 0.12,  9: 0.12,
    10: 0.12, 11: 0.06, 13: 0.04, 14: 0.13, 15: 0.06, 16: 0.06, 17: 0.15,
    18: 0.14, 19: 0.12, 20: 0.10, 21: 0.10,
}
_TEXTURE_DEFAULT = 0.08


def synthetic_texture_3d(label_vol: np.ndarray, seed: int = 0) -> np.ndarray:
    """A multiplicative MR-texture field (≈1.0) aligned to ``label_vol``.

    Sums a few octaves of band-limited value noise (coarse parenchymal mottle +
    finer speckle) and scales it per tissue (``_TEXTURE_AMP``), so synthetic
    organs/muscle/marrow read like real parenchyma instead of flat fills, while
    fluid and bone stay smooth. Computed once per region (cached by the caller)
    and consistent across slices/orientations."""
    from scipy.ndimage import gaussian_filter
    rng = np.random.default_rng(seed)
    field = np.zeros(label_vol.shape, dtype=np.float64)
    for sigma, weight in ((1.0, 0.5), (3.0, 0.8), (7.0, 0.5)):
        n = gaussian_filter(rng.standard_normal(label_vol.shape), sigma)
        std = float(n.std())
        if std > 1e-9:
            field += weight * (n / std)
    fstd = float(field.std())
    if fstd > 1e-9:
        field /= fstd                                  # unit-std composite noise
    amp = np.full(label_vol.shape, _TEXTURE_DEFAULT, dtype=np.float64)
    for lab, a in _TEXTURE_AMP.items():
        amp[label_vol == lab] = a
    return np.clip(1.0 + amp * field, 0.45, 1.7).astype(np.float32)


def build_region_texture(name: str, label_vol: "np.ndarray | None" = None) -> "np.ndarray | None":
    """Anatomical texture field for *name*, aligned to build_region(name).

    Prefers the real-MRI detail field — the TotalSegmentator body atlases and the
    real Knee atlas (KneeBones3Dify); otherwise, for the synthetic phantoms (and
    any region without a cache), returns a procedural :func:`synthetic_texture_3d`
    so tissues show parenchymal texture rather than flat fills. ``label_vol`` lets
    the caller pass the already-built volume to avoid rebuilding it."""
    cached_tex = _load_cache(_CACHE_SUBDIR.get(name), "texture")
    if cached_tex is not None:
        return cached_tex.astype(np.float32)
    try:
        from nifti_region import load_region_texture
        from brainweb_loader import data_dir
        tex = load_region_texture(name, data_dir())
        if tex is not None:
            return tex
    except Exception:
        pass
    vol = label_vol if label_vol is not None else build_region(name)
    seed = abs(hash(name)) % (2 ** 32)
    return synthetic_texture_3d(vol, seed=seed)


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
