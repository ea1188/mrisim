"""
region_index.py  —  scan a folder of TotalSegmentator label masks, classify the
body region of each, and summarise the anatomy present, so masks can be picked
by body part instead of opaque case IDs (s0011, ...).

Reads only the integer label set of each mask (fast; uses nibabel's lazy
dataobj + a coarse subsample), classifies into a coarse region, and writes a
JSON cache so the (slow) scan happens once. Built against the CT-Lite 117-class
scheme; the MR scheme can be added later via TS_MR_NAMES.
"""
from __future__ import annotations

from collections.abc import Callable
import json
import os

# CT 'total' task class names (index -> name), used to describe each mask.
TS_CT_NAMES = {
    1: "spleen", 2: "kidney_right", 3: "kidney_left", 4: "gallbladder", 5: "liver",
    6: "stomach", 7: "pancreas", 8: "adrenal_gland_right", 9: "adrenal_gland_left",
    10: "lung_upper_lobe_left", 11: "lung_lower_lobe_left", 12: "lung_upper_lobe_right",
    13: "lung_middle_lobe_right", 14: "lung_lower_lobe_right", 15: "esophagus",
    16: "trachea", 17: "thyroid_gland", 18: "small_bowel", 19: "duodenum", 20: "colon",
    21: "urinary_bladder", 22: "prostate", 23: "kidney_cyst_left", 24: "kidney_cyst_right",
    25: "sacrum", 51: "heart", 52: "aorta", 63: "inferior_vena_cava",
    79: "spinal_cord", 90: "brain", 91: "skull", 116: "sternum", 117: "costal_cartilages",
}
# vertebrae 26-50, vessels 53-68, limb bones 69-78, muscles 80-89, ribs 92-115
for _i in range(26, 51):
    TS_CT_NAMES[_i] = "vertebra"
for _i in range(53, 69):
    TS_CT_NAMES[_i] = "vessel"
for _i in (69, 70):
    TS_CT_NAMES[_i] = "humerus"
for _i in (71, 72):
    TS_CT_NAMES[_i] = "scapula"
for _i in (73, 74):
    TS_CT_NAMES[_i] = "clavicle"
for _i in (75, 76):
    TS_CT_NAMES[_i] = "femur"
for _i in (77, 78):
    TS_CT_NAMES[_i] = "hip"
for _i in range(80, 90):
    TS_CT_NAMES[_i] = "muscle"
for _i in range(92, 116):
    TS_CT_NAMES[_i] = "rib"

# MR 'total_mr' task class names (different numbering from CT).
TS_MR_NAMES = {
    1: "spleen", 2: "kidney_right", 3: "kidney_left", 4: "gallbladder", 5: "liver",
    6: "stomach", 7: "pancreas", 8: "adrenal_gland_right", 9: "adrenal_gland_left",
    10: "lung_left", 11: "lung_right", 12: "esophagus", 13: "small_bowel",
    14: "duodenum", 15: "colon", 16: "urinary_bladder", 17: "prostate", 18: "sacrum",
    19: "vertebra", 20: "intervertebral_disc", 21: "spinal_cord", 22: "heart",
    23: "aorta", 24: "inferior_vena_cava", 25: "vessel", 26: "vessel", 27: "vessel",
    28: "vessel", 29: "vessel", 30: "humerus", 31: "humerus", 32: "scapula",
    33: "scapula", 34: "clavicle", 35: "clavicle", 36: "femur", 37: "femur",
    38: "hip", 39: "hip", 40: "muscle", 41: "muscle", 42: "muscle", 43: "muscle",
    44: "muscle", 45: "muscle", 46: "muscle", 47: "muscle", 48: "muscle",
    49: "muscle", 50: "brain",
}


def detect_scheme(label_set: set[int]) -> str:
    """'mr' if max label <= 50 else 'ct' (mirrors nifti_region.detect_scheme)."""
    s = set(int(x) for x in label_set if x > 0)
    if not s:
        return "ct"
    return "ct" if max(s) > 50 else "mr"

# Marker label sets used to classify the body region.
_LUNG = set(range(10, 15))
_HEART = {51}
_ABDO = {1, 2, 3, 4, 5, 6, 7, 18, 19, 20}        # spleen/kidneys/liver/stomach/bowel...
_PELVIS = {21, 22, 25, 77, 78}                     # bladder/prostate/sacrum/hip
_LIMB = {69, 70, 71, 72, 75, 76}                   # humerus/scapula/femur
_HEAD = {90, 91}                                   # brain/skull
_CERV = set(range(44, 51))                         # cervical vertebrae


def _names_for(label_set: set[int], scheme: str) -> set[str]:
    table = TS_MR_NAMES if scheme == "mr" else TS_CT_NAMES
    return set(table.get(int(x), "") for x in label_set) - {""}


def classify_region(label_set: set[int], scheme: str | None = None) -> str:
    """Map present labels to a coarse body-region string (scheme-aware)."""
    if scheme is None:
        scheme = detect_scheme(label_set)
    names = _names_for(label_set, scheme)

    def any_name(*subs: str) -> bool:
        return any(any(sub in nm for sub in subs) for nm in names)

    lungs = any_name("lung")
    heart = "heart" in names
    abdo = bool(names & {"spleen", "kidney_right", "kidney_left", "liver",
                         "stomach", "pancreas", "small_bowel", "duodenum",
                         "colon", "gallbladder"})
    pelvis = bool(names & {"urinary_bladder", "prostate", "sacrum", "hip"})
    head = bool(names & {"brain", "skull"})
    limb = bool(names & {"humerus", "scapula", "femur"})

    if head and not (lungs or abdo):
        return "Head / Neck"
    if (lungs or heart) and abdo:
        return "Chest + Abdomen"
    if lungs or heart:
        return "Chest"
    if abdo and pelvis:
        return "Abdomen + Pelvis"
    if abdo:
        return "Abdomen"
    if pelvis:
        return "Pelvis"
    if limb:
        return "Limb"
    if "vertebra" in names or "spinal_cord" in names:
        return "Neck / Spine"
    return "Other"


def summarise_anatomy(label_set: set[int], max_items: int = 10, scheme: str | None = None) -> str:
    """Human-readable list of distinct structures present (deduped group names)."""
    if scheme is None:
        scheme = detect_scheme(label_set)
    table = TS_MR_NAMES if scheme == "mr" else TS_CT_NAMES
    names, seen = [], set()
    for lab in sorted(int(x) for x in label_set):
        nm = table.get(lab)
        if not nm or nm in seen:
            continue
        seen.add(nm)
        names.append(nm.replace("_", " "))
    if len(names) > max_items:
        return ", ".join(names[:max_items]) + f", +{len(names) - max_items} more"
    return ", ".join(names) if names else "(no recognised structures)"


def labels_in_mask(path: str, subsample: int = 4) -> set[int]:
    """Return the set of integer labels present in a mask, reading lazily and
    coarsely subsampling for speed (a present structure spans many voxels, so a
    1-in-4 stride per axis still catches everything but tiny specks)."""
    import nibabel as nib
    import numpy as np
    img = nib.load(str(path))
    arr = np.asarray(img.dataobj[::subsample, ::subsample, ::subsample])  # type: ignore[attr-defined]
    vals = np.unique(arr)
    return set(int(v) for v in vals if v > 0)


def _mask_files(folder: str) -> list[str]:
    out = []
    for fn in sorted(os.listdir(folder)):
        if fn.endswith(".nii") or fn.endswith(".nii.gz"):
            out.append(fn)
    return out


def build_index(
    folder: str,
    cache_path: str | None = None,
    progress: Callable[[int, int, str], None] | None = None,
    subsample: int = 4,
) -> list[dict]:
    """
    Scan every mask in `folder`, classify + summarise each, and return a list of
    dict entries. Writes/reads a JSON cache keyed by filename+mtime+size so the
    expensive scan only happens once (and incrementally for new files).
    """
    folder = os.path.expanduser(folder)
    if cache_path is None:
        cache_path = os.path.join(folder, ".region_index.json")

    cache = {}
    if os.path.exists(cache_path):
        try:
            with open(cache_path) as fh:
                cache = {e["key"]: e for e in json.load(fh)}
        except Exception:
            cache = {}

    files = _mask_files(folder)
    entries = []
    changed = False
    for i, fn in enumerate(files):
        path = os.path.join(folder, fn)
        st = os.stat(path)
        key = f"{fn}:{int(st.st_mtime)}:{st.st_size}"
        if key in cache:
            entries.append(cache[key])
        else:
            if progress:
                progress(i + 1, len(files), fn)
            labs = labels_in_mask(path, subsample=subsample)
            scheme = detect_scheme(labs)
            entry = {
                "key": key, "file": fn, "path": path,
                "region": classify_region(labs, scheme),
                "anatomy": summarise_anatomy(labs, scheme=scheme),
                "scheme": scheme,
                "n_labels": len(labs),
            }
            entries.append(entry)
            changed = True

    if changed:
        try:
            with open(cache_path, "w") as fh:
                json.dump(entries, fh, indent=0)
        except Exception:
            pass
    return entries


def regions_summary(entries: list[dict]) -> dict[str, int]:
    """Count of masks per region, for building filter buttons."""
    from collections import Counter
    c = Counter(e["region"] for e in entries)
    return dict(sorted(c.items(), key=lambda kv: (-kv[1], kv[0])))
