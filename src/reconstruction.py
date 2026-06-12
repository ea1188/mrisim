"""3-D reconstruction helpers — MPR, MIP and oblique reformats from an acquired
slab (the Simulator's ``_recon3d`` block, a raw ``(Z, Y, X)`` recon sub-volume).

Pure and Qt-free: both the desktop and the browser build feed the same acquired
block through these and render the result, so the reconstruction maths lives in
one tested place. All functions take and return plain numpy arrays.
"""
from __future__ import annotations

import numpy as np

from phantom3d import get_slice

# Display plane -> volume axis (matches get_slice / Simulator._THROUGH_AXIS).
THROUGH_AXIS = {"axial": 0, "coronal": 1, "sagittal": 2}


def _clip(idx: int, n: int) -> int:
    return int(np.clip(int(idx), 0, n - 1))


def mpr_triplanar(block: np.ndarray,
                  center: tuple[int, int, int]) -> dict[str, np.ndarray]:
    """Three orthogonal reformats through ``center`` (cz, cy, cx) of the block.

    Returns ``{"axial", "coronal", "sagittal"}`` 2-D arrays sliced with the same
    display convention as the live viewport (``get_slice``), so a crosshair at
    ``center`` lines up across the three panels.
    """
    cz = _clip(center[0], block.shape[0])
    cy = _clip(center[1], block.shape[1])
    cx = _clip(center[2], block.shape[2])
    return {
        "axial": get_slice(block, "axial", cz),
        "coronal": get_slice(block, "coronal", cy),
        "sagittal": get_slice(block, "sagittal", cx),
    }


def thick_slab_mip(block: np.ndarray, plane: str, center: int,
                   thickness: int) -> np.ndarray:
    """Maximum-intensity projection over ``thickness`` partitions centred on
    ``center`` along ``plane``'s through-axis — the brightest voxel along each
    ray. ``thickness`` is clamped to the block; a thickness of 1 is a plain slice.
    """
    ax = THROUGH_AXIS[plane]
    n = block.shape[ax]
    c = _clip(center, n)
    half = max(1, int(thickness)) // 2
    lo, hi = max(0, c - half), min(n, c + half + 1)
    sub = block[tuple(slice(lo, hi) if a == ax else slice(None) for a in range(3))]
    proj = sub.max(axis=ax)
    if plane == "sagittal":           # match get_slice's sagittal flip
        proj = np.fliplr(proj)
    return np.ascontiguousarray(proj)


def rotating_mip(block: np.ndarray, azimuth_deg: float = 0.0,
                 elevation_deg: float = 0.0) -> np.ndarray:
    """Full-volume MIP viewed from a rotation (azimuth about S/I, elevation about
    L/R), projecting along the (rotated) A/P axis. Reuses the angiography MIP so
    the angiogram and a slab MIP rotate identically. Returns a 2-D (Z, X) image.
    """
    from angiography import rotating_mip as _rotating_mip
    return _rotating_mip(np.asarray(block, dtype=float), azimuth_deg, elevation_deg)


def oblique_mpr(block: np.ndarray, center: tuple[float, float, float],
                tilt_deg: float = 0.0, rot_deg: float = 0.0,
                base: str = "axial",
                shape: tuple[int, int] | None = None) -> np.ndarray:
    """Reformat an arbitrary tilted plane through ``center`` of the block by
    interpolation — tilt/rot angle the plane off the ``base`` orthogonal. Reuses
    ``oblique.oblique_plane`` (the same sampler the oblique acquisition uses).
    """
    from oblique import oblique_plane, plane_from_angles
    _normal, row_vec, col_vec = plane_from_angles(base, tilt_deg=tilt_deg, rot_deg=rot_deg)
    return oblique_plane(np.asarray(block, dtype=float), row_vec, col_vec,
                         center, shape=shape, order=1)
