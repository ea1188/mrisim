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

from presets import (get_preset, get_preset_names, get_preset_region,
                     get_preset_plane)

# The sequences offered in the GUI dropdown (app_qt build_controls).
SEQUENCES = [
    "Spin Echo", "FSE / TSE", "Gradient Echo", "Inversion Recovery",
    "Balanced SSFP", "Diffusion (DWI)", "MR Angiography", "fMRI (BOLD)",
    "Quantitative (qMRI)", "Echo Planar (EPI)",
]

# Full-FOV anatomical images — the energy-spread (anti-collapse) check is only
# meaningful for these; MRA MIPs, activation/qMRI maps are legitimately sparse.
ANATOMICAL = {"Spin Echo", "FSE / TSE", "Gradient Echo", "Inversion Recovery",
              "Balanced SSFP", "Echo Planar (EPI)"}

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
              w.show_tissue_overlay, w.compare_mode):
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
    def __init__(self, button=None, x=120, y=120, dblclick=False, step=0, ctrl=False):
        self.button = button
        self.x = x; self.y = y
        self.dblclick = dblclick
        self.step = step
        self.guiEvent = _GUIEvent(ctrl)
        self.xdata = self.ydata = self.inaxes = None
        self.key = None


def test_scroll_steps_slice(win):
    set_state(win, sequence="Spin Echo")
    win.slice_idx.set(40)
    win._on_scroll(_Ev(button="up", step=1))
    assert win.slice_idx.get() == 41
    win._on_scroll(_Ev(button="down", step=-1))
    assert win.slice_idx.get() == 40


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
