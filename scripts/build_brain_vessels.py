"""Precompute the brain TOF vessel tree → data/brain_vessels_idx.npy.

``add_vessels_3d`` paints a deterministic vascular tree (label 11) into the
BrainWeb phantom, but takes ~minute of CPU. The browser needs it for MR
angiography and SWI, where a 60 s stall is painful. The tree is *deterministic*
(fixed RNG seed) and brain-specific, so we precompute it once here and ship the
result: the indices of the voxels the vessel tree changes. At runtime the
adapter rebuilds the vessel volume with ``brain.copy(); flat[idx] = 11`` in
under a millisecond (see web_adapter._ensure_vessels).

Run: ``PYTHONPATH=src python scripts/build_brain_vessels.py``
A test (test_web_adapter) guards that this file still matches add_vessels_3d.
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import brainweb_loader  # noqa: E402
from phantom3d_extended import add_vessels_3d  # noqa: E402

VESSEL_LABEL = 11
OUT = os.path.join(os.path.dirname(__file__), "..", "data", "brain_vessels_idx.npy")


def main() -> None:
    brain = brainweb_loader.load_brainweb_phantom(4)
    with_vessels = add_vessels_3d(brain)
    idx = np.flatnonzero(with_vessels != brain).astype(np.uint32)
    # Sanity: every changed voxel must be a vessel (label 11).
    assert np.all(with_vessels.flat[idx] == VESSEL_LABEL)
    np.save(OUT, idx)
    print(f"wrote {os.path.relpath(OUT)}: {idx.size} vessel voxels, "
          f"{os.path.getsize(OUT) // 1024} KB  (brain shape {brain.shape})")


if __name__ == "__main__":
    main()
