"""Tests for the guided lessons: pure-data definitions, the resolved per-control
state (lock/unlock semantics), and that each lesson renders without error.
"""

import os
import sys

import numpy as np
import pytest

# app.py and lessons.py live at the repo root; conftest only adds src/.
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import lessons


# --- Lesson definitions (pure data) -----------------------------------------
def test_three_lessons_defined():
    assert set(lessons.LESSONS) == {"What TR does", "Nulling fat with STIR", "SE vs FSE"}
    # Free Explore is offered as a key but is not a real lesson.
    assert lessons.keys()[0] == lessons.FREE_EXPLORE
    assert lessons.get(lessons.FREE_EXPLORE) is None


@pytest.mark.parametrize("key", list(lessons.LESSONS))
def test_lesson_required_fields_present(key):
    """Each lesson carries title, explanation, region, sequence, and lock info."""
    lesson = lessons.get(key)
    assert lesson.title and isinstance(lesson.title, str)
    # Resident-level explanation: a real paragraph ending in a concrete instruction.
    assert isinstance(lesson.explanation, str) and len(lesson.explanation) > 120
    assert lesson.region in ("Brain", "Abdomen", "Knee", "Spine", "Pelvis")
    assert lesson.left.sequence  # left panel always has a sequence
    assert isinstance(lesson.unlocked, frozenset) and len(lesson.unlocked) >= 1
    if lesson.compare:
        assert lesson.right is not None and lesson.right.sequence


def test_se_vs_fse_uses_two_sequences():
    """The SE vs FSE lesson needs different sequences per panel simultaneously."""
    lesson = lessons.get("SE vs FSE")
    assert lesson.compare is True
    assert lesson.left.sequence == "Spin Echo"
    assert lesson.right.sequence == "FSE / TSE"
    assert lesson.show_scan_time is True


def test_stir_targets_fat_null():
    lesson = lessons.get("Nulling fat with STIR")
    assert lesson.left.sequence == "Inversion Recovery"
    assert lesson.show_target_ti is True
    # ln(2) * fat T1(1.5T = 290 ms) ≈ 201 ms
    assert abs(lessons.fat_null_ti(290.0) - 201.0) < 1.0


# --- resolve(): lock / unlock / visibility semantics ------------------------
def test_resolve_locks_all_but_unlocked_controls():
    """'What TR does' leaves only TR interactive; everything else is locked."""
    view = lessons.resolve("What TR does")
    assert view.controls["tr_l"].interactive is True
    for name in ("te_l", "flip_l", "ti_l", "field", "region", "sequence_l"):
        assert view.controls[name].interactive is False, name
    assert view.compare is False


def test_resolve_stir_unlocks_ti_and_field():
    view = lessons.resolve("Nulling fat with STIR")
    assert view.controls["ti_l"].interactive is True
    assert view.controls["field"].interactive is True   # field changes the target
    assert view.controls["tr_l"].interactive is False
    assert view.controls["ti_l"].visible is True         # IR → TI slider shown
    assert view.region == "Abdomen"


def test_resolve_se_vs_fse_locks_both_sequences():
    view = lessons.resolve("SE vs FSE")
    assert view.compare is True
    assert view.controls["sequence_l"].interactive is False
    assert view.controls["sequence_r"].interactive is False
    assert view.controls["field"].interactive is True    # shared field stays unlocked


def test_free_explore_unlocks_everything():
    """Leaving a lesson (Free Explore) releases every lock — the key restore."""
    view = lessons.resolve(lessons.FREE_EXPLORE)
    for name in lessons.CONTROL_NAMES:
        assert view.controls[name].interactive is True, name
    assert view.compare is False
    assert view.explanation == ""


def test_switching_lesson_then_free_explore_restores_locked_sliders():
    """A slider locked by one lesson must be interactive again after Free Explore."""
    locked = lessons.resolve("What TR does")
    assert locked.controls["te_l"].interactive is False
    restored = lessons.resolve(lessons.FREE_EXPLORE)
    assert restored.controls["te_l"].interactive is True
    # And a different lesson re-locks a different set.
    stir = lessons.resolve("Nulling fat with STIR")
    assert stir.controls["tr_l"].interactive is False
    assert stir.controls["ti_l"].interactive is True


# --- Each lesson renders through the app callback without error -------------
@pytest.mark.parametrize("key", lessons.keys())
def test_apply_lesson_renders(key):
    """Constructing the lesson's callback invocation produces valid 2-D images."""
    import app

    out = app.apply_lesson(key, None, None)
    assert isinstance(out, tuple) and len(out) == 23
    img_l, img_r = out[18], out[19]
    for img in (img_l, img_r):
        assert isinstance(img, np.ndarray)
        assert img.ndim == 2
        assert img.max() > 0
    # Last element is the lesson key echoed into lesson_state.
    assert out[22] == key
