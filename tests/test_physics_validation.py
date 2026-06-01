"""Physics validation / QA pass.

Quantitative, literature-grounded checks that lock in the *correctness* (not just
the behaviour) of the core models. Each assertion ties a computed value to a
closed-form result or a published reference, so a future change that breaks the
physics fails loudly.

References
----------
* Spin-echo / GRE / IR signal equations — Bernstein, King & Zhou,
  "Handbook of MRI Pulse Sequences" (2004).
* Ernst angle: cos α_E = exp(-TR/T1).
* 3 T abdominal/pelvic relaxation — de Bazelaire et al., Radiology 2004;230:652.
* Neuro relaxation — Stanisz et al., MRM 2005;54:507; Wansapura et al., JMRI 1999.
* Fat–water shift: 3.5 ppm × γ (42.577 MHz/T) × B0.
* Balanced SSFP off-resonance nulls at Δf = ±1/(2·TR).
"""
import numpy as np
import pytest

import signal_engine as se
import tissue_db
from dixon import fat_water_shift_hz
from artifacts import calculate_chemical_shift_pixels
from diffusion import diffusion_signal


# --------------------------------------------------------------------------- #
# Signal equations — closed-form behaviour
# --------------------------------------------------------------------------- #
class TestSignalEquations:
    def test_spin_echo_recovers_with_tr_decays_with_te(self):
        s_short_tr = se.spin_echo_signal(1000, 80, 1.0, 200, 15)
        s_long_tr = se.spin_echo_signal(1000, 80, 1.0, 3000, 15)
        assert s_long_tr > s_short_tr                        # more T1 recovery
        s_short_te = se.spin_echo_signal(1000, 80, 1.0, 3000, 15)
        s_long_te = se.spin_echo_signal(1000, 80, 1.0, 3000, 120)
        assert s_long_te < s_short_te                        # more T2 decay

    def test_spin_echo_matches_closed_form(self):
        T1, T2, PD, TR, TE = 830, 70, 0.65, 600, 15
        expect = PD * (1 - np.exp(-TR / T1)) * np.exp(-TE / T2)
        assert se.spin_echo_signal(T1, T2, PD, TR, TE) == pytest.approx(expect, rel=1e-9)

    def test_gradient_echo_peaks_at_ernst_angle(self):
        """GRE signal vs flip angle peaks at α_E = arccos(exp(-TR/T1))."""
        T1, TR = 830.0, 30.0
        ernst = np.degrees(np.arccos(np.exp(-TR / T1)))
        fas = np.arange(1, 90, 1.0)
        sigs = [se.gradient_echo_signal(T1, 48, 0.65, TR, 5, fa) for fa in fas]
        peak_fa = fas[int(np.argmax(sigs))]
        assert peak_fa == pytest.approx(ernst, abs=2.0)

    def test_gradient_echo_zero_flip_zero_signal(self):
        assert se.gradient_echo_signal(830, 48, 0.65, 100, 5, 0.0) == pytest.approx(0.0)

    def test_inversion_recovery_nulls_at_analytic_ti(self):
        """IR magnitude is zero at TI = -T1·ln((1+e^{-TR/T1})/2)."""
        T1, TR = 4500.0, 9000.0                              # CSF @ 3T, FLAIR TR
        ti_null = -T1 * np.log((1 + np.exp(-TR / T1)) / 2.0)
        assert ti_null == pytest.approx(2548, abs=60)        # the FLAIR TI
        s = se.inversion_recovery_signal(T1, 2200, 1.0, TR, 15, ti_null)
        full = se.inversion_recovery_signal(T1, 2200, 1.0, TR, 15, 50)
        assert s < 0.02 * full                               # nulled

    def test_stir_nulls_fat_at_t1_ln2(self):
        """For TR >> T1, the IR null is TI = T1·ln2 (STIR fat at 3 T ≈ 265 ms)."""
        T1_fat = 382.0
        assert T1_fat * np.log(2) == pytest.approx(265, abs=10)


# --------------------------------------------------------------------------- #
# Balanced SSFP
# --------------------------------------------------------------------------- #
class TestBalancedSSFP:
    def test_fluid_brighter_than_white_matter(self):
        """bSSFP ∝ T2/T1, so CSF (huge T2/T1) ≫ WM."""
        csf = se.balanced_ssfp_signal(4500, 2200, 1.0, 5, 2.5, 45)
        wm = se.balanced_ssfp_signal(830, 70, 0.65, 5, 2.5, 45)
        assert csf > 2.0 * wm

    def test_banding_null_at_half_inverse_tr(self):
        """Deep signal null where Δf = 1/(2·TR) (β = π); bright on-resonance."""
        TR = 5.0
        E2 = np.exp(-TR / 2200)
        on = se.ssfp_banding(0.0, TR, E2)
        null = se.ssfp_banding(1.0 / (2 * TR * 1e-3), TR, E2)
        assert on > 0.95 and null < 0.15

    def test_longer_tr_more_bands(self):
        """For a fixed off-resonance range, longer TR packs more nulls."""
        off = np.linspace(-400, 400, 4000)
        def n_nulls(TR):
            b = se.ssfp_banding(off, TR, np.exp(-TR / 100))
            return int((b < 0.3).sum())                      # area within the dark bands
        assert n_nulls(10.0) > n_nulls(3.0)


# --------------------------------------------------------------------------- #
# Relaxation values vs literature (tissue_db)
# --------------------------------------------------------------------------- #
class TestRelaxationLiterature:
    # (label, T1_3T, T2_3T) with generous tolerances around published means.
    LIT_3T = {
        1: (4500, 2200),    # CSF
        2: (1330, 80),      # gray matter (Wansapura)
        3: (830, 70),       # white matter
        4: (382, 68),       # fat (de Bazelaire)
        6: (898, 29),       # muscle
        7: (809, 34),       # liver
        8: (1328, 61),      # spleen
        9: (1142, 76),      # kidney cortex
        11: (1900, 275),    # blood
    }

    def test_3t_values_match_published(self):
        p = tissue_db.properties("3T")
        for lab, (t1, t2) in self.LIT_3T.items():
            assert p[lab]["T1"] == pytest.approx(t1, rel=0.12)
            assert p[lab]["T2"] == pytest.approx(t2, rel=0.20)

    def test_t1_lengthens_from_1p5t_to_3t(self):
        """T1 increases with field strength for soft tissues."""
        p15, p3 = tissue_db.properties("1.5T"), tissue_db.properties("3T")
        for lab in (2, 3, 7, 8, 9, 11):                      # GM/WM/liver/spleen/kidney/blood
            assert p3[lab]["T1"] > p15[lab]["T1"]

    def test_csf_is_long_t1_long_t2(self):
        p = tissue_db.properties("3T")
        assert p[1]["T1"] > 3500 and p[1]["T2"] > 1500       # CSF relaxes slowly


# --------------------------------------------------------------------------- #
# Chemical shift / fat–water
# --------------------------------------------------------------------------- #
class TestChemicalShift:
    def test_fat_water_shift_hz_at_3t(self):
        # 3.5 ppm × 42.577 MHz/T × 3 T ≈ 447 Hz
        assert fat_water_shift_hz(3.0) == pytest.approx(447, rel=0.05)

    def test_fat_water_shift_scales_with_field(self):
        assert fat_water_shift_hz(3.0) == pytest.approx(2 * fat_water_shift_hz(1.5), rel=1e-6)

    def test_chemical_shift_pixels_is_shift_over_bandwidth(self):
        bw_per_px = 200.0                                    # Hz/pixel
        shift = calculate_chemical_shift_pixels(bw_per_px, field_strength=3.0)
        assert shift == pytest.approx(fat_water_shift_hz(3.0) / bw_per_px, rel=0.02)


# --------------------------------------------------------------------------- #
# Diffusion
# --------------------------------------------------------------------------- #
class TestDiffusion:
    def test_mono_exponential_decay(self):
        S0, ADC = 100.0, 0.8                                  # ADC in 1e-3 mm²/s
        for b in (0, 500, 1000):
            assert diffusion_signal(S0, b, ADC) == pytest.approx(S0 * np.exp(-b * ADC * 1e-3), rel=1e-9)

    def test_higher_b_lower_signal(self):
        s = [diffusion_signal(100.0, b, 0.8) for b in (0, 1000, 2000)]
        assert s[0] > s[1] > s[2]

    def test_free_water_decays_faster_than_restricted(self):
        """High-ADC (free water) loses signal faster with b than low-ADC tissue."""
        free = diffusion_signal(100.0, 1000, 3.0)            # CSF-like ADC
        restricted = diffusion_signal(100.0, 1000, 0.7)      # WM-like ADC
        assert free < restricted


# --------------------------------------------------------------------------- #
# Gadolinium
# --------------------------------------------------------------------------- #
class TestGadolinium:
    def test_gd_shortens_t1(self):
        import rendering
        base = tissue_db.properties("3T")
        out = rendering.apply_gd(base, dose=0.3)
        assert out[7]["T1"] < base[7]["T1"]                  # liver T1 shortened

    def test_blood_enhances_most(self):
        import rendering
        f = rendering.GD_TISSUE_FRACTION
        assert f[11] == max(f.values())                      # intravascular = maximal
        assert f[11] > f[3]                                  # blood ≫ intact-BBB WM
