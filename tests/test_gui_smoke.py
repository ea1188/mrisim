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
    """Drive the window the way a user would: region → sequence → plane → params,
    then render. Returns the reconstructed image."""
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
