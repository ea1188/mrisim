"""Protocol-planning data: the exam → sequence-queue definitions (protocols.py)."""
import pytest

import protocols
import presets


def test_expected_exams_exist():
    exams = protocols.exam_names()
    assert {"Brain", "Spine", "Knee"} <= set(exams)


@pytest.mark.parametrize("exam", ["Brain", "Spine", "Knee"])
def test_protocol_is_localizer_first_then_real_presets(exam):
    q = protocols.get_protocol(exam)
    assert q[0]["preset"] == protocols.LOCALIZER and q[0]["sequence"] is None
    assert len(q) >= 5
    # every non-localizer entry names a real preset (of the right region) with a sequence
    for item in q[1:]:
        assert presets.get_preset(item["preset"]) is not None, item["preset"]
        assert (presets.get_preset_region(item["preset"]) or "") == exam, item["preset"]
        assert item["sequence"] and item["label"], item


def test_unknown_exam_is_empty():
    assert protocols.get_protocol("Nope") == []
