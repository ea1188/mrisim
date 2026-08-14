"""Metal-implant artifact physics: the void radius must respond to the levers the
way real metal artifact does, and the painter must actually null the metal region.
Source: src/artifacts.py (metal_bloom_radius / add_metal_artifact)."""
import numpy as np
from artifacts import add_metal_artifact, metal_bloom_radius


def test_radius_shrinks_with_bandwidth():
    lo = metal_bloom_radius(bandwidth=60)
    hi = metal_bloom_radius(bandwidth=250)
    assert hi < lo


def test_spin_echo_void_smaller_than_gradient_echo():
    se = metal_bloom_radius(sequence="Spin Echo")
    gre = metal_bloom_radius(sequence="Gradient Echo")
    assert se < gre
    assert metal_bloom_radius(sequence="FSE / TSE") < gre


def test_longer_te_grows_the_void():
    assert metal_bloom_radius(TE=60) > metal_bloom_radius(TE=10)


def test_higher_field_grows_the_void():
    assert metal_bloom_radius(field_strength=3.0) > metal_bloom_radius(field_strength=1.5)


def test_reduction_shrinks_the_void():
    assert metal_bloom_radius(mar_enabled=True) < metal_bloom_radius(mar_enabled=False)


def test_radius_has_a_floor():
    # even with every lever set to minimize it, the void keeps a small visible core
    r = metal_bloom_radius(field_strength=1.5, bandwidth=1000, sequence="Spin Echo", TE=1, mar_enabled=True)
    assert r >= 4.0


def test_add_metal_artifact_nulls_the_core_and_preserves_shape():
    img = np.full((128, 128), 100.0)
    center = (64, 50)
    out = add_metal_artifact(img, center, radius=20)
    assert out.shape == img.shape
    assert out[center[0], center[1]] < 10       # near-total dropout at the core
    assert out[0, 0] == 100.0                    # far corner untouched
    assert float(out.max()) > 100.0              # a bright pile-up rim appears
