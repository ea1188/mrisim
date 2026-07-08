"""All 19 premium education modules must carry well-formed, dash-free depth fields
(worked_example, memory_hooks, exam_traps). Source of truth: data/course_content.json."""
import json
import os
import re

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(HERE, "data", "course_content.json")
DASH = re.compile(r"[—–]")  # em dash, en dash


def _edu_bodies():
    with open(SRC, encoding="utf-8") as f:
        data = json.load(f)
    return [it["body"] for it in data["items"] if it.get("kind") == "education"]


def test_all_education_modules_have_depth_fields():
    bodies = _edu_bodies()
    assert len(bodies) == 19, len(bodies)
    for b in bodies:
        title = b.get("title")
        assert isinstance(b.get("worked_example"), str) and b["worked_example"].strip(), title
        hooks = b.get("memory_hooks")
        assert isinstance(hooks, list) and 1 <= len(hooks) <= 3, title
        assert all(isinstance(x, str) and x.strip() for x in hooks), title
        traps = b.get("exam_traps")
        assert isinstance(traps, list) and 1 <= len(traps) <= 3, title
        assert all(isinstance(x, str) and x.strip() for x in traps), title


def test_education_bodies_have_no_em_dashes():
    """Covers the depth fields and the existing html/keypoints, per the plan."""
    for b in _edu_bodies():
        parts = [b.get("worked_example", ""), b.get("html", "")]
        parts += b.get("memory_hooks", []) + b.get("exam_traps", []) + b.get("keypoints", [])
        assert not DASH.search(" ".join(parts)), b.get("title")
