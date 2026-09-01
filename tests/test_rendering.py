"""Tests for rendering.py — the Qt-free signal-rendering helpers."""

import numpy as np
import pytest

import rendering
import tissue_db
from signal_engine import spin_echo_signal, gradient_echo_signal, inversion_recovery_signal


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture
def props():
    return tissue_db.properties("3T")


@pytest.fixture
def brain_slice():
    """Small label slice: CSF(1) outer, GM(2), WM(3) core, fat(4) rim."""
    ph = np.zeros((40, 40), dtype=int)
    ph[2:38, 2:38] = 4     # fat rim
    ph[6:34, 6:34] = 1     # CSF
    ph[12:28, 12:28] = 2   # GM
    ph[17:23, 17:23] = 3   # WM
    return ph


def _median(img, ph, label):
    return float(np.median(img[ph == label]))


# --------------------------------------------------------------------------- #
# apply_gd
# --------------------------------------------------------------------------- #
def test_apply_gd_shortens_enhancing_t1(props):
    out = rendering.apply_gd(props, dose=0.2)
    # Fat/scalp (label 4) has the largest BBB fraction → most T1 shortening
    assert out[4]["T1"] < props[4]["T1"]
    assert out[1]["T1"] < props[1]["T1"]   # CSF enhances modestly


def test_apply_gd_zero_dose_is_identity(props):
    out = rendering.apply_gd(props, dose=0.0)
    for lab in props:
        assert out[lab]["T1"] == pytest.approx(props[lab]["T1"])


def test_apply_gd_higher_dose_shortens_more(props):
    lo = rendering.apply_gd(props, dose=0.1)
    hi = rendering.apply_gd(props, dose=0.5)
    assert hi[4]["T1"] < lo[4]["T1"]


def test_apply_gd_does_not_mutate_input(props):
    before = props[4]["T1"]
    rendering.apply_gd(props, dose=0.3)
    assert props[4]["T1"] == before


def test_apply_gd_leaves_non_enhancing_labels(props):
    out = rendering.apply_gd(props, dose=0.3)
    # Gas (label 12) has a zero enhancement fraction → T1 unchanged.
    assert rendering.GD_TISSUE_FRACTION[12] == 0.0
    assert out[12]["T1"] == pytest.approx(props[12]["T1"])


def test_apply_gd_enhances_blood_more_than_intact_bbb(props):
    """Blood (intravascular) must enhance far more than intact-BBB brain."""
    out = rendering.apply_gd(props, dose=0.3)
    blood_drop = 1 - out[11]["T1"] / props[11]["T1"]
    wm_drop = 1 - out[3]["T1"] / props[3]["T1"]
    assert blood_drop > 0.4          # strong vascular enhancement
    assert wm_drop < 0.1             # intact BBB barely changes
    assert blood_drop > wm_drop


# --------------------------------------------------------------------------- #
# param_maps
# --------------------------------------------------------------------------- #
def test_param_maps_fills_per_label(brain_slice, props):
    (t1,) = rendering.param_maps(brain_slice, props, ("T1",))
    assert t1[brain_slice == 3].std() == 0          # uniform within a label
    assert _median(t1, brain_slice, 3) == pytest.approx(props[3]["T1"])
    assert _median(t1, brain_slice, 1) == pytest.approx(props[1]["T1"])


def test_param_maps_multiple_keys(brain_slice, props):
    t1, t2, pd = rendering.param_maps(brain_slice, props, ("T1", "T2", "PD"))
    assert _median(t2, brain_slice, 2) == pytest.approx(props[2]["T2"])
    assert _median(pd, brain_slice, 2) == pytest.approx(props[2]["PD"])


def test_param_maps_missing_key_falls_back_to_t2(brain_slice, props):
    # No tissue defines "bogus"; helper falls back to that label's T2.
    (m,) = rendering.param_maps(brain_slice, props, ("bogus",))
    assert _median(m, brain_slice, 3) == pytest.approx(props[3]["T2"])


def test_param_maps_background_is_zero(brain_slice, props):
    # Label 0 has PD 0 but its T1 is still filled; background stays 0 only where
    # no label matches. Here every pixel is labelled, so verify shape instead.
    (t1,) = rendering.param_maps(brain_slice, props, ("T1",))
    assert t1.shape == brain_slice.shape


# --------------------------------------------------------------------------- #
# simulate_slice_props
# --------------------------------------------------------------------------- #
def test_simulate_slice_props_se_matches_signal_engine(brain_slice, props):
    img = rendering.simulate_slice_props(brain_slice, 600, 15, "SE", 0, 90, props)
    expect = spin_echo_signal(props[3]["T1"], props[3]["T2"], props[3]["PD"], 600, 15)
    assert _median(img, brain_slice, 3) == pytest.approx(expect)


def test_simulate_slice_props_gre_uses_t2star(brain_slice, props):
    img = rendering.simulate_slice_props(brain_slice, 200, 5, "GRE", 0, 30, props)
    expect = gradient_echo_signal(props[2]["T1"], props[2]["T2star"], props[2]["PD"],
                                  200, 5, 30)
    assert _median(img, brain_slice, 2) == pytest.approx(expect)


def test_simulate_slice_props_ir_uses_ti(brain_slice, props):
    img = rendering.simulate_slice_props(brain_slice, 9000, 90, "IR", 2548, 90, props)
    expect = inversion_recovery_signal(props[1]["T1"], props[1]["T2"], props[1]["PD"],
                                       9000, 90, 2548)
    assert _median(img, brain_slice, 1) == pytest.approx(expect)


def test_simulate_slice_props_t1_weighting_ordering(brain_slice, props):
    img = rendering.simulate_slice_props(brain_slice, 500, 15, "SE", 0, 90, props)
    wm = _median(img, brain_slice, 3)
    gm = _median(img, brain_slice, 2)
    csf = _median(img, brain_slice, 1)
    assert wm > gm > csf      # T1-weighted contrast


# --------------------------------------------------------------------------- #
# apply_mt
# --------------------------------------------------------------------------- #
def test_apply_mt_zero_power_is_identity(brain_slice, props):
    img = np.ones_like(brain_slice, dtype=float)
    out = rendering.apply_mt(img, brain_slice, props, 0, "Spin Echo", 600, 12, 90)
    assert np.array_equal(out, img)


def test_apply_mt_suppresses_white_matter_most(brain_slice, props):
    img = np.ones_like(brain_slice, dtype=float)
    out = rendering.apply_mt(img, brain_slice, props, 100, "Spin Echo", 600, 12, 90)
    supp_wm = 1 - _median(out, brain_slice, 3)
    supp_csf = 1 - _median(out, brain_slice, 1)
    assert supp_wm > supp_csf        # WM has higher bound-pool fraction
    assert 0.3 < supp_wm < 0.6       # clinically realistic WM MTR at full power


def test_apply_mt_shape_mismatch_is_identity(props):
    img = np.ones((10, 10))
    ph = np.ones((8, 8), dtype=int)
    assert np.array_equal(rendering.apply_mt(img, ph, props, 100, "Spin Echo", 600, 12, 90), img)


# --------------------------------------------------------------------------- #
# apply_b1
# --------------------------------------------------------------------------- #
def test_apply_b1_shape_mismatch_is_identity(props):
    img = np.ones((10, 10))
    ph = np.ones((8, 8), dtype=int)
    assert np.array_equal(rendering.apply_b1(img, ph, props, "Gradient Echo", 20, 200, 5, 3.0), img)


def test_apply_b1_gre_finite_and_modulates(brain_slice, props):
    img = rendering.simulate_slice_props(brain_slice, 200, 5, "GRE", 0, 20, props)
    out = rendering.apply_b1(img, brain_slice, props, "Gradient Echo", 20, 200, 5, 3.0)
    assert np.isfinite(out).all()
    assert out.shape == img.shape
    # Centre-bright B1 map → centre and edge differ for a low-flip GRE
    assert not np.allclose(out, img)


def test_apply_b1_se_center_near_nominal(brain_slice, props):
    img = rendering.simulate_slice_props(brain_slice, 600, 15, "SE", 0, 90, props)
    out = rendering.apply_b1(img, brain_slice, props, "Spin Echo", 90, 600, 15, 3.0)
    # At map centre B1≈nominal, so signal is essentially unchanged there.
    c = img.shape[0] // 2
    assert out[c, c] == pytest.approx(img[c, c], rel=0.05)


def test_apply_b1_field_strength_changes_magnitude(brain_slice, props):
    img = rendering.simulate_slice_props(brain_slice, 600, 15, "SE", 0, 90, props)
    o15 = rendering.apply_b1(img, brain_slice, props, "Spin Echo", 90, 600, 15, 1.5)
    o30 = rendering.apply_b1(img, brain_slice, props, "Spin Echo", 90, 600, 15, 3.0)
    # 3T uses larger B1 variation than 1.5T → larger edge deviation
    assert not np.allclose(o15, o30)


# --------------------------------------------------------------------------- #
# gre_fatwater_phase
# --------------------------------------------------------------------------- #
def test_gre_fatwater_no_fat_is_identity(props):
    ph = np.full((20, 20), 2, dtype=int)   # all GM, no fat
    img = np.ones_like(ph, dtype=float)
    assert np.array_equal(rendering.gre_fatwater_phase(img, ph, 5.0, 3.0), img)


def test_gre_fatwater_opposed_darker_than_inphase():
    import dixon
    ph = np.zeros((40, 40), dtype=int)
    ph[:, :20] = 4     # fat
    ph[:, 20:] = 2     # water (GM)
    img = np.where(ph == 4, 0.6, 0.3).astype(float)
    op = rendering.gre_fatwater_phase(img, ph, dixon.opposed_phase_te_ms(3.0), 3.0)
    ip = rendering.gre_fatwater_phase(img, ph, dixon.inphase_te_ms(3.0), 3.0)
    col = 19  # fat side of the fat-water boundary
    assert op[:, col].mean() < ip[:, col].mean()   # India-ink at opposed phase


def test_gre_fatwater_marrow_drops_on_opposed_phase():
    """Marrow is a fat+water mix *within* each voxel, so opposed-phase must
    drop its signal even deep inside the marrow — the basis of in/opposed
    imaging for marrow lesions (normal marrow drops; a metastasis doesn't)."""
    import dixon
    ph = np.zeros((40, 40), dtype=int)
    ph[:, :20] = 14    # marrow
    ph[:, 20:] = 2     # water (GM)
    img = np.where(ph == 14, 0.6, 0.3).astype(float)
    op = rendering.gre_fatwater_phase(img, ph, dixon.opposed_phase_te_ms(3.0), 3.0)
    ip = rendering.gre_fatwater_phase(img, ph, dixon.inphase_te_ms(3.0), 3.0)
    deep = (slice(None), slice(2, 10))   # well inside the marrow, away from the border
    assert op[deep].mean() < 0.8 * ip[deep].mean(), "no intra-voxel marrow drop"


# --------------------------------------------------------------------------- #
# gre_fw_phase_label
# --------------------------------------------------------------------------- #
def test_gre_fw_phase_label_classification():
    import dixon
    assert rendering.gre_fw_phase_label(dixon.inphase_te_ms(3.0), 3.0) == "In-phase"
    assert rendering.gre_fw_phase_label(dixon.opposed_phase_te_ms(3.0), 3.0) == "Opposed"
    # A quarter-cycle TE is neither in- nor opposed-phase
    quarter = dixon.opposed_phase_te_ms(3.0) / 2.0
    assert rendering.gre_fw_phase_label(quarter, 3.0).startswith("Partial")


# --------------------------------------------------------------------------- #
# g_factor
# --------------------------------------------------------------------------- #
def test_g_factor_no_acceleration_is_one():
    assert rendering.g_factor(1) == 1.0
    assert rendering.g_factor(0) == 1.0


def test_g_factor_increases_with_acceleration():
    g2 = rendering.g_factor(2)
    g3 = rendering.g_factor(3)
    g4 = rendering.g_factor(4)
    assert 1.0 < g2 < g3 < g4          # superlinear SENSE penalty
    assert g2 < 1.3                    # R=2 on an 8ch head coil is mild


def test_g_factor_matches_coil_median():
    import coil
    sens = coil.head_coil_array((96, 96), n_coils=8)
    expect = float(np.median(coil.g_factor_map(sens, 2)))
    assert rendering.g_factor(2) == pytest.approx(expect)


def test_g_factor_is_cached_deterministic():
    assert rendering.g_factor(3) == rendering.g_factor(3)


# --------------------------------------------------------------------------- #
# partial_volume
# --------------------------------------------------------------------------- #
def _two_tissue():
    ph = np.zeros((40, 40), dtype=int)
    ph[:, :20] = 2   # GM (signal 0.5)
    ph[:, 20:] = 3   # WM (signal 0.8)
    img = np.where(ph == 2, 0.5, 0.8).astype(float)
    return ph, img


def test_partial_volume_zero_sigma_is_identity():
    ph, img = _two_tissue()
    assert np.array_equal(rendering.partial_volume(img, ph, 0.0), img)


def test_partial_volume_preserves_interiors():
    ph, img = _two_tissue()
    out = rendering.partial_volume(img, ph, 1.5)
    assert out[:, 5] == pytest.approx(0.5, abs=1e-3)    # deep GM unchanged
    assert out[:, 35] == pytest.approx(0.8, abs=1e-3)   # deep WM unchanged


def test_partial_volume_mixes_at_boundary():
    ph, img = _two_tissue()
    out = rendering.partial_volume(img, ph, 1.5)
    # boundary column sits between GM (0.5) and WM (0.8) -> intermediate value
    edge = out[20, 19]
    assert 0.5 < edge < 0.8
    assert not np.isclose(edge, img[20, 19])


def test_partial_volume_shape_mismatch_is_identity():
    img = np.ones((10, 10))
    ph = np.ones((8, 8), dtype=int)
    assert np.array_equal(rendering.partial_volume(img, ph, 1.5), img)


# --------------------------------------------------------------------------- #
# EPI helpers
# --------------------------------------------------------------------------- #
def test_scale_to_peak_sets_p95_magnitude():
    f = np.linspace(-50, 200, 1000).reshape(20, 50)
    out = rendering.scale_to_peak(f, 80.0)
    assert np.percentile(np.abs(out), 95) == pytest.approx(80.0, rel=1e-6)
    # spatial pattern preserved (uniform rescale)
    nz = f != 0
    assert np.allclose((out[nz] / f[nz]).std(), 0.0, atol=1e-9)


def test_scale_to_peak_zero_and_flat():
    f = np.random.default_rng(0).normal(size=(16, 16))
    assert np.all(rendering.scale_to_peak(f, 0.0) == 0.0)        # peak 0 → no field
    assert np.all(rendering.scale_to_peak(np.zeros((8, 8)), 50.0) == 0.0)  # flat → 0


def test_scale_to_peak_drives_b0_distortion():
    # a real dipole field, scaled, distorts an EPI image
    import b0
    vol = np.zeros((24, 32, 32), int); vol[:, 8:24, 8:24] = 3   # tissue block in air
    field = b0.susceptibility_b0_map(vol, field_strength_T=3.0)
    b0_slice = rendering.scale_to_peak(field[12], 150.0)
    img = np.zeros((32, 32)); img[10:22, 10:22] = 1.0
    t2s = np.full_like(img, 50.0)
    clean = rendering.simulate_epi_slice(img, t2s, np.zeros_like(img), 0.8, 0.0, False)
    dist  = rendering.simulate_epi_slice(img, t2s, b0_slice, 0.8, 0.0, False)
    assert not np.allclose(dist, clean)        # the susceptibility field warps geometry


def test_epi_b0_field_scales_and_shape():
    f = rendering.epi_b0_field((64, 64), 100.0)
    assert f.shape == (64, 64)
    assert np.isfinite(f).all()
    # peak magnitude tracks the requested strength (localised blob ~1.0)
    assert 80 < np.abs(f).max() < 160
    assert np.allclose(rendering.epi_b0_field((64, 64), 0.0), 0.0)


def test_epi_slice_clean_is_faithful():
    # object in the top half; with no B0 and no ghost the recon stays there
    img = np.zeros((96, 96)); img[12:40, 30:66] = 1.0
    t2s = np.full_like(img, 50.0)
    out = rendering.simulate_epi_slice(img, t2s, np.zeros_like(img), 0.5, 0.0, False)
    assert np.abs(out)[48:].mean() < 0.01      # bottom (ghost) half stays empty


def test_epi_slice_nyquist_ghost_appears():
    img = np.zeros((96, 96)); img[12:40, 30:66] = 1.0
    t2s = np.full_like(img, 50.0); Z = np.zeros_like(img)
    clean = rendering.simulate_epi_slice(img, t2s, Z, 0.5, 0.0, False)
    ghost = rendering.simulate_epi_slice(img, t2s, Z, 0.5, 0.30, False)
    assert ghost[48:].mean() > 5 * clean[48:].mean()   # N/2 ghost in bottom half


def test_epi_slice_b0_distorts_geometry():
    # A block sitting in a uniform off-resonance field: B0 must shift it bodily
    # in the phase-encode (row) direction without destroying its signal.
    img = np.zeros((96, 96)); img[34:62, 30:66] = 1.0
    t2s = np.full_like(img, 50.0)
    b0 = np.full_like(img, 80.0)            # uniform off-resonance over the object
    clean = rendering.simulate_epi_slice(img, t2s, np.zeros_like(img), 0.8, 0.0, False)
    dist  = rendering.simulate_epi_slice(img, t2s, b0, 0.8, 0.0, False)

    def row_centroid(a):
        m = np.abs(a)
        return (m.sum(1) * np.arange(m.shape[0])).sum() / m.sum()
    # Geometry shifts...
    assert abs(row_centroid(dist) - row_centroid(clean)) > 0.5
    # ...but signal is conserved (the old model collapsed it to a thin lens).
    assert dist.sum() > 0.7 * clean.sum()


def test_epi_slice_b0_conserves_energy_no_collapse():
    """Regression: the EPI B0 model must warp geometry, not annihilate signal.

    The previous implementation built each k-space line from the 1-D FFT of an
    image *row* (confusing an image index with a k-space line index), which
    destroyed >90% of the signal and collapsed brain to a thin lens.
    """
    img = np.zeros((128, 128))
    yy, xx = np.ogrid[:128, :128]
    img[((yy - 64) ** 2 + (xx - 64) ** 2) < 48 ** 2] = 1.0
    t2s = np.full_like(img, 50.0)
    for peak in (20.0, 60.0, 150.0):
        b0 = rendering.epi_b0_field(img.shape, peak)
        out = rendering.simulate_epi_slice(img, t2s, b0, 0.5, 0.0, False)
        # FFT is unitary, so a pure phase forward model conserves energy: the
        # distorted image keeps essentially all the signal (allow for T2* blur
        # and edge cropping), nowhere near the old ~95 % loss.
        assert out.sum() > 0.7 * img.sum(), f"signal collapsed at {peak} Hz"


# --- Spectral fat saturation (CHESS) ----------------------------------------
def test_fat_sat_suppresses_fat_only():
    sl = np.zeros((10, 10), dtype=np.uint8); sl[:, :5] = 4; sl[:, 5:] = 6  # fat | muscle
    img = np.where(sl == 4, 1.0, 0.5)
    out = rendering.apply_fat_sat(img, sl)
    assert out[sl == 4].mean() < 0.2 * img[sl == 4].mean()   # fat nulled
    np.testing.assert_allclose(out[sl == 6], img[sl == 6])   # water untouched


def test_fat_sat_no_fat_unchanged():
    sl = np.full((6, 6), 6, dtype=np.uint8)
    img = np.ones((6, 6))
    np.testing.assert_array_equal(rendering.apply_fat_sat(img, sl), img)


def test_fat_sat_fails_in_off_resonance():
    """Where B0 off-resonance is worst, suppression fails and fat signal returns."""
    sl = np.full((10, 100), 4, dtype=np.uint8)        # all fat
    img = np.ones((10, 100))
    off = np.zeros((10, 100)); off[:, 96:] = 500.0     # small strong off-res patch (~4%)
    out = rendering.apply_fat_sat(img, sl, off)
    assert out[:, 98].mean() > 3 * out[:, 2].mean()    # failed patch much brighter than suppressed bulk


def test_fat_sat_suppresses_marrow():
    """Yellow marrow is ~80% fat chemically: spectral fat-sat must darken it
    (the knee PD FS hallmark — dark marrow), though less completely than pure
    fat because of its residual water signal."""
    sl = np.zeros((10, 12), dtype=np.uint8)
    sl[:, :4] = 4; sl[:, 4:8] = 14; sl[:, 8:] = 6     # fat | marrow | muscle
    img = np.ones((10, 12))
    out = rendering.apply_fat_sat(img, sl)
    assert out[sl == 14].mean() < 0.4                  # marrow clearly suppressed
    assert out[sl == 14].mean() >= out[sl == 4].mean()  # but not below pure fat
    np.testing.assert_allclose(out[sl == 6], img[sl == 6])  # water untouched


def test_fat_sat_marrow_fails_in_off_resonance_too():
    sl = np.full((10, 100), 14, dtype=np.uint8)       # all marrow
    img = np.ones((10, 100))
    off = np.zeros((10, 100)); off[:, 96:] = 500.0
    out = rendering.apply_fat_sat(img, sl, off)
    assert out[:, 98].mean() > 2 * out[:, 2].mean()
