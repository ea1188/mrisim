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
    "Balanced SSFP", "Diffusion (DWI)", "MR Angiography", "Susceptibility (SWI)",
    "fMRI (BOLD)", "Quantitative (qMRI)", "Echo Planar (EPI)",
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


@pytest.mark.parametrize("orient", ["axial", "coronal", "sagittal"])
def test_scout_renders(orient):
    """The 3-plane FOV-planning localizer renders a real PNG for every plane."""
    wa.init()
    png = wa.render_scout({"region": "Brain", "orientation": orient, "slice_idx": 80})
    _decode(png, f"scout {orient}")
    out = json.loads(wa.render_scout_json(json.dumps(
        {"region": "Brain", "orientation": orient, "slice_idx": 80})))
    _decode(out["scout"], f"scout_json {orient}")
    # Panel geometry drives the click-to-move-slice interaction.
    panels = out["panels"]
    assert len(panels) == 3
    for p in panels:
        assert set(p) >= {"name", "box", "map", "n", "flip"}
        assert len(p["box"]) == 4
        assert p["map"] in ("row", "col", "none")
    # exactly one panel is the acquired plane (no remap); the other two reposition
    assert sum(p["map"] == "none" for p in panels) == 1
    assert all(p["n"] > 0 for p in panels if p["map"] != "none")


def test_scout_acq_panel_has_fov_box():
    """The acquired-plane panel reports a draggable FOV-box rect (image fraction)."""
    wa.init()
    out = json.loads(wa.render_scout_json(json.dumps(
        {"region": "Brain", "orientation": "axial", "slice_idx": 80,
         "inplane_fov_pct": 60, "inplane_off": 0,
         "params": {"sequence": "Spin Echo", "slice_thickness": 5}})))
    acq = [p for p in out["panels"] if p.get("role") == "acq"]
    assert len(acq) == 1
    fb = acq[0]["fov_box"]
    assert len(fb) == 4 and all(0.0 <= v <= 1.0 for v in fb)
    # 60% FOV → box noticeably smaller than the full panel in both dims
    assert 0.4 < fb[2] < 0.8 and 0.4 < fb[3] < 0.8


def test_fov_planning_crop_changes_main_image():
    """Turning on FOV planning with a reduced in-plane FOV crops the main image."""
    wa.init()
    base = {"region": "Brain", "orientation": "axial", "slice_idx": 90,
            "params": {"sequence": "Spin Echo"}}
    full = wa.render(dict(base))
    cropped = wa.render({**base, "fov_planning": True,
                         "inplane_fov_pct": 50, "inplane_off": 0, "tilt": 0, "rot": 0})
    assert full["image"] != cropped["image"]


def test_oblique_planning_changes_main_image():
    """A non-zero tilt angle under FOV planning re-samples an oblique slice."""
    wa.init()
    base = {"region": "Brain", "orientation": "axial", "slice_idx": 90,
            "fov_planning": True, "inplane_fov_pct": 100, "inplane_off": 0,
            "params": {"sequence": "Spin Echo"}}
    straight = wa.render({**base, "tilt": 0, "rot": 0})
    oblique = wa.render({**base, "tilt": 20, "rot": 0})
    assert straight["image"] != oblique["image"]


def test_multislice_scout_renders():
    """A multi-slice prescription renders the localizer with the slice stack."""
    wa.init()
    out = json.loads(wa.render_scout_json(json.dumps(
        {"region": "Brain", "orientation": "axial", "slice_idx": 90,
         "params": {"sequence": "Spin Echo", "slice_thickness": 4,
                    "n_slices": 9, "slice_gap": 2}})))
    _decode(out["scout"], "multislice scout")


def test_multislice_crosstalk_lowers_snr():
    """Contiguous multi-slice (no gap) costs SNR via cross-talk; a gap recovers it."""
    wa.init()
    base = {"region": "Brain", "orientation": "axial", "slice_idx": 90,
            "params": {"sequence": "Spin Echo", "TR": 2500, "TE": 30, "slice_thickness": 4}}

    def snr(ns, gap):
        p = {**base, "params": {**base["params"], "n_slices": ns, "slice_gap": gap}}
        return wa.render(p)["metrics"]["snr_wm"]

    one, packed, gapped = snr(1, 0), snr(16, 0), snr(16, 8)
    assert packed < one            # cross-talk penalty
    assert gapped > packed         # a gap recovers signal


def test_render_returns_aligned_tissue_probe():
    """render() returns a compact label map + tissue table for the cursor probe,
    aligned to the image (centre of an axial brain slice is CSF, not background)."""
    import base64
    wa.init()
    res = wa.render({"region": "Brain", "orientation": "axial", "slice_idx": 90,
                     "params": {"sequence": "Spin Echo", "field_strength": "3T"}})
    pb = res["probe"]
    assert pb and pb["h"] > 0 and pb["w"] > 0 and max(pb["h"], pb["w"]) <= 160
    lab = np.frombuffer(base64.b64decode(pb["labels"]), dtype=np.uint8)
    assert lab.size == pb["h"] * pb["w"]
    centre = int(lab.reshape(pb["h"], pb["w"])[pb["h"] // 2, pb["w"] // 2])
    assert centre in pb["tissues"] or str(centre) in pb["tissues"]
    # every present label has a name + T1/T2/PD
    for info in pb["tissues"].values():
        assert {"name", "T1", "T2", "PD"} <= set(info)


def test_probe_carries_signal_for_show_the_math():
    """Each probe tissue includes the predicted signal S (for the 'show the math'
    panel), and it matches the spin-echo equation S = PD·(1−e^−TR/T1)·e^−TE/T2."""
    import math
    wa.init()
    res = wa.render({"region": "Brain", "orientation": "axial", "slice_idx": 90,
                     "params": {"sequence": "Spin Echo", "TR": 500, "TE": 15}})
    wm = next(v for v in res["probe"]["tissues"].values() if v["name"] == "White matter")
    assert {"S", "T2star"} <= set(wm)
    expect = wm["PD"] * (1 - math.exp(-500 / wm["T1"])) * math.exp(-15 / wm["T2"])
    assert abs(wm["S"] - expect) < 1e-3


def test_anatomy_labels_change_image():
    """The 'label the anatomy' overlay draws named structures onto the image."""
    wa.init()
    base = {"region": "Brain", "orientation": "axial", "slice_idx": 90,
            "params": {"sequence": "Spin Echo", "TR": 4000, "TE": 100}}
    plain = wa.render(base)["image"]
    labeled = wa.render({**base, "label_anatomy": True})["image"]
    _decode(plain, "plain"); _decode(labeled, "labeled")
    assert plain != labeled, "anatomy labels did not change the image"


def test_anatomy_labels_do_not_overlap():
    """The named-structure labels must be de-overlapped — placing several tissues
    whose centroids coincide (gray/white matter, CSF, and the lesion inside WM)
    must still yield non-overlapping label boxes."""
    wa.init()
    host = wa._host()
    base = {"region": "Brain", "orientation": "axial", "slice_idx": 90,
            "params": {"sequence": "Spin Echo", "TR": 500, "TE": 12},
            "lesion": True, "label_anatomy": True}
    host.render(base)                                       # sets up sim + last image

    class _Rec:
        def __init__(self):
            self.calls = []

        def text(self, x, y, s, **_kw):
            self.calls.append((x, y, s))

    rec = _Rec()
    params = wa.default_params(sequence="Spin Echo", TR=500, TE=12)
    img_shape = host.current_image.shape
    host._draw_anatomy_labels(rec, "axial", 90, params, img_shape)
    assert len(rec.calls) >= 4, f"too few labels drawn ({len(rec.calls)})"

    rowh = host._label_rowh(img_shape[0])
    boxes = [(host._label_box(x, y, s, rowh), s) for x, y, s in rec.calls]
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            assert not host._boxes_hit(boxes[i][0], boxes[j][0]), \
                f"labels overlap: {boxes[i][1]!r} & {boxes[j][1]!r}"


@pytest.mark.parametrize("extra", [
    {"motion_enabled": True, "motion_type": "periodic"},
    {"chemical_shift_enabled": True, "bandwidth": 32},
    {"susceptibility_enabled": True},
])
def test_artifacts_change_the_image(extra):
    """Each teaching artifact the browser exposes (motion, chemical shift,
    susceptibility) must flow through to the engine and visibly alter the image."""
    wa.init()
    base = {"region": "Brain", "orientation": "axial", "slice_idx": 90,
            "params": {"sequence": "Spin Echo", "TR": 500, "TE": 15}}
    clean = wa.render(base)
    dirty = wa.render({**base, "params": {**base["params"], **extra}})
    _assert_good_render(dirty, str(extra))
    assert clean["image"] != dirty["image"], f"artifact had no effect: {extra}"


def test_contrast_map_opt_in():
    """The TR×TE contrast map is returned only when requested, as a valid PNG."""
    wa.init()
    base = {"region": "Brain", "orientation": "axial", "slice_idx": 90,
            "params": {"sequence": "Spin Echo", "TR": 500, "TE": 15}}
    assert wa.render(base)["cmap"] is None                 # off by default
    on = wa.render({**base, "contrast_map": True})
    _decode(on["cmap"], "contrast map")


def test_lesion_demo_appears_and_is_brain_only():
    """The demo lesion changes the image, shows up as label 23 in the probe table,
    and only paints into the brain (a body region ignores the flag)."""
    wa.init()
    base = {"region": "Brain", "orientation": "axial", "slice_idx": 90,
            "params": {"sequence": "Spin Echo", "TR": 4000, "TE": 100}}
    off = wa.render(base)
    on = wa.render({**base, "lesion": True})
    _decode(on["image"], "lesion")
    assert off["image"] != on["image"], "lesion did not change the image"
    assert "23" not in {str(k) for k in off["probe"]["tissues"]}, "lesion present when off"
    assert "23" in {str(k) for k in on["probe"]["tissues"]}, "lesion missing from probe"
    # A body region must not gain a (brain-white-matter) lesion.
    body = wa.render({"region": "Abdomen", "orientation": "axial", "slice_idx": 55,
                      "params": {"sequence": "FSE / TSE"}, "lesion": True})
    assert "23" not in {str(k) for k in body["probe"]["tissues"]}, "lesion leaked into body"


def test_lesion_hides_on_t1_but_bright_on_t2():
    """The teaching invariant: the lesion is far more conspicuous against white
    matter on T2 than on T1 (its T1 sits close to WM; its T2 is long)."""
    wa.init()
    props = __import__("tissue_db").properties("3T")
    wm, les = props[3], props[23]

    def se(p, tr, te):
        import numpy as _np
        return p["PD"] * (1 - _np.exp(-tr / p["T1"])) * _np.exp(-te / p["T2"])

    t1_ratio = se(les, 500, 12) / se(wm, 500, 12)        # ~1 → invisible
    t2_ratio = se(les, 4000, 100) / se(wm, 4000, 100)    # ≫1 → bright
    assert abs(t1_ratio - 1.0) < 0.15, f"lesion too obvious on T1 ({t1_ratio:.2f})"
    assert t2_ratio > 1.8, f"lesion not bright enough on T2 ({t2_ratio:.2f})"


def test_render_json_roundtrip():
    wa.init()
    payload = json.dumps({"region": "Brain", "orientation": "axial",
                          "slice_idx": 90, "params": {"sequence": "Spin Echo"}})
    out = json.loads(wa.render_json(payload))
    _assert_good_render(out, "render_json")
