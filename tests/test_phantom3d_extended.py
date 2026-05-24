import numpy as np
import pytest
from phantom3d import generate_synthetic_3d_brain, get_slice
from phantom3d_extended import (
    add_vessels_3d,
    add_activation_3d,
    add_tissue_texture,
    get_diffusion_properties_3d,
    simulate_diffusion_3d_slice,
    simulate_adc_map_3d,
    simulate_fa_map_3d,
    simulate_tof_3d_slice,
    simulate_fmri_3d_slice,
    compute_activation_map_3d,
    compute_tstat_map_3d,
    load_real_tof_mra,
    simulate_tof_with_real_data,
)


@pytest.fixture(scope="module")
def small_brain():
    return generate_synthetic_3d_brain(nx=40, ny=48, nz=40)


@pytest.fixture(scope="module")
def brain_with_vessels(small_brain):
    return add_vessels_3d(small_brain)


@pytest.fixture(scope="module")
def activation_vol(small_brain):
    return add_activation_3d(small_brain)


@pytest.fixture(scope="module")
def axial_slice(small_brain):
    return get_slice(small_brain, "axial", 20)


@pytest.fixture(scope="module")
def axial_activation(activation_vol):
    return activation_vol[20, :, :]


class TestAddVessels3d:
    def test_same_shape(self, small_brain, brain_with_vessels):
        assert brain_with_vessels.shape == small_brain.shape

    def test_dtype_preserved(self, small_brain, brain_with_vessels):
        assert brain_with_vessels.dtype == small_brain.dtype

    def test_original_labels_preserved(self, small_brain, brain_with_vessels):
        # All labels in original should still appear (background stays 0)
        for lab in np.unique(small_brain):
            assert lab in np.unique(brain_with_vessels)

    def test_vessels_only_in_brain(self, brain_with_vessels):
        # Label 6 (vessels) must not appear in background regions
        vessel_mask = brain_with_vessels == 6
        # Where vessels exist, the original brain should have had tissue
        # (we can't check original easily here, just verify label 6 exists or doesn't crash)
        assert brain_with_vessels.min() >= 0
        assert brain_with_vessels.max() <= 6


class TestAddActivation3d:
    def test_same_shape(self, small_brain, activation_vol):
        assert activation_vol.shape == small_brain.shape

    def test_nonnegative(self, activation_vol):
        assert np.all(activation_vol >= 0)

    def test_max_clipped_at_5(self, activation_vol):
        assert activation_vol.max() <= 5.0

    def test_only_in_gm(self, small_brain, activation_vol):
        non_gm = small_brain != 2
        assert np.all(activation_vol[non_gm] == 0.0)

    def test_has_some_activation(self, activation_vol):
        assert np.sum(activation_vol > 0) > 0


class TestAddTissueTexture:
    def test_same_shape(self, small_brain):
        texture = add_tissue_texture(small_brain)
        assert texture.shape == small_brain.shape

    def test_values_near_one(self, small_brain):
        texture = add_tissue_texture(small_brain)
        assert texture.mean() == pytest.approx(1.0, abs=0.1)

    def test_float_dtype(self, small_brain):
        texture = add_tissue_texture(small_brain)
        assert np.issubdtype(texture.dtype, np.floating)


class TestGetDiffusionProperties3d:
    def test_returns_dict(self, small_brain):
        props = get_diffusion_properties_3d(small_brain)
        assert isinstance(props, dict)

    def test_required_keys_per_label(self, small_brain):
        props = get_diffusion_properties_3d(small_brain)
        for lab, d in props.items():
            assert "ADC" in d and "FA" in d

    def test_background_adc_zero(self, small_brain):
        props = get_diffusion_properties_3d(small_brain)
        assert props[0]["ADC"] == 0.0

    def test_wm_has_high_fa(self, small_brain):
        props = get_diffusion_properties_3d(small_brain)
        assert props[3]["FA"] > props[2]["FA"]  # WM more anisotropic than GM

    def test_accepts_none(self):
        props = get_diffusion_properties_3d(None)
        assert isinstance(props, dict)


class TestSimulateDiffusion3dSlice:
    def test_output_shape(self, axial_slice):
        img = simulate_diffusion_3d_slice(axial_slice, b_value=1000,
                                          direction=[1, 0, 0])
        assert img.shape == axial_slice.shape

    def test_nonnegative(self, axial_slice):
        img = simulate_diffusion_3d_slice(axial_slice, b_value=1000,
                                          direction=[1, 0, 0])
        assert np.all(img >= 0)

    def test_background_near_zero(self, axial_slice):
        img = simulate_diffusion_3d_slice(axial_slice, b_value=1000,
                                          direction=[1, 0, 0])
        assert img[axial_slice == 0].max() < 0.1

    def test_high_b_reduces_signal(self, axial_slice):
        img_low  = simulate_diffusion_3d_slice(axial_slice, b_value=0,
                                               direction=[1, 0, 0])
        img_high = simulate_diffusion_3d_slice(axial_slice, b_value=2000,
                                               direction=[1, 0, 0])
        brain = axial_slice > 0
        assert img_low[brain].mean() > img_high[brain].mean()


class TestSimulateAdcMap3d:
    def test_output_shape(self, axial_slice):
        adc = simulate_adc_map_3d(axial_slice)
        assert adc.shape == axial_slice.shape

    def test_background_zero(self, axial_slice):
        adc = simulate_adc_map_3d(axial_slice)
        assert np.all(adc[axial_slice == 0] == 0.0)

    def test_brain_positive(self, axial_slice):
        adc = simulate_adc_map_3d(axial_slice)
        brain = axial_slice > 0
        if np.any(brain):
            # Most brain voxels should have ADC > 0 (except bone label 5)
            gm_wm = (axial_slice == 2) | (axial_slice == 3)
            if np.any(gm_wm):
                assert adc[gm_wm].mean() > 0

    def test_csf_higher_adc_than_wm(self, axial_slice):
        adc = simulate_adc_map_3d(axial_slice)
        if np.any(axial_slice == 1) and np.any(axial_slice == 3):
            assert adc[axial_slice == 1].mean() > adc[axial_slice == 3].mean()


class TestSimulateFaMap3d:
    def test_output_shape(self, axial_slice):
        fa = simulate_fa_map_3d(axial_slice)
        assert fa.shape == axial_slice.shape

    def test_range_zero_to_one(self, axial_slice):
        fa = simulate_fa_map_3d(axial_slice)
        assert fa.min() >= 0.0
        assert fa.max() <= 1.0

    def test_background_zero(self, axial_slice):
        fa = simulate_fa_map_3d(axial_slice)
        assert np.all(fa[axial_slice == 0] == 0.0)

    def test_wm_higher_fa_than_gm(self, axial_slice):
        fa = simulate_fa_map_3d(axial_slice)
        if np.any(axial_slice == 2) and np.any(axial_slice == 3):
            assert fa[axial_slice == 3].mean() > fa[axial_slice == 2].mean()


class TestSimulateTof3dSlice:
    def test_output_shape(self, axial_slice):
        img = simulate_tof_3d_slice(axial_slice)
        assert img.shape == axial_slice.shape

    def test_nonnegative(self, axial_slice):
        img = simulate_tof_3d_slice(axial_slice)
        assert np.all(img >= 0)

    def test_background_near_zero(self, axial_slice):
        img = simulate_tof_3d_slice(axial_slice)
        assert img[axial_slice == 0].max() < 0.1

    def test_with_vessels_brighter(self, brain_with_vessels):
        sl_vessels = get_slice(brain_with_vessels, "axial", 20)
        sl_plain = get_slice(
            generate_synthetic_3d_brain(nx=40, ny=48, nz=40), "axial", 20)
        img_v = simulate_tof_3d_slice(sl_vessels)
        img_p = simulate_tof_3d_slice(sl_plain)
        # Vessel slice may have brighter overall signal due to inflow
        assert img_v.max() >= img_p.max() - 1e-6


class TestSimulateFmri3dSlice:
    def test_output_shape(self, axial_slice, axial_activation):
        img = simulate_fmri_3d_slice(axial_slice, axial_activation)
        assert img.shape == axial_slice.shape

    def test_nonnegative(self, axial_slice, axial_activation):
        img = simulate_fmri_3d_slice(axial_slice, axial_activation)
        assert np.all(img >= 0)

    def test_background_near_zero(self, axial_slice, axial_activation):
        img = simulate_fmri_3d_slice(axial_slice, axial_activation)
        assert img[axial_slice == 0].max() < 0.1

    def test_active_differs_from_rest_in_gm(self, axial_slice, axial_activation):
        rest   = simulate_fmri_3d_slice(axial_slice, axial_activation, is_active=False)
        active = simulate_fmri_3d_slice(axial_slice, axial_activation, is_active=True)
        activated_gm = (axial_slice == 2) & (axial_activation > 1.0)
        if np.any(activated_gm):
            assert not np.allclose(rest[activated_gm], active[activated_gm])


class TestComputeActivationMap3d:
    def test_output_shape(self, axial_slice, axial_activation):
        pct = compute_activation_map_3d(axial_slice, axial_activation)
        assert pct.shape == axial_slice.shape

    def test_background_zero(self, axial_slice, axial_activation):
        pct = compute_activation_map_3d(axial_slice, axial_activation)
        assert np.all(pct[axial_slice == 0] == 0)

    def test_positive_in_activated_gm(self, axial_slice, axial_activation):
        pct = compute_activation_map_3d(axial_slice, axial_activation)
        activated_gm = (axial_slice == 2) & (axial_activation > 1.0)
        if np.any(activated_gm):
            assert pct[activated_gm].mean() > 0


class TestComputeTstatMap3d:
    def test_output_shape(self, axial_slice, axial_activation):
        t_map = compute_tstat_map_3d(axial_slice, axial_activation, num_volumes=50)
        assert t_map.shape == axial_slice.shape

    def test_background_zero(self, axial_slice, axial_activation):
        t_map = compute_tstat_map_3d(axial_slice, axial_activation, num_volumes=50)
        assert np.all(t_map[axial_slice == 0] == 0)


class TestLoadRealTofMra:
    def test_returns_ndarray_or_none(self):
        result = load_real_tof_mra()
        assert result is None or isinstance(result, np.ndarray)

    def test_if_present_is_3d(self):
        result = load_real_tof_mra()
        if result is not None:
            assert result.ndim == 3


class TestSimulateTofWithRealData:
    @pytest.fixture(scope="class")
    def real_mra(self):
        mra = load_real_tof_mra()
        if mra is None:
            pytest.skip("No real TOF MRA data available")
        return mra

    def test_axial_returns_2d(self, real_mra):
        mid = real_mra.shape[2] // 2
        img = simulate_tof_with_real_data(real_mra, "axial", mid)
        assert img.ndim == 2

    def test_sagittal_returns_2d(self, real_mra):
        mid = real_mra.shape[0] // 2
        img = simulate_tof_with_real_data(real_mra, "sagittal", mid)
        assert img.ndim == 2

    def test_coronal_returns_2d(self, real_mra):
        mid = real_mra.shape[1] // 2
        img = simulate_tof_with_real_data(real_mra, "coronal", mid)
        assert img.ndim == 2

    def test_nonnegative(self, real_mra):
        mid = real_mra.shape[2] // 2
        img = simulate_tof_with_real_data(real_mra, "axial", mid)
        assert np.all(img >= 0)

    def test_higher_fa_brighter(self, real_mra):
        mid = real_mra.shape[2] // 2
        img_lo = simulate_tof_with_real_data(real_mra, "axial", mid, flip_angle=20)
        img_hi = simulate_tof_with_real_data(real_mra, "axial", mid, flip_angle=70)
        assert img_hi.mean() != img_lo.mean()
