"""Headless smoke tests for the PyQt GUI (app_qt.MRISimulator).

The physics library is well covered; the 2,800-line GUI that wires it together
is not. These boot the real window offscreen and drive it through the states a
user can reach, asserting "no exception + the output is sane". They exist to
catch the *wiring* bugs the library tests can't see — every regression noted
inline below was a real bug found by hand during development.

Layers implemented here:
  A. every sequence renders a sane image
  B. every preset applies the right region / plane / sequence and renders
  C. every orientation (brain & body) renders with correct anatomical labels
"""
import numpy as np
import pytest
from PyQt6.QtWidgets import QFileDialog

from presets import (get_preset, get_preset_names, get_preset_region,
                     get_preset_plane)

# The sequences offered in the GUI dropdown (app_qt build_controls).
SEQUENCES = [
    "Spin Echo", "FSE / TSE", "Gradient Echo", "Inversion Recovery",
    "Balanced SSFP", "Diffusion (DWI)", "MR Angiography", "Susceptibility (SWI)",
    "fMRI (BOLD)", "Quantitative (qMRI)", "Echo Planar (EPI)",
]

# Full-FOV anatomical images — the energy-spread (anti-collapse) check is only
# meaningful for these; MRA MIPs, activation/qMRI maps are legitimately sparse.
ANATOMICAL = {"Spin Echo", "FSE / TSE", "Gradient Echo", "Inversion Recovery",
              "Balanced SSFP", "Echo Planar (EPI)", "Susceptibility (SWI)"}

# Radiological orientation labels (top, bottom, left, right) — brain and body
# share this map after the body phantoms were mirrored to radiological.
EXPECTED_ORIENT = {
    "axial":    ("A", "P", "R", "L"),
    "coronal":  ("S", "I", "R", "L"),
    "sagittal": ("S", "I", "A", "P"),
}


# --------------------------------------------------------------------------- #
#  Fixture — build the window once per session (loading phantoms is the cost)
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="session")
def win():
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    import app_qt
    w = app_qt.MRISimulator()
    w.resize(1500, 940)
    yield w
    # Tear down the Qt objects while the QApplication is still alive; otherwise
    # they are freed during interpreter shutdown in the wrong order and Qt
    # aborts the process (exit 134), failing CI even though the tests passed.
    for fig in (w.fig, w.scout_fig, w.psd_fig):
        fig.clear()
    w.close()
    w.deleteLater()
    app.processEvents()
    app.processEvents()


# --------------------------------------------------------------------------- #
#  Helpers
# --------------------------------------------------------------------------- #
def set_state(w, *, region="Brain", sequence="Spin Echo",
              orientation="axial", **params):
    """Drive the window the way a user would: reset the view to a clean single-
    image baseline, then region → sequence → plane → params, then render.
    Returns the reconstructed image."""
    # Reset view toggles so each test starts clean (these only fire a harmless
    # checkbox-sync trace, not a recalc).
    for v in (w.show_kspace, w.multi_slice, w.show_psd,
              w.show_tissue_overlay, w.compare_mode, w.acq3d):
        v.set(False)
    w.compare_params = None
    if w.fov_planning.get():        # this one recalcs + restores the layout
        w.fov_planning.set(False)
    w._ensure_1x2_layout()          # back to the normal 2-axes figure
    if w.region.get() != region:
        w.region.set(region); w.on_region_change()
    w.sequence_type.set(sequence); w.on_sequence_change()
    w._set_orientation(orientation)
    for key, val in params.items():
        getattr(w, key).set(val)
    w.recalculate()
    return w.current_image


def assert_good_image(img, ctx=""):
    assert img is not None, f"{ctx}: no image produced"
    img = np.asarray(img)
    assert img.ndim == 2 and img.size >= 32 * 32, f"{ctx}: bad shape {img.shape}"
    assert np.all(np.isfinite(img)), f"{ctx}: image has NaN/Inf"
    assert float(np.max(np.abs(img))) > 0, f"{ctx}: blank image"


def _energy_row_span(img):
    """Fraction of the rows spanned by the central 80% of the signal energy.
    Tiny for a collapsed 'thin lens' (the old EPI-distortion bug), large for a
    real image that fills the FOV."""
    img = np.abs(np.asarray(img, dtype=float))
    rs = img.sum(axis=1)
    total = rs.sum()
    if total <= 0:
        return 0.0
    c = np.cumsum(rs) / total
    lo = int(np.searchsorted(c, 0.10))
    hi = int(np.searchsorted(c, 0.90))
    return (hi - lo) / len(rs)


# --------------------------------------------------------------------------- #
#  Layer A — every sequence renders
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("seq", SEQUENCES)
def test_sequence_renders(win, seq):
    img = set_state(win, region="Brain", sequence=seq)
    assert_good_image(img, seq)
    assert win.sequence_type.get() == seq
    if seq in ANATOMICAL:
        assert _energy_row_span(img) > 0.2, f"{seq}: signal collapsed to a thin band"


def test_epi_not_collapsed_with_off_resonance(win):
    """Regression: EPI B0 distortion used to collapse the brain to a thin lens.
    With off-resonance on, the image must still fill the FOV (energy conserved)."""
    img = set_state(win, region="Brain", sequence="Echo Planar (EPI)",
                    epi_b0_hz=120, epi_esp=6)
    assert_good_image(img, "EPI b0=120")
    assert _energy_row_span(img) > 0.3, "EPI image collapsed under off-resonance"


# --------------------------------------------------------------------------- #
#  Layer B — every preset applies the right region / plane / sequence
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("name", get_preset_names())
def test_preset_applies_and_renders(win, name):
    win.preset_name.set(name)
    win.on_preset_change()
    p = get_preset(name)
    assert win.region.get() == get_preset_region(name), f"{name}: wrong region"
    assert win.orientation.get() == get_preset_plane(name), f"{name}: wrong plane"
    assert win.sequence_type.get() == p["sequence"], f"{name}: wrong sequence"
    win.recalculate()
    assert_good_image(win.current_image, name)
    # slice landed inside the (possibly new) volume
    assert 0 <= win.slice_idx.get() <= win.get_max_slice_idx()


# --------------------------------------------------------------------------- #
#  Layer C — orientation × region, with correct anatomical labels
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("region", ["Brain", "Abdomen"])
@pytest.mark.parametrize("plane", ["axial", "coronal", "sagittal"])
def test_orientation_renders_and_labels(win, region, plane):
    img = set_state(win, region=region, sequence="Spin Echo", orientation=plane)
    assert_good_image(img, f"{region}/{plane}")
    assert win.orientation.get() == plane
    assert 0 <= win.slice_idx.get() <= win.get_max_slice_idx()
    # radiological orientation labels (skipped only for MRA/oblique/loaded — N/A here)
    assert win._orientation_letters(plane) == EXPECTED_ORIENT[plane], \
        f"{region}/{plane}: wrong orientation labels"


def test_region_change_resets_to_axial(win):
    set_state(win, region="Brain", orientation="sagittal")
    win.region.set("Pelvis"); win.on_region_change()
    assert win.orientation.get() == "axial", "new region should default to axial"
    win.recalculate()
    assert_good_image(win.current_image, "Pelvis axial")


# --------------------------------------------------------------------------- #
#  Layer D — display modes / toggles (assert matplotlib state, not Qt visibility)
# --------------------------------------------------------------------------- #
def test_show_kspace(win):
    set_state(win, sequence="Spin Echo")
    win.show_kspace.set(True); win.recalculate()
    assert len(win.axes[1].images) > 0, "k-space not shown in the side panel"
    assert_good_image(win.current_image, "kspace mode")


def test_show_psd_draws(win):
    set_state(win, sequence="Spin Echo")
    win.show_psd.set(True); win.recalculate()
    assert win.psd_fig._suptitle is not None, "PSD not drawn"


def test_tissue_overlay(win):
    set_state(win, sequence="Spin Echo")
    win.show_tissue_overlay.set(True); win.recalculate()
    assert len(win.axes[0].images) >= 2, "overlay not composited over the image"
    assert_good_image(win.current_image, "overlay")


def test_multi_slice_grid(win):
    set_state(win, sequence="Spin Echo")
    win.multi_slice.set(True); win.recalculate()
    assert len(win.fig.axes) >= 4, "multi-slice grid not rendered"


def test_fov_planning_scout(win):
    set_state(win, sequence="Spin Echo")
    win.fov_planning.set(True)              # trace → on_fov_planning_toggle recalcs
    n_imgs = sum(len(ax.images) for ax in win.scout_axes)
    assert n_imgs > 0, "3-plane localizer did not draw"


def test_compare_mode(win):
    set_state(win, sequence="Spin Echo")
    win.set_protocol_a()                    # capture A and enter compare
    win.sequence_type.set("Gradient Echo"); win.on_sequence_change(); win.recalculate()
    assert win.compare_mode.get()
    assert len(win.axes[0].images) > 0 and len(win.axes[1].images) > 0, "A|B not shown"
    win.clear_compare()


# --------------------------------------------------------------------------- #
#  Layer E — PSD reflects the selected sequence (GUI passes the right one)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("seq,keyword", [
    ("Balanced SSFP", "SSFP"),           # these three used to fall back to
    ("Echo Planar (EPI)", "EPI"),        # a mislabeled Spin-Echo diagram
    ("Quantitative (qMRI)", "qMRI"),
    ("Inversion Recovery", "Inversion"),
])
def test_psd_matches_sequence_via_gui(win, seq, keyword):
    set_state(win, sequence=seq)
    win.show_psd.set(True); win.recalculate()
    title = win.psd_fig._suptitle.get_text()
    assert keyword.lower() in title.lower(), f"{seq} drew PSD {title!r}"


# --------------------------------------------------------------------------- #
#  Layer F — interaction handlers (synthetic matplotlib events)
# --------------------------------------------------------------------------- #
class _GUIEvent:
    def __init__(self, ctrl=False):
        from PyQt6.QtCore import Qt
        self._m = (Qt.KeyboardModifier.ControlModifier if ctrl
                   else Qt.KeyboardModifier.NoModifier)

    def modifiers(self):
        return self._m


class _Ev:
    """Minimal stand-in for a matplotlib backend event."""
    def __init__(self, button=None, x=120, y=120, dblclick=False, step=0, ctrl=False,
                 xdata=None, ydata=None, inaxes=None, key=None):
        self.button = button
        self.x = x; self.y = y
        self.dblclick = dblclick
        self.step = step
        self.guiEvent = _GUIEvent(ctrl)
        self.xdata = xdata; self.ydata = ydata; self.inaxes = inaxes
        self.key = key


def test_scroll_steps_slice(win):
    set_state(win, sequence="Spin Echo", slice_thickness=1)
    win.slice_idx.set(40)
    win._on_scroll(_Ev(button="up", step=1))
    assert win.slice_idx.get() == 41
    win._on_scroll(_Ev(button="down", step=-1))
    assert win.slice_idx.get() == 40


def test_scroll_steps_by_slice_thickness(win):
    """The wheel advances a whole slice-thickness (contiguous slices), so a 6 mm
    slice jumps 6 voxels per detent rather than 1."""
    set_state(win, sequence="Spin Echo", slice_thickness=6)
    win.slice_idx.set(40)
    win._on_scroll(_Ev(button="up", step=1))
    assert win.slice_idx.get() == 46
    win._on_scroll(_Ev(button="down", step=-1))
    assert win.slice_idx.get() == 40
    # MRA ignores slice thickness → always one voxel per detent
    set_state(win, sequence="MR Angiography", slice_thickness=6)
    win.slice_idx.set(40)
    win._on_scroll(_Ev(button="up", step=1))
    assert win.slice_idx.get() == 41


def test_left_drag_sets_window_level(win):
    set_state(win, sequence="Spin Echo")
    win.window_width = 1.0; win.window_level = 0.5
    win._on_press(_Ev(button=1, x=100, y=100))
    win._on_motion(_Ev(button=1, x=160, y=140))
    win._on_release(_Ev(button=1))
    assert (win.window_width, win.window_level) != (1.0, 0.5)


def test_double_click_resets_window_level(win):
    set_state(win, sequence="Spin Echo")
    win.window_width = 0.4; win.window_level = 0.2
    win._on_press(_Ev(button=1, dblclick=True))
    assert win.window_width == 1.0 and win.window_level == 0.5


def test_mra_left_drag_rotates_not_window_level(win):
    set_state(win, sequence="MR Angiography")
    az0 = win.angio_azimuth.get()
    wl0 = (win.window_width, win.window_level)
    win._on_press(_Ev(button=1, x=100, y=100))        # plain left on MRA → rotate
    assert win._mra_dragging is True
    win._on_motion(_Ev(button=1, x=175, y=100))
    win._on_release(_Ev(button=1))
    assert win.angio_azimuth.get() != az0, "MRA left-drag should rotate the MIP"
    assert (win.window_width, win.window_level) == wl0, "MRA rotate must not W/L"


def test_mra_ctrl_drag_does_window_level(win):
    set_state(win, sequence="MR Angiography")
    win.window_width = 1.0; win.window_level = 0.5
    win._on_press(_Ev(button=1, x=100, y=100, ctrl=True))   # Ctrl → W/L even on MRA
    assert win._mra_dragging is False
    win._on_motion(_Ev(button=1, x=150, y=130))
    win._on_release(_Ev(button=1))
    assert (win.window_width, win.window_level) != (1.0, 0.5)


# --------------------------------------------------------------------------- #
#  Layer G — every region builds, renders, and resets to axial
# --------------------------------------------------------------------------- #
from body_phantoms import REGION_NAMES  # noqa: E402


@pytest.mark.parametrize("region", REGION_NAMES)
def test_region_renders_and_resets_axial(win, region):
    set_state(win, region="Brain")
    win._set_orientation("sagittal")
    win.region.set(region); win.on_region_change()
    assert win.orientation.get() == "axial", f"{region}: did not reset to axial"
    win.recalculate()
    assert_good_image(win.current_image, region)


# --------------------------------------------------------------------------- #
#  Signal-curve physics — the curve uses the same library equations as the image
# --------------------------------------------------------------------------- #
def test_curve_signal_matches_library_per_sequence(win):
    """Regression for the GUI physics audit: the plotted signal curve must use
    the tested signal_engine equations, not inline approximations.
      * GRE/EPI use the measured T2* (was an inline T2·0.6 approximation), and
      * bSSFP/EPI/qMRI no longer fall through to the Inversion-Recovery equation.
    """
    from signal_engine import (spin_echo_signal, gradient_echo_signal,
                               inversion_recovery_signal, balanced_ssfp_signal)
    p = {"T1": 1000.0, "T2": 100.0, "T2star": 55.0, "PD": 1.0}   # T2*≠0.6·T2 (=60)
    TR, TE, TI, FA = 500.0, 20.0, 150.0, 40.0
    cs = win._curve_signal

    assert cs("Spin Echo", p, TR, TE, TI, FA) == pytest.approx(
        spin_echo_signal(p["T1"], p["T2"], p["PD"], TR, TE))
    assert cs("Inversion Recovery", p, TR, TE, TI, FA) == pytest.approx(
        inversion_recovery_signal(p["T1"], p["T2"], p["PD"], TR, TE, TI))
    # GRE / EPI: measured T2*, not T2·0.6
    gre = cs("Gradient Echo", p, TR, TE, TI, FA)
    assert gre == pytest.approx(gradient_echo_signal(p["T1"], 55.0, p["PD"], TR, TE, FA))
    assert gre != pytest.approx(gradient_echo_signal(p["T1"], 60.0, p["PD"], TR, TE, FA))
    assert cs("Echo Planar (EPI)", p, TR, TE, TI, FA) == pytest.approx(gre)
    # bSSFP: balanced steady state, NOT the IR equation it used to fall through to
    ssfp = cs("Balanced SSFP", p, 5.0, 2.5, TI, FA)
    assert ssfp == pytest.approx(balanced_ssfp_signal(p["T1"], p["T2"], p["PD"], 5.0, 2.5, FA))
    assert ssfp != pytest.approx(inversion_recovery_signal(p["T1"], p["T2"], p["PD"], 5.0, 2.5, TI))


def test_bssfp_curve_is_brighter_for_fluid(win):
    """At the GUI level: with the bSSFP curve fixed, CSF outshines white matter
    in TR-recovery mode (it read darkest under the old IR fall-through)."""
    import matplotlib.colors as mcolors
    win.plot_curve_mode.set("TR recovery")
    set_state(win, sequence="Balanced SSFP")
    win.recalculate()
    lines = {c: None for c in ("#74c0fc", "#ff6b6b")}      # CSF, WM
    for ln in win.axes[1].lines:
        for c in lines:
            if mcolors.same_color(ln.get_color(), c):
                lines[c] = np.asarray(ln.get_ydata(), float)
    csf, wm = lines["#74c0fc"], lines["#ff6b6b"]
    assert csf is not None and wm is not None and csf.size and wm.size
    assert csf.max() > wm.max(), "bSSFP CSF should be brighter than WM"
    win.plot_curve_mode.set("TE decay")                    # restore default


# --------------------------------------------------------------------------- #
#  All signal-curve modes render for representative sequences
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("mode", ["TE decay", "TR recovery", "TI sweep",
                                  "Contrast Map", "Histogram"])
@pytest.mark.parametrize("seq", ["Spin Echo", "Gradient Echo", "Inversion Recovery"])
def test_curve_modes_render(win, mode, seq):
    set_state(win, sequence=seq)
    win.plot_curve_mode.set(mode)
    win.recalculate()                       # exercises the mode's _plot_curves branch
    assert len(win.axes[1].get_children()) > 0
    win.plot_curve_mode.set("TE decay")


# --------------------------------------------------------------------------- #
#  Keyboard navigation / toggles (_on_key)
# --------------------------------------------------------------------------- #
def test_key_navigation_and_toggles(win):
    set_state(win, sequence="Spin Echo", slice_thickness=1)   # 1 slice == 1 voxel
    win.slice_idx.set(40)
    win._on_key(_Ev(key="up"));       assert win.slice_idx.get() == 41
    win._on_key(_Ev(key="down"));     assert win.slice_idx.get() == 40
    win._on_key(_Ev(key="pageup"));   assert win.slice_idx.get() == 45
    win._on_key(_Ev(key="pagedown")); assert win.slice_idx.get() == 40
    for key, var in [("k", win.show_kspace), ("m", win.multi_slice), ("p", win.show_psd)]:
        before = var.get()
        win._on_key(_Ev(key=key))
        assert var.get() is not before
    win.window_width = 0.3
    win._on_key(_Ev(key="r"))         # reset W/L
    assert win.window_width == 1.0
    set_state(win)                    # restore toggles/layout


# --------------------------------------------------------------------------- #
#  Cursor readout (_update_readout) — over the image and off it
# --------------------------------------------------------------------------- #
def test_cursor_readout(win):
    set_state(win, sequence="Spin Echo")
    H, W = win.current_image.shape[:2]
    win._update_readout(_Ev(xdata=W // 2, ydata=H // 2, inaxes=win.axes[0]))
    msg = win.statusBar().currentMessage()
    assert "signal:" in msg and "slice" in msg
    win._update_readout(_Ev(xdata=None, ydata=None, inaxes=win.axes[1]))   # off-image branch


# --------------------------------------------------------------------------- #
#  Export wrappers + protocol round-trip (writes only to a tmp dir)
# --------------------------------------------------------------------------- #
def test_export_and_load_protocol_roundtrip(win, tmp_path, monkeypatch):
    import export
    monkeypatch.setattr(export, "EXPORT_DIR", str(tmp_path))
    set_state(win, sequence="Spin Echo")
    win.TE.set(42.0)
    win.export_current_image()                 # writes a PNG to tmp
    win.export_current_protocol()
    win.export_current_report()
    saved = list(tmp_path.glob("*"))
    assert any(p.suffix == ".png" for p in saved) and any(p.suffix == ".json" for p in saved)

    proto = next(p for p in saved if p.suffix == ".json")
    monkeypatch.setattr(QFileDialog, "getOpenFileName",
                        staticmethod(lambda *a, **k: (str(proto), "")))
    win.TE.set(11.0)
    win.load_protocol_file()
    assert win.TE.get() == pytest.approx(42.0)  # restored from the protocol


# --------------------------------------------------------------------------- #
#  Misc methods
# --------------------------------------------------------------------------- #
def test_brain_subject_change(win):
    set_state(win, region="Brain")
    win.brain_subject.set("05")
    win.on_subject_change()                    # loads (or falls back) + rebuilds Brain
    assert win.region.get() == "Brain"
    assert_good_image(set_state(win, region="Brain"), "subject 05")
    win.brain_subject.set("04"); win.on_subject_change()   # restore default subject


def test_reset_oblique(win):
    set_state(win, sequence="Spin Echo")
    win.fov_planning.set(True)
    win.slice_tilt.set(20.0); win.slice_rot.set(10.0)
    win._reset_oblique()
    assert win.slice_tilt.get() == 0.0 and win.slice_rot.get() == 0.0
    assert win.inplane_fov_pct.get() == 100
    set_state(win)


@pytest.mark.parametrize("TR,TE,seq,expected", [
    (500, 15, "Spin Echo", "T1-weighted"),
    (4000, 90, "Spin Echo", "T2-weighted"),
    (4000, 15, "Spin Echo", "PD-weighted"),
    (1500, 40, "Spin Echo", "Mixed"),
    (5, 2.5, "Balanced SSFP", "T2/T1 (bSSFP)"),
    (4000, 50, "Echo Planar (EPI)", "T2* (EPI)"),
])
def test_determine_weighting(win, TR, TE, seq, expected):
    assert win.determine_weighting(TR, TE, seq) == expected


def test_compare_toggle_and_clear(win):
    set_state(win, sequence="Spin Echo")
    win.set_protocol_a()
    assert win.compare_mode.get()
    win.toggle_compare(); win.recalculate()      # toggle off
    assert not win.compare_mode.get()
    win.toggle_compare(); win.recalculate()      # toggle back on
    assert win.compare_mode.get()
    win.clear_compare()
    assert not win.compare_mode.get() and win.compare_params is None


# --------------------------------------------------------------------------- #
#  Scout / FOV-planning interaction (_scout_press / _motion / _release)
# --------------------------------------------------------------------------- #
def _scout_primary_axis(win):
    plane = next(p for p, ov in win._scout_overlays.items() if ov["role"] == "primary")
    return win.scout_axes[win._scout_plane_names.index(plane)]


def _axis_center(ax):
    xl, yl = ax.get_xlim(), ax.get_ylim()
    return (xl[0] + xl[1]) / 2, (yl[0] + yl[1]) / 2


def test_scout_move_drag(win):
    set_state(win, sequence="Spin Echo", region="Brain")
    win.fov_planning.set(True)                   # draws scout → sets _scout_box_info
    info = win._scout_box_info
    assert info is not None
    ax = _scout_primary_axis(win)
    cx, cy = info["x0"] + info["w"] / 2, info["y0"] + info["h"] / 2
    win._scout_press(_Ev(xdata=cx, ydata=cy, inaxes=ax))
    assert win._scout_drag is not None
    win._scout_motion(_Ev(xdata=cx + 4, ydata=cy + 12, inaxes=ax))
    win._scout_release(_Ev(xdata=cx, ydata=cy, inaxes=ax))
    assert win._scout_drag is None
    set_state(win)


def test_scout_oblique_and_secondary_drag(win):
    set_state(win, sequence="Spin Echo", region="Brain")
    win.fov_planning.set(True)
    win.slice_tilt.set(12.0)                      # oblique primary-drag branch
    win._draw_scout(win.get_current_params())
    ax = _scout_primary_axis(win)
    cx, cy = _axis_center(ax)
    win._scout_press(_Ev(xdata=cx, ydata=cy, inaxes=ax))
    win._scout_motion(_Ev(xdata=cx + 6, ydata=cy + 6, inaxes=ax))
    win._scout_release(_Ev(xdata=cx, ydata=cy, inaxes=ax))
    # secondary panel drag
    sec_plane = next((p for p, ov in win._scout_overlays.items()
                      if ov["role"] == "secondary"), None)
    if sec_plane is not None:
        sax = win.scout_axes[win._scout_plane_names.index(sec_plane)]
        win._scout_press(_Ev(xdata=cx, ydata=cy, inaxes=sax))
        win._scout_motion(_Ev(xdata=cx, ydata=cy + 8, inaxes=sax))
        win._scout_release(_Ev(xdata=cx, ydata=cy, inaxes=sax))
    win._reset_oblique()
    set_state(win)


def test_load_nifti_region(win, tmp_path, monkeypatch):
    """Load an external segmented NIfTI mask (success + empty-dialog + error)."""
    import nibabel as nib
    data = np.zeros((40, 40, 40), dtype=np.int16)   # TotalSeg-style label mask
    data[8:32, 10:30, 10:30] = 5
    data[12:28, 12:28, 12:28] = 3
    data[20:30, 14:26, 14:26] = 13
    p = tmp_path / "mask.nii.gz"
    nib.save(nib.Nifti1Image(data, np.eye(4)), str(p))

    # empty dialog → no-op
    monkeypatch.setattr(QFileDialog, "getOpenFileName",
                        staticmethod(lambda *a, **k: ("", "")))
    r0 = win.region.get(); win.load_nifti_region()
    assert win.region.get() == r0

    # real path → loaded as a "Real:" region and renders
    monkeypatch.setattr(QFileDialog, "getOpenFileName",
                        staticmethod(lambda *a, **k: (str(p), "")))
    win.load_nifti_region()
    assert win.region.get().startswith("Real:")
    win.recalculate()
    assert_good_image(win.current_image, "loaded NIfTI")
    # unknown axis convention → orientation labels suppressed
    assert win._orientation_letters("axial") is None

    # error path (bad file)
    win._load_mask_path("/no/such/file.nii.gz")
    assert "fail" in win.statusBar().currentMessage().lower()

    set_state(win, region="Brain")                  # restore


def test_browse_masks_indexes_folder(win, tmp_path, monkeypatch):
    """Folder picker → index → picker. Real folder scan, stubbed index + picker."""
    import nibabel as nib
    import region_index
    nib.save(nib.Nifti1Image(np.zeros((8, 8, 8), np.int16), np.eye(4)),
             str(tmp_path / "m.nii.gz"))             # so _mask_files() finds one
    entry = {"region": "Abdomen", "file": "m.nii.gz", "anatomy": "liver",
             "path": str(tmp_path / "m.nii.gz"), "scheme": "mr"}

    def fake_build_index(folder, progress=None):
        if progress:
            progress(1, 1, "m.nii.gz")               # exercise the progress callback
        return [entry]
    monkeypatch.setattr(region_index, "build_index", fake_build_index)
    monkeypatch.setattr(QFileDialog, "getExistingDirectory",
                        staticmethod(lambda *a, **k: str(tmp_path)))
    captured = {}
    monkeypatch.setattr(win, "_show_mask_picker", lambda e: captured.update(e=e))
    win.browse_masks()
    assert captured.get("e") == [entry]

    # empty folder → "no files" early return
    (tmp_path / "empty").mkdir()
    monkeypatch.setattr(QFileDialog, "getExistingDirectory",
                        staticmethod(lambda *a, **k: str(tmp_path / "empty")))
    win.browse_masks()                               # returns without calling picker


def test_show_mask_picker_loads_selection(win, tmp_path, monkeypatch):
    """Drive the modal picker: select the first item and 'Load selected'."""
    import nibabel as nib
    from PyQt6.QtWidgets import QDialog, QListWidget, QPushButton
    data = np.zeros((32, 32, 32), np.int16); data[8:24, 8:24, 8:24] = 5
    p = tmp_path / "pick.nii.gz"
    nib.save(nib.Nifti1Image(data, np.eye(4)), str(p))
    entry = {"region": "Abdomen", "file": "pick.nii.gz", "anatomy": "liver",
             "path": str(p), "scheme": "mr"}

    def fake_exec(dlg):
        lw = dlg.findChild(QListWidget); lw.setCurrentRow(0)
        for b in dlg.findChildren(QPushButton):
            if b.text() == "Load selected":
                b.click(); break                     # → do_load → dlg.accept()
        return dlg.result()
    monkeypatch.setattr(QDialog, "exec", fake_exec)
    win._show_mask_picker([entry])
    assert win.region.get().startswith("Real:")
    set_state(win, region="Brain")


def test_scout_angle_handle_drag(win):
    set_state(win, sequence="Spin Echo", region="Brain")
    win.fov_planning.set(True)
    if not win._scout_angle_handles:
        pytest.skip("no angle handles drawn for this geometry")
    lx0, ly0, lx1, ly1, plane, _var, _cx, _cy = win._scout_angle_handles[0]
    ax = win.scout_axes[win._scout_plane_names.index(plane)]
    win._scout_press(_Ev(xdata=lx0, ydata=ly0, inaxes=ax))     # endpoint → angle drag
    win._scout_motion(_Ev(xdata=lx0 + 5, ydata=ly0 + 5, inaxes=ax))
    win._scout_release(_Ev(xdata=lx0, ydata=ly0, inaxes=ax))
    win._reset_oblique()
    set_state(win)


# --------------------------------------------------------------------------- #
#  3-D (slab) acquisition + any-plane reformat
# --------------------------------------------------------------------------- #
def test_3d_acquisition_renders(win):
    set_state(win, sequence="Gradient Echo")
    win.acq3d.set(True); win.n_partitions.set(24); win.recalculate()
    assert_good_image(win.current_image, "3D acquisition")
    assert win.sim._recon3d is not None
    win.acq3d.set(False); win.recalculate()


def test_3d_reformat_reuses_block(win):
    set_state(win, sequence="Gradient Echo")
    win._set_orientation("axial"); win.slice_idx.set(90)
    win.acq3d.set(True); win.n_partitions.set(20); win.recalculate()
    block = id(win.sim._recon3d)
    win._set_orientation("coronal"); win.recalculate()      # reformat the slab
    assert id(win.sim._recon3d) == block, "orientation change must reformat, not re-scan"
    assert_good_image(win.current_image, "3D reformat")
    win.acq3d.set(False); win._set_orientation("axial"); win.recalculate()


def test_3d_param_change_reacquires(win):
    set_state(win, sequence="Spin Echo")
    win.acq3d.set(True); win.n_partitions.set(16); win.recalculate()
    block = id(win.sim._recon3d)
    win.TE.set(win.TE.get() + 25); win.recalculate()        # scan-affecting change
    assert id(win.sim._recon3d) != block, "param change must re-acquire"
    win.acq3d.set(False); win.recalculate()


def _overlay_text(win):
    return " ".join(t.get_text() for t in win.axes[0].texts)


def test_3d_overlay_badge_and_reformat_tag(win):
    """The 3-D slab badge always shows in 3-D mode; the REFORMAT tag appears only
    when the view plane differs from the acquired plane."""
    set_state(win, sequence="Gradient Echo")
    win._set_orientation("axial"); win.slice_idx.set(90)
    win.acq3d.set(True); win.n_partitions.set(20); win.recalculate()
    txt = _overlay_text(win)
    assert "3D SLAB" in txt and "20p" in txt
    assert "REFORMAT" not in txt, "acquired plane is not a reformat"
    # metrics panel also surfaces the 3-D slab + the √Nz SNR gain (√20 ≈ 4.5)
    assert "3D slab" in win.metrics_labels["slice_info"].text()
    arts = win.metrics_labels["artifacts"].text()
    assert "3D×20part" in arts and "4.5" in arts
    win._set_orientation("coronal"); win.recalculate()      # now a reformat
    txt = _overlay_text(win)
    assert "REFORMAT" in txt and "Axial" in txt
    win.acq3d.set(False); win._set_orientation("axial"); win.recalculate()
    assert "3D SLAB" not in _overlay_text(win)               # gone in 2-D mode
    assert "3D slab" not in win.metrics_labels["slice_info"].text()
