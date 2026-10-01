"""Export the landing-page hero slice → data/brain_slice.bin + data/brain_slice_tex.bin.

index.html runs a tiny JS mini-simulator (the engine's spoiled-GRE equation on a
real BrainWeb axial slice) so the hero responds live to TR / TE / flip without
Pyodide. It needs two 212×181 uint8 planes:

* ``brain_slice.bin``      tissue labels — the simulator's own axial slice
  (phantom3d.get_slice), cropped to 212 rows and flipped anterior-up, the way the
  simulator displays it.
* ``brain_slice_tex.bin``  the engine's intra-tissue texture for that slice: the
  same seeded, σ=2.5-smoothed noise simulator.py applies to the brain (which ships
  no measured texture field), amplitude ±8 %. Stored as n ∈ [-1, 1] → 0..255 and
  decoded in JS as ``1 + 0.08 * (v / 127.5 - 1)``.

The slice index defaults to the simulator's default brain slice (90), so the
homepage and the app show the same anatomy.

Run: ``PYTHONPATH=src python scripts/build_hero_slice.py [slice_idx]``
"""
import os
import sys

import numpy as np
from scipy.ndimage import gaussian_filter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from phantom3d import get_slice  # noqa: E402

DATA = os.path.join(os.path.dirname(__file__), "..", "data")
ROWS, COLS = 212, 181       # what index.html expects (SW = 181, SH = 212)
ROW_CROP = 5                # BrainWeb axial slices are 217 rows; drop the empty top band
DEFAULT_SLICE = 90          # simulator default brain slice
TEX_AMPLITUDE = 0.08        # simulator.py fallback texture: 1 + 0.08 * n


def hero_labels(vol: np.ndarray, slice_idx: int) -> np.ndarray:
    """The axial label slice as the simulator displays it: cropped, anterior up."""
    sl = get_slice(vol, "axial", slice_idx)
    return np.ascontiguousarray(sl[ROW_CROP:ROW_CROP + ROWS][::-1]).astype(np.uint8)


def hero_texture(shape: tuple[int, int], slice_idx: int) -> np.ndarray:
    """Engine texture recipe (simulator.py, brain fallback): seeded normal noise,
    Gaussian σ=2.5, normalised to ±1. Encoded 0..255."""
    rng = np.random.default_rng(slice_idx * 7919)          # axial → +0, as in simulator.py
    n = gaussian_filter(rng.standard_normal(shape).astype(float), sigma=2.5)
    n /= max(float(np.abs(n).max()), 1e-9)
    return np.clip(np.round((n + 1.0) * 127.5), 0, 255).astype(np.uint8)


def decode_texture(v: np.ndarray) -> np.ndarray:
    """Reference decode of the uint8 texture (mirrors the JS)."""
    return 1.0 + TEX_AMPLITUDE * (v.astype(float) / 127.5 - 1.0)


def main(slice_idx: int = DEFAULT_SLICE) -> None:
    import brainweb_loader
    vol = brainweb_loader.load_brainweb_phantom(4)
    lab = hero_labels(vol, slice_idx)
    tex = hero_texture(lab.shape, slice_idx)
    lab.tofile(os.path.join(DATA, "brain_slice.bin"))
    tex.tofile(os.path.join(DATA, "brain_slice_tex.bin"))
    print(f"wrote brain_slice.bin + brain_slice_tex.bin  (slice {slice_idx}, "
          f"{lab.shape[0]}x{lab.shape[1]}, labels {sorted(np.unique(lab).tolist())})")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SLICE)
