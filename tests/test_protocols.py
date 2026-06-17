"""Protocol-planning data: the exam → sequence-queue definitions (protocols.py)."""
import protocols
import presets


def test_brain_protocol_is_localizer_first_then_real_presets():
    exams = protocols.exam_names()
    assert "Brain" in exams
    q = protocols.get_protocol("Brain")
    assert q[0]["preset"] == protocols.LOCALIZER and q[0]["sequence"] is None
    assert len(q) >= 6
    # every non-localizer entry names a real preset with a sequence
    for item in q[1:]:
        assert presets.get_preset(item["preset"]) is not None, item["preset"]
        assert item["sequence"], item
        assert item["label"]


def test_unknown_exam_is_empty():
    assert protocols.get_protocol("Nope") == []
