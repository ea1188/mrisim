"""Guard the course teaching figures: every <img src="img/course/..."> referenced
by an education module in data/course_content.json must exist on disk under
web/img/course/ (rendered by scripts/render_course_figures.py and committed).
Catches a wired-but-unrendered figure — a broken image in the paid course.
Source of truth: data/course_content.json education bodies + web/img/course/."""
import json
import os
import re

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(HERE, "data", "course_content.json")
IMG_DIR = os.path.join(HERE, "web", "img", "course")

_IMG_RE = re.compile(r'img/course/([A-Za-z0-9._-]+)')


def _referenced_figures():
    """Every img/course/<file> path appearing in any education module's html."""
    with open(SRC, encoding="utf-8") as f:
        data = json.load(f)
    refs = []
    for it in data["items"]:
        if it.get("kind") != "education":
            continue
        html = it.get("body", {}).get("html", "")
        refs.extend(_IMG_RE.findall(html))
    return refs


def test_every_referenced_figure_exists():
    refs = _referenced_figures()
    assert refs, "expected at least one course figure to be wired in"
    for name in refs:
        assert os.path.isfile(os.path.join(IMG_DIR, name)), f"missing course figure: {name}"


def test_figure_references_unique_per_module():
    # A module referencing the same figure twice is almost certainly a paste error.
    with open(SRC, encoding="utf-8") as f:
        data = json.load(f)
    for it in data["items"]:
        if it.get("kind") != "education":
            continue
        names = _IMG_RE.findall(it.get("body", {}).get("html", ""))
        assert len(names) == len(set(names)), f"duplicate figure ref in module: {it['body'].get('title')}"
