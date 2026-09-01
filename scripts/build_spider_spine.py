#!/usr/bin/env python3
"""Build the real lumbar-Spine region cache from the SPIDER dataset.

Source: van der Graaf et al., "SPIDER - Lumbar spine segmentation in MR images:
a dataset and a public benchmark", Zenodo (https://zenodo.org/records/10159290),
CC-BY-4.0 — sagittal lumbar T1/T2 MRI with per-structure masks: vertebrae
(labels 1-25), the spinal canal (100) and the intervertebral discs (200+N).

This processes one subject's T2 study into the same kind of cache the other body
regions use: a uint8 tissue-label atlas + a ~1.0 multiplicative real-MRI texture
field, resampled to (near-)isotropic so axial/coronal reformats stay sensible.
Vertebrae become cortical shell + marrow, discs map to the Cartilage/Disc label,
the canal carries CSF with the cord down its centre, and the surrounding soft
tissue is classified from the real T2 intensity (fat / muscle / skin) via
k-means. Optionally, a multilabel volume from an offline TotalSegmentator
``total_mr`` run densifies the fill with real organ / vessel / paraspinal-muscle
/ sacrum masks (SPIDER's gold vertebra/disc/canal masks always take priority).

The 3.7 GB image archive is never downloaded whole: a seekable HTTP file lets
``zipfile`` pull just the one subject's image via range requests.

    python scripts/build_spider_spine.py [subject]   # default subject 1
writes data/spider_spine/{atlas,texture}.npy (only the small cache is committed).
"""
import io
import json
import os
import sys
import urllib.request
import zipfile
import zlib

import numpy as np
from scipy.ndimage import (binary_closing, binary_erosion, binary_fill_holes,
                           gaussian_filter, label, zoom)

# tissue_db labels
BG, FLUID, FAT, SKIN, MUSCLE = 0, 1, 4, 5, 6
BLOOD = 11
BONE_CORTICAL, MARROW, CARTILAGE, CORD = 13, 14, 15, 16

OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "spider_spine")
ZENODO = "https://zenodo.org/records/10159290/files/"
ISO_MM = 1.3            # target isotropic voxel (mm) for the resampled cache


class _HttpFile(io.RawIOBase):
    """Seekable read-only file over HTTP range requests, so zipfile can extract a
    single member from the huge remote images.zip without fetching it all."""

    def __init__(self, url: str) -> None:
        self.url = url
        self.pos = 0
        with urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=60) as r:
            self.size = int(r.headers["Content-Length"])

    def seekable(self) -> bool:
        return True

    def readable(self) -> bool:
        return True

    def seek(self, off: int, whence: int = 0) -> int:
        self.pos = off if whence == 0 else (self.pos + off if whence == 1 else self.size + off)
        return self.pos

    def tell(self) -> int:
        return self.pos

    def read(self, n: int = -1) -> bytes:
        if n is None or n < 0:
            n = self.size - self.pos
        if n <= 0:
            return b""
        end = min(self.pos + n, self.size) - 1
        req = urllib.request.Request(self.url, headers={"Range": f"bytes={self.pos}-{end}"})
        data = urllib.request.urlopen(req, timeout=180).read()
        self.pos += len(data)
        return data


def _extract(zip_name: str, member: str) -> bytes:
    return zipfile.ZipFile(_HttpFile(ZENODO + zip_name)).open(member).read()


def _read_mha(blob: bytes) -> "tuple[np.ndarray, list[float]]":
    """Minimal MetaImage reader (handles zlib CompressedData). Returns the volume
    in (axis0, axis1, axis2) order matching DimSize reversed, + ElementSpacing."""
    end = blob.index(b"\n", blob.index(b"ElementDataFile")) + 1
    meta = {}
    for line in blob[:end].decode("ascii", "ignore").splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            meta[k.strip()] = v.strip()
    dims = [int(x) for x in meta["DimSize"].split()]
    spacing = [float(x) for x in meta["ElementSpacing"].split()]
    dt = {"MET_SHORT": np.int16, "MET_USHORT": np.uint16, "MET_UCHAR": np.uint8,
          "MET_FLOAT": np.float32, "MET_DOUBLE": np.float64, "MET_INT": np.int32}[meta["ElementType"]]
    raw = blob[end:]
    if meta.get("CompressedData", "False") == "True":
        raw = zlib.decompress(raw)
    vol = np.frombuffer(raw, dtype=dt).reshape(dims[::-1])
    return vol, spacing[::-1]


def _kmeans1d(x: np.ndarray, k: int = 3, iters: int = 25) -> "tuple[np.ndarray, np.ndarray]":
    """Tiny 1-D k-means (no sklearn dep). Returns (assignments, sorted centres);
    cluster ids are ordered dark -> bright."""
    c = np.percentile(x, np.linspace(15, 90, k)).astype(np.float64)
    a = np.zeros(x.shape, dtype=np.int64)
    for _ in range(iters):
        a = np.abs(x[:, None] - c[None, :]).argmin(1)
        for j in range(k):
            if (a == j).any():
                c[j] = x[a == j].mean()
    order = np.argsort(c)
    return np.argsort(order)[a], c[order]


def _ts_overlay(ts_path: str, ts_labels: str, native_shape: tuple, zf: tuple) -> np.ndarray:
    """Load a TotalSegmentator --ml multilabel volume (run offline on the same
    native-grid T2 study) and return it as a tissue_db-label volume on the
    resampled+flipped grid build() works on.

    The class-name -> tissue-label mapping is nifti_region._SEG_FILE_TO_MR (the
    body-region source of truth); TS class names match its keys.
    """
    import nibabel as nib
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "src"))
    from nifti_region import _SEG_FILE_TO_MR

    with open(ts_labels) as f:
        id_to_name = {int(k): v for k, v in json.load(f).items()}
    ts_xyz = np.asarray(nib.load(ts_path).dataobj).astype(np.uint8)
    ts = np.transpose(ts_xyz, (2, 1, 0))            # back to the MHA (Z, Y, X) grid
    if ts.shape != native_shape:
        raise ValueError(f"TS grid {ts.shape} != study grid {native_shape}")
    ts = zoom(ts, zf, order=0)[:, ::-1]             # same resample + A-P flip as msk

    out = np.zeros(ts.shape, dtype=np.uint8)
    for ts_id, name in id_to_name.items():
        mr = _SEG_FILE_TO_MR.get(name)
        if mr is None or not (ts == ts_id).any():
            continue
        out[ts == ts_id] = mr
    # TS bone (sacrum, hips...) gets the same cortical-shell + marrow treatment
    # the vertebrae get, so it doesn't render as a solid dark block.
    ts_bone = out == BONE_CORTICAL
    out[binary_erosion(ts_bone, iterations=1)] = MARROW
    return out


def build(subject: int, ts_path: "str | None" = None,
          ts_labels: "str | None" = None) -> None:
    img, sp = _read_mha(_extract("images.zip", f"images/{subject}_t2.mha"))
    msk, _ = _read_mha(_extract("masks.zip", f"masks/{subject}_t2.mha"))
    img = img.astype(np.float32)
    native_shape = msk.shape

    # Resample to isotropic ISO_MM so reformats aren't distorted by the thick
    # sagittal slice spacing (image: linear; mask: nearest to keep integer labels).
    zf = tuple(s / ISO_MM for s in sp)
    img = zoom(img, zf, order=1)
    msk = zoom(msk, zf, order=0)

    # Orient to the body-atlas convention (axis0↑=Superior, axis1↑=Anterior,
    # axis2↑=Right). Measured from this study's anatomy: vertebrae enlarge toward
    # low axis0 (L5 inferior), so axis0↑ is ALREADY superior — leave it. The canal
    # (posterior) sits at high axis1, i.e. axis1↑=Posterior, so flip axis1 to put
    # the anterior vertebral bodies at high axis1 like every other region.
    img, msk = img[:, ::-1], msk[:, ::-1]

    v = img / max(np.percentile(img[img > 0], 99), 1e-3)
    v = np.clip(v, 0, 1.6)

    vert = (msk >= 1) & (msk <= 99)
    disc = (msk >= 200)
    canal = (msk == 100)

    # Body mask: the segmented structures plus the bright/mid soft tissue.
    body = gaussian_filter(v, 1.0) > 0.06
    body = binary_closing(body, iterations=2)
    body = np.stack([binary_fill_holes(s) for s in body]) | vert | disc | canal
    lbl, n = label(body)
    if n > 1:
        body = lbl == (1 + int(np.argmax(np.bincount(lbl.flat)[1:])))

    lab = np.zeros(v.shape, dtype=np.uint8)
    soft = body & ~(vert | disc | canal)
    # Residual soft tissue: 3-cluster k-means on the T2 intensity instead of a
    # single percentile threshold (which classified 2/3 of the body as muscle).
    # Dark + mid clusters -> muscle, bright cluster -> fat; the very bright
    # tail stays fluid. Organs/vessels are then overlaid from real TS masks.
    if soft.any():
        assign, _ = _kmeans1d(v[soft].astype(np.float64))
        soft_lab = np.where(assign >= 2, FAT, MUSCLE).astype(np.uint8)
        p97 = np.percentile(v[soft], 97)
        soft_lab[v[soft] > p97] = FLUID               # bright fluid pockets
        lab[soft] = soft_lab
    # Real organ/vessel/muscle/bone masks from an offline TotalSegmentator
    # total_mr run (aorta/IVC -> Blood, kidney/liver/... -> organ labels,
    # autochthon/iliopsoas -> Muscle, sacrum -> bone shell + marrow).
    ts = None
    if ts_path is not None:
        ts = _ts_overlay(ts_path, ts_labels, native_shape, zf)
        lab[ts > 0] = ts[ts > 0]
    # SPIDER's gold masks always win where they overlap the TS estimates.
    # Intervertebral discs (bright on T2) and vertebrae (cortical rim + marrow).
    lab[disc] = CARTILAGE
    lab[vert] = BONE_CORTICAL
    lab[binary_erosion(vert, iterations=1)] = MARROW
    # Spinal canal: CSF with the cord down its centre — the real TS cord mask
    # where available, the erosion approximation otherwise.
    lab[canal] = FLUID
    ts_cord = (ts == CORD) & canal if ts is not None else np.zeros_like(canal)
    if ts_cord.sum() > 500:
        lab[ts_cord] = CORD
    else:
        lab[binary_erosion(canal, iterations=2)] = CORD
    # skin rind
    lab[body & ~binary_erosion(body, iterations=1)] = SKIN
    lab[~body] = BG
    # Dark bowel content (from the TS colon/bowel overlay) is gas — label it 12
    # so susceptibility and rendering treat it as air, like the body regions.
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "src"))
    from nifti_region import _mark_bowel_gas, _normalize_texture_per_label
    lab = _mark_bowel_gas(lab, v)

    # Crop to the body bounding box (a little padding).
    zz, yy, xx = np.where(body)
    pad = 4
    sl = tuple(slice(max(0, a.min() - pad), min(s, a.max() + 1 + pad))
               for a, s in zip((zz, yy, xx), body.shape, strict=True))
    lab, v, body = lab[sl], v[sl], body[sl]

    # Texture = the real MR intensity, lightly denoised (the raw study is noisy)
    # and normalised to a ~1.0 multiplicative field, so tissues keep parenchymal
    # detail without salt-and-pepper speckle.
    vs = gaussian_filter(v, 0.7)
    tex = np.ones(v.shape, dtype=np.float32)
    mean = float(vs[body].mean())
    tex[body] = np.clip(vs[body] / max(mean, 1e-3), 0.5, 1.7)
    # Per-label normalisation: texture keeps only intra-tissue detail; the
    # source study's own contrast no longer leaks into every rendered sequence.
    tex = _normalize_texture_per_label(tex, lab)

    os.makedirs(OUT_DIR, exist_ok=True)
    np.save(os.path.join(OUT_DIR, "atlas.npy"), lab)
    np.save(os.path.join(OUT_DIR, "texture.npy"), tex.astype(np.float16))
    print(f"wrote {OUT_DIR}: atlas {lab.shape} {lab.nbytes // 1024} KB, "
          f"labels {sorted(np.unique(lab).tolist())}")


if __name__ == "__main__":
    #   python scripts/build_spider_spine.py [subject] [ts_multilabel.nii.gz ts_labels.json]
    # The optional TS pair comes from an offline TotalSegmentator run:
    #   TotalSegmentator -i <subject_t2.nii.gz> -o ts.nii.gz --task total_mr --ml
    build(int(sys.argv[1]) if len(sys.argv) > 1 else 1,
          ts_path=sys.argv[2] if len(sys.argv) > 2 else None,
          ts_labels=sys.argv[3] if len(sys.argv) > 3 else None)
