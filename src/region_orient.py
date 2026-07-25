"""Small orientation corrections applied to real body atlases at load time.

Some bundled TotalSegmentator / SPIDER subjects sit slightly rotated relative to
the simulator's (S/I, A/P, L/R) = (axis0, axis1, axis2) convention, so a plane
that should read straight comes out tilted. These are pure geometric rotations
(label-preserving, ``order=0`` for the segmentation, linear for the texture)
applied identically to the label volume and its texture wherever a real atlas is
loaded — the browser (``web_adapter``) and the desktop (``body_phantoms``).

Only ``numpy`` + ``scipy`` are used, so this is safe to import under Pyodide
(no ``nibabel``).
"""
from __future__ import annotations

import numpy as np

# Per-region correction: (degrees, plane axes). The angle is measured from the
# atlas data (e.g. the spine's vertebral column leans 16.8° in the coronal plane,
# i.e. the (S/I, L/R) = (0, 2) plane) and applied before the L/R display mirror.
_TILT: dict[str, tuple[float, tuple[int, int]]] = {
    # SPIDER lumbar spine (s0267): column drifts sideways as it descends; rotate
    # about the A/P axis to stand it vertical.
    "Spine": (-16.8, (0, 2)),
}


def straighten(name: str, arr: "np.ndarray | None", order: int) -> "np.ndarray | None":
    """Return ``arr`` rotated to correct *name*'s known tilt, or unchanged.

    ``order`` is the spline order for the rotation: 0 for a label volume (keeps
    labels intact), 1 for a continuous texture field.
    """
    if arr is None or name not in _TILT:
        return arr
    from scipy.ndimage import rotate
    deg, axes = _TILT[name]
    return np.ascontiguousarray(
        rotate(arr, deg, axes=axes, order=order, reshape=False, mode="constant", cval=0)
    )
