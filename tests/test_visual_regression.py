"""Rendering-invariant regression tests for the browser build's images.

These guard the *visual* failure modes that array-level physics tests miss and
that have actually regressed before: blank/collapsed panels and stretched (wrong
aspect-ratio) reformats — the "very stretched out MPR" bug among them.

We assert invariants of the engine's matplotlib-Agg PNGs (decoded to arrays)
rather than pixel-exact baselines: the matplotlib pin is loose (``>=3.7``), so
pixel baselines would break spuriously on every CI matplotlib bump — *adding*
flakiness — whereas these invariants catch stretch / blank / empty deterministically
and version-independently.
"""
import base64
import io

import matplotlib.image as mpimg
import numpy as np
import pytest

from web_adapter import WebHost


def _decode(data_url: str) -> np.ndarray:
    """A ``data:image/png;base64,…`` URL → grayscale uint8 array (H, W).

    Uses matplotlib's native PNG reader (a core dependency) so the test needs no
    extra image library.
    """
    assert data_url.startswith("data:image/png"), "not a PNG data URL"
    raw = base64.b64decode(data_url.split(",", 1)[1])
    arr = mpimg.imread(io.BytesIO(raw), format="png")   # float 0..1, (H,W) or (H,W,3/4)
    if arr.ndim == 3:
        arr = arr[..., :3].mean(axis=2)
    return (arr * 255.0).astype(np.uint8)


def _central_colorfulness(data_url: str) -> float:
    """Mean RGB channel-spread over the central 40% of a PNG data URL — ~0 for a
    grayscale image, clearly positive for a colormapped one. The central crop
    avoids the coloured DICOM corner annotations and the colorbar inset."""
    raw = base64.b64decode(data_url.split(",", 1)[1])
    a = mpimg.imread(io.BytesIO(raw), format="png")[..., :3]
    h, w = a.shape[:2]
    c = a[int(h * 0.30):int(h * 0.70), int(w * 0.30):int(w * 0.70)]
    return float(np.mean(c.max(axis=2) - c.min(axis=2)))


@pytest.fixture(scope="module")
def host() -> WebHost:
    h = WebHost()
    h.load_region("Brain")
    return h


def _assert_not_blank(arr: np.ndarray, label: str, floor: float = 8.0) -> None:
    # A real render has structure; a blank/collapsed panel is near-uniform.
    assert arr.std() > floor, f"{label} looks blank (std={arr.std():.1f} ≤ {floor})"
    assert int(arr.max()) - int(arr.min()) > 40, f"{label} has no tonal range"


def test_main_image_renders_with_content(host: WebHost) -> None:
    r = host.render({"region": "Brain", "orientation": "axial", "slice_idx": 90,
                     "params": {"sequence": "Spin Echo", "TR": 500, "TE": 15}})
    img = _decode(r["image"])
    _assert_not_blank(img, "main image")
    # A meaningful share of the frame is anatomy (not an all-black or all-white panel).
    frac = float((img > 24).mean())
    assert 0.1 < frac < 0.95, f"main image foreground fraction implausible: {frac:.2f}"


def test_signal_curve_renders(host: WebHost) -> None:
    r = host.render({"region": "Brain", "orientation": "axial", "slice_idx": 90,
                     "curve_mode": "TE decay",
                     "params": {"sequence": "Spin Echo", "TR": 500, "TE": 15}})
    _assert_not_blank(_decode(r["curve"]), "signal curve", floor=3.0)


@pytest.mark.parametrize("seq,dispkey,disp", [
    ("Quantitative (qMRI)", "qmri_display", "T1 Map (VFA)"),
    ("Quantitative (qMRI)", "qmri_display", "T2 Map (multi-echo)"),
    ("Diffusion (DWI)", "diff_display", "ADC Map"),
    ("Diffusion (DWI)", "diff_display", "FA Map"),
])
def test_quantitative_maps_render_grayscale(host: WebHost, seq, dispkey, disp) -> None:
    """Quantitative parameter maps render in grayscale (radiology convention — read in
    black-and-white). The colorbar + unit label, not colour, mark them as maps."""
    r = host.render({"region": "Brain", "orientation": "axial", "slice_idx": 90,
                     "params": {"sequence": seq, dispkey: disp}})
    assert _central_colorfulness(r["image"]) < 0.02, f"{disp} should be grayscale"


@pytest.mark.parametrize("seq,dispkey,disp", [
    ("Spin Echo", None, None),
    ("Quantitative (qMRI)", "qmri_display", "Synthetic SE"),   # a weighted image, not a map
])
def test_weighted_images_stay_grayscale(host: WebHost, seq, dispkey, disp) -> None:
    """Plain weighted images keep grayscale — the colormap is reserved for maps."""
    params = {"sequence": seq}
    if dispkey:
        params[dispkey] = disp
    r = host.render({"region": "Brain", "orientation": "axial", "slice_idx": 90, "params": params})
    assert _central_colorfulness(r["image"]) < 0.02, f"{seq}/{disp} should be grayscale"


@pytest.mark.parametrize("flag,key,params", [
    ("show_kspace", "kspace", {"sequence": "Spin Echo"}),
    ("show_psd", "psd", {"sequence": "Gradient Echo"}),
    ("show_b0map", "b0map", {"sequence": "Echo Planar (EPI)"}),
    ("show_gfactor", "gfactor", {"sequence": "Spin Echo", "accel_factor": 3}),
])
def test_side_panels_render_with_structure(host: WebHost, flag, key, params) -> None:
    """The optional side panels — k-space, pulse-sequence diagram, B0 field map and
    g-factor map — each render real structure rather than a blank panel."""
    r = host.render({"region": "Brain", "orientation": "axial", "slice_idx": 90,
                     "params": params, flag: True})
    assert r[key] is not None, f"{key} panel was not produced"
    arr = _decode(r[key])
    assert arr.std() > 5.0, f"{key} panel looks blank (std={arr.std():.1f})"


def test_mpr_panels_are_not_stretched(host: WebHost) -> None:
    """Each MPR reformat's PNG aspect ratio must match its data aspect — this is
    the direct guard against the 'stretched-out reformat' regression."""
    rec = host.reconstruct({"region": "Brain", "orientation": "axial", "slice_idx": 90,
                            "params": {"sequence": "Gradient Echo", "acq3d": True,
                                       "n_partitions": 180}, "mode": "mpr"})
    assert rec["ok"], rec.get("error")
    nz, ny, nx = rec["dims"]["nz"], rec["dims"]["ny"], rec["dims"]["nx"]
    # mpr_triplanar planes: axial=(ny,nx), coronal=(nz,nx), sagittal=(nz,ny).
    expected = {"axial": ny / nx, "coronal": nz / nx, "sagittal": nz / ny}
    panels = rec["panels"]
    assert set(panels) == {"axial", "coronal", "sagittal", "overview"}
    for name, exp in expected.items():
        a = _decode(panels[name])
        _assert_not_blank(a, f"MPR {name}")
        got = a.shape[0] / a.shape[1]
        # The figure is sized to the data aspect (panels fill edge-to-edge); allow
        # a little slack for the rasteriser. The old stretch bug was >100% off.
        assert abs(got - exp) / exp < 0.08, \
            f"MPR {name} is stretched: aspect {got:.3f} vs data {exp:.3f}"
    _assert_not_blank(_decode(panels["overview"]), "MPR overview")
