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


def test_precomputed_vessels_match_add_vessels_3d():
    """The shipped vessel-index file must reconstruct exactly what add_vessels_3d
    builds — a drift guard so the precomputed SWI/MRA tree never goes stale."""
    from phantom3d_extended import add_vessels_3d
    wa.init()
    h = wa._host()
    brain = h._region_cache["Brain"]
    fast = h._load_precomputed_vessels(brain)
    assert fast is not None, "precomputed vessel index missing — run scripts/build_brain_vessels.py"
    assert np.array_equal(fast, add_vessels_3d(brain)), \
        "precomputed vessels drifted from add_vessels_3d; regenerate brain_vessels_idx.npy"


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


@pytest.mark.parametrize("region,plane", [("Spine", "sagittal"), ("Knee", "sagittal")])
def test_region_opens_on_canonical_plane_midslice(region, plane):
    """A sagittal-canonical region (Spine/Knee) must open centred on its canonical
    plane: the returned max_slice spans that plane's axis (not the axial axis), and
    the initial slice sits at its midpoint. Regression for the Spine opening on a
    near-lateral, body-edge slice (a 'cut in half' localizer) because the mid slice
    was computed before the engine's orientation was synced to the plane."""
    d = wa.set_region(region)
    axis_len = d["dims"][plane]
    assert d["max_slice"] == axis_len - 1, (
        f"{region} max_slice should span the {plane} axis ({axis_len}), got {d['max_slice'] + 1}")
    h = wa._host()
    assert h.orientation.get() == plane
    assert h.slice_idx.get() == (axis_len - 1) // 2, "should open at the canonical-plane midslice"


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


def test_3d_metrics_report_slab_geometry_and_snr_gain():
    """A 3-D render must report the slab geometry the UI shows: partition count,
    isotropic partition thickness, total slab coverage, and the √(Nz·NEX) SNR gain
    over a single 2-D slice. A 2-D render must not be flagged 3-D."""
    import numpy as np
    wa.init()
    nz = 24
    r = wa.render({"region": "Brain", "orientation": "axial", "slice_idx": 95,
                   "params": {"sequence": "Gradient Echo", "acq3d": True,
                              "n_partitions": nz, "NEX": 1, "FOV": 240, "matrix_size": 256}})
    m = r["metrics"]
    assert m.get("is_3d")
    assert m["n_partitions"] == nz
    # Isotropic partitions: through-plane thickness == the in-plane resolution.
    assert m["partition_mm"] == pytest.approx(m["resolution"], rel=1e-3)
    assert m["slab_mm"] == pytest.approx(nz * m["partition_mm"], rel=1e-3)
    assert m["snr_3d_gain"] == pytest.approx(np.sqrt(nz), rel=1e-3)   # √(Nz·NEX), NEX=1
    r2 = wa.render({"region": "Brain", "orientation": "axial", "slice_idx": 95,
                    "params": {"sequence": "Gradient Echo", "TR": 500, "TE": 12}})
    assert not r2["metrics"].get("is_3d")


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
    # The two cross panels expose the two independent oblique DOF (tilt + rot), so
    # both planes can be angled (double-oblique) — not just one.
    cross_angles = sorted(p["angle"] for p in panels if p["role"] == "cross")
    assert cross_angles == ["rot", "tilt"], f"{orient}: cross panels don't cover both DOF"


def test_double_oblique_renders_distinctly():
    """tilt, rot and tilt+rot must each produce a distinct image (both oblique
    degrees of freedom are honoured, not just one)."""
    wa.init()
    base = {"region": "Brain", "orientation": "axial", "slice_idx": 90,
            "fov_planning": True, "params": {"sequence": "Spin Echo", "TR": 2000, "TE": 15}}
    ref = wa.render(base)["image"]
    tilt = wa.render({**base, "tilt": 25, "rot": 0})["image"]
    rot = wa.render({**base, "tilt": 0, "rot": 25})["image"]
    both = wa.render({**base, "tilt": 25, "rot": 25})["image"]
    assert tilt != ref and rot != ref, "a single oblique angle had no effect"
    assert both != tilt and both != rot, "the two oblique angles aren't independent"


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


def test_interior_anchor_is_on_a_ring_not_its_hollow_centre():
    """The label anchor must sit ON the structure. A ring's centroid is its hollow
    centre (off-tissue); the interior anchor must land on the ring itself."""
    yy, xx = np.ogrid[:60, :60]
    d = np.hypot(yy - 30, xx - 30)
    ring = (d > 18) & (d < 24)
    r, c, size = wa.WebHost._interior_anchor(ring)
    assert ring[r, c], "anchor fell in the ring's hollow centre (off-tissue)"
    assert size == int(ring.sum())


def test_anatomy_label_anchors_land_on_their_tissue():
    """On the real brain, every named structure's anchor must sit on that tissue —
    not, as the centroid did, pile every ring/ribbon label near the brain centre."""
    wa.init()
    h = wa._host()
    from simulator import default_params as _dp
    params = _dp(sequence="Spin Echo", TR=500, TE=12)
    lab = np.asarray(h.sim._get_phantom_slice("axial", 90, params))
    total = max(int((lab > 0).sum()), 1)
    checked = 0
    for v in np.unique(lab):
        if v == 0 or v == 12 or (lab == v).sum() < 0.012 * total:
            continue
        r, c, _ = h._interior_anchor(lab == v)
        assert lab[r, c] == v, f"label {v} anchored off its tissue at ({r},{c})"
        checked += 1
    assert checked >= 4, "expected several brain tissues to be labelled"


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


# Each artifact is exercised where it is physically meaningful: motion and
# chemical shift on the brain; susceptibility on the abdomen with a gradient echo
# (spin echo refocuses static susceptibility, and the brain phantom carries no
# internal air cavities, so neither would show the dropout — see the susceptibility
# model in artifacts.py). Noise is deterministic, so a no-op artifact would now be
# caught as an identical image rather than masked by random noise.
@pytest.mark.parametrize("extra,region,slice_idx,sequence", [
    ({"motion_enabled": True, "motion_type": "periodic"}, "Brain", 90, "Spin Echo"),
    ({"chemical_shift_enabled": True, "bandwidth": 32}, "Brain", 90, "Spin Echo"),
    ({"susceptibility_enabled": True, "susceptibility_strength": 5.0},
     "Abdomen", 128, "Gradient Echo"),
])
def test_artifacts_change_the_image(extra, region, slice_idx, sequence):
    """Each teaching artifact the browser exposes (motion, chemical shift,
    susceptibility) must flow through to the engine and visibly alter the image."""
    wa.init()
    base = {"region": region, "orientation": "axial", "slice_idx": slice_idx,
            "params": {"sequence": sequence, "TR": 500, "TE": 15}}
    clean = wa.render(base)
    dirty = wa.render({**base, "params": {**base["params"], **extra}})
    _assert_good_render(dirty, str(extra))
    assert clean["image"] != dirty["image"], f"artifact had no effect: {extra}"


def test_measure_ruler_reports_fov_scale():
    """A ruler spanning the full image height must read ≈ the region's field of
    view in mm (the brain's native FOV is 220 mm)."""
    wa.init()
    wa.render({"region": "Brain", "orientation": "axial", "slice_idx": 90,
               "params": {"sequence": "Spin Echo"}})
    # Full-height vertical line down the image centre.
    res = wa.measure({"kind": "ruler", "points": [[0.5, 0.0], [0.5, 1.0]]})
    assert res["ok"] and res["kind"] == "ruler"
    assert 210 < res["mm"] < 230, f"full-height ruler should be ~220 mm, got {res['mm']:.1f}"


def test_measure_roi_separates_tissue_from_background():
    """An ROI over central brain tissue must read a much higher mean signal than
    one over a background corner — the ROI reads the true image, not the display."""
    wa.init()
    wa.render({"region": "Brain", "orientation": "axial", "slice_idx": 90,
               "params": {"sequence": "Spin Echo", "TR": 500, "TE": 12}})
    tissue = wa.measure({"kind": "roi", "points": [[0.45, 0.45], [0.55, 0.55]]})
    corner = wa.measure({"kind": "roi", "points": [[0.85, 0.05], [0.95, 0.15]]})
    assert tissue["ok"] and corner["ok"]
    assert tissue["n"] > 0 and tissue["mean"] > 3 * corner["mean"]
    assert tissue["area_mm2"] > 0 and tissue["snr"] > 0


def test_contrast_map_opt_in():
    """The TR×TE contrast map is returned only when requested, as a valid PNG."""
    wa.init()
    base = {"region": "Brain", "orientation": "axial", "slice_idx": 90,
            "params": {"sequence": "Spin Echo", "TR": 500, "TE": 15}}
    assert wa.render(base)["cmap"] is None                 # off by default
    on = wa.render({**base, "contrast_map": True})
    _decode(on["cmap"], "contrast map")


@pytest.mark.parametrize("kind,label", [
    ("lesion", 23), ("stroke", 24), ("hemorrhage", 25), ("tumor", 26),
    ("abscess", 27)])
def test_pathology_appears_and_is_brain_only(kind, label):
    """Each demo pathology changes the image, shows up as its tissue label in the
    probe table, and only paints into the brain (a body region ignores it)."""
    wa.init()
    base = {"region": "Brain", "orientation": "axial", "slice_idx": 90,
            "params": {"sequence": "Spin Echo", "TR": 4000, "TE": 100}}
    off = wa.render(base)
    on = wa.render({**base, "pathology": kind})
    _decode(on["image"], kind)
    assert off["image"] != on["image"], f"{kind} did not change the image"
    assert str(label) not in {str(k) for k in off["probe"]["tissues"]}, "present when off"
    assert str(label) in {str(k) for k in on["probe"]["tissues"]}, f"{kind} missing from probe"
    # A body region must not gain a (brain-white-matter) pathology.
    body = wa.render({"region": "Abdomen", "orientation": "axial", "slice_idx": 55,
                      "params": {"sequence": "FSE / TSE"}, "pathology": kind})
    assert str(label) not in {str(k) for k in body["probe"]["tissues"]}, f"{kind} leaked into body"


def test_legacy_lesion_flag_still_works():
    """The old boolean `lesion: true` payload still paints the WM lesion (label 23)."""
    wa.init()
    base = {"region": "Brain", "orientation": "axial", "slice_idx": 90,
            "params": {"sequence": "Spin Echo", "TR": 4000, "TE": 100}}
    on = wa.render({**base, "lesion": True})
    assert "23" in {str(k) for k in on["probe"]["tissues"]}


def test_pathologies_show_on_their_sequence():
    """The teaching invariant: stroke is bright on DWI, the tumour enhances with Gd.
    (SWI/haemorrhage is covered by the susceptibility table, which is slow to render
    here as it builds the venous map.)"""
    wa.init()
    h = wa._host()
    import numpy as _np
    from simulator import default_params as _dp

    def region_vs_wm(kind, label, params):
        wa.render({"region": "Brain", "orientation": "axial", "slice_idx": 90,
                   "pathology": kind, "params": params})
        sl = _np.asarray(h.sim._get_phantom_slice("axial", 90, _dp(**params)))
        return float(h.current_image[sl == label].mean()), float(h.current_image[sl == 3].mean())

    # Acute infarct: restricted diffusion → brighter than white matter on DWI.
    inf, wm = region_vs_wm("stroke", 24,
                           {"sequence": "Diffusion (DWI)", "b_value": 1000, "diff_display": "DWI"})
    assert inf > wm, f"stroke should be bright on DWI (infarct {inf:.3f} vs WM {wm:.3f})"

    # Enhancing tumour: T1 signal rises with gadolinium.
    p = {"sequence": "Spin Echo", "TR": 600, "TE": 12}
    pre, _ = region_vs_wm("tumor", 26, {**p, "contrast_enabled": False})
    post, _ = region_vs_wm("tumor", 26, {**p, "contrast_enabled": True, "contrast_dose": 10})
    assert post > pre * 1.2, f"tumour should enhance with Gd (pre {pre:.3f} → post {post:.3f})"


def test_abscess_has_dwi_bright_core_and_enhancing_rim():
    """An abscess paints two labels: a pus core (27) that restricts diffusion
    (bright on DWI) and a capsule/rim (28) that enhances with gadolinium."""
    wa.init()
    h = wa._host()
    import numpy as _np
    from simulator import default_params as _dp

    # Both components must be painted, distinct, and on the default slice.
    vol = h._pathology_volume("abscess")
    assert (vol == 27).sum() > 0 and (vol == 28).sum() > 0, "abscess core/rim not painted"

    def mean_of(label, params):
        wa.render({"region": "Brain", "orientation": "axial", "slice_idx": 90,
                   "pathology": "abscess", "params": params})
        sl = _np.asarray(h.sim._get_phantom_slice("axial", 90, _dp(**params)))
        return float(h.current_image[sl == label].mean()), float(h.current_image[sl == 3].mean())

    core, wm = mean_of(27, {"sequence": "Diffusion (DWI)", "b_value": 1000, "diff_display": "DWI"})
    assert core > wm, f"abscess core should be bright on DWI (core {core:.3f} vs WM {wm:.3f})"

    # T2: bright pus core, T2-hypointense (dark) rim — the classic ring.
    wa.render({"region": "Brain", "orientation": "axial", "slice_idx": 90,
               "pathology": "abscess", "params": {"sequence": "Spin Echo", "TR": 4000, "TE": 100}})
    sl = _np.asarray(h.sim._get_phantom_slice("axial", 90,
                     _dp(sequence="Spin Echo", TR=4000, TE=100)))
    rim_vals, wm_t2 = h.current_image[sl == 28], float(h.current_image[sl == 3].mean())
    core_t2 = float(h.current_image[sl == 27].mean())
    assert core_t2 > wm_t2, "pus core should be bright on T2"
    assert float((rim_vals < wm_t2).mean()) > 0.4, "rim should be T2-hypointense (dark ring)"

    p = {"sequence": "Spin Echo", "TR": 600, "TE": 12}
    pre, _ = mean_of(28, {**p, "contrast_enabled": False})
    post, _ = mean_of(28, {**p, "contrast_enabled": True, "contrast_dose": 10})
    assert post > pre * 1.2, f"abscess rim should enhance with Gd (pre {pre:.3f} → post {post:.3f})"


def test_abscess_core_brighter_than_tumour_core_on_dwi():
    """The diagnostic dilemma behind the compare-pathologies lesson: on DWI the
    abscess's pus core restricts (bright) while the tumour's necrotic core
    facilitates (dark) — so the abscess core reads clearly brighter."""
    wa.init()
    h = wa._host()
    import numpy as _np
    from simulator import default_params as _dp
    dwi = {"sequence": "Diffusion (DWI)", "b_value": 1000, "diff_display": "DWI"}

    def core(kind, label):
        wa.render({"region": "Brain", "orientation": "axial", "slice_idx": 90,
                   "pathology": kind, "params": dwi})
        sl = _np.asarray(h.sim._get_phantom_slice("axial", 90, _dp(**dwi)))
        return float(h.current_image[sl == label].mean())

    abscess = core("abscess", 27)
    tumour = core("tumor", 26)
    assert abscess > tumour * 1.3, \
        f"abscess core should be brighter on DWI than tumour core ({abscess:.3f} vs {tumour:.3f})"


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
