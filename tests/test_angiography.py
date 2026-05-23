import numpy as np
import pytest
from angiography import (
    create_vascular_phantom,
    ANGIO_TISSUE_PROPERTIES,
    simulate_tof_mra,
    simulate_phase_contrast,
    compute_mip,
)


@pytest.fixture(scope="module")
def vascular_phantom():
    return create_vascular_phantom(64)


class TestCreateVascularPhantom:
    def test_shape(self, vascular_phantom):
        assert vascular_phantom.shape == (64, 64)

    def test_has_vessel_label(self, vascular_phantom):
        assert 5 in np.unique(vascular_phantom)

    def test_dtype_int(self, vascular_phantom):
        assert np.issubdtype(vascular_phantom.dtype, np.integer)

    def test_vessel_count_reasonable(self, vascular_phantom):
        n_vessels = np.sum(vascular_phantom == 5)
        assert n_vessels > 0


class TestAngioTissueProperties:
    def test_all_labels_present(self):
        for label in range(6):  # 0-5
            assert label in ANGIO_TISSUE_PROPERTIES

    def test_blood_label_5(self):
        props = ANGIO_TISSUE_PROPERTIES[5]
        for key in ("T1", "T2", "PD"):
            assert key in props

    def test_blood_high_pd(self):
        assert ANGIO_TISSUE_PROPERTIES[5]["PD"] > 0.5

    def test_background_pd_zero(self):
        assert ANGIO_TISSUE_PROPERTIES[0]["PD"] == 0.0


class TestSimulateTofMra:
    def test_output_shape(self, vascular_phantom):
        img = simulate_tof_mra(vascular_phantom, TR=25, TE=4, flip_angle=60)
        assert img.shape == vascular_phantom.shape

    def test_nonnegative(self, vascular_phantom):
        img = simulate_tof_mra(vascular_phantom, TR=25, TE=4, flip_angle=60)
        assert np.all(img >= 0)

    def test_background_zero(self, vascular_phantom):
        img = simulate_tof_mra(vascular_phantom, TR=25, TE=4, flip_angle=60)
        assert np.all(img[vascular_phantom == 0] == 0)

    def test_vessels_brighter_than_brain(self, vascular_phantom):
        img = simulate_tof_mra(vascular_phantom, TR=25, TE=4, flip_angle=60)
        if np.any(vascular_phantom == 5) and np.any(vascular_phantom == 2):
            vessel_signal = img[vascular_phantom == 5].mean()
            gm_signal = img[vascular_phantom == 2].mean()
            assert vessel_signal > gm_signal


class TestSimulatePhaseContrast:
    def test_output_shapes(self, vascular_phantom):
        mag, phase, speed = simulate_phase_contrast(vascular_phantom, venc=80, flow_velocity=60)
        assert mag.shape == vascular_phantom.shape
        assert phase.shape == vascular_phantom.shape
        assert speed.shape == vascular_phantom.shape

    def test_static_tissue_zero_phase(self, vascular_phantom):
        _, phase, _ = simulate_phase_contrast(vascular_phantom, venc=80, flow_velocity=60)
        gm_mask = vascular_phantom == 2
        if np.any(gm_mask):
            assert np.all(phase[gm_mask] == 0)

    def test_vessel_phase_nonzero(self, vascular_phantom):
        _, phase, _ = simulate_phase_contrast(vascular_phantom, venc=80, flow_velocity=60)
        vessel_mask = vascular_phantom == 5
        if np.any(vessel_mask):
            assert np.any(phase[vessel_mask] != 0)

    def test_velocity_encoded_within_minus_pi_pi(self, vascular_phantom):
        _, phase, _ = simulate_phase_contrast(vascular_phantom, venc=80, flow_velocity=60)
        vessel_phase = phase[vascular_phantom == 5]
        if len(vessel_phase):
            assert np.all(np.abs(vessel_phase) <= np.pi + 1e-9)

    def test_speed_nonnegative(self, vascular_phantom):
        _, _, speed = simulate_phase_contrast(vascular_phantom, venc=80, flow_velocity=60)
        assert np.all(speed >= 0)


class TestComputeMip:
    def test_basic_mip(self):
        slices = np.array([[[1, 2], [3, 4]],
                           [[5, 1], [2, 6]]])
        mip = compute_mip(slices)
        expected = np.array([[5, 2], [3, 6]])
        np.testing.assert_array_equal(mip, expected)

    def test_single_slice(self):
        slices = np.array([[[1, 2], [3, 4]]])
        mip = compute_mip(slices)
        np.testing.assert_array_equal(mip, [[1, 2], [3, 4]])

    def test_shape(self, vascular_phantom):
        imgs = np.stack([
            simulate_tof_mra(vascular_phantom, TR=25, TE=4, flip_angle=60)
            for _ in range(3)
        ])
        mip = compute_mip(imgs)
        assert mip.shape == vascular_phantom.shape
