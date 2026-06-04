#!/usr/bin/env python3
"""Assemble the static browser bundle for the Pyodide build.

Zips every ``src/*.py`` module into ``web/mrisim_src.zip`` (Pyodide unpacks it to
``/src`` and adds that to ``sys.path``) and copies the bundled BrainWeb phantom
into ``web/data/``. Everything else under ``web/`` (index.html, app.js, styles)
is checked in. Run from the repo root:  ``python build_web.py``.
"""
import os
import shutil
import zipfile

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ROOT, "src")
WEB = os.path.join(ROOT, "web")
BRAIN_NPY = "brainweb_sub04_anat.npy"


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


if __name__ == "__main__":
    build()
