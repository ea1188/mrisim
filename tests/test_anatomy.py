"""Tests for the procedural anatomy toolkit (anatomy.Builder)."""
import numpy as np

import anatomy


def test_ellipsoid_centered_and_bounded():
    b = anatomy.Builder(20, 30, 30, seed=0)
    m = b.ellipsoid((10, 15, 15), (6, 8, 8), ps=0.0)
    assert m[10, 15, 15]                       # centre is inside
    assert not m[0, 0, 0]                       # corner is outside
    # roughly an ellipsoid volume (4/3 π a b c), within tolerance of the perturbed mask
    assert 0.5 < m.sum() / (4 / 3 * np.pi * 6 * 8 * 8) < 1.6


def test_tube_connects_endpoints_and_radius():
    b = anatomy.Builder(40, 20, 20, seed=1)
    m = b.tube((2, 10, 10), (37, 10, 10), radius=2.0, ps=0.0)
    assert m[2, 10, 10] and m[37, 10, 10] and m[20, 10, 10]   # along the axis
    assert not m[20, 10, 16]                                   # well outside the radius
    # taper shrinks the far end
    mt = b.tube((2, 10, 10), (37, 10, 10), radius=3.0, taper=0.9, ps=0.0)
    near = mt[5].sum(); far = mt[34].sum()
    assert near > far > 0


def test_bone_has_cortical_shell_and_marrow_core():
    b = anatomy.Builder(24, 24, 24, seed=2)
    mask = b.ellipsoid((12, 12, 12), (8, 8, 8), ps=0.0)
    b.bone(mask, rim=2.0)
    assert b.vol[12, 12, 12] == anatomy.MARROW          # core is marrow
    # a voxel just inside the surface is cortical bone
    surf = mask & ~(b.vol == anatomy.MARROW)
    assert (b.vol[surf] == anatomy.BONE_CORTICAL).all()
    assert (b.vol == anatomy.MARROW).sum() < mask.sum()  # marrow ⊂ bone


def test_coat_wraps_the_outside_with_a_layer():
    b = anatomy.Builder(24, 24, 24, seed=3)
    mask = b.ellipsoid((12, 12, 12), (6, 6, 6), ps=0.0)
    b.paint(mask, anatomy.BONE_CORTICAL)
    coat = b.coat(mask, 2.0, anatomy.CARTILAGE)
    assert coat.any()
    assert not (coat & mask).any()                       # the coat is outside the mask
    assert (b.vol[coat] == anatomy.CARTILAGE).all()


def test_paint_where_restricts_region():
    b = anatomy.Builder(10, 10, 10, seed=4)
    half = b.gz < 5
    painted = b.paint(np.ones((10, 10, 10), bool), anatomy.MUSCLE, where=half)
    assert painted[:5].all() and not painted[5:].any()
