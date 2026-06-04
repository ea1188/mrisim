"""Headless tests for the browser/Pyodide adapter (web_adapter).

These run the *same* engine the browser does — no Qt, no browser — and assert
that `render()` returns a real PNG + JSON-safe metrics for every sequence, every
web region, presets, the 3-D acquire-once/reformat path, and the JSON round-trip
the JS shell uses. They guard the Python half of the web build so the browser
layer only has to worry about wiring.
"""
import base64
import json

import numpy as np
import pytest

import web_adapter as wa

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

SEQUENCES = [
    "Spin Echo", "FSE / TSE", "Gradient Echo", "Inversion Recovery",
    "Balanced SSFP", "Diffusion (DWI)", "MR Angiography", "fMRI (BOLD)",
    "Quantitative (qMRI)", "Echo Planar (EPI)",
]


def _decode(data_url, ctx=""):
    """A data URL must carry a real, non-trivial PNG."""
    assert isinstance(data_url, str) and data_url.startswith("data:image/png;base64,"), \
        f"{ctx}: not a PNG data URL"
    raw = base64.b64decode(data_url.split(",", 1)[1])
    assert raw[:8] == _PNG_MAGIC, f"{ctx}: bad PNG header"
    assert len(raw) > 1000, f"{ctx}: PNG suspiciously small ({len(raw)} bytes)"
    return raw


def _assert_good_render(r, ctx=""):
    _decode(r["image"], f"{ctx} image")
    _decode(r["curve"], f"{ctx} curve")
    # metrics must be JSON-serialisable (no numpy scalar types leaking out)
    json.dumps(r["metrics"])
    assert np.isfinite(r["metrics"]["scan_time"]) and r["metrics"]["scan_time"] > 0
    assert np.isfinite(r["metrics"]["snr_wm"])


# --------------------------------------------------------------------------- #
def test_init_reports_choices():
    info = wa.init()
    assert "Brain" in info["regions"]
    assert set(info["regions"]) == set(wa.WEB_REGIONS)
    assert len(info["presets"]) > 0
    assert info["dims"]["axial"] > 0 and info["max_slice"] > 0


@pytest.mark.parametrize("seq", SEQUENCES)
def test_every_sequence_renders(seq):
    wa.init()
    r = wa.render({"region": "Brain", "orientation": "axial", "slice_idx": 95,
                   "params": {"sequence": seq, "TR": 500, "TE": 15}})
    _assert_good_render(r, seq)
    assert r["orientation"] == "axial" and r["slice_idx"] == 95


@pytest.mark.parametrize("orient", ["axial", "coronal", "sagittal"])
def test_every_orientation_renders(orient):
    wa.init()
    r = wa.render({"region": "Brain", "orientation": orient, "slice_idx": 80,
                   "params": {"sequence": "Spin Echo"}})
    _assert_good_render(r, orient)
    assert r["orientation"] == orient


@pytest.mark.parametrize("region", wa.WEB_REGIONS)
def test_every_web_region_renders(region):
    d = wa.set_region(region)
    assert d["dims"]["axial"] > 0
    r = wa.render({"region": region, "orientation": "axial",
                   "slice_idx": d["max_slice"] // 2,
                   "params": {"sequence": "Spin Echo", "TR": 600, "TE": 12}})
    _assert_good_render(r, region)


def test_metrics_are_plain_json_types():
    wa.init()
    m = wa.render({"region": "Brain", "orientation": "axial", "slice_idx": 90,
                   "params": {"sequence": "Spin Echo"}})["metrics"]
    for k, v in m.items():
        assert not isinstance(v, np.generic), f"{k} is a numpy scalar, not JSON-safe"


def test_slice_index_is_clamped():
    wa.init()
    r = wa.render({"region": "Brain", "orientation": "axial", "slice_idx": 99999,
                   "params": {"sequence": "Spin Echo"}})
    assert 0 <= r["slice_idx"] <= r["max_slice"]


# --------------------------------------------------------------------------- #
#  3-D acquire-once / reformat
# --------------------------------------------------------------------------- #
def test_3d_acquire_then_reformat_reuses_block():
    wa.init()
    p = {"sequence": "Gradient Echo", "acq3d": True, "n_partitions": 24}
    wa.render({"region": "Brain", "orientation": "axial", "slice_idx": 95, "params": p})
    block = id(wa._host().sim._recon3d)
    r = wa.render({"region": "Brain", "orientation": "coronal", "slice_idx": 110, "params": p})
    assert id(wa._host().sim._recon3d) == block, "orientation change must reformat, not re-scan"
    _assert_good_render(r, "3D reformat")


def test_3d_param_change_reacquires():
    wa.init()
    base = {"sequence": "Spin Echo", "acq3d": True, "n_partitions": 16}
    wa.render({"region": "Brain", "orientation": "axial", "slice_idx": 95, "params": base})
    block = id(wa._host().sim._recon3d)
    changed = dict(base, TE=80)
    wa.render({"region": "Brain", "orientation": "axial", "slice_idx": 95, "params": changed})
    assert id(wa._host().sim._recon3d) != block, "scan-affecting change must re-acquire"


# --------------------------------------------------------------------------- #
#  Presets + JSON round-trip (the JS shell's contract)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("name", wa.presets_mod.get_preset_names())
def test_every_preset_resolves(name):
    """Every preset must resolve to a valid region/plane/params bundle (cheap —
    no render)."""
    bundle = wa.apply_preset(name)
    assert bundle["region"] is not None
    assert bundle["orientation"] in ("axial", "coronal", "sagittal")
    assert "sequence" in bundle["params"]


def test_sample_presets_render():
    """Render a representative spread of web-region presets end to end (the heavy
    full-render coverage is the per-sequence test above; this proves the preset →
    params → render path)."""
    rendered = 0
    for name in wa.presets_mod.get_preset_names():
        bundle = wa.apply_preset(name)
        if bundle["region"] != "Brain":
            continue
        d = wa.set_region("Brain")
        r = wa.render({"region": "Brain", "orientation": bundle["orientation"],
                       "slice_idx": d["max_slice"] // 2, "params": bundle["params"]})
        _assert_good_render(r, name)
        rendered += 1
        if rendered >= 5:
            break
    assert rendered >= 3, "expected several Brain presets to render"


def test_window_level_changes_image():
    """The window/level passed in the payload must change the rendered PNG (the
    web window/level drag drives this)."""
    wa.init()
    base = {"region": "Brain", "orientation": "axial", "slice_idx": 95,
            "params": {"sequence": "Spin Echo"}}
    a = wa.render(base)["image"]
    b = wa.render({**base, "window_width": 0.4, "window_level": 0.3})["image"]
    _decode(a, "default W/L"); _decode(b, "custom W/L")
    assert a != b, "window/level did not affect the image"


def test_render_json_roundtrip():
    wa.init()
    payload = json.dumps({"region": "Brain", "orientation": "axial",
                          "slice_idx": 90, "params": {"sequence": "Spin Echo"}})
    out = json.loads(wa.render_json(payload))
    _assert_good_render(out, "render_json")
