import pytest
from presets import PRESETS, get_preset, get_preset_names, estimate_sar

REQUIRED_KEYS = {"sequence", "TR", "TE", "TI", "flip_angle", "matrix_size",
                 "FOV", "bandwidth", "NEX", "description"}


class TestPresets:
    def test_all_presets_have_required_keys(self):
        for name, p in PRESETS.items():
            missing = REQUIRED_KEYS - set(p.keys())
            assert not missing, f"Preset '{name}' missing: {missing}"

    def test_tr_positive(self):
        for name, p in PRESETS.items():
            assert p["TR"] > 0, f"{name}: TR must be positive"

    def test_te_positive(self):
        for name, p in PRESETS.items():
            assert p["TE"] > 0, f"{name}: TE must be positive"

    def test_te_less_than_tr(self):
        for name, p in PRESETS.items():
            assert p["TE"] < p["TR"], f"{name}: TE must be less than TR"

    def test_flip_angle_in_range(self):
        for name, p in PRESETS.items():
            assert 0 < p["flip_angle"] <= 90, f"{name}: flip_angle out of range"

    def test_nex_positive(self):
        for name, p in PRESETS.items():
            assert p["NEX"] >= 1, f"{name}: NEX must be >= 1"

    def test_matrix_size_power_of_two_or_common(self):
        common = {64, 128, 192, 256, 320, 384, 512}
        for name, p in PRESETS.items():
            assert p["matrix_size"] in common, f"{name}: unexpected matrix_size {p['matrix_size']}"


class TestGetPreset:
    def test_returns_dict_for_known_preset(self):
        p = get_preset("Brain T1 SE")
        assert isinstance(p, dict)

    def test_returns_none_for_unknown(self):
        assert get_preset("Nonexistent Preset XYZ") is None

    def test_round_trip(self):
        for name in get_preset_names():
            assert get_preset(name) is not None


class TestGetPresetNames:
    def test_returns_list(self):
        names = get_preset_names()
        assert isinstance(names, list)
        assert len(names) > 0

    def test_all_names_are_strings(self):
        for name in get_preset_names():
            assert isinstance(name, str)

    def test_brain_t1_present(self):
        assert "Brain T1 SE" in get_preset_names()


class TestEstimateSAR:
    def test_returns_dict(self):
        sar = estimate_sar(90, 500, sequence="SE")
        assert isinstance(sar, dict)

    def test_required_keys(self):
        sar = estimate_sar(90, 500, sequence="SE")
        for key in ("whole_body", "head", "limit_whole_body", "limit_head", "exceeds_limit"):
            assert key in sar

    def test_head_higher_than_whole_body(self):
        sar = estimate_sar(90, 500, sequence="SE")
        assert sar["head"] > sar["whole_body"]

    def test_large_flip_small_tr_exceeds_limit(self):
        sar = estimate_sar(90, 5, sequence="SE", num_slices=20)
        assert sar["exceeds_limit"]

    def test_small_flip_large_tr_within_limit(self):
        sar = estimate_sar(15, 5000, sequence="GRE", num_slices=5)
        assert not sar["exceeds_limit"]

    def test_higher_flip_angle_more_sar(self):
        sar_low = estimate_sar(10, 500, sequence="SE")
        sar_high = estimate_sar(90, 500, sequence="SE")
        assert sar_high["whole_body"] > sar_low["whole_body"]

    def test_gre_lower_sar_than_se(self):
        sar_se = estimate_sar(90, 500, sequence="SE")
        sar_gre = estimate_sar(90, 500, sequence="GRE")
        assert sar_gre["whole_body"] < sar_se["whole_body"]
