#!/usr/bin/env python3
"""Assemble the static browser bundle for the Pyodide build.

Zips every ``src/*.py`` module into ``web/mrisim_src.zip`` (Pyodide unpacks it to
``/src`` and adds that to ``sys.path``) and copies the bundled BrainWeb phantom
into ``web/data/``. Everything else under ``web/`` (index.html, app.js, styles)
is checked in. Run from the repo root:  ``python build_web.py``.
"""
import glob
import os
import shutil
import zipfile

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ROOT, "src")
WEB = os.path.join(ROOT, "web")
BRAIN_NPY = "brainweb_sub04_anat.npy"

# Real segmented body regions (TotalSegmentator MRI) → the subject whose cached
# atlas/texture the desktop uses. Bundled into the web build so the browser shows
# the same accurate anatomy as the desktop (lazy-fetched per region).
_REGION_SUBJECT = {"Abdomen": "s0246", "Spine": "s0267",
                   "Pelvis": "s0187", "Torso": "s0250"}


def build() -> None:
    os.makedirs(WEB, exist_ok=True)
    os.makedirs(os.path.join(WEB, "data"), exist_ok=True)

    # 1. Zip the Python engine. Flat layout so Pyodide can `sys.path.insert('/src')`.
    zip_path = os.path.join(WEB, "mrisim_src.zip")
    modules = sorted(f for f in os.listdir(SRC) if f.endswith(".py"))
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in modules:
            zf.write(os.path.join(SRC, name), name)
    print(f"wrote {zip_path}  ({len(modules)} modules)")

    # 2. Copy the bundled real brain phantom (the only data file the web build
    #    fetches; body regions are generated in-Python with no download).
    src_npy = os.path.join(ROOT, "data", BRAIN_NPY)
    dst_npy = os.path.join(WEB, "data", BRAIN_NPY)
    if os.path.exists(src_npy):
        shutil.copy2(src_npy, dst_npy)
        print(f"copied {BRAIN_NPY}  ({os.path.getsize(dst_npy) // 1024} KB)")
    else:
        print(f"WARNING: {src_npy} not found — the web build will fall back to a "
              f"synthetic brain.")

    # 3. Copy the app logo (shared with the desktop header).
    src_logo = os.path.join(ROOT, "data", "logo.png")
    if os.path.exists(src_logo):
        shutil.copy2(src_logo, os.path.join(WEB, "logo.png"))
        print("copied logo.png")

    # 4. Bundle the real body-region atlases (lazy-fetched per region in-browser).
    _bundle_regions()


def _bundle_regions() -> None:
    """Copy each real region's cached atlas (uint8 labels) + texture (the ~1.0
    multiplicative MR-detail field, stored float16 to halve the download) into
    web/data/regions/. Skips a region whose cache is absent — the browser then
    falls back to the synthetic phantom."""
    import numpy as np
    out = os.path.join(WEB, "data", "regions")
    os.makedirs(out, exist_ok=True)
    for region, subj in _REGION_SUBJECT.items():
        atlas = glob.glob(os.path.join(ROOT, "data", "Totalsegmentator*",
                                       subj, "atlas_iso_adapt_256.npy"))
        if not atlas:
            print(f"  region {region}: no real atlas cache — browser uses synthetic")
            continue
        vol = np.load(atlas[0]).astype(np.uint8)
        np.save(os.path.join(out, f"{region}_atlas.npy"), vol)
        tex = glob.glob(os.path.join(ROOT, "data", "Totalsegmentator*",
                                     subj, "texture_iso_adapt_256.npy"))
        if tex:
            np.save(os.path.join(out, f"{region}_texture.npy"),
                    np.load(tex[0]).astype(np.float16))
        mb = sum(os.path.getsize(os.path.join(out, f"{region}_{k}.npy"))
                 for k in ("atlas", "texture")
                 if os.path.exists(os.path.join(out, f"{region}_{k}.npy"))) // (1024 * 1024)
        print(f"  region {region}: bundled real atlas {vol.shape} (~{mb} MB)")


if __name__ == "__main__":
    build()
