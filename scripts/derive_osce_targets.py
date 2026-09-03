#!/usr/bin/env python3
"""Derive OSCE grading targets from atlas label geometry.

Reads the authored scenarios (data/osce_scenarios.json), computes every numeric
target from the same volumes and functions the engine itself uses, and writes
the merged web/osce.json the browser rubric consumes. No target is hand-tuned:

- disc_plane   : PCA plane normal of a disc's voxels, converted to the planner's
                 tilt convention by solving against oblique.plane_from_angles —
                 the function that renders the band, so conventions cannot drift.
- band / band_span / extent : voxel ranges from connected components of a label.
- null_ti      : inversion time nulling a tissue, from tissue_db T1 at 3 T with
                 the scenario's TR (TI = T1 · ln(2 / (1 + exp(-TR/T1)))).

Volumes load through body_phantoms.build_region / brainweb_loader — the exact
code paths the web adapter uses, including the region_orient base-tilt fix.

Run:  .venv/bin/python scripts/derive_osce_targets.py
"""
from __future__ import annotations

import json
import math
import os
import sys
from typing import Any

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

SRC = os.path.join(ROOT, "data", "osce_scenarios.json")
OUT = os.path.join(ROOT, "web", "osce.json")

# Physical in-plane FOV (mm) per region. Mirrors web_adapter._NATIVE_FOV;
# tests/test_osce_targets.py asserts the two stay identical.
NATIVE_FOV = {"Brain": 220.0, "Abdomen": 380.0, "Spine": 320.0,
              "Pelvis": 380.0, "Knee": 150.0, "Torso": 400.0}

# Scout fixed axes (oblique.scout_band's convention): the axis a stack of that
# orientation steps along, and therefore the axis plan.slice indexes.
ACQ_AXIS = {"axial": 0, "coronal": 1, "sagittal": 2}

MIN_COMPONENT_VOXELS = 1000


def load_volume(region: str) -> np.ndarray:
    """The exact volume the web adapter plans on for this region."""
    if region == "Brain":
        import brainweb_loader
        return np.asarray(brainweb_loader.load_brainweb_phantom(4))
    import body_phantoms
    return np.asarray(body_phantoms.build_region(region))


def components(vol: np.ndarray, label: int) -> list[dict[str, Any]]:
    """Connected components of a label, size-filtered, sorted along axis 0."""
    from scipy import ndimage
    mask = vol == label
    lab, n = ndimage.label(mask)
    out: list[dict[str, Any]] = []
    for i in range(1, int(n) + 1):
        idx = np.argwhere(lab == i)
        if len(idx) < MIN_COMPONENT_VOXELS:
            continue
        out.append({
            "voxels": idx,
            "centroid": idx.mean(axis=0),
            "lo": idx.min(axis=0),
            "hi": idx.max(axis=0),
        })
    out.sort(key=lambda c: float(c["centroid"][0]))
    return out


def plane_normal(voxels: np.ndarray) -> np.ndarray:
    """Unit normal of the best-fit plane through a voxel cloud (smallest PC)."""
    centered = voxels.astype(np.float64) - voxels.mean(axis=0)
    _, _, vt = np.linalg.svd(centered, full_matrices=False)
    n = vt[-1]
    if n[0] < 0:                      # canonical sign: +Z half-space
        n = -n
    return n / float(np.linalg.norm(n))


def solve_angles(base: str, target_normal: np.ndarray) -> tuple[float, float]:
    """Find (tilt, rot) whose plane_from_angles normal matches target_normal.

    Solved numerically against the engine's own function, so the emitted target
    is in exactly the convention the planner applies. Coarse grid, then refine.
    """
    from oblique import plane_from_angles

    def err(t: float, r: float) -> float:
        n = plane_from_angles(base, tilt_deg=t, rot_deg=r)[0]
        d = abs(float(np.dot(n, target_normal)))
        return math.degrees(math.acos(min(1.0, d)))

    best = (0.0, 0.0)
    best_e = err(0.0, 0.0)
    for t in range(-60, 61, 2):
        for r in range(-60, 61, 2):
            e = err(float(t), float(r))
            if e < best_e:
                best, best_e = (float(t), float(r)), e
    step = 1.0
    while step >= 0.05:
        t0, r0 = best
        for tf in (t0 - step, t0, t0 + step):
            for rf in (r0 - step, r0, r0 + step):
                e = err(tf, rf)
                if e < best_e:
                    best, best_e = (tf, rf), e
        if best == (t0, r0):
            step /= 2.0
    if best_e > 1.0:
        raise ValueError(f"angle solve did not converge: residual {best_e:.2f} deg")
    return best


def null_ti(tissue: int, tr: float) -> float:
    """TI that nulls a tissue's longitudinal signal at this TR (3 T values)."""
    import tissue_db
    t1 = float(tissue_db.properties("3T")[tissue]["T1"])
    return t1 * math.log(2.0 / (1.0 + math.exp(-tr / t1)))


def rank(comps: list[dict[str, Any]], r: int) -> dict[str, Any]:
    return comps[r] if r >= 0 else comps[len(comps) + r]


def derive(spec: dict[str, Any], vols: dict[str, np.ndarray]) -> dict[str, Any]:
    kind = spec["kind"]
    if kind == "null_ti":
        ti = null_ti(int(spec["tissue"]), float(spec["TR"]))
        return {
            "target": round(ti, 1),
            "full": [round(ti * (1 - spec["full_frac"]), 1), round(ti * (1 + spec["full_frac"]), 1)],
            "partial": [round(ti * (1 - spec["partial_frac"]), 1), round(ti * (1 + spec["partial_frac"]), 1)],
        }

    region = spec["region"]
    vol = vols[region]
    if kind == "disc_plane":
        comps = components(vol, 15)
        disc = rank(comps, int(spec["disc_rank"]))
        tilt, rot = solve_angles("axial", plane_normal(disc["voxels"]))
        if abs(rot) > 3.0:
            raise ValueError(f"disc plane needs rot {rot:.1f} deg; tilt-only grading invalid")
        return {"tilt_deg": round(tilt, 1), "rot_deg": 0.0,
                "full_deg": spec["full_deg"], "partial_deg": spec["partial_deg"]}

    axis = int(spec["axis"])
    if kind == "band":
        c = rank(components(vol, int(spec["label"])), int(spec["component_rank"]))
        return {"axis": axis, "lo": int(c["lo"][axis]), "hi": int(c["hi"][axis])}
    if kind == "band_span":
        comps = components(vol, int(spec["label"]))
        lo_r, hi_r = spec["component_ranks"]
        span = [rank(comps, r) for r in range(int(lo_r), int(hi_r) + 1)]
        part = rank(comps, int(spec["partial_component_rank"]))
        return {"axis": axis,
                "full": [int(min(c["lo"][axis] for c in span)), int(max(c["hi"][axis] for c in span))],
                "partial": [int(part["lo"][axis]), int(part["hi"][axis])]}
    if kind == "extent":
        mask = vol == int(spec["label"])
        idx = np.argwhere(mask)
        lo, hi = int(idx[:, axis].min()), int(idx[:, axis].max())
        mid, half = (lo + hi) / 2.0, (hi - lo) / 2.0
        f = float(spec["partial_frac"])
        return {"axis": axis, "full": [lo, hi],
                "partial": [int(round(mid - half * f)), int(round(mid + half * f))]}
    raise ValueError(f"unknown derive kind: {kind}")


def main() -> None:
    src = json.load(open(SRC))
    regions = sorted({s["region"] for s in src["scenarios"]})
    vols = {r: load_volume(r) for r in regions}

    meta = {}
    for r, v in vols.items():
        nz, ny, nx = (int(x) for x in v.shape)
        meta[r] = {"shape": [nz, ny, nx],
                   "voxel_mm": round(NATIVE_FOV[r] / float(nx), 4)}

    for s in src["scenarios"]:
        for c in s["criteria"]:
            if "derive" in c:
                c["target"] = derive(c.pop("derive"), vols)

    out = {"version": src["version"], "regions": meta, "scenarios": src["scenarios"]}
    with open(OUT, "w") as f:
        json.dump(out, f, indent=1, sort_keys=True)
        f.write("\n")
    n_crit = sum(len(s["criteria"]) for s in src["scenarios"])
    print(f"wrote {OUT}: {len(src['scenarios'])} scenarios, {n_crit} criteria, regions {regions}")


if __name__ == "__main__":
    main()
