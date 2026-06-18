"""Cross-table label consistency — the guard against the bug class found in the audit.

tissue_db._RAW is the canonical label → (properties, name) source. Several per-label
physics tables (diffusion ADC, B0 susceptibility) were written for the brain era and
silently drifted from the body-atlas label scheme, so body labels fell through to wrong
defaults (ADC 0 → no DWI contrast; missing → wrong off-resonance). These tests assert the
tables stay in sync with the canonical labels, so adding/renaming a label is caught here
rather than producing wrong physics in body images.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import tissue_db          # noqa: E402
import b0                 # noqa: E402
from phantom3d_extended import get_diffusion_properties_3d  # noqa: E402

# Canonical anatomy labels (0-22); pathologies (>=23) are brain-demo only.
CANON = {L: v[-1] for L, v in tissue_db._RAW.items() if L <= 22}
AIR_NAMES = ("air", "gas", "lung")


def _is_air(name: str) -> bool:
    return any(a in name.lower() for a in AIR_NAMES)


def test_diffusion_props_cover_every_tissue_label():
    dp = get_diffusion_properties_3d(None)
    missing = sorted(L for L in CANON if L not in dp)
    assert not missing, f"labels missing diffusion props (→ ADC 0, no DWI contrast): " \
                        f"{[(L, CANON[L]) for L in missing]}"


def test_b0_susceptibility_covers_every_tissue_label():
    missing = sorted(L for L in CANON if L not in b0.SUSCEPTIBILITY_PPM)
    assert not missing, f"labels missing B0 susceptibility (→ wrong off-resonance default): " \
                        f"{[(L, CANON[L]) for L in missing]}"


def test_air_labels_are_air_like():
    """Air-filled structures (Gas, Lung) must be paramagnetic in the B0 table and carry
    no diffusion signal — not silently treated as soft tissue."""
    for L, name in CANON.items():
        if L == 0 or not _is_air(name):       # 0 = background reference (χ=0)
            continue
        assert b0.SUSCEPTIBILITY_PPM[L] > 0, f"{name} (label {L}) should be air-like (χ>0)"
        assert get_diffusion_properties_3d(None)[L]["ADC"] == 0.0, \
            f"{name} (label {L}) should have no diffusion signal"


def test_tissue_labels_are_not_air_like():
    """Real tissue must be diamagnetic (χ ≤ 0) in the B0 table — a positive value means a
    tissue label was mistakenly classified as air (the lung/bowel-vs-tissue mix-up)."""
    for L, name in CANON.items():
        if L == 0 or _is_air(name) or "bowel" in name.lower():   # bowel lumen carries gas
            continue
        assert b0.SUSCEPTIBILITY_PPM[L] <= 0, \
            f"{name} (label {L}) is tissue but marked air-like (χ>0)"
