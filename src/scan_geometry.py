"""
scan_geometry.py  —  graphic slice prescription for the MRI simulator.

Pure geometry, no Qt/UI. The app drives everything through these functions so
the math can be tested in isolation. Coordinates are VOXEL INDICES of the active
volume; the scout image is displayed with matplotlib origin='lower', so display
x == column index, display y == row index.

Volume axis convention matches phantom3d.get_slice:  axis0=Z (axial index),
axis1=Y (coronal index), axis2=X (sagittal index).

For each acquisition orientation we pick a scout plane that shows the
through-slice axis edge-on, so the prescribed slices appear as a band:

  acq        scout      display rows / cols       through  in-plane(shown)  depth
  --------   --------   -----------------------   -------  ---------------  -----
  axial      coronal    rows=Z(0)  cols=X(2)      Z (v)    X (2)            Y (1)
  coronal    axial      rows=Y(1)  cols=X(2)      Y (v)    X (2)            Z (0)
  sagittal   coronal    rows=Z(0)  cols=X(2)      X (h)    Z (0)            Y (1)

None of these scouts is get_slice's 'sagittal' view (the only one that flips an
axis), so display<->index mapping is a direct identity in every case below.
"""
from typing import TypedDict

import numpy as np
from phantom3d import get_slice


class _ScoutCfg(TypedDict):
    scout: str
    through: str
    through_axis: int
    inplane_axis: int
    depth_axis: int


SCOUT: dict[str, _ScoutCfg] = {
    "axial":    dict(scout="coronal", through="v", through_axis=0, inplane_axis=2, depth_axis=1),
    "coronal":  dict(scout="axial",   through="v", through_axis=1, inplane_axis=2, depth_axis=0),
    "sagittal": dict(scout="coronal", through="h", through_axis=2, inplane_axis=0, depth_axis=1),
}


def cfg_for(acq: str) -> _ScoutCfg:
    return SCOUT[acq]


def depth_index(acq: str, vol_shape: tuple[int, ...]) -> int:
    """Index of the scout plane along the depth axis (centre of the volume)."""
    return vol_shape[SCOUT[acq]["depth_axis"]] // 2


def scout_slice(vol: np.ndarray, acq: str) -> tuple[np.ndarray, _ScoutCfg, int]:
    """Return (scout_label_slice, cfg, depth_idx) for the given acquisition plane."""
    cfg = SCOUT[acq]
    d = depth_index(acq, vol.shape)
    return get_slice(vol, cfg["scout"], d), cfg, d


def prescribed_indices(
    acq: str,
    vol_shape: tuple[int, ...],
    slice_idx: float,
    n_slices: int,
    thickness: float,
    gap: float = 0.0,
) -> list[int]:
    """
    List of integer through-axis indices for the prescribed slice group,
    centred on slice_idx, clamped to the volume. thickness/gap are in voxels.
    """
    through_len = vol_shape[SCOUT[acq]["through_axis"]]
    step = thickness + gap
    out = []
    for i in range(int(n_slices)):
        off = (i - (n_slices - 1) / 2.0) * step
        idx = int(round(slice_idx + off))
        out.append(int(np.clip(idx, 0, through_len - 1)))
    return out


def box_rect(
    acq: str,
    vol_shape: tuple[int, ...],
    slice_idx: float,
    n_slices: int,
    thickness: float,
    gap: float,
    inplane_fov_frac: float,
    inplane_off: float,
) -> dict:
    """
    Compute the FOV box in scout DISPLAY coordinates.

    Returns dict with x0,y0,w,h (matplotlib Rectangle, lower-left origin) plus
    the through/in-plane centres and half-extents and which display axis is the
    through-slice direction ('v' or 'h'). Also returns slice-line positions.
    """
    cfg = SCOUT[acq]
    through_len = vol_shape[cfg["through_axis"]]
    inplane_len = vol_shape[cfg["inplane_axis"]]

    cov = n_slices * thickness + max(0, n_slices - 1) * gap
    half_cov = cov / 2.0
    through_c = float(slice_idx)

    inplane_c = inplane_len / 2.0 + inplane_off
    half_w = inplane_fov_frac * inplane_len / 2.0

    # Slice-line centres in the through display direction
    lines = prescribed_indices(acq, vol_shape, slice_idx, n_slices, thickness, gap)

    if cfg["through"] == "v":
        rect = dict(x0=inplane_c - half_w, y0=through_c - half_cov,
                    w=2 * half_w, h=2 * half_cov)
        info = dict(through="v", through_c=through_c, half_cov=half_cov,
                    inplane_c=inplane_c, half_w=half_w,
                    through_len=through_len, inplane_len=inplane_len,
                    line_axis="y", lines=lines)
    else:  # through == 'h'
        rect = dict(x0=through_c - half_cov, y0=inplane_c - half_w,
                    w=2 * half_cov, h=2 * half_w)
        info = dict(through="h", through_c=through_c, half_cov=half_cov,
                    inplane_c=inplane_c, half_w=half_w,
                    through_len=through_len, inplane_len=inplane_len,
                    line_axis="x", lines=lines)
    info.update(rect)
    return info


def update_from_drag(
    acq: str,
    vol_shape: tuple[int, ...],
    mode: str,
    dx_through: float,
    d_inplane: float,
    slice_idx: float,
    n_slices: int,
    thickness: float,
    gap: float,
    inplane_fov_frac: float,
    inplane_off: float,
) -> tuple[float, float, float, int]:
    """
    Apply a drag to the geometry and return updated
    (slice_idx, inplane_off, inplane_fov_frac, n_slices).

    mode:
      'move'        -> translate group (through + in-plane centre)
      'resize_cov'  -> change coverage (=> n_slices) by dragging a through edge
      'resize_fov'  -> change in-plane FOV by dragging an in-plane edge
    dx_through  : signed drag along the through display axis (voxels)
    d_inplane   : signed drag along the in-plane display axis (voxels)
    """
    cfg = SCOUT[acq]
    through_len = vol_shape[cfg["through_axis"]]
    inplane_len = vol_shape[cfg["inplane_axis"]]

    if mode == "move":
        slice_idx = float(np.clip(slice_idx + dx_through, 0, through_len - 1))
        inplane_off = float(np.clip(inplane_off + d_inplane,
                                    -inplane_len / 2.0, inplane_len / 2.0))
    elif mode == "resize_cov":
        # Edge moved by dx_through changes total coverage by 2*|dx| about centre
        cov = n_slices * thickness + max(0, n_slices - 1) * gap
        cov = max(thickness, cov + 2 * dx_through)
        n_slices = int(np.clip(round((cov + gap) / (thickness + gap)), 1, 64))
    elif mode == "resize_fov":
        half_w = inplane_fov_frac * inplane_len / 2.0
        half_w = max(4.0, half_w + d_inplane)
        inplane_fov_frac = float(np.clip(2 * half_w / inplane_len, 0.1, 1.0))

    return slice_idx, inplane_off, inplane_fov_frac, n_slices


# ---- 3-plane localizer overlays ---------------------------------------------

def secondary_overlay(
    viewer: str,
    acq: str,
    vol_shape: tuple[int, ...],
    slice_idx: float,
    n_slices: int,
    thickness: float,
    gap: float,
    inplane_fov_frac: float,
    inplane_off: float,
) -> dict:
    """
    Overlay geometry for the *secondary* panel of a 3-plane scout.

    Returns:
      orient        'h'|'v'  — horizontal or vertical lines
      positions     list[int]— display-axis coords of each slice line
      span          (lo, hi) — perpendicular extent of each line
      through       'v'|'h'  — which display axis the user must drag to move lines
      through_sign  +1|-1    — sign relating drag delta to slice_idx delta
    """
    nZ, nY, nX = vol_shape[0], vol_shape[1], vol_shape[2]
    slices = prescribed_indices(acq, vol_shape, slice_idx, n_slices, thickness, gap)

    if acq == "axial" and viewer == "sagittal":
        # Sagittal: rows=Z, cols=Y(flipped). Axial slices → h-lines at y=Z
        return dict(orient="h", positions=list(slices), span=(0, nY),
                    through="v", through_sign=+1)

    if acq == "coronal" and viewer == "sagittal":
        # Sagittal: rows=Z, cols=Y(flipped). Coronal slices at Y=y_i → v-lines at x=nY-1-y
        return dict(orient="v", positions=[nY - 1 - y for y in slices], span=(0, nZ),
                    through="h", through_sign=-1)

    if acq == "sagittal" and viewer == "axial":
        # Axial: rows=Y, cols=X. Sagittal slices → v-lines at x=X
        return dict(orient="v", positions=list(slices), span=(0, nY),
                    through="h", through_sign=+1)

    return {}


def inplane_box(
    acq: str,
    vol_shape: tuple[int, ...],
    inplane_fov_frac: float,
    inplane_off: float,
) -> dict:
    """
    Dashed FOV crop rectangle for the acquisition-plane panel in the 3-plane scout.
    Returns {x0, y0, w, h} in display coords of the acquired slice image.

    Viewer conventions (same as get_slice):
      axial   : rows=Y(nY), cols=X(nX)  — inplane along cols(X), depth along rows(Y)
      coronal : rows=Z(nZ), cols=X(nX)  — inplane along cols(X), depth along rows(Z)
      sagittal: rows=Z(nZ), cols=Y(nY)  — inplane along rows(Z), depth along cols(Y)

    The crop window is a square fraction of each dimension (mirrors fov_crop logic).
    """
    nZ, nY, nX = vol_shape[0], vol_shape[1], vol_shape[2]

    if acq == "axial":
        inplane_len, depth_len = nX, nY
        half_ip = max(2.0, inplane_fov_frac * inplane_len / 2.0)
        half_dp = max(2.0, inplane_fov_frac * depth_len / 2.0)
        ip_c = inplane_len / 2.0 + inplane_off   # cols = X (not flipped)
        dp_c = depth_len / 2.0
        return dict(x0=ip_c - half_ip, y0=dp_c - half_dp, w=2 * half_ip, h=2 * half_dp)

    if acq == "coronal":
        inplane_len, depth_len = nX, nZ
        half_ip = max(2.0, inplane_fov_frac * inplane_len / 2.0)
        half_dp = max(2.0, inplane_fov_frac * depth_len / 2.0)
        ip_c = inplane_len / 2.0 + inplane_off
        dp_c = depth_len / 2.0
        return dict(x0=ip_c - half_ip, y0=dp_c - half_dp, w=2 * half_ip, h=2 * half_dp)

    # sagittal: inplane=Z(rows), depth=Y(cols, symmetric)
    inplane_len, depth_len = nZ, nY
    half_ip = max(2.0, inplane_fov_frac * inplane_len / 2.0)
    half_dp = max(2.0, inplane_fov_frac * depth_len / 2.0)
    ip_c = inplane_len / 2.0 + inplane_off   # rows=Z (not flipped in acquired array)
    dp_c = depth_len / 2.0
    return dict(x0=dp_c - half_dp, y0=ip_c - half_ip, w=2 * half_dp, h=2 * half_ip)


# ---- In-plane FOV crop of an acquired 2D slice ------------------------------
# Maps the two in-plane axes onto the get_slice(acq, idx) output array, so we can
# crop the acquired image to the prescribed FOV (square zoom + in-plane shift).
def _arr_axis(acq: str, vol_axis: int) -> tuple[int, bool]:
    """Which output-array axis (0=row,1=col) a given volume axis maps to,
    plus whether that array axis is flipped relative to the index."""
    if acq == "axial":     # vol[idx,:,:] -> rows=Y(1), cols=X(2)
        m = {1: (0, False), 2: (1, False)}
    elif acq == "coronal":  # vol[:,idx,:] -> rows=Z(0), cols=X(2)
        m = {0: (0, False), 2: (1, False)}
    else:                   # sagittal: fliplr(vol[:,:,idx]) -> rows=Z(0), cols=Y(1, flipped)
        m = {0: (0, False), 1: (1, True)}
    return m[vol_axis]


def fov_crop(
    acq: str,
    slice2d: np.ndarray,
    inplane_fov_frac: float,
    inplane_off: float,
) -> np.ndarray:
    """
    Crop a 2D acquired slice to the prescribed FOV: a centred square window of
    side inplane_fov_frac * dimension, shifted by inplane_off along the shown
    in-plane axis. Returns the cropped 2D array (never empty).
    """
    cfg = SCOUT[acq]
    H, W = slice2d.shape

    ip_arr, ip_flip = _arr_axis(acq, cfg["inplane_axis"])
    dp_arr, _ = _arr_axis(acq, cfg["depth_axis"])

    dims = {0: H, 1: W}

    def window(axis_len: int, frac: float, off: float) -> tuple[int, int]:
        half = max(2, int(round(frac * axis_len / 2.0)))
        c = axis_len / 2.0 + off
        lo = int(round(c - half)); hi = int(round(c + half))
        lo = max(0, min(lo, axis_len - 2 * half if axis_len > 2 * half else 0))
        hi = min(axis_len, lo + 2 * half)
        lo = max(0, hi - 2 * half)
        return lo, hi

    off_ip = -inplane_off if ip_flip else inplane_off
    lo_ip, hi_ip = window(dims[ip_arr], inplane_fov_frac, off_ip)
    lo_dp, hi_dp = window(dims[dp_arr], inplane_fov_frac, 0.0)

    win = [slice(None), slice(None)]
    win[ip_arr] = slice(lo_ip, hi_ip)
    win[dp_arr] = slice(lo_dp, hi_dp)
    cropped = slice2d[tuple(win)]
    if cropped.size == 0:
        return slice2d
    return cropped
