"""scripts/build_hero_slice.py: the landing-page hero slice + texture export.

The homepage mini-simulator renders data/brain_slice.bin (labels) modulated by
data/brain_slice_tex.bin (the engine's intra-tissue texture recipe), so these
guard that the export matches what the simulator shows for the same slice.
"""
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import build_hero_slice as hs  # noqa: E402
from phantom3d import get_slice  # noqa: E402


@pytest.fixture
def vol():
    """Small synthetic volume with the BrainWeb layout (axial = axis 0, A-P = axis 1)."""
    v = np.zeros((12, 217, 181), dtype=np.uint8)
    v[:, 20:200, 30:150] = 1          # CSF
    v[:, 40:180, 50:130] = 2          # GM
    v[:, 60:160, 70:110] = 3          # WM
    v[5, 100, 90] = 14                # a marker voxel in slice 5
    return v


def test_hero_labels_are_the_engines_axial_slice_displayed_anterior_up(vol):
    lab = hs.hero_labels(vol, 5)
    assert lab.shape == (hs.ROWS, hs.COLS) == (212, 181)
    assert lab.dtype == np.uint8
    # Same voxels the simulator slices (get_slice axial), cropped to 212 rows and
    # flipped so anterior is at the top, exactly as data/brain_slice.bin has always been.
    expect = get_slice(vol, "axial", 5)[hs.ROW_CROP:hs.ROW_CROP + hs.ROWS][::-1]
    assert np.array_equal(lab, expect)
    assert (lab == 14).sum() == 1                  # the marker survives the crop/flip
    assert not np.array_equal(lab, hs.hero_labels(vol, 4))


def test_hero_texture_matches_the_simulator_recipe(vol):
    tex = hs.hero_texture((hs.ROWS, hs.COLS), 90)
    assert tex.shape == (hs.ROWS, hs.COLS) and tex.dtype == np.uint8
    # Encodes n ∈ [-1, 1] as 0..255; the field is normalised so it reaches ±1.
    assert tex.min() == 0 or tex.max() == 255
    # Smooth (σ=2.5 Gaussian): neighbouring pixels differ by little.
    d = np.abs(np.diff(tex.astype(int), axis=1))
    assert d.mean() < 6
    # Deterministic per slice index (same seed rule as simulator.py's fallback texture).
    assert np.array_equal(tex, hs.hero_texture((hs.ROWS, hs.COLS), 90))
    assert not np.array_equal(tex, hs.hero_texture((hs.ROWS, hs.COLS), 78))


def test_decode_is_the_js_formula():
    # index.html decodes tex = 1 + 0.08 * (v / 127.5 - 1); the amplitude is the engine's.
    assert hs.TEX_AMPLITUDE == 0.08
    assert hs.decode_texture(np.array([0, 255], dtype=np.uint8)) == pytest.approx([0.92, 1.08])
