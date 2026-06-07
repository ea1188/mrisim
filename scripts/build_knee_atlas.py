#!/usr/bin/env python3
"""Build the real Knee region cache from the KneeBones3Dify dataset.

Source: D. Romano et al., "KneeBones3Dify-Annotated-Dataset" v1.0.0, Zenodo
(https://zenodo.org/records/10534328), CC-BY-4.0 — one 3-D isotropic T2 (3D
SST2) right-knee series (286 × 512 × 512 @ 0.35 mm) plus per-slice bone masks.

This processes that raw download into the same kind of cache the body regions
use: a uint8 tissue-label atlas + a ~1.0 multiplicative real-MRI texture field.
Bones come from the masks (cortical rim + marrow); the surrounding soft tissue
(subcutaneous fat, muscle, joint fluid, articular cartilage, skin) is classified
from the real T2 intensity; the real intensity becomes the texture so the knee
renders with genuine parenchymal detail at any sequence/contrast.

Run once after downloading + unzipping the dataset:
    python scripts/build_knee_atlas.py <raw_dir>   # writes data/knee_kb3d/{atlas,texture}.npy
Only the small processed cache is committed; the raw dataset stays out of git.
"""
import glob
import os
import sys

import numpy as np
import pydicom
from PIL import Image
from scipy.ndimage import (binary_closing, binary_dilation, binary_erosion,
                           binary_fill_holes, gaussian_filter, label)

# tissue_db labels
BG, FLUID, FAT, SKIN, MUSCLE = 0, 1, 4, 5, 6
BONE_CORTICAL, MARROW, CARTILAGE, LIGAMENT = 13, 14, 15, 22

OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "knee_kb3d")
TARGET_MAX = 256


def _load_raw(raw_dir):
    data = glob.glob(os.path.join(raw_dir, "**", "Data"), recursive=True)
    masks = glob.glob(os.path.join(raw_dir, "**", "GT-Masks"), recursive=True)
    if not data or not masks:
        raise SystemExit(f"Data/ and GT-Masks/ not found under {raw_dir}")
    dcm = sorted(glob.glob(os.path.join(data[0], "*.dcm")),
                 key=lambda f: int(f.split("_")[-1].split(".")[0]))
    png = sorted(glob.glob(os.path.join(masks[0], "*.png")),
                 key=lambda f: int("".join(c for c in os.path.basename(f) if c.isdigit())))
    vol = np.stack([pydicom.dcmread(f).pixel_array.astype(np.float32) for f in dcm])
    bone = np.stack([np.asarray(Image.open(f)) > 0 for f in png]).astype(bool)
    return vol, bone


def _downsample(vol, bone):
    from scipy.ndimage import zoom
    f = TARGET_MAX / max(vol.shape)
    return zoom(vol, f, order=1), zoom(bone.astype(np.float32), f, order=0) > 0.5


def _crop_to_body(vol, body):
    zz, yy, xx = np.where(body)
    pad = 4
    sl = tuple(slice(max(0, a.min() - pad), min(s, a.max() + 1 + pad))
               for a, s in zip((zz, yy, xx), body.shape, strict=True))
    return sl


def build(raw_dir):
    vol, bone = _downsample(*_load_raw(raw_dir))
    # Reorient the raw DICOM to the body-atlas storage convention so the knee
    # composes through the same engine + load_region path as every BODY_REGION.
    # nifti_region builds those atlases as axis0↑=Superior, axis1↑=Anterior,
    # axis2↑=Right (RAS+ transposed to Z,Y,X). This DICOM's tags (IOP/IPP) give
    # axis0↑=Inferior, axis1↑=Posterior, axis2↑=Left — the opposite on all three
    # axes — so flip all three. (Without this the knee was upside-down, then
    # A-P-mirrored, then L-R-mirrored.)
    vol, bone = vol[::-1, ::-1, ::-1], bone[::-1, ::-1, ::-1]
    v = vol / max(np.percentile(vol[vol > 0], 99), 1e-3)
    v = np.clip(v, 0, 1.6)

    # Foreground (the leg): threshold the smoothed volume, close + fill, keep the
    # largest connected component (drops background speckle).
    body = gaussian_filter(v, 1.2) > 0.07
    body = binary_closing(body, iterations=2)
    body = np.stack([binary_fill_holes(s) for s in body])
    lbl, n = label(body)
    if n > 1:
        body = lbl == (1 + np.argmax(np.bincount(lbl.flat)[1:]))

    sl = _crop_to_body(vol, body)
    v, body, bone = v[sl], body[sl], bone[sl] & body[sl]

    lab = np.zeros(v.shape, dtype=np.uint8)
    soft = body & ~bone
    # subcutaneous fat = bright AND within ~6 voxels of the skin boundary
    rim = body & ~binary_erosion(body, iterations=6)
    p25, p60, p85 = np.percentile(v[soft], (25, 60, 85))
    lab[soft] = MUSCLE
    lab[soft & (v > p60) & rim] = FAT             # subcutaneous fat
    lab[soft & (v > p85) & ~rim] = FLUID          # bright focal interior = effusion/fluid
    # dense fibrous tissue — menisci (dark wedges at the tibiofemoral joint line),
    # cruciates in the notch, the patellar/quadriceps tendons: all very low signal,
    # so dark *interior* soft tissue (below the skin rim) maps to ligament/meniscus.
    lab[soft & (v < p25) & ~rim] = LIGAMENT
    # articular cartilage: a thin bright coat on the bone surface
    coat = binary_dilation(bone, iterations=2) & ~bone & body
    lab[coat & (v > p60)] = CARTILAGE
    # bone: cortical shell + marrow core
    lab[bone] = BONE_CORTICAL
    lab[binary_erosion(bone, iterations=2)] = MARROW
    # skin rind
    lab[body & ~binary_erosion(body, iterations=1)] = SKIN
    lab[~body] = BG

    # texture = real intensity, normalised to a ~1.0 multiplicative field
    tex = np.ones(v.shape, dtype=np.float32)
    mean = float(v[body].mean())
    tex[body] = np.clip(v[body] / max(mean, 1e-3), 0.4, 1.8)

    os.makedirs(OUT_DIR, exist_ok=True)
    np.save(os.path.join(OUT_DIR, "atlas.npy"), lab)
    np.save(os.path.join(OUT_DIR, "texture.npy"), tex.astype(np.float16))
    print(f"wrote {OUT_DIR}: atlas {lab.shape} {lab.nbytes // 1024} KB, "
          f"labels {sorted(np.unique(lab).tolist())}")


if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else "/tmp/knee_ds")
