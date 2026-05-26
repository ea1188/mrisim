"""
oblique.py — True double-oblique slice prescription via direct plane sampling.

Two tilt angles are composed into a single rotation matrix which defines the
sampled plane's row and column unit vectors.  scipy.ndimage.map_coordinates
then samples the volume at those coordinates in one pass — the volume is never
rotated or resampled as a whole.

Volume index convention (matches phantom3d / scan_geometry):
    axis 0 = Z  (superior → inferior)
    axis 1 = Y  (anterior → posterior)
    axis 2 = X  (right → left)
"""
from __future__ import annotations
import numpy as np
from scipy.ndimage import map_coordinates


# ---------------------------------------------------------------------------
# Rotation helpers
# ---------------------------------------------------------------------------

def _rot_matrix(axis: np.ndarray | list[float], angle_rad: float) -> np.ndarray:
    """3×3 Rodrigues rotation matrix: rotate by angle_rad around axis."""
    k = np.asarray(axis, dtype=float)
    k = k / np.linalg.norm(k)
    K = np.array([[ 0.0,  -k[2],  k[1]],
                  [ k[2],  0.0,  -k[0]],
                  [-k[1],  k[0],  0.0 ]])
    return np.eye(3) + np.sin(angle_rad) * K + (1.0 - np.cos(angle_rad)) * (K @ K)


# ---------------------------------------------------------------------------
# Base orientation frames  (normal, row_vec, col_vec) in (Z, Y, X) space
# ---------------------------------------------------------------------------

_BASE_FRAMES = {
    "axial":    (np.array([1., 0., 0.]),
                 np.array([0., 1., 0.]),
                 np.array([0., 0., 1.])),
    "coronal":  (np.array([0., 1., 0.]),
                 np.array([1., 0., 0.]),
                 np.array([0., 0., 1.])),
    # col_vec = +Y so coords increase naturally; GUI can flip display if desired
    "sagittal": (np.array([0., 0., 1.]),
                 np.array([1., 0., 0.]),
                 np.array([0., 1., 0.])),
}


# ---------------------------------------------------------------------------
# Plane orientation
# ---------------------------------------------------------------------------

def plane_from_angles(
    base: str = "axial",
    tilt_deg: float = 0.0,
    rot_deg: float = 0.0,
    rot_inplane_deg: float = 0.0,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Compose three rotation angles on top of a base orientation.

    tilt_deg       : rotation around col_vec  — tips the plane forward / back
    rot_deg        : rotation around row_vec  — rotates the plane left / right
    rot_inplane_deg: rotation around normal   — spins the FOV in-place without
                     changing which anatomy the plane cuts through

    Applied in the order tilt → rot → rot_inplane, so each angle is defined
    relative to the result of the previous one.

    Returns (normal, row_vec, col_vec) as unit float64 arrays in (Z, Y, X) space.
    The three vectors are mutually orthogonal; the frame is right- or left-handed
    depending on the base orientation convention.
    """
    if base not in _BASE_FRAMES:
        raise ValueError(f"base must be one of {list(_BASE_FRAMES)}; got {base!r}")
    n, r, c = [v.copy() for v in _BASE_FRAMES[base]]

    if tilt_deg:
        R = _rot_matrix(c, np.radians(tilt_deg))
        n = R @ n
        r = R @ r

    if rot_deg:
        R = _rot_matrix(r, np.radians(rot_deg))
        n = R @ n
        c = R @ c

    if rot_inplane_deg:
        # Rotating around n leaves n fixed; only r and c spin.
        R = _rot_matrix(n, np.radians(rot_inplane_deg))
        r = R @ r
        c = R @ c

    return (n / np.linalg.norm(n),
            r / np.linalg.norm(r),
            c / np.linalg.norm(c))


# ---------------------------------------------------------------------------
# Direct plane sampler
# ---------------------------------------------------------------------------

def oblique_plane(
    vol: np.ndarray,
    row_vec: np.ndarray,
    col_vec: np.ndarray,
    center: np.ndarray | tuple[float, float, float],
    shape: tuple[int, int] | None = None,
    order: int = 0,
    voxel_size: tuple[float, float, float] = (1.0, 1.0, 1.0),
    pixel_size_mm: float | None = None,
) -> np.ndarray:
    """
    Sample an oblique 2D plane from vol by direct interpolation.

    vol           : 3-D ndarray (Z, Y, X)
    row_vec       : unit vector along display rows, in physical (Z, Y, X) space
    col_vec       : unit vector along display cols, in physical (Z, Y, X) space
    center        : (Z, Y, X) voxel-index coordinate of the plane centre
    shape         : (rows, cols) output size; defaults to (max_dim, max_dim)
    order         : 0 = nearest-neighbour (preserves integer labels)
                    1 = trilinear (for floating-point signal images)
    voxel_size    : (sz, sy, sx) physical size of one voxel in mm along each axis.
                    Corrects for anisotropy so that tilt angles are physically accurate.
    pixel_size_mm : physical size of one output pixel in mm.
                    Defaults to min(voxel_size) so the finest voxel dimension sets
                    the output resolution.

    Returns 2-D array with the same dtype as vol.
    Voxels that map outside the volume boundaries are filled with 0.
    """
    if shape is None:
        d = max(vol.shape)
        shape = (d, d)
    rows, cols = int(shape[0]), int(shape[1])

    vox = np.asarray(voxel_size, dtype=float)
    if pixel_size_mm is None:
        pixel_size_mm = float(np.min(vox))

    ri = np.arange(rows, dtype=float) - rows / 2.0
    ci = np.arange(cols, dtype=float) - cols / 2.0
    rr, cc = np.meshgrid(ri, ci, indexing='ij')  # (rows, cols)

    rv = np.asarray(row_vec, dtype=float)
    cv = np.asarray(col_vec, dtype=float)
    ctr = np.asarray(center, dtype=float)

    # Each output pixel represents pixel_size_mm of physical displacement.
    # Converting mm → voxel indices requires dividing by voxel_size per axis.
    coords = np.empty((3, rows, cols), dtype=float)
    for ax in range(3):
        coords[ax] = ctr[ax] + (rr * rv[ax] + cc * cv[ax]) * pixel_size_mm / vox[ax]

    return map_coordinates(
        vol.astype(float), coords, order=order, mode='constant', cval=0.0
    ).astype(vol.dtype)


# ---------------------------------------------------------------------------
# Multi-slice slab
# ---------------------------------------------------------------------------

def oblique_slab(
    vol: np.ndarray,
    normal: np.ndarray,
    row_vec: np.ndarray,
    col_vec: np.ndarray,
    center: np.ndarray | tuple[float, float, float],
    n_slices: int = 1,
    thickness_mm: float = 5.0,
    gap_mm: float = 0.0,
    shape: tuple[int, int] | None = None,
    order: int = 0,
    voxel_size: tuple[float, float, float] = (1.0, 1.0, 1.0),
    pixel_size_mm: float | None = None,
) -> np.ndarray:
    """
    Sample a stack of N parallel oblique slices (a prescribed slab).

    Slices are evenly distributed about `center` along the normal direction,
    separated by (thickness_mm + gap_mm) in physical space.  The centre of
    slice i (0-indexed) is displaced from `center` by:

        offset_mm = (i − (n_slices−1)/2) × (thickness_mm + gap_mm)

    converted to voxel-index space per axis via voxel_size.

    Parameters
    ----------
    vol           : 3-D ndarray (Z, Y, X)
    normal        : unit normal of the plane family, physical (Z, Y, X) space
    row_vec       : unit vector along display rows, physical (Z, Y, X) space
    col_vec       : unit vector along display cols, physical (Z, Y, X) space
    center        : (Z, Y, X) voxel-index coordinate of the slab centre
    n_slices      : number of parallel slices
    thickness_mm  : physical slice thickness in mm
    gap_mm        : physical gap between adjacent slices in mm
    shape         : (rows, cols) in-plane output size per slice
    order         : 0 = nearest-neighbour, 1 = trilinear
    voxel_size    : (sz, sy, sx) mm per voxel
    pixel_size_mm : output pixel size in mm; defaults to min(voxel_size)

    Returns
    -------
    ndarray of shape (n_slices, rows, cols) with the same dtype as vol.
    """
    n = np.asarray(normal, dtype=float)
    n = n / np.linalg.norm(n)
    vox = np.asarray(voxel_size, dtype=float)
    ctr = np.asarray(center, dtype=float)
    step_mm = thickness_mm + gap_mm

    slices = []
    for i in range(int(n_slices)):
        offset_mm = (i - (n_slices - 1) / 2.0) * step_mm
        # Physical offset along normal → voxel-index displacement
        center_i = ctr + offset_mm * n / vox
        slices.append(
            oblique_plane(vol, row_vec, col_vec, center_i,
                          shape=shape, order=order,
                          voxel_size=voxel_size, pixel_size_mm=pixel_size_mm)
        )

    return np.stack(slices, axis=0)


# ---------------------------------------------------------------------------
# MRI signal rendering
# ---------------------------------------------------------------------------

def _render_label_map(
    label_map: np.ndarray,
    TR: float,
    TE: float,
    sequence: str,
    TI: float | None,
    flip_angle: float,
    tissue_props: dict,
) -> np.ndarray:
    """Apply MRI signal equations to a 2D integer label map.

    Returns a 2D float64 image.  Labels absent from tissue_props are left at 0.
    """
    from signal_engine import (spin_echo_signal, gradient_echo_signal,
                                inversion_recovery_signal)
    image = np.zeros(label_map.shape, dtype=float)
    ti = TI if TI is not None else 150.0
    for label, props in tissue_props.items():
        mask = label_map == label
        if not np.any(mask):
            continue
        if sequence == "GRE":
            sig = gradient_echo_signal(
                props["T1"], props["T2star"], props["PD"], TR, TE, flip_angle)
        elif sequence == "IR":
            sig = inversion_recovery_signal(
                props["T1"], props["T2"], props["PD"], TR, TE, ti)
        else:  # SE and fallback
            sig = spin_echo_signal(props["T1"], props["T2"], props["PD"], TR, TE)
        image[mask] = sig
    return image


def simulate_oblique(
    vol: np.ndarray,
    row_vec: np.ndarray,
    col_vec: np.ndarray,
    center: np.ndarray | tuple[float, float, float],
    TR: float = 500.0,
    TE: float = 15.0,
    sequence: str = "SE",
    TI: float | None = None,
    flip_angle: float = 90.0,
    shape: tuple[int, int] | None = None,
    voxel_size: tuple[float, float, float] = (1.0, 1.0, 1.0),
    pixel_size_mm: float | None = None,
    tissue_props: dict | None = None,
) -> np.ndarray:
    """
    Sample one oblique plane from vol and render MRI signal.

    vol          : 3-D integer label array (Z, Y, X)
    row_vec      : unit vector along display rows, physical (Z, Y, X) space
    col_vec      : unit vector along display cols, physical (Z, Y, X) space
    center       : (Z, Y, X) voxel-index coordinate
    TR / TE      : repetition / echo time in ms
    sequence     : 'SE' (default), 'GRE', or 'IR'
    TI           : inversion time in ms (IR only; default 150)
    flip_angle   : flip angle in degrees (GRE only; default 90)
    shape        : (rows, cols) output size; defaults to (max_dim, max_dim)
    voxel_size   : (sz, sy, sx) mm per voxel for anisotropy correction
    pixel_size_mm: output pixel size in mm; defaults to min(voxel_size)
    tissue_props : dict {label: {T1, T2, T2star, PD, ...}}.
                   Defaults to phantom3d.TISSUE_PROPERTIES_3D.

    Returns 2-D float64 image.
    """
    if tissue_props is None:
        from phantom3d import TISSUE_PROPERTIES_3D
        tissue_props = TISSUE_PROPERTIES_3D

    label_map = oblique_plane(vol, row_vec, col_vec, center,
                              shape=shape, order=0,
                              voxel_size=voxel_size, pixel_size_mm=pixel_size_mm)
    return _render_label_map(label_map, TR, TE, sequence, TI, flip_angle,
                             tissue_props)


def simulate_oblique_slab(
    vol: np.ndarray,
    normal: np.ndarray,
    row_vec: np.ndarray,
    col_vec: np.ndarray,
    center: np.ndarray | tuple[float, float, float],
    n_slices: int = 1,
    thickness_mm: float = 5.0,
    gap_mm: float = 0.0,
    TR: float = 500.0,
    TE: float = 15.0,
    sequence: str = "SE",
    TI: float | None = None,
    flip_angle: float = 90.0,
    shape: tuple[int, int] | None = None,
    voxel_size: tuple[float, float, float] = (1.0, 1.0, 1.0),
    pixel_size_mm: float | None = None,
    tissue_props: dict | None = None,
) -> np.ndarray:
    """
    Sample a slab of parallel oblique slices and render MRI signal for each.

    Geometry parameters (normal, row_vec, col_vec, center, n_slices,
    thickness_mm, gap_mm, shape, voxel_size, pixel_size_mm) are identical to
    oblique_slab.  MRI sequence parameters (TR, TE, sequence, TI, flip_angle,
    tissue_props) are passed through to simulate_oblique for every slice.

    Returns (n_slices, rows, cols) float64 array.
    """
    if tissue_props is None:
        from phantom3d import TISSUE_PROPERTIES_3D
        tissue_props = TISSUE_PROPERTIES_3D

    label_stack = oblique_slab(vol, normal, row_vec, col_vec, center,
                               n_slices=n_slices, thickness_mm=thickness_mm,
                               gap_mm=gap_mm, shape=shape, order=0,
                               voxel_size=voxel_size, pixel_size_mm=pixel_size_mm)

    return np.stack(
        [_render_label_map(label_stack[i], TR, TE, sequence, TI, flip_angle,
                           tissue_props)
         for i in range(int(n_slices))],
        axis=0,
    )


# ---------------------------------------------------------------------------
# Three-scout intersection lines
# ---------------------------------------------------------------------------

def _intersect_line(
    n: np.ndarray,
    center: np.ndarray,
    fixed_axis: int,
    fixed_val: float,
    row_axis: int,
    col_axis: int,
    row_len: int,
    col_len: int,
) -> tuple[float, float, float, float] | None:
    """
    Clip the intersection of the oblique plane with an axis-aligned scout plane.

    The oblique plane satisfies  n · (p − center) = 0.
    The scout plane fixes one volume axis at fixed_val.

    Returns (c0, r0, c1, r1) display-coordinate endpoints, or None if the
    oblique plane is parallel to the scout (no transecting line).
    """
    nr = n[row_axis]
    nc = n[col_axis]
    if abs(nr) < 1e-9 and abs(nc) < 1e-9:
        return None

    # Intersection equation:  nr*r + nc*c = rhs
    rhs = (nr * center[row_axis] + nc * center[col_axis]
           - n[fixed_axis] * (fixed_val - center[fixed_axis]))

    pts = []
    tol = 0.5  # half-pixel tolerance at image edges
    if abs(nc) > 1e-9:
        for r_val in (0.0, float(row_len - 1)):
            c_val = (rhs - nr * r_val) / nc
            if -tol <= c_val <= col_len - 1 + tol:
                pts.append((r_val, float(np.clip(c_val, 0, col_len - 1))))
    if abs(nr) > 1e-9:
        for c_val in (0.0, float(col_len - 1)):
            r_val = (rhs - nc * c_val) / nr
            if -tol <= r_val <= row_len - 1 + tol:
                pts.append((float(np.clip(r_val, 0, row_len - 1)), c_val))

    # Deduplicate within half a pixel
    unique: list[tuple[float, float]] = []
    for p in pts:
        if not any(abs(p[0] - q[0]) < 0.5 and abs(p[1] - q[1]) < 0.5
                   for q in unique):
            unique.append(p)
    if len(unique) < 2:
        return None

    (r0, c0), (r1, c1) = unique[0], unique[1]
    return (c0, r0, c1, r1)  # (x0, y0, x1, y1) in display / matplotlib coords


def scout_lines(
    vol_shape: tuple[int, int, int],
    normal: np.ndarray,
    center: np.ndarray | tuple[float, float, float],
    voxel_size: tuple[float, float, float] = (1.0, 1.0, 1.0),
) -> dict[str, tuple[float, float, float, float] | None]:
    """
    Intersect the oblique plane with the three axis-aligned scout planes.

    All three scouts pass through `center`, one per principal axis.

    vol_shape  : (nz, ny, nx)
    normal     : unit normal vector in physical (Z, Y, X) space
    center     : (Z, Y, X) voxel-index coordinate
    voxel_size : (sz, sy, sx) mm per voxel — scales the physical normal into
                 index space so that intersection lines reflect true physical geometry.

    Returns dict with keys 'axial', 'coronal', 'sagittal', each mapped to a
    (c0, r0, c1, r1) line-endpoint tuple in display coordinates, or None when
    the oblique plane is parallel to (or coincident with) that scout.
    """
    nz, ny, nx = vol_shape
    n_phys = np.asarray(normal, dtype=float)
    vox = np.asarray(voxel_size, dtype=float)
    ctr = np.asarray(center, dtype=float)

    # Convert physical-space normal to index-space: n_idx[ax] = n_phys[ax] * vox[ax].
    # The plane equation n·(p-center)=0 in physical space becomes
    # n_idx·(p_idx-center_idx)=0 in index space after this substitution.
    n = n_phys * vox

    return {
        # axial scout:    z fixed,  display rows = Y (axis 1), cols = X (axis 2)
        "axial":    _intersect_line(n, ctr, 0, ctr[0], 1, 2, ny, nx),
        # coronal scout:  y fixed,  display rows = Z (axis 0), cols = X (axis 2)
        "coronal":  _intersect_line(n, ctr, 1, ctr[1], 0, 2, nz, nx),
        # sagittal scout: x fixed,  display rows = Z (axis 0), cols = Y (axis 1)
        "sagittal": _intersect_line(n, ctr, 2, ctr[2], 0, 1, nz, ny),
    }


# ---------------------------------------------------------------------------
# Slab band overlay
# ---------------------------------------------------------------------------

def scout_band(
    vol_shape: tuple[int, int, int],
    normal: np.ndarray,
    center: np.ndarray | tuple[float, float, float],
    n_slices: int = 1,
    thickness_mm: float = 5.0,
    gap_mm: float = 0.0,
    voxel_size: tuple[float, float, float] = (1.0, 1.0, 1.0),
    scout_positions: np.ndarray | tuple[float, float, float] | None = None,
) -> dict[str, dict]:
    """
    Compute slab-band overlay lines for a three-scout localizer display.

    For each of the three orthogonal scouts this returns:
      - two edge lines: the front and back boundary planes of the slab
      - one line per prescribed slice: the centre plane of each slice

    All lines are intersected with fixed scout planes.  By default the scouts
    all pass through `center`; pass `scout_positions=(z, y, x)` to override.

    Parameters
    ----------
    vol_shape       : (nz, ny, nx)
    normal          : unit normal in physical (Z, Y, X) space
    center          : (Z, Y, X) voxel-index slab centre
    n_slices        : number of parallel slices
    thickness_mm    : physical slice thickness in mm
    gap_mm          : physical gap between adjacent slices in mm
    voxel_size      : (sz, sy, sx) mm per voxel
    scout_positions : (z, y, x) voxel-index positions of the three fixed scouts;
                      defaults to `center`

    Returns
    -------
    dict with keys 'axial', 'coronal', 'sagittal'.  Each value is a dict::

        {
          "edges":  [front_line, back_line],     # (c0,r0,c1,r1) or None each
          "slices": [slice_line_0, ...],          # one per slice
        }
    """
    nz, ny, nx = vol_shape
    n_unit = np.asarray(normal, dtype=float)
    n_unit = n_unit / np.linalg.norm(n_unit)
    vox = np.asarray(voxel_size, dtype=float)
    ctr = np.asarray(center, dtype=float)
    sp  = ctr if scout_positions is None else np.asarray(scout_positions, dtype=float)

    # Physical-space normal → index-space normal for _intersect_line
    n_idx = n_unit * vox

    step_mm     = thickness_mm + gap_mm
    half_cov_mm = (n_slices * thickness_mm + max(0, n_slices - 1) * gap_mm) / 2.0

    # Front/back boundary plane centres in voxel-index space
    front_ctr = ctr - half_cov_mm * n_unit / vox
    back_ctr  = ctr + half_cov_mm * n_unit / vox

    # Individual slice plane centres
    slice_ctrs = [ctr + (i - (n_slices - 1) / 2.0) * step_mm * n_unit / vox
                  for i in range(int(n_slices))]

    # Scout geometry: (fixed_axis, row_axis, col_axis, row_len, col_len)
    scouts = {
        "axial":    (0, 1, 2, ny, nx),
        "coronal":  (1, 0, 2, nz, nx),
        "sagittal": (2, 0, 1, nz, ny),
    }

    def _line(
        plane_ctr: np.ndarray,
        fa: int,
        ra: int,
        ca: int,
        rl: int,
        cl: int,
    ) -> tuple[float, float, float, float] | None:
        return _intersect_line(n_idx, np.asarray(plane_ctr, dtype=float),
                               fa, sp[fa], ra, ca, rl, cl)

    result = {}
    for key, (fa, ra, ca, rl, cl) in scouts.items():
        result[key] = {
            "edges":  [_line(front_ctr, fa, ra, ca, rl, cl),
                       _line(back_ctr,  fa, ra, ca, rl, cl)],
            "slices": [_line(sc, fa, ra, ca, rl, cl) for sc in slice_ctrs],
        }
    return result


# ---------------------------------------------------------------------------
# Convenience: extract three axis-aligned scouts through a centre point
# ---------------------------------------------------------------------------

def three_scouts(
    vol: np.ndarray,
    center: tuple[int, int, int] | None = None,
) -> dict[str, np.ndarray]:
    """
    Extract the three orthogonal scout slices that all pass through center.

    Returns dict with keys 'axial', 'coronal', 'sagittal' → 2-D arrays.
    Shapes: axial (ny, nx), coronal (nz, nx), sagittal (nz, ny).
    """
    nz, ny, nx = vol.shape
    if center is None:
        center = (nz // 2, ny // 2, nx // 2)
    cz = int(np.clip(round(center[0]), 0, nz - 1))
    cy = int(np.clip(round(center[1]), 0, ny - 1))
    cx = int(np.clip(round(center[2]), 0, nx - 1))
    return {
        "axial":    vol[cz, :, :],
        "coronal":  vol[:, cy, :],
        "sagittal": vol[:, :, cx],
    }
