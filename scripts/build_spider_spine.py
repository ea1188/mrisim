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
tissue is classified from the real T2 intensity (fat / muscle / skin).

The 3.7 GB image archive is never downloaded whole: a seekable HTTP file lets
``zipfile`` pull just the one subject's image via range requests.

    python scripts/build_spider_spine.py [subject]   # default subject 1
writes data/spider_spine/{atlas,texture}.npy (only the small cache is committed).
"""
import io
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


def build(subject: int) -> None:
    img, sp = _read_mha(_extract("images.zip", f"images/{subject}_t2.mha"))
    msk, _ = _read_mha(_extract("masks.zip", f"masks/{subject}_t2.mha"))
    img = img.astype(np.float32)

    # Resample to isotropic ISO_MM so reformats aren't distorted by the thick
    # sagittal slice spacing (image: linear; mask: nearest to keep integer labels).
    zf = tuple(s / ISO_MM for s in sp)
    img = zoom(img, zf, order=1)
    msk = zoom(msk, zf, order=0)

    # Orient to the body-atlas convention (axis0↑=Superior, axis1↑=Anterior,
    # axis2↑=Right); SPIDER T2 comes in head-first sagittal — flip axis0 so the
    # vertebrae run inferior→superior like every other region.
    img, msk = img[::-1], msk[::-1]

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
    rim = body & ~binary_erosion(body, iterations=5)
    p60, p85 = np.percentile(v[soft], (60, 85)) if soft.any() else (0.5, 0.8)
    lab[soft] = MUSCLE
    lab[soft & (v > p60) & rim] = FAT                 # subcutaneous / epidural fat
    lab[soft & (v > p85)] = FLUID                     # bright fluid pockets
    # Intervertebral discs (bright on T2) and vertebrae (cortical rim + marrow).
    lab[disc] = CARTILAGE
    lab[vert] = BONE_CORTICAL
    lab[binary_erosion(vert, iterations=1)] = MARROW
    # Spinal canal: CSF with the cord running down its centre.
    lab[canal] = FLUID
    lab[binary_erosion(canal, iterations=2)] = CORD
    # skin rind
    lab[body & ~binary_erosion(body, iterations=1)] = SKIN
    lab[~body] = BG

    # Crop to the body bounding box (a little padding).
    zz, yy, xx = np.where(body)
    pad = 4
    sl = tuple(slice(max(0, a.min() - pad), min(s, a.max() + 1 + pad))
               for a, s in zip((zz, yy, xx), body.shape, strict=True))
    lab, v, body = lab[sl], v[sl], body[sl]

    tex = np.ones(v.shape, dtype=np.float32)
    mean = float(v[body].mean())
    tex[body] = np.clip(v[body] / max(mean, 1e-3), 0.4, 1.8)

    os.makedirs(OUT_DIR, exist_ok=True)
    np.save(os.path.join(OUT_DIR, "atlas.npy"), lab)
    np.save(os.path.join(OUT_DIR, "texture.npy"), tex.astype(np.float16))
    print(f"wrote {OUT_DIR}: atlas {lab.shape} {lab.nbytes // 1024} KB, "
          f"labels {sorted(np.unique(lab).tolist())}")


if __name__ == "__main__":
    build(int(sys.argv[1]) if len(sys.argv) > 1 else 1)
