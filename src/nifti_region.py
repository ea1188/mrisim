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
import numpy as np

# Tissue properties come from the authoritative tissue_db (1.5T/3T aware). This
# is only used as a fallback for register_properties(); the app drives rendering
# via tissue_db.apply_to_engine() at the selected field strength.
import tissue_db as _tdb
EXTRA_MR_PROPERTIES = {k: v for k, v in _tdb.properties("3T").items() if k >= 1}

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

    mr = _remap(data, scheme=scheme)       # still (X, Y, Z) RAS order
    vol = np.transpose(mr, (2, 1, 0))      # -> (Z, Y, X) to match get_slice

    vol = _maybe_downsample(vol, target_max)   # shrink first (cheap), then fill
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
