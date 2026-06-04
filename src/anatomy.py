"""Reusable procedural primitives for building detailed synthetic anatomy.

The body phantoms used to be plain ellipsoid blobs. This module provides a small
toolkit so each region can be authored a structure at a time with anatomically
shaped parts — tapered tubes (vessels / tendons / ligaments / long bones),
cortical-shell-plus-marrow bones, surface coats (cartilage / skin), crescents
(menisci), and compartment partitions — all with organic boundary perturbation
and per-structure sub-texture. Labels follow the shared ``tissue_db`` vocabulary.

A :class:`Builder` wraps a labelled volume + its coordinate grids; every paint
primitive returns the boolean mask it painted, so structures can be composed
(e.g. "marrow inside this bone", "cartilage on that surface").
"""
import numpy as np
from scipy.ndimage import binary_dilation, distance_transform_edt, gaussian_filter

# Common tissue labels (tissue_db vocabulary).
FLUID, FAT, BONE_CORTICAL, MARROW = 1, 4, 13, 14
MUSCLE, CARTILAGE, BLOOD = 6, 15, 11


class Builder:
    """A labelled volume (Z,H,W) with paint primitives.

    Coordinates are voxel indices; sizes are in voxels. ``ps`` scales how much the
    organic boundary perturbation roughens an edge (0 = smooth)."""

    def __init__(self, Z: int, H: int, W: int, seed: int = 0):
        self.Z, self.H, self.W = Z, H, W
        self.vol = np.zeros((Z, H, W), dtype=np.uint8)
        self.gz, self.gy, self.gx = np.ogrid[:Z, :H, :W]
        self.rng = np.random.default_rng(seed)
        n1 = gaussian_filter(self.rng.standard_normal((Z, H, W)), 2.6)
        n2 = gaussian_filter(self.rng.standard_normal((Z, H, W)), 1.2)
        self.pert = 0.045 * n1 + 0.020 * n2

    # --- shape masks ------------------------------------------------------- #
    def ellipsoid(self, c: "tuple[float, float, float]", r: "tuple[float, float, float]",
                  ps: float = 1.0) -> np.ndarray:
        cz, cy, cx = c
        rz, ry, rx = r
        d = ((self.gz - cz) / rz) ** 2 + ((self.gy - cy) / ry) ** 2 + ((self.gx - cx) / rx) ** 2
        return d <= 1.0 + self.pert * ps

    def tube(self, p0: "tuple[float, float, float]", p1: "tuple[float, float, float]",
             radius: float, taper: float = 0.0, ps: float = 0.6) -> np.ndarray:
        """Mask of a (optionally tapered) cylinder between two 3-D points — the
        workhorse for vessels, tendons, ligaments, nerves and long-bone shafts."""
        a = np.array(p0, dtype=float)
        b = np.array(p1, dtype=float)
        ab = b - a
        L2 = float(ab @ ab) or 1.0
        pz, py, px = (self.gz - a[0]), (self.gy - a[1]), (self.gx - a[2])
        t = (pz * ab[0] + py * ab[1] + px * ab[2]) / L2
        t = np.clip(t, 0.0, 1.0)
        dz = pz - t * ab[0]; dy = py - t * ab[1]; dx = px - t * ab[2]
        dist = np.sqrt(dz * dz + dy * dy + dx * dx)
        rad = radius * (1.0 - taper * t) * (1.0 + self.pert * ps)
        return dist <= rad

    # --- composite painters ------------------------------------------------ #
    def paint(self, mask: np.ndarray, label: int, where: "np.ndarray | None" = None) -> np.ndarray:
        if where is not None:
            mask = mask & where
        self.vol[mask] = label
        return mask

    def bone(self, mask: np.ndarray, rim: float = 2.0,
             cortical: int = BONE_CORTICAL, marrow: int = MARROW) -> np.ndarray:
        """Paint ``mask`` as a bone: a thin cortical shell with a marrow core.
        ``rim`` is the cortical thickness in voxels."""
        self.vol[mask] = cortical
        core = distance_transform_edt(mask) > rim
        self.vol[core] = marrow
        return mask

    def coat(self, mask: np.ndarray, thickness: float, label: int,
             where: "np.ndarray | None" = None, side: "np.ndarray | None" = None) -> np.ndarray:
        """Coat the outside of ``mask`` with a layer ``thickness`` voxels thick
        (cartilage on bone, skin on body). ``side`` optionally restricts the coat
        to a half-space mask (e.g. only the joint-facing surface)."""
        grown = binary_dilation(mask, iterations=int(round(thickness)))
        shell = grown & ~mask
        if where is not None:
            shell = shell & where
        if side is not None:
            shell = shell & side
        self.vol[shell] = label
        return shell
