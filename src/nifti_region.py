"""
nifti_region.py  —  load a REAL segmented human volume (TotalSegmentator-style
NIfTI label mask) into the simulator's label-based engine.

This is the body equivalent of BrainWeb: a real human anatomy that is already
*segmented*, so the existing per-label signal equations render it under any
sequence. We use only the label mask (small, compresses to a few MB) — not the
CT/MR intensity image — and remap TotalSegmentator's 117 'total'-task classes
onto the simulator's MR tissue labels.

Requires nibabel:  pip install nibabel

Volume is reoriented to the simulator convention (axis0=Z axial, axis1=Y coronal,
axis2=X sagittal) so phantom3d.get_slice and scan_geometry work unchanged.
"""
import os
import numpy as np

# Tissue properties come from the authoritative tissue_db (1.5T/3T aware). This
# is only used as a fallback for register_properties(); the app drives rendering
# via tissue_db.apply_to_engine() at the selected field strength. Labels 1-22 are
# the NIfTI/TotalSegmentator body vocabulary; label 23 (the demo WM lesion) is a
# synthetic brain-only label and is intentionally excluded here.
import tissue_db as _tdb
EXTRA_MR_PROPERTIES = {k: v for k, v in _tdb.properties("3T").items() if 1 <= k <= 22}

TS_TO_MR = {
    1: 8,  # spleen
    2: 9,  # kidney_right
    3: 9,  # kidney_left
    4: 1,  # gallbladder
    5: 7,  # liver
    6: 17,  # stomach
    7: 19,  # pancreas
    8: 21,  # adrenal_gland_right
    9: 21,  # adrenal_gland_left
    10: 18,  # lung_upper_lobe_left
    11: 18,  # lung_lower_lobe_left
    12: 18,  # lung_upper_lobe_right
    13: 18,  # lung_middle_lobe_right
    14: 18,  # lung_lower_lobe_right
    15: 17,  # esophagus
    16: 6,  # trachea
    17: 21,  # thyroid_gland
    18: 17,  # small_bowel
    19: 17,  # duodenum
    20: 17,  # colon
    21: 1,  # urinary_bladder
    22: 21,  # prostate
    23: 9,  # kidney_cyst_left
    24: 9,  # kidney_cyst_right
    25: 13,  # sacrum
    26: 13,  # vertebrae_S1
    27: 13,  # vertebrae_L5
    28: 13,  # vertebrae_L4
    29: 13,  # vertebrae_L3
    30: 13,  # vertebrae_L2
    31: 13,  # vertebrae_L1
    32: 13,  # vertebrae_T12
    33: 13,  # vertebrae_T11
    34: 13,  # vertebrae_T10
    35: 13,  # vertebrae_T9
    36: 13,  # vertebrae_T8
    37: 13,  # vertebrae_T7
    38: 13,  # vertebrae_T6
    39: 13,  # vertebrae_T5
    40: 13,  # vertebrae_T4
    41: 13,  # vertebrae_T3
    42: 13,  # vertebrae_T2
    43: 13,  # vertebrae_T1
    44: 13,  # vertebrae_C7
    45: 13,  # vertebrae_C6
    46: 13,  # vertebrae_C5
    47: 13,  # vertebrae_C4
    48: 13,  # vertebrae_C3
    49: 13,  # vertebrae_C2
    50: 13,  # vertebrae_C1
    51: 20,  # heart
    52: 11,  # aorta
    53: 11,  # pulmonary_vein
    54: 11,  # brachiocephalic_trunk
    55: 11,  # subclavian_artery_right
    56: 11,  # subclavian_artery_left
    57: 11,  # common_carotid_artery_right
    58: 11,  # common_carotid_artery_left
    59: 11,  # brachiocephalic_vein_left
    60: 11,  # brachiocephalic_vein_right
    61: 11,  # atrial_appendage_left
    62: 11,  # superior_vena_cava
    63: 11,  # inferior_vena_cava
    64: 11,  # portal_vein_and_splenic_vein
    65: 11,  # iliac_artery_left
    66: 11,  # iliac_artery_right
    67: 11,  # iliac_vena_left
    68: 11,  # iliac_vena_right
    69: 13,  # humerus_left
    70: 13,  # humerus_right
    71: 13,  # scapula_left
    72: 13,  # scapula_right
    73: 13,  # clavicula_left
    74: 13,  # clavicula_right
    75: 13,  # femur_left
    76: 13,  # femur_right
    77: 13,  # hip_left
    78: 13,  # hip_right
    79: 16,  # spinal_cord
    80: 6,  # gluteus_maximus_left
    81: 6,  # gluteus_maximus_right
    82: 6,  # gluteus_medius_left
    83: 6,  # gluteus_medius_right
    84: 6,  # gluteus_minimus_left
    85: 6,  # gluteus_minimus_right
    86: 6,  # autochthon_left
    87: 6,  # autochthon_right
    88: 6,  # iliopsoas_left
    89: 6,  # iliopsoas_right
    90: 2,  # brain
    91: 13,  # skull
    92: 13,  # rib_left_1
    93: 13,  # rib_left_2
    94: 13,  # rib_left_3
    95: 13,  # rib_left_4
    96: 13,  # rib_left_5
    97: 13,  # rib_left_6
    98: 13,  # rib_left_7
    99: 13,  # rib_left_8
    100: 13,  # rib_left_9
    101: 13,  # rib_left_10
    102: 13,  # rib_left_11
    103: 13,  # rib_left_12
    104: 13,  # rib_right_1
    105: 13,  # rib_right_2
    106: 13,  # rib_right_3
    107: 13,  # rib_right_4
    108: 13,  # rib_right_5
    109: 13,  # rib_right_6
    110: 13,  # rib_right_7
    111: 13,  # rib_right_8
    112: 13,  # rib_right_9
    113: 13,  # rib_right_10
    114: 13,  # rib_right_11
    115: 13,  # rib_right_12
    116: 13,  # sternum
    117: 15,  # costal_cartilages
}

# TotalSegmentator 'total_mr' task (50 classes) -> MR tissue labels.
# NOTE: different numbering from the CT scheme above.
TS_MR_TO_MR = {
    1: 8,  # spleen
    2: 9,  # kidney_right
    3: 9,  # kidney_left
    4: 1,  # gallbladder
    5: 7,  # liver
    6: 17,  # stomach
    7: 19,  # pancreas
    8: 21,  # adrenal_gland_right
    9: 21,  # adrenal_gland_left
    10: 18,  # lung_left
    11: 18,  # lung_right
    12: 17,  # esophagus
    13: 17,  # small_bowel
    14: 17,  # duodenum
    15: 17,  # colon
    16: 1,  # urinary_bladder
    17: 21,  # prostate
    18: 13,  # sacrum
    19: 13,  # vertebrae
    20: 15,  # intervertebral_discs
    21: 16,  # spinal_cord
    22: 20,  # heart
    23: 11,  # aorta
    24: 11,  # inferior_vena_cava
    25: 11,  # portal_vein_and_splenic_vein
    26: 11,  # iliac_artery_left
    27: 11,  # iliac_artery_right
    28: 11,  # iliac_vena_left
    29: 11,  # iliac_vena_right
    30: 13,  # humerus_left
    31: 13,  # humerus_right
    32: 13,  # scapula_left
    33: 13,  # scapula_right
    34: 13,  # clavicula_left
    35: 13,  # clavicula_right
    36: 13,  # femur_left
    37: 13,  # femur_right
    38: 13,  # hip_left
    39: 13,  # hip_right
    40: 6,  # gluteus_maximus_left
    41: 6,  # gluteus_maximus_right
    42: 6,  # gluteus_medius_left
    43: 6,  # gluteus_medius_right
    44: 6,  # gluteus_minimus_left
    45: 6,  # gluteus_minimus_right
    46: 6,  # autochthon_left
    47: 6,  # autochthon_right
    48: 6,  # iliopsoas_left
    49: 6,  # iliopsoas_right
    50: 2,  # brain
}


def register_properties(field: str | None = None) -> None:
    """Ensure body tissue properties exist in the engine table.

    Delegates to tissue_db (the single source of truth) when available so a
    loaded volume renders at the same field strength as the rest of the app.
    `field` of None means: don't change the current field, only fill any gaps.
    """
    import phantom3d
    try:
        import tissue_db
        if field is not None:
            tissue_db.apply_to_engine(field)
        else:
            # fill any labels missing from the current table without disturbing
            # the field strength already applied by the app
            cur = phantom3d.TISSUE_PROPERTIES_3D
            for lab, props in tissue_db.properties("3T").items():
                cur.setdefault(lab, props)
        return
    except Exception:
        pass
    # Fallback if tissue_db isn't present: use the local defaults.
    for lab, props in EXTRA_MR_PROPERTIES.items():
        phantom3d.TISSUE_PROPERTIES_3D.setdefault(lab, props)


def detect_scheme(label_set: np.ndarray) -> str:
    """
    Decide whether a mask uses the CT 'total' (117-class) or MR 'total_mr'
    (50-class) numbering, from the set of labels actually present.

    The schemes diverge above ~label 9, so the same integer means different
    things (CT 19=small_bowel vs MR 19=vertebrae). Discriminators:
      * CT-only labels exist > 50 (ribs 92-115, costal_cartilages 117, etc.)
      * MR has intervertebral_discs at 20 (no CT equivalent at that index),
        and never exceeds 50.
    Falls back to CT (the more common public dataset) when ambiguous.
    """
    s = set(int(x) for x in label_set if x > 0)
    if not s:
        return "ct"
    if max(s) > 50:
        return "ct"        # only CT scheme has labels above 50
    # max <= 50: almost certainly MR. (A CT scan cropped to only low labels is
    # rare and would just lose a few high-label bones; MR is the safe call.)
    return "mr"


def _remap(ts_volume: np.ndarray, scheme: str = "ct") -> np.ndarray:
    """Vectorised remap of TS class indices -> MR tissue labels (0 = air)."""
    table = TS_MR_TO_MR if scheme == "mr" else TS_TO_MR
    lut = np.zeros(int(ts_volume.max()) + 1, dtype=np.uint8)
    for ts_idx, mr in table.items():
        if ts_idx < lut.size:
            lut[ts_idx] = mr
    return lut[ts_volume]


def load_segmented_nifti(path: str, target_max: int = 256, scheme: str = "auto") -> np.ndarray:
    """
    Load a TotalSegmentator label NIfTI and return a uint8 labeled volume in the
    simulator's (Z, Y, X) convention, with body fat filled around the organs so
    the torso reads as a solid body rather than floating structures.

    scheme: 'ct' (117-class), 'mr' (50-class total_mr), or 'auto' to detect.
    """
    import nibabel as nib
    img = nib.as_closest_canonical(nib.load(str(path)))   # RAS+: (X, Y, Z)
    data = np.asarray(img.dataobj)
    data = np.rint(data).astype(np.int32)
    data[data < 0] = 0

    if scheme == "auto":
        scheme = detect_scheme(np.unique(data))

    zooms = img.header.get_zooms()[:3]                     # (sx, sy, sz) RAS
    spacing_zyx = (float(zooms[2]), float(zooms[1]), float(zooms[0]))

    mr = _remap(data, scheme=scheme)       # still (X, Y, Z) RAS order
    vol = np.transpose(mr, (2, 1, 0))      # -> (Z, Y, X) to match get_slice

    # Isotropic shape-based resample (fixes blocky reformats) capped at target_max,
    # then synthesize the body fat/muscle envelope.
    vol = resample_labels_isotropic(vol, spacing_zyx, max_dim=target_max)
    vol = _fill_body_fat(vol)
    return vol


def _slice_silhouette(mask: np.ndarray) -> np.ndarray:
    """Approximate the body silhouette of one axial slice as the region bounded
    by the outermost labeled voxels along each row AND each column. Robust on
    sparse structures and needs no SciPy/skimage; reconstructs a torso outline
    from organs+bones+muscle even though TS doesn't label skin/subcutaneous fat."""
    H, W = mask.shape
    rowfill = np.zeros_like(mask)
    colfill = np.zeros_like(mask)
    rows = np.where(mask.any(axis=1))[0]
    for r in rows:
        c = np.where(mask[r])[0]
        rowfill[r, c[0]:c[-1] + 1] = True
    cols = np.where(mask.any(axis=0))[0]
    for c in cols:
        rr = np.where(mask[:, c])[0]
        colfill[rr[0]:rr[-1] + 1, c] = True
    return rowfill & colfill


def _erode(mask: np.ndarray, iters: int = 1) -> np.ndarray:
    """Binary erosion via 4-neighbour min, dependency-free (no scipy needed)."""
    m = mask
    for _ in range(iters):
        e = m.copy()
        e[1:, :] &= m[:-1, :]; e[:-1, :] &= m[1:, :]
        e[:, 1:] &= m[:, :-1]; e[:, :-1] &= m[:, 1:]
        m = e
    return m


def _fill_body_layers(
    vol: np.ndarray,
    fat_label: int = 4,
    muscle_label: int = 6,
    skin_iters: int = 2,
    wall_iters: int = 5,
) -> np.ndarray:
    """
    Fill the unlabeled body interior with a realistic envelope instead of solid
    fat: an outer subcutaneous-fat rim, then a muscle wall, then interior fat
    between organs. TS doesn't label skin/subcutaneous fat/abdominal wall, so we
    synthesize the layering that makes the torso read as MR rather than a flat
    fat blob. Existing segmented structures are never overwritten.
    """
    out = vol.copy()
    for z in range(vol.shape[0]):
        sl = vol[z]
        if not sl.any():
            continue
        body = _slice_silhouette(sl > 0)
        empty = body & (sl == 0)
        if not empty.any():
            continue
        inner_skin = _erode(body, skin_iters)     # everything inside the fat rim
        inner_wall = _erode(inner_skin, wall_iters)  # everything inside muscle wall
        # subcutaneous fat = rim between body edge and inner_skin
        out[z][empty & ~inner_skin] = fat_label
        # muscle wall = band between inner_skin and inner_wall
        out[z][empty & inner_skin & ~inner_wall] = muscle_label
        # deep interior fat (mesenteric/retroperitoneal) fills remaining gaps
        out[z][empty & inner_wall] = fat_label
    return out


# Backwards-compatible alias used by the loader.
def _fill_body_fat(vol: np.ndarray) -> np.ndarray:
    return _fill_body_layers(vol)


def _maybe_downsample(vol: np.ndarray, target_max: int) -> np.ndarray:
    """Nearest-neighbour downsample so the largest axis <= target_max (keeps
    interactive speed; label maps must use NN to preserve class values)."""
    m = max(vol.shape)
    if m <= target_max:
        return vol
    step = int(np.ceil(m / target_max))
    return vol[::step, ::step, ::step].copy()


def resample_labels_isotropic(
    vol: np.ndarray,
    spacing_zyx: "tuple[float, float, float]",
    target_mm: "float | None" = None,
    max_dim: int = 256,
) -> np.ndarray:
    """Resample a uint8 label volume to (near-)isotropic voxels.

    Anisotropic clinical scans (thick slices) reformat into blocky sagittal /
    coronal images. We resample to ``target_mm`` isotropic using *shape-based*
    interpolation: each label's binary mask is lightly smoothed, linearly
    zoomed, and the per-voxel arg-max label is kept. That gives smooth,
    label-preserving boundaries through-plane instead of nearest-neighbour
    stair-steps — and it never invents a label that wasn't already present.

    ``target_mm`` defaults to the finest (smallest) input spacing; the longest
    output axis is capped at ``max_dim`` to bound memory / interactive cost.
    Returns the input unchanged when it is already at the target sampling.
    """
    from scipy.ndimage import zoom, gaussian_filter

    sz, sy, sx = (float(s) for s in spacing_zyx)
    if target_mm is None:
        target_mm = min(sz, sy, sx)
    target_mm = max(target_mm, 1e-3)

    Z, Y, X = vol.shape
    tZ = max(1, int(round(Z * sz / target_mm)))
    tY = max(1, int(round(Y * sy / target_mm)))
    tX = max(1, int(round(X * sx / target_mm)))
    longest = max(tZ, tY, tX)
    if longest > max_dim:
        scale = max_dim / longest
        tZ = max(1, int(round(tZ * scale)))
        tY = max(1, int(round(tY * scale)))
        tX = max(1, int(round(tX * scale)))
    if (tZ, tY, tX) == (Z, Y, X):
        return vol

    fac = (tZ / Z, tY / Y, tX / X)
    labels = [int(v) for v in np.unique(vol) if v > 0]
    best_val = np.zeros((tZ, tY, tX), dtype=np.float32)
    out = np.zeros((tZ, tY, tX), dtype=np.uint8)
    for lab in labels:
        m = gaussian_filter((vol == lab).astype(np.float32), sigma=0.6)
        mz = zoom(m, fac, order=1)
        upd = mz > best_val
        best_val[upd] = mz[upd]
        out[upd] = lab
    out[best_val < 0.5] = 0   # below half occupancy -> background
    return out


# Mapping from TotalSegmentatorMRI per-organ binary mask filename stems to
# simulator MR tissue labels.  Used by load_totalseg_mri_subject().
_SEG_FILE_TO_MR: dict[str, int] = {
    "adrenal_gland_left": 21, "adrenal_gland_right": 21,
    "aorta": 11,
    "autochthon_left": 6, "autochthon_right": 6,
    "brain": 2,
    "colon": 17, "duodenum": 17, "esophagus": 17,
    "femur_left": 13, "femur_right": 13,
    "fibula": 13,
    "gallbladder": 1,
    "gluteus_maximus_left": 6, "gluteus_maximus_right": 6,
    "gluteus_medius_left": 6, "gluteus_medius_right": 6,
    "gluteus_minimus_left": 6, "gluteus_minimus_right": 6,
    "heart": 20,
    "hip_left": 13, "hip_right": 13,
    "humerus_left": 13, "humerus_right": 13,
    "iliac_artery_left": 11, "iliac_artery_right": 11,
    "iliac_vena_left": 11, "iliac_vena_right": 11,
    "iliopsoas_left": 6, "iliopsoas_right": 6,
    "inferior_vena_cava": 11,
    "intervertebral_discs": 15,
    "kidney_left": 9, "kidney_right": 9,
    "liver": 7,
    "lung_left": 18, "lung_right": 18,
    "pancreas": 19,
    "portal_vein_and_splenic_vein": 11,
    "prostate": 21,
    "quadriceps_femoris_left": 6, "quadriceps_femoris_right": 6,
    "sacrum": 13,
    "sartorius_left": 6, "sartorius_right": 6,
    "small_bowel": 17,
    "spinal_cord": 16,
    "spleen": 8,
    "stomach": 17,
    "thigh_medial_compartment_left": 6, "thigh_medial_compartment_right": 6,
    "thigh_posterior_compartment_left": 6, "thigh_posterior_compartment_right": 6,
    "tibia": 13,
    "urinary_bladder": 1,
    "vertebrae": 13,
}

# Organ groups in ascending priority — later groups overwrite earlier ones when
# masks overlap (e.g. a vessel running through the liver, cord inside vertebra).
_SEG_PRIORITY_GROUPS: list[list[str]] = [
    # background muscle (lowest — explicit organ labels take precedence)
    ["autochthon_left", "autochthon_right",
     "gluteus_maximus_left", "gluteus_maximus_right",
     "gluteus_medius_left", "gluteus_medius_right",
     "gluteus_minimus_left", "gluteus_minimus_right",
     "quadriceps_femoris_left", "quadriceps_femoris_right",
     "thigh_medial_compartment_left", "thigh_medial_compartment_right",
     "thigh_posterior_compartment_left", "thigh_posterior_compartment_right",
     "sartorius_left", "sartorius_right",
     "iliopsoas_left", "iliopsoas_right"],
    # hollow structures
    ["lung_left", "lung_right",
     "colon", "small_bowel", "duodenum", "esophagus", "stomach"],
    # solid organs
    ["liver", "spleen", "kidney_left", "kidney_right", "pancreas",
     "adrenal_gland_left", "adrenal_gland_right", "gallbladder",
     "urinary_bladder", "prostate", "heart", "brain"],
    # vessels
    ["aorta", "inferior_vena_cava", "portal_vein_and_splenic_vein",
     "iliac_artery_left", "iliac_artery_right",
     "iliac_vena_left", "iliac_vena_right"],
    # bone
    ["femur_left", "femur_right", "fibula", "tibia",
     "sacrum", "vertebrae",
     "hip_left", "hip_right",
     "humerus_left", "humerus_right"],
    # highest priority: soft-tissue structures within bone
    ["intervertebral_discs", "spinal_cord"],
]

# TotalSegmentatorMRI per-subject source: real MRI with scanner-adaptive
# fat/muscle fill, resampled to isotropic at load. Subjects are chosen for
# near-isotropic acquisition AND full coverage in ALL three planes (large A-P
# extent in particular), so axial/coronal/sagittal reformats are all crisp and
# anatomically proportioned — not a thin acquired slab that squashes in one
# view. Picked by scanning the dataset headers (isotropy <=1.3, A-P >=200 mm,
# L-R >=280 mm, S-I >=200 mm) then ranking by target-organ slice span:
#   s0246  abdomen — ~1.4 mm iso, full torso, widest liver S-I span (5/5 organs)
#   s0267  spine   — ~1.4 mm iso, full torso, longest vertebral column (246 vox)
#   s0187  pelvis  — ~1.4 mm iso, full pelvis coverage (sacrum/hips/bladder 5/5)
#   s0250  torso   — ~1.4 mm iso, deepest A-P (270 mm) in the dataset; lung bases
#                    through pelvis with heart/aorta/liver/spleen/kidneys/bones
_REGION_TOTALSEG: dict[str, str] = {
    "Abdomen": "s0246",
    "Spine":   "s0267",
    "Pelvis":  "s0187",
    "Torso":   "s0250",
}


def _ts_subject_root(data_dir: str, subj_name: str) -> "str | None":
    """Locate ``subj_name`` inside whichever TotalSegmentatorMRI dataset release
    sits in ``data_dir`` (the dir name carries a version suffix, e.g. _v100,
    _v200). Returns the subject path if found, else None."""
    import glob
    for ds in sorted(glob.glob(os.path.join(data_dir, "TotalsegmentatorMRI_dataset_v*"))):
        cand = os.path.join(ds, subj_name)
        if os.path.isdir(cand):
            return cand
    return None

# 1.5 mm-isotropic flat combined NIfTI (TotalSegmentator CT 'total' scheme),
# used only as a fallback if the per-subject MRI data above is unavailable.
_REGION_NIFTI = {
    "Abdomen": "s0009.nii.gz",
    "Spine":   "s0021.nii.gz",
    "Pelvis":  "s0000.nii.gz",
}


def _kmeans1d(x: np.ndarray, k: int = 3, iters: int = 25) -> np.ndarray:
    """Tiny 1-D k-means (no sklearn dep). Returns centres sorted dark -> bright."""
    c = np.percentile(x, np.linspace(15, 90, k)).astype(np.float64)
    for _ in range(iters):
        a = np.abs(x[:, None] - c[None, :]).argmin(1)
        for j in range(k):
            if (a == j).any():
                c[j] = x[a == j].mean()
    return np.sort(c)


def _classify_unlabeled_from_mri(
    label_vol: np.ndarray,
    mri_vol: np.ndarray,
    fat_thresh: "float | None" = None,
    body_thresh: "float | None" = None,
    fat_pct: float = 72.0,
) -> np.ndarray:
    """Fill unlabeled interior voxels using real MRI intensity.

    Uses the MRI image to define the body boundary, then assigns fat (label 4)
    to bright unlabeled voxels and muscle (label 6) to medium-intensity ones.
    Existing segmented labels are never overwritten.

    The default (``fat_thresh``/``body_thresh`` = None) is *measured*, not a
    quota. Because the dataset mixes sequences with opposite fat/muscle
    polarity (fat bright on some subjects, darker than muscle on others), the
    split is calibrated per volume from two reference distributions: the gold
    muscle masks already painted as label 6, and the subcutaneous rind (which
    is anatomically fat). Each unlabeled voxel goes to the nearer reference
    median in per-slice-normalised intensity. When no muscle reference exists,
    a 3-cluster k-means brightest-cluster-is-fat fallback applies. The old
    fixed ``fat_pct`` percentile forced ~28% of every body to be fat
    regardless of anatomy. Explicit values restore fixed-threshold mode.
    """
    out = label_vol.copy()
    nz = min(label_vol.shape[0], mri_vol.shape[0])

    # Pass 1: per-slice silhouettes, normalised intensities, reference samples.
    slices = []          # (z, empty, norm_sl)
    empty_samples, mus_samples, fat_samples = [], [], []
    for z in range(nz):
        sl = label_vol[z]
        mri_sl = mri_vol[z].astype(float)
        if body_thresh is None:
            pos = mri_sl[mri_sl > 0]
            bt = max(0.10 * float(mri_sl.max()),
                     float(np.percentile(pos, 20))) if pos.size else 0.0
        else:
            bt = body_thresh
        body = _slice_silhouette(mri_sl > bt)
        empty = body & (sl == 0)
        if not empty.any():
            continue
        if fat_thresh is not None:
            out[z][empty & (mri_sl >= fat_thresh)] = 4
            out[z][empty & (mri_sl < fat_thresh)] = 6
            continue
        scale = float(np.median(mri_sl[body])) if body.any() else 1.0
        norm_sl = mri_sl / max(scale, 1e-6)
        slices.append((z, empty, norm_sl))
        empty_samples.append(norm_sl[empty])
        mus = body & (sl == 6)
        if mus.any():
            mus_samples.append(norm_sl[mus])
        rind = empty & ~_erode(body, 3)          # subcutaneous layer ~ fat
        if rind.any():
            fat_samples.append(norm_sl[rind])

    if fat_thresh is not None or not slices:
        return out

    mus_ref = np.concatenate(mus_samples) if mus_samples else np.empty(0)
    fat_ref = np.concatenate(fat_samples) if fat_samples else np.empty(0)
    if mus_ref.size >= 500 and fat_ref.size >= 500:
        # Pass 2a: nearest-reference-median split (polarity-agnostic).
        med_mus, med_fat = float(np.median(mus_ref)), float(np.median(fat_ref))
        for z, empty, norm_sl in slices:
            d_fat = np.abs(norm_sl - med_fat)
            d_mus = np.abs(norm_sl - med_mus)
            out[z][empty & (d_fat <= d_mus)] = 4
            out[z][empty & (d_fat > d_mus)] = 6
        return out

    # Pass 2b: no reference masks — k-means over the normalised empties,
    # cut midway between the middle and bright cluster centres.
    x = np.concatenate(empty_samples)
    if x.size >= 30:
        c = _kmeans1d(x[:: max(1, x.size // 200_000)])
        cut = 0.5 * (c[-2] + c[-1])
    else:
        cut = float(np.percentile(x, fat_pct)) if x.size else np.inf
    for z, empty, norm_sl in slices:
        out[z][empty & (norm_sl >= cut)] = 4   # subcutaneous / mesenteric fat
        out[z][empty & (norm_sl < cut)] = 6    # abdominal wall / unlabeled muscle
    return out


def _mark_bowel_gas(label_vol: np.ndarray, mri_vol: np.ndarray,
                    gas_frac: float = 0.3, bowel_label: int = 17,
                    gas_label: int = 12) -> np.ndarray:
    """Dark bowel content is gas: relabel it 12 (internal gas) so the
    susceptibility artifact sees real bowel-gas sources and every sequence
    renders it signal-void. The cut is relative to the body's median MRI
    intensity (measured: 31%/47% of Abdomen/Torso bowel falls below 0.3x)."""
    body = label_vol > 0
    nz = min(label_vol.shape[0], mri_vol.shape[0])
    if not body[:nz].any():
        return label_vol
    med = float(np.median(mri_vol[:nz][body[:nz]]))
    out = label_vol.copy()
    gas = (label_vol[:nz] == bowel_label) & (mri_vol[:nz] < gas_frac * med)
    out[:nz][gas] = gas_label
    return out


def _normalize_texture_per_label(tex: np.ndarray, label_vol: np.ndarray,
                                 clip: "tuple[float, float]" = (0.6, 1.6)) -> np.ndarray:
    """Remove cross-tissue contrast from the texture field: divide by each
    label's median so texture carries only intra-tissue parenchymal detail.
    Without this the source acquisition's own contrast leaks into every
    rendered sequence (e.g. a fat-dark source muting physics-bright fat on
    T1). Background (label 0) keeps its 1.0."""
    out = tex.astype(np.float32).copy()
    for lab in np.unique(label_vol):
        if lab == 0:
            continue
        m = label_vol == lab
        med = float(np.median(tex[m]))
        if med > 1e-6:
            out[m] = tex[m] / med
    out[label_vol > 0] = np.clip(out[label_vol > 0], *clip)
    return out


def encode_mixel_fraction(f: np.ndarray) -> np.ndarray:
    """Dominant fraction f in [0.5, 1.0] -> uint8 byte (255 = pure)."""
    return np.clip(np.round((np.asarray(f, np.float32) - 0.5) * 510.0),
                   0, 255).astype(np.uint8)


def decode_mixel_fraction(b: np.ndarray) -> np.ndarray:
    """Inverse of encode_mixel_fraction."""
    return 0.5 + np.asarray(b, np.float32) / 510.0


def build_mixel(labels_src: np.ndarray, atlas: np.ndarray,
                blur_sigma: float = 0.5) -> np.ndarray:
    """Two-tissue partial-volume sidecar for *atlas*: (2, Z, Y, X) uint8 —
    channel 0 the second tissue's label (0 = pure), channel 1 the dominant
    (atlas-label) fraction via encode_mixel_fraction.

    Fractions come from linearly resampling each label's indicator from
    ``labels_src`` (the pipeline's higher-resolution grid) onto the atlas
    grid; when the grids share a shape a ``blur_sigma`` indicator blur
    stands in (synthetic sub-voxel estimate). The dominant label is always
    the atlas's own label, so atlas and sidecar cannot disagree.
    """
    from scipy.ndimage import gaussian_filter, zoom
    shape = atlas.shape
    same = tuple(labels_src.shape) == tuple(shape)
    zf = None if same else [t / s for t, s in zip(shape, labels_src.shape)]

    fa = np.zeros(shape, np.float32)               # fraction of the atlas label
    fb = np.zeros(shape, np.float32)               # best other-label fraction
    lb = np.zeros(shape, np.uint8)
    for lab in np.unique(labels_src):
        if lab == 0:
            continue
        ind = (labels_src == lab).astype(np.float32)
        f = gaussian_filter(ind, blur_sigma) if same else zoom(ind, zf, order=1)
        mine = atlas == lab
        fa[mine] = f[mine]
        other = ~mine & (f > fb)
        fb[other] = f[other]
        lb[other] = lab

    mixed = (fb > 0.02) & (atlas > 0)
    with np.errstate(invalid="ignore", divide="ignore"):
        frac = np.where(mixed, fa / np.maximum(fa + fb, 1e-6), 1.0)
    frac = np.clip(frac, 0.5, 1.0)

    out = np.zeros((2,) + shape, np.uint8)
    out[0][mixed] = lb[mixed]
    out[1] = np.where(mixed, encode_mixel_fraction(frac), np.uint8(255))
    return out


def _enrich_filled_labels(label_vol: np.ndarray) -> np.ndarray:
    """Post-fill enrichment: split bone into cortical shell + marrow interior
    (label 13 -> shell 13 / interior 14) and paint a 1-voxel in-plane skin rind
    (label 5) on the body silhouette — the same treatment the SPIDER spine
    build applies, so bones aren't solid dark blocks and STIR/T1 read right."""
    from scipy.ndimage import binary_erosion

    out = label_vol.copy()
    bone = out == 13
    if bone.any():
        out[binary_erosion(bone, iterations=1)] = 14   # trabecular marrow
    body = out > 0
    for z in range(out.shape[0]):
        b = body[z]
        if b.any():
            out[z][b & ~binary_erosion(b, iterations=1)] = 5   # skin rind
    return out


def _mri_texture(mri: np.ndarray, sigma: float = 2.0,
                 lo: float = 0.6, hi: float = 1.5) -> np.ndarray:
    """Local-detail (anatomical texture) field of a real MRI, centred on 1.0.

    The simulator renders flat per-label signal, which looks 'painted'. Real
    parenchyma, vessels and organ heterogeneity live in the *high-frequency*
    component of the acquired image. Dividing the MRI by a smoothed copy yields
    a contrast-independent multiplicative texture (≈1.0 in uniform regions,
    higher/lower on real detail) that we modulate the synthetic signal with,
    preserving label-based TR/TE contrast while restoring realism.
    """
    from scipy.ndimage import gaussian_filter
    mri = np.asarray(mri, dtype=np.float32)
    sm = gaussian_filter(mri, sigma=sigma)
    tex = np.where(sm > 1e-6, mri / sm, 1.0)
    return np.clip(tex, lo, hi).astype(np.float32)


def load_totalseg_mri_subject(
    subject_dir: str,
    target_max: int = 256,
    fat_threshold: "float | None" = None,
    body_threshold: "float | None" = None,
    with_texture: bool = False,
    with_mixel: bool = False,
) -> "np.ndarray | tuple":
    """Build a rich multi-label atlas from a TotalSegmentatorMRI per-subject dir.

    Combines up to 56 per-organ binary masks into a single uint8 label volume,
    then uses the accompanying real MRI (mri.nii.gz) to fill the remaining body
    voxels (subcutaneous fat, abdominal wall muscle, mesenteric fat) using
    intensity thresholding.

    Returns a uint8 volume in simulator (Z, Y, X) convention, resampled to
    isotropic with the longest axis <= target_max. If ``with_texture`` is set,
    a float32 real-MRI detail texture is appended (see :func:`_mri_texture`);
    if ``with_mixel`` is set, a partial-volume sidecar built from the
    working-grid labels is appended (see :func:`build_mixel`). Return shapes:
    ``labels`` | ``(labels, tex)`` | ``(labels, mixel)`` | ``(labels, tex, mixel)``.
    """
    import nibabel as nib

    mri_path = os.path.join(subject_dir, "mri.nii.gz")
    seg_dir = os.path.join(subject_dir, "segmentations")
    if not os.path.exists(mri_path) or not os.path.isdir(seg_dir):
        raise FileNotFoundError(f"Missing mri.nii.gz or segmentations/ in {subject_dir}")

    mri_img = nib.as_closest_canonical(nib.load(mri_path))
    mri_xyz = np.asarray(mri_img.dataobj).astype(np.float32)  # (X, Y, Z) RAS+
    zooms = mri_img.header.get_zooms()[:3]                     # (sx, sy, sz)

    label_xyz = np.zeros(mri_xyz.shape, dtype=np.uint8)

    for group in _SEG_PRIORITY_GROUPS:
        for seg_name in group:
            mr_label = _SEG_FILE_TO_MR.get(seg_name)
            if mr_label is None:
                continue
            seg_path = os.path.join(seg_dir, f"{seg_name}.nii.gz")
            if not os.path.exists(seg_path):
                continue
            seg_img = nib.as_closest_canonical(nib.load(seg_path))
            seg_mask = np.asarray(seg_img.dataobj) > 0
            label_xyz[seg_mask] = mr_label

    # Reorient both to simulator (Z, Y, X)
    label_zyx = np.transpose(label_xyz, (2, 1, 0))
    mri_zyx = np.transpose(mri_xyz, (2, 1, 0))

    # Cap the *working* grid only if the native volume is very large, so the
    # per-slice fill stays fast without discarding resolution for normal subjects
    # (the final isotropic resample does the real downsizing to target_max).
    m = max(label_zyx.shape)
    work_cap = 2 * target_max
    if m > work_cap:
        step = int(np.ceil(m / work_cap))
        label_zyx = label_zyx[::step, ::step, ::step].copy()
        mri_zyx = mri_zyx[::step, ::step, ::step].copy()
    else:
        step = 1

    label_filled = _classify_unlabeled_from_mri(label_zyx, mri_zyx, fat_threshold, body_threshold)
    label_filled = _mark_bowel_gas(label_filled, mri_zyx)
    label_filled = _enrich_filled_labels(label_filled)

    # Resample to isotropic so sagittal/coronal reformats are smooth rather than
    # stair-stepped. Spacing is (sz, sy, sx), scaled by any working-grid step.
    spacing_zyx = (float(zooms[2]) * step, float(zooms[1]) * step, float(zooms[0]) * step)
    labels_iso = resample_labels_isotropic(label_filled, spacing_zyx, max_dim=target_max)

    # Partial-volume sidecar from the working-grid labels (the honest
    # sub-voxel source: finer than the iso grid it is resampled onto).
    mixel = build_mixel(label_filled, labels_iso) if with_mixel else None

    if not with_texture:
        return (labels_iso, mixel) if with_mixel else labels_iso

    # Real-MRI texture, resampled (linear) to exactly match the iso label grid.
    from scipy.ndimage import zoom
    tex = _mri_texture(mri_zyx)
    if tex.shape == labels_iso.shape:
        tex_iso = tex
    else:
        zf = [labels_iso.shape[i] / tex.shape[i] for i in range(3)]
        tex_iso = zoom(tex, zf, order=1).astype(np.float32)
    tex_iso = _normalize_texture_per_label(tex_iso, labels_iso)
    return (labels_iso, tex_iso, mixel) if with_mixel else (labels_iso, tex_iso)


def load_region_nifti(
    region: str,
    data_dir: str,
    *,
    target_max: int = 256,
) -> "np.ndarray | None":
    """Load a real TotalSegmentator segmentation for *region* and return a
    remapped uint8 label volume in simulator (Z, Y, X) convention.

    Tries the rich TotalSegmentatorMRI per-subject data first (real MRI-guided
    fat/muscle fill), then falls back to the flat combined NIfTI files.
    Caches results as .npy files for fast subsequent loads.
    Returns ``None`` if no data source is found or nibabel is unavailable.
    """
    # --- primary: TotalSegmentatorMRI per-subject (best quality) ---
    subj_name = _REGION_TOTALSEG.get(region)
    if subj_name is not None:
        ts_root = _ts_subject_root(data_dir, subj_name)
        if ts_root is not None:
            cache = os.path.join(ts_root, f"atlas_iso_adapt_{target_max}.npy")
            if os.path.exists(cache):
                return np.load(cache)
            try:
                vol, tex, mixel = load_totalseg_mri_subject(
                    ts_root, target_max=target_max, with_texture=True, with_mixel=True)
                np.save(cache, vol)
                np.save(os.path.join(ts_root, f"texture_iso_adapt_{target_max}.npy"), tex)
                np.save(os.path.join(ts_root, f"mixel_iso_adapt_{target_max}.npy"), mixel)
                return vol
            except Exception as exc:
                print(f"nifti_region: TotalSegMRI load failed for {subj_name}: {exc}")

    # --- fallback: flat combined NIfTI ---
    filename = _REGION_NIFTI.get(region)
    if filename is None:
        return None
    nii_path = os.path.join(data_dir, filename)
    if not os.path.exists(nii_path):
        return None
    cache_path = nii_path.replace(".nii.gz", f"_mr_iso{target_max}.npy")
    if os.path.exists(cache_path):
        return np.load(cache_path)
    try:
        vol = load_segmented_nifti(nii_path, target_max=target_max)
        np.save(cache_path, vol)
        return vol
    except Exception as exc:
        print(f"nifti_region: could not load {nii_path}: {exc}")
        return None


def load_region_texture(
    region: str,
    data_dir: str,
    *,
    target_max: int = 256,
) -> "np.ndarray | None":
    """Real-MRI anatomical texture field for *region*, aligned to its label
    volume (same shape), for multiplicative signal modulation in the renderer.

    Only the TotalSegmentatorMRI per-subject sources carry a texture (the flat
    NIfTI fallback and the brain have none). Returns ``None`` when unavailable.
    Builds the cache on first use by loading the region (which writes both the
    label atlas and its sibling texture file)."""
    subj_name = _REGION_TOTALSEG.get(region)
    if subj_name is None:
        return None
    ts_root = _ts_subject_root(data_dir, subj_name)
    if ts_root is None:
        return None
    tex_cache = os.path.join(ts_root, f"texture_iso_adapt_{target_max}.npy")
    if not os.path.exists(tex_cache):
        # Build both caches together (the atlas cache may already exist from an
        # earlier label-only load, which wouldn't have written the texture).
        try:
            vol, tex = load_totalseg_mri_subject(ts_root, target_max=target_max, with_texture=True)
            np.save(os.path.join(ts_root, f"atlas_iso_adapt_{target_max}.npy"), vol)
            np.save(tex_cache, tex)
        except Exception as exc:
            print(f"nifti_region: texture build failed for {subj_name}: {exc}")
            return None
    return np.load(tex_cache)
