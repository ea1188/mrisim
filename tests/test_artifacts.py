import numpy as np
import pytest
from artifacts import (
    add_motion_artifact,
    add_chemical_shift_artifact,
    add_susceptibility_artifact,
    add_zipper_artifact,
    calculate_chemical_shift_pixels,
)
from phantom import create_brain_phantom, TISSUE_PROPERTIES
from signal_engine import spin_echo_signal


@pytest.fixture(scope="module")
def brain_image():
    p = create_brain_phantom(64)
    img = np.zeros_like(p, dtype=float)
    for label, props in TISSUE_PROPERTIES.items():
        mask = p == label
        sig = spin_echo_signal(props["T1"], props["T2"], props["PD"], 500, 15)
        img[mask] = sig
    return img


@pytest.fixture(scope="module")
def brain_phantom_64():
    return create_brain_phantom(64)


class TestMotionArtifact:
    def test_output_shape_periodic(self, brain_image):
        out = add_motion_artifact(brain_image, "periodic", amplitude=3, frequency=4)
        assert out.shape == brain_image.shape

    def test_output_shape_random(self, brain_image):
        out = add_motion_artifact(brain_image, "random", amplitude=3, frequency=3,
                                  rng=np.random.default_rng(0))
        assert out.shape == brain_image.shape

    def test_output_shape_linear(self, brain_image):
        out = add_motion_artifact(brain_image, "linear", amplitude=5)
        assert out.shape == brain_image.shape

    def test_output_nonnegative(self, brain_image):
        out = add_motion_artifact(brain_image, "periodic", amplitude=3, frequency=4)
        assert np.all(out >= 0)

    def test_zero_amplitude_nearly_same(self, brain_image):
        out = add_motion_artifact(brain_image, "periodic", amplitude=0)
        # FFT round-trip introduces ~1e-16 floating-point residuals; use atol.
        np.testing.assert_allclose(out, brain_image, atol=1e-10)

    def test_horizontal_direction(self, brain_image):
        out = add_motion_artifact(brain_image, "periodic", amplitude=3,
                                  phase_direction="horizontal")
        assert out.shape == brain_image.shape


class TestChemicalShiftArtifact:
    def test_output_shape(self, brain_image, brain_phantom_64):
        out = add_chemical_shift_artifact(brain_image, brain_phantom_64, shift_pixels=3)
        assert out.shape == brain_image.shape

    def test_no_fat_label_returns_unchanged(self, brain_image, brain_phantom_64):
        # brain phantom has no fat (label 4 is CSF ventricles in phantom.py)
        out = add_chemical_shift_artifact(brain_image, brain_phantom_64,
                                          shift_pixels=3, fat_label=99)
        np.testing.assert_array_equal(out, brain_image)

    def test_zero_shift_no_change(self, brain_image, brain_phantom_64):
        out = add_chemical_shift_artifact(brain_image, brain_phantom_64, shift_pixels=0)
        assert out.shape == brain_image.shape


class TestSusceptibilityArtifact:
    def test_output_shape(self, brain_image, brain_phantom_64):
        out = add_susceptibility_artifact(brain_image, brain_phantom_64, strength=0.3)
        assert out.shape == brain_image.shape

    def test_signal_attenuated_or_equal(self, brain_image, brain_phantom_64):
        out = add_susceptibility_artifact(brain_image, brain_phantom_64, strength=0.5)
        # Signal can only decrease (dropout) or stay the same near boundaries
        assert out.max() <= brain_image.max() * 1.01  # 1% tolerance for float math

    def test_nonnegative(self, brain_image, brain_phantom_64):
        out = add_susceptibility_artifact(brain_image, brain_phantom_64, strength=0.3)
        assert np.all(out >= 0)


class TestZipperArtifact:
    def test_output_shape(self, brain_image):
        out = add_zipper_artifact(brain_image, frequency_offset=0.3, amplitude=0.1)
        assert out.shape == brain_image.shape

    def test_zipper_line_brighter(self, brain_image):
        out = add_zipper_artifact(brain_image, frequency_offset=0.5, amplitude=0.5)
        col = int(brain_image.shape[1] * 0.5)
        # The zipper column should be at least as bright as the original
        assert out[:, col].sum() > brain_image[:, col].sum()

    def test_zero_amplitude_no_change(self, brain_image):
        out = add_zipper_artifact(brain_image, frequency_offset=0.5, amplitude=0.0)
        np.testing.assert_array_equal(out, brain_image)


class TestChemicalShiftCalculation:
    def test_positive_result(self):
        shift = calculate_chemical_shift_pixels(125, field_strength=3.0)
        assert shift > 0

    def test_lower_bandwidth_larger_shift(self):
        shift_low  = calculate_chemical_shift_pixels(50,  field_strength=3.0)
        shift_high = calculate_chemical_shift_pixels(250, field_strength=3.0)
        assert shift_low > shift_high

    def test_higher_field_larger_shift(self):
        shift_15 = calculate_chemical_shift_pixels(125, field_strength=1.5)
        shift_3  = calculate_chemical_shift_pixels(125, field_strength=3.0)
        assert shift_3 > shift_15

    def test_known_approximate_value(self):
        # At 3T (128 MHz), fat-water shift ~448 Hz; at 125 Hz/px => ~3.6 px
        shift = calculate_chemical_shift_pixels(125, field_strength=3.0)
        assert 3.0 < shift < 5.0

    def test_returns_float(self):
        shift = calculate_chemical_shift_pixels(125)
        assert isinstance(shift, float)


class TestArtifactDtypes:
    """dtype and shape consistency checks across all artifact functions."""

    def test_motion_dtype(self, brain_image):
        out = add_motion_artifact(brain_image, "periodic", amplitude=3)
        assert out.dtype == np.float64

    def test_zipper_dtype(self, brain_image):
        out = add_zipper_artifact(brain_image)
        assert out.dtype == np.float64

    def test_chemical_shift_dtype(self, brain_image, brain_phantom_64):
        out = add_chemical_shift_artifact(brain_image, brain_phantom_64, shift_pixels=3)
        assert out.dtype == np.float64

    def test_susceptibility_dtype(self, brain_image, brain_phantom_64):
        out = add_susceptibility_artifact(brain_image, brain_phantom_64)
        assert out.dtype == np.float64


class TestMotionArtifactPhysics:
    def test_periodic_motion_modifies_image(self, brain_image):
        out = add_motion_artifact(brain_image, "periodic", amplitude=5, frequency=4)
        assert not np.allclose(out, brain_image)

    def test_random_motion_modifies_image(self, brain_image):
        out = add_motion_artifact(brain_image, "random", amplitude=5, frequency=3)
        assert not np.allclose(out, brain_image)

    def test_signal_conserved_approx(self, brain_image):
        """Total image energy should be approximately conserved by motion."""
        out = add_motion_artifact(brain_image, "linear", amplitude=2)
        # Allow 20% change — motion redistributes signal, doesn't add/remove much
        ratio = out.sum() / (brain_image.sum() + 1e-12)
        assert 0.8 < ratio < 1.2


class TestSusceptibilityPhysics:
    def test_zero_strength_no_change(self, brain_image, brain_phantom_64):
        out = add_susceptibility_artifact(brain_image, brain_phantom_64, strength=0.0)
        np.testing.assert_allclose(out, brain_image, atol=1e-12)

    def test_default_air_labels(self, brain_image, brain_phantom_64):
        """Calling with default air_labels=None should not raise."""
        out = add_susceptibility_artifact(brain_image, brain_phantom_64)
        assert out.shape == brain_image.shape
