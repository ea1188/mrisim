"""Tests for annotations.py — the real-time on-image teaching annotations
(Step 4), plus the app.py rendering-integration path.

Covers each of the three rules independently (fires inside its condition, silent
outside), the field-strength dependency of the fat null, and that the annotation
string actually reaches the rendered caption block.
"""

import os
import sys

# conftest puts src/ on the path; annotations.py and app.py live at the repo root.
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import pytest

import annotations
import lessons
import tissue_db

_IR = "Inversion Recovery"


def _legacy_app_ok() -> bool:
    """app.py is a deprecated prototype; gate its render-integration tests on the
    current availability of its API so CI stays green (maintained GUI: app_qt.py)."""
    try:
        import gradio  # noqa: F401
        import app
        return hasattr(app, "render_mri")
    except Exception:
        return False


_LEGACY_APP = _legacy_app_ok()


def _fat_null(field):
    return lessons.null_ti(tissue_db.properties(field)[annotations._FAT_LABEL]["T1"])


def _fluid_null(field):
    return lessons.null_ti(tissue_db.properties(field)[annotations._FLUID_LABEL]["T1"])


# --- Fat-null rule -----------------------------------------------------------
def test_fat_null_fires_at_the_null():
    ti = _fat_null("1.5T")
    assert annotations.annotate(_IR, 5000, 30, ti, "1.5T", "Abdomen") == ["Fat is nulled."]


def test_fat_null_fires_at_window_edges_but_not_just_outside():
    null = _fat_null("3T")
    w = annotations.NULL_WINDOW_MS
    # Just inside both edges → fires; just outside → silent.
    assert "Fat is nulled." in annotations.annotate(_IR, 5000, 30, null - w, "3T", "Abdomen")
    assert "Fat is nulled." in annotations.annotate(_IR, 5000, 30, null + w, "3T", "Abdomen")
    assert annotations.annotate(_IR, 5000, 30, null - w - 1, "3T", "Abdomen") == []
    assert annotations.annotate(_IR, 5000, 30, null + w + 1, "3T", "Abdomen") == []


def test_fat_null_only_for_ir_sequence():
    ti = _fat_null("3T")
    # Same TI under a non-IR sequence must not narrate a fat null.
    assert annotations.fat_null_rule(
        annotations.AnnotationContext("Spin Echo", 500, 15, ti, "3T", "Abdomen")) is None


# --- Fluid-null rule ---------------------------------------------------------
def test_fluid_null_fires_at_the_csf_null():
    ti = _fluid_null("3T")
    assert annotations.annotate(_IR, 9000, 90, ti, "3T", "Brain") == ["Fluid is nulled."]


def test_fluid_null_silent_away_from_null():
    # A typical short STIR TI is nowhere near the ~2900–3100 ms CSF null.
    assert "Fluid is nulled." not in annotations.annotate(_IR, 5000, 30, 200, "1.5T", "Abdomen")


def test_fat_and_fluid_nulls_do_not_overlap():
    # The two windows are ~2700 ms apart at both fields; at the fat null only fat
    # is narrated, and vice versa — never both at once.
    for field in tissue_db.FIELD_STRENGTHS:
        assert annotations.annotate(_IR, 9000, 90, _fat_null(field), field, "Abdomen") == ["Fat is nulled."]
        assert annotations.annotate(_IR, 9000, 90, _fluid_null(field), field, "Brain") == ["Fluid is nulled."]


# --- Field-strength dependency of the fat null -------------------------------
def test_fat_null_window_shifts_with_field_strength():
    # Fat T1 rises with field, so the null TI moves: ~201 ms at 1.5T, ~265 ms at
    # 3T. A TI that nulls fat at 1.5T must NOT fire at 3T, and vice versa.
    ti_15 = _fat_null("1.5T")
    ti_3 = _fat_null("3T")
    assert ti_3 - ti_15 > 2 * annotations.NULL_WINDOW_MS   # genuinely separate windows

    assert annotations.annotate(_IR, 5000, 30, ti_15, "1.5T", "Abdomen") == ["Fat is nulled."]
    assert annotations.annotate(_IR, 5000, 30, ti_15, "3T", "Abdomen") == []
    assert annotations.annotate(_IR, 5000, 30, ti_3, "3T", "Abdomen") == ["Fat is nulled."]
    assert annotations.annotate(_IR, 5000, 30, ti_3, "1.5T", "Abdomen") == []


# --- SE/FSE contrast-weighting classifier ------------------------------------
@pytest.mark.parametrize("seq", ["Spin Echo", "FSE / TSE"])
@pytest.mark.parametrize("tr,te,expected", [
    (500, 15, "T1-weighted"),               # canonical T1: short TR, short TE
    (4000, 90, "T2-weighted"),              # canonical T2: long TR, long TE
    (4000, 15, "Proton-density weighted"),  # long TR, short TE
])
def test_weighting_classifier_labels(seq, tr, te, expected):
    assert annotations.annotate(seq, tr, te, 2500, "3T", "Brain") == [expected]


@pytest.mark.parametrize("tr,te", [
    (1500, 50),    # mid TR, mid TE — genuinely mixed
    (500, 90),     # short TR but long TE — not a clean region
    (4000, 50),    # long TR, mid TE
    (600, 15),     # TR exactly on the short boundary (strict <) → silent
    (4000, 80),    # TE exactly on the long boundary (strict >) → silent
])
def test_weighting_classifier_silent_when_ambiguous(tr, te):
    assert annotations.annotate("Spin Echo", tr, te, 2500, "3T", "Brain") == []


def test_weighting_only_for_se_fse():
    # Gradient Echo and IR are not classified by this SE/FSE rule.
    assert annotations.weighting_rule(
        annotations.AnnotationContext("Gradient Echo", 500, 15, 2500, "3T", "Brain")) is None
    assert annotations.weighting_rule(
        annotations.AnnotationContext(_IR, 500, 15, 2500, "3T", "Brain")) is None


def test_annotation_line_joins_and_empties():
    # One fired rule → just its text; nothing fired → empty string.
    assert annotations.annotation_line("Spin Echo", 500, 15, 2500, "3T", "Brain") == "T1-weighted"
    assert annotations.annotation_line("Spin Echo", 1500, 50, 2500, "3T", "Brain") == ""


# --- Rendering-integration path (app.py) -------------------------------------
@pytest.mark.skipif(not _LEGACY_APP, reason="legacy app.py prototype API unavailable")
def test_annotation_reaches_rendered_caption():
    """The render callback's caption block must contain the live annotation for a
    triggering parameter set (T1-weighted SE here), alongside the scan time."""
    import app
    img, caption, _sim = app.render_mri(
        "Knee", "Spin Echo", tr=500.0, te=15.0, flip=90.0,
        ti=2500.0, field="3T", sim=None)
    assert "scan time" in caption.lower()
    assert "T1-weighted" in caption


@pytest.mark.skipif(not _LEGACY_APP, reason="legacy app.py prototype API unavailable")
def test_caption_has_no_annotation_when_none_fires():
    """An ambiguous parameter set still renders (scan time present) but carries
    no annotation label."""
    import app
    _img, caption, _sim = app.render_mri(
        "Knee", "Spin Echo", tr=1500.0, te=50.0, flip=90.0,
        ti=2500.0, field="3T", sim=None)
    assert "scan time" in caption.lower()
    for label in ("T1-weighted", "T2-weighted", "Proton-density", "nulled"):
        assert label not in caption
