"""Performance benchmarks — assert that core functions complete within a
wall-clock budget on a 256×256 image.

These tests guard against accidental O(N²) regressions (e.g., Python loops
where vectorised numpy ops are expected).  They run on every CI pass; they do
NOT replace pytest-benchmark profiling.

Budget is intentionally generous (×10 headroom over typical timings on a
modern laptop) so they never false-positive on slow CI machines.
"""

import timeit
import numpy as np
import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def phantom256():
    from phantom import create_brain_phantom
    return create_brain_phantom(256)


@pytest.fixture(scope="module")
def image256():
    rng = np.random.default_rng(0)
    return rng.random((256, 256)).astype(np.float64)


@pytest.fixture(scope="module")
def kspace256(image256):
    from kspace import image_to_kspace
    return image_to_kspace(image256)


@pytest.fixture(scope="module")
def vascular256():
    from angiography import create_vascular_phantom
    return create_vascular_phantom(256)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _time(fn, repeats: int = 3) -> float:
    """Return minimum wall-clock time (seconds) over `repeats` calls."""
    return min(timeit.repeat(fn, number=1, repeat=repeats))


# ---------------------------------------------------------------------------
# kspace benchmarks
# ---------------------------------------------------------------------------

class TestKspaceBenchmarks:
    def test_forward_fft_256(self, image256):
        """image_to_kspace on 256×256 should finish in under 0.05 s."""
        from kspace import image_to_kspace
        t = _time(lambda: image_to_kspace(image256))
        assert t < 0.05, f"image_to_kspace took {t:.3f}s (budget 0.05s)"

    def test_inverse_fft_256(self, kspace256):
        """kspace_to_image on 256×256 should finish in under 0.05 s."""
        from kspace import kspace_to_image
        t = _time(lambda: kspace_to_image(kspace256))
        assert t < 0.05, f"kspace_to_image took {t:.3f}s (budget 0.05s)"

    def test_apply_aliasing_256(self, image256):
        """apply_aliasing on 256×256 should finish in under 0.05 s.

        The vectorised np.add.at implementation must not regress to the old
        O(N²) nested Python loop (which was ~10 s at 256×256).
        """
        from kspace import apply_aliasing
        t = _time(lambda: apply_aliasing(image256, fov_fraction=0.5))
        assert t < 0.05, f"apply_aliasing took {t:.3f}s (budget 0.05s)"

    def test_kspace_filter_256(self, kspace256):
        """kspace_filter on 256×256 should finish in under 0.1 s."""
        from kspace import kspace_filter
        t = _time(lambda: kspace_filter(kspace256, "hamming"))
        assert t < 0.1, f"kspace_filter took {t:.3f}s (budget 0.1s)"

    def test_simulate_acquisition_256(self, image256):
        """End-to-end simulate_acquisition on 256×256 should finish in under 0.5 s."""
        from kspace import simulate_acquisition
        t = _time(lambda: simulate_acquisition(image256, matrix_size=128))
        assert t < 0.5, f"simulate_acquisition took {t:.3f}s (budget 0.5s)"


# ---------------------------------------------------------------------------
# Diffusion benchmarks
# ---------------------------------------------------------------------------

class TestDiffusionBenchmarks:
    def test_compute_adc_map_256(self, phantom256):
        """compute_adc_map on 256×256 should finish in under 0.5 s."""
        from diffusion import compute_adc_map
        np.random.default_rng(0)
        t = _time(lambda: compute_adc_map(phantom256, rng=np.random.default_rng(0)))
        assert t < 0.5, f"compute_adc_map took {t:.3f}s (budget 0.5s)"

    def test_compute_fa_map_256(self, phantom256):
        """compute_fa_map on 256×256 should finish in under 0.5 s."""
        from diffusion import compute_fa_map
        t = _time(lambda: compute_fa_map(phantom256, rng=np.random.default_rng(0)))
        assert t < 0.5, f"compute_fa_map took {t:.3f}s (budget 0.5s)"

    def test_simulate_diffusion_image_256(self, phantom256):
        """simulate_diffusion_image on 256×256 should finish in under 0.1 s."""
        from diffusion import simulate_diffusion_image
        from phantom import TISSUE_PROPERTIES
        t = _time(lambda: simulate_diffusion_image(phantom256, TISSUE_PROPERTIES, 1000))
        assert t < 0.1, f"simulate_diffusion_image took {t:.3f}s (budget 0.1s)"


# ---------------------------------------------------------------------------
# FSE / EPG benchmarks
# ---------------------------------------------------------------------------

class TestFseBenchmarks:
    def test_epg_run_etl32(self):
        """EPG echo train of 32 echoes should finish in under 0.01 s."""
        from fse import _epg_run
        t = _time(lambda: _epg_run(800, 80, 0.8, 4000, 32, 10))
        assert t < 0.01, f"_epg_run(ETL=32) took {t:.3f}s (budget 0.01s)"

    def test_simulate_fse_image_256(self, phantom256):
        """simulate_fse_image on 256×256 should finish in under 0.5 s."""
        from fse import simulate_fse_image
        from phantom import TISSUE_PROPERTIES
        t = _time(lambda: simulate_fse_image(
            phantom256, TR=4000, TE_eff=80, ETL=16,
            echo_spacing=10, tissue_properties=TISSUE_PROPERTIES
        ))
        assert t < 0.5, f"simulate_fse_image took {t:.3f}s (budget 0.5s)"


# ---------------------------------------------------------------------------
# Acceleration benchmarks
# ---------------------------------------------------------------------------

class TestAccelerationBenchmarks:
    def test_vd_poisson_mask_256(self):
        """vd_poisson_mask on 256×256 should finish in under 0.1 s."""
        from acceleration import vd_poisson_mask
        np.random.default_rng(0)
        t = _time(lambda: vd_poisson_mask(256, 256, 4, rng=np.random.default_rng(0)))
        assert t < 0.1, f"vd_poisson_mask took {t:.3f}s (budget 0.1s)"

    def test_apply_compressed_sensing_256(self, image256):
        """apply_compressed_sensing on 256×256 should finish in under 0.2 s."""
        from acceleration import apply_compressed_sensing
        t = _time(lambda: apply_compressed_sensing(
            image256, acceleration_factor=4, rng=np.random.default_rng(0)
        ))
        assert t < 0.2, f"apply_compressed_sensing took {t:.3f}s (budget 0.2s)"


# ---------------------------------------------------------------------------
# Coil benchmarks
# ---------------------------------------------------------------------------

class TestCoilBenchmarks:
    def test_head_coil_array_256(self):
        """head_coil_array on 256×256 × 8 coils should finish in under 0.5 s."""
        from coil import head_coil_array
        t = _time(lambda: head_coil_array(shape=(256, 256), n_coils=8,
                                          voxel_size_mm=(1.0, 1.0)))
        assert t < 0.5, f"head_coil_array took {t:.3f}s (budget 0.5s)"

    def test_combine_sos_256_8coils(self):
        """combine_sos on (8, 256, 256) should finish in under 0.05 s."""
        from coil import combine_sos
        coil_imgs = np.random.default_rng(0).random((8, 256, 256))
        t = _time(lambda: combine_sos(coil_imgs))
        assert t < 0.05, f"combine_sos took {t:.3f}s (budget 0.05s)"
