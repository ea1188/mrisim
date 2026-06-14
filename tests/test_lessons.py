"""Lesson data + browser→desktop translation (Qt-free)."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import lessons  # noqa: E402


def test_lessons_load_from_shared_json():
    data = lessons.load_lessons()
    assert len(data["lessons"]) >= 30, "expected the full shared lesson set"
    assert len(data["curriculum"]) >= 5
    for L in data["lessons"]:
        assert L.get("title") and L.get("steps"), L


def test_desktop_supported_filters_browser_only_panels():
    # A lesson that only sets supported keys is runnable on the desktop.
    ok = {"steps": [{"text": "x", "state": {"seq": "Spin Echo", "tr": 500, "te": 12}}]}
    assert lessons.desktop_supported(ok)
    # A browser-only panel toggled OFF is ignored (still supported)…
    off = {"steps": [{"text": "x", "state": {"tr": 500, "cmap": False}}]}
    assert lessons.desktop_supported(off)
    # …but turning that panel ON makes it the lesson's focus → unsupported.
    on = {"steps": [{"text": "x", "state": {"tr": 500, "cmap": True}}]}
    assert not lessons.desktop_supported(on)


def test_desktop_lessons_is_nonempty_subset():
    allL = lessons.load_lessons()["lessons"]
    desk = lessons.desktop_lessons()
    assert 0 < len(desk) <= len(allL)
    titles = {L["title"] for L in allL}
    assert {L["title"] for L in desk} <= titles
    # The beginner "Start here" track must survive the desktop filter.
    assert any(L.get("beginner") for L in desk)


def test_value_maps_cover_lesson_values():
    """Every coil/pathology code any lesson uses has a desktop label."""
    coils, pathos = set(), set()
    for L in lessons.load_lessons()["lessons"]:
        for s in L["steps"]:
            for st in (s.get("state", {}), s.get("compareWith") or {}):
                if "receivecoil" in st:
                    coils.add(st["receivecoil"])
                if "pathology" in st:
                    pathos.add(st["pathology"] or "")
    assert coils <= set(lessons.COIL_LABEL), coils - set(lessons.COIL_LABEL)
    assert pathos <= set(lessons.PATHOLOGY_LABEL), pathos - set(lessons.PATHOLOGY_LABEL)
