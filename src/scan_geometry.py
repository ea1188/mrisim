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
    nZ, nY, _nX = vol_shape[0], vol_shape[1], vol_shape[2]
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


def apply_sat_band(slice2d: np.ndarray, pos_frac: float, width_frac: float,
                   angle_deg: float = 0.0, fill: float = 0.0) -> np.ndarray:
    """Saturation band: null a strip of the acquired slice (saturated spins give no
    signal). ``pos_frac`` is the band centre (0=top … 1=bottom) and ``width_frac``
    its fraction of the through-image extent. ``angle_deg`` tilts the band about the
    image centre (0 = horizontal). Returns a copy with the strip set to ``fill``
    (0 = air / no signal for a label slice). A no-op for a zero-width band."""
    h, w = slice2d.shape
    half = width_frac * h / 2.0
    if half < 0.5:
        return slice2d
    out = slice2d.copy()
    if abs(angle_deg) < 0.5:                      # fast path: axis-aligned strip
        c = pos_frac * h
        lo = max(0, int(round(c - half)))
        hi = min(h, int(round(c + half)))
        if hi <= lo:
            return slice2d
        out[lo:hi, :] = fill
        return out
    # Tilted band: null where the perpendicular distance to the centre line (a line
    # through y = pos_frac·H, tilted by angle_deg about the image x-centre) is ≤ half.
    th = np.radians(angle_deg)
    cy, cx = pos_frac * h, w / 2.0
    yy, xx = np.mgrid[0:h, 0:w].astype(float)
    dist = (yy - cy) * np.cos(th) - (xx - cx) * np.sin(th)
    out[np.abs(dist) <= half] = fill
    return out


# Volume axes for each acquisition's get_slice output (matches phantom3d.get_slice):
# (through axis = slice index, row axis, col axis). Sagittal cols are flipped Y.
_SLICE_AXES = {"axial": (0, 1, 2), "coronal": (1, 0, 2), "sagittal": (2, 0, 1)}


def sat_band_extent(vol_shape: tuple, normal: np.ndarray) -> float:
    """The volume's extent (voxels) projected onto the slab normal."""
    return float(sum(abs(float(normal[i])) * vol_shape[i] for i in range(3)))


def sat_band_center(vol_shape: tuple, normal: np.ndarray, pos_frac: float) -> np.ndarray:
    """Slab centre (Z, Y, X): the volume centre offset **along the normal** by
    (pos_frac − 0.5) of the volume's extent in that direction. So moving the
    position slides the slab perpendicular to itself whatever its orientation —
    unlike moving along a fixed axis, which only works for an unrotated band."""
    c = np.array([vol_shape[0] / 2.0, vol_shape[1] / 2.0, vol_shape[2] / 2.0])
    ext = sat_band_extent(vol_shape, normal)
    return c + (pos_frac - 0.5) * ext * np.asarray(normal, dtype=float)


def sat_band_half_width(vol_shape: tuple, normal: np.ndarray, width_frac: float) -> float:
    """Half the slab thickness in voxels: ``width_frac`` of the extent along the normal."""
    return max(0.5, width_frac * sat_band_extent(vol_shape, normal) / 2.0)


def apply_sat_slab(slice2d: np.ndarray, acq: str, sl_idx: int,
                   vol_shape: tuple[int, int, int], center: np.ndarray,
                   normal: np.ndarray, half_w: float, fill: float = 0.0) -> np.ndarray:
    """Null a 3-D saturation slab on the (non-oblique) acquired slice.

    ``center`` and ``normal`` are (Z, Y, X) in voxel space; ``slice2d`` is the
    ``get_slice(vol, acq, sl_idx)`` output. Each pixel's signed perpendicular
    distance to the slab's centre plane is ``normal · (pixel_voxel − center)``;
    pixels within ``half_w`` of it are nulled. Because the slab is 3-D, an
    out-of-acquisition-plane tilt shifts the band across slices — exactly how a
    tilted sat band behaves on a scanner."""
    h, w = slice2d.shape
    rr = np.arange(h, dtype=float)[:, None]
    cc = np.arange(w, dtype=float)[None, :]
    nz, ny, nx = float(normal[0]), float(normal[1]), float(normal[2])
    cz, cy, cx = float(center[0]), float(center[1]), float(center[2])
    if acq == "axial":           # r=Y, c=X, through=Z
        dist = nz * (sl_idx - cz) + ny * (rr - cy) + nx * (cc - cx)
    elif acq == "coronal":       # r=Z, c=X, through=Y
        dist = nz * (rr - cz) + ny * (sl_idx - cy) + nx * (cc - cx)
    else:                        # sagittal: r=Z, c=flipped-Y, through=X
        dist = nz * (rr - cz) + ny * ((vol_shape[1] - 1 - cc) - cy) + nx * (sl_idx - cx)
    out = slice2d.copy()
    out[np.abs(dist) <= half_w] = fill
    return out


def _fold_axis(arr: np.ndarray, axis: int, lo: int, hi: int) -> np.ndarray:
    """Phase-encode wraparound (aliasing) along ``axis``: anatomy outside the
    [lo, hi) FOV window folds back in periodically (period = window length), the
    out-of-FOV signal adding onto the opposite side — exactly the fold-over a
    too-small phase FOV produces. Returns an array of window length along ``axis``."""
    length = hi - lo
    n = arr.shape[axis]
    bins = (np.arange(n) - lo) % length            # where each line aliases to
    out_shape = list(arr.shape)
    out_shape[axis] = length
    out = np.zeros(out_shape, dtype=float)
    src = np.moveaxis(arr, axis, 0)
    dst = np.moveaxis(out, axis, 0)
    np.add.at(dst, bins, src)                       # sum aliased lines into bins
    return np.moveaxis(dst, 0, axis)


def fov_crop(
    acq: str,
    slice2d: np.ndarray,
    inplane_fov_frac: float,
    inplane_off: float,
    wrap: bool = False,
    phase_swap: bool = False,
) -> np.ndarray:
    """
    Restrict a 2D acquired slice to the prescribed FOV: a centred square window of
    side inplane_fov_frac * dimension, shifted by inplane_off along the shown
    in-plane axis.

    With ``wrap=False`` (default) both shown axes are simply cropped. With
    ``wrap=True`` the **phase-encode axis** instead *aliases*: anatomy beyond the
    FOV folds over onto the opposite side, the way a too-small phase FOV wraps in a
    real scan, while the readout axis is cropped cleanly (it is oversampled, so it
    doesn't alias). The phase axis is ``inplane_axis`` by default; ``phase_swap``
    swaps phase and readout, so the wraparound flips to the other in-plane direction
    (as it does when you swap the phase-encode direction on a scanner). Returns a 2D
    array the same size as the plain crop (never empty).
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

    if wrap:
        # Phase axis aliases (fold-over); readout axis is cropped cleanly. PE swap
        # exchanges which in-plane axis plays each role, flipping the wrap direction.
        phase_arr, plo, phi = (ip_arr, lo_ip, hi_ip)
        freq_arr, flo, fhi = (dp_arr, lo_dp, hi_dp)
        if phase_swap:
            phase_arr, plo, phi, freq_arr, flo, fhi = (dp_arr, lo_dp, hi_dp, ip_arr, lo_ip, hi_ip)
        freq_win = [slice(None), slice(None)]
        freq_win[freq_arr] = slice(flo, fhi)
        sub = slice2d[tuple(freq_win)]
        folded = _fold_axis(sub, phase_arr, plo, phi)
        return folded if folded.size else slice2d

    win = [slice(None), slice(None)]
    win[ip_arr] = slice(lo_ip, hi_ip)
    win[dp_arr] = slice(lo_dp, hi_dp)
    cropped = slice2d[tuple(win)]
    if cropped.size == 0:
        return slice2d
    return cropped


def fov_transform(slice2d: np.ndarray, fov_ratio: float) -> np.ndarray:
    """Resample a 2D slice to a display FOV that is ``fov_ratio`` × the native
    object extent, returning an array of the *same* shape.

    Models how field-of-view actually behaves on a scanner:

    * ``fov_ratio < 1`` (FOV smaller than the object) — the central FOV region is
      magnified to fill the frame; anatomy beyond the FOV folds back in the
      **phase-encode (row) direction** (classic reduced-FOV *wraparound* /
      aliasing), while the frequency (column) direction is oversampled and simply
      cropped (no wrap). The true central anatomy keeps priority over the
      wrapped-in ghost on overlap.
    * ``fov_ratio > 1`` (FOV larger than the object) — the object shrinks toward
      the centre with empty surround.
    * ``fov_ratio ≈ 1`` — returned unchanged.

    Nearest-neighbour resampling and overlay folding keep integer label maps
    valid (the rendered signal inherits the wraparound through the labels).
    """
    from scipy.ndimage import zoom

    R, C = slice2d.shape
    if abs(fov_ratio - 1.0) < 0.01:
        return slice2d

    if fov_ratio > 1.0:
        # Larger FOV: object occupies a smaller, centred patch with empty surround.
        s = 1.0 / fov_ratio
        small = zoom(slice2d, s, order=0)
        out = np.zeros((R, C), dtype=slice2d.dtype)
        sr = small[:R, :C]
        r0 = max(0, (R - sr.shape[0]) // 2)
        c0 = max(0, (C - sr.shape[1]) // 2)
        out[r0:r0 + sr.shape[0], c0:c0 + sr.shape[1]] = sr
        return out

    # Smaller FOV: magnify, crop frequency axis, fold phase axis (wraparound).
    z = 1.0 / fov_ratio
    big = zoom(slice2d, z, order=0)
    BR, BC = big.shape

    # Frequency (columns): centre-crop to C (oversampled — no wrap).
    c0 = max(0, (BC - C) // 2)
    big = big[:, c0:c0 + C]
    if big.shape[1] < C:
        big = np.pad(big, ((0, 0), (0, C - big.shape[1])))

    # Phase (rows): fold BR magnified rows into R display rows, centred so the
    # middle of the object maps to the middle of the frame.
    out = np.zeros((R, C), dtype=slice2d.dtype)
    offset = (R - BR) // 2
    dst = (np.arange(BR) + offset) % R
    # Apply far-from-centre rows first so the central (true) anatomy wins overlaps.
    order_rows = np.argsort(np.abs(np.arange(BR) - BR / 2.0))[::-1]
    for r in order_rows:
        row = big[r]
        tgt = dst[r]
        out[tgt] = np.where(row != 0, row, out[tgt])
    return out
