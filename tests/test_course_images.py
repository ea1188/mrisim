"""Premium image questions carry exactly one image source: a simulator `setup`
(rendered by scripts/prerender_course_quiz.py) or a curated `credit` (a committed
CC0/PD/CC-BY image). This guards the XOR, the commercial-safe license allow-list,
and that every referenced image file exists. Source: data/course_content.json."""
import json
import os

import pytest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(HERE, "data", "course_content.json")
IMG_DIR = os.path.join(HERE, "web", "img", "course-quiz")

# Commercial-safe only: a paid product may not use -NC / -ND / "free for education".
ALLOWED_LICENSES = {"CC0-1.0", "Public-Domain", "CC-BY-4.0", "CC-BY-3.0", "CC-BY-2.0"}


def validate_image_body(body):
    """Raise AssertionError if an image-question body violates the schema."""
    img = body.get("img")
    assert img, "image body must have an img filename"
    has_setup = isinstance(body.get("setup"), dict)
    has_credit = isinstance(body.get("credit"), dict)
    assert has_setup != has_credit, f"{img}: body must have exactly one of setup/credit"
    if has_setup:
        s = body["setup"]
        assert s.get("region") and s.get("params"), f"{img}: setup needs region + params"
    else:
        c = body["credit"]
        assert c.get("author") and c.get("source_url") and c.get("title"), f"{img}: credit needs author/source_url/title"
        assert c.get("license") in ALLOWED_LICENSES, f"{img}: license {c.get('license')!r} not commercial-safe"


def test_validator_rejects_both_sources():
    with pytest.raises(AssertionError):
        validate_image_body({"img": "x.jpg", "setup": {"region": "Brain", "params": {}}, "credit": {"author": "a", "license": "CC0-1.0", "source_url": "u", "title": "t"}})


def test_validator_rejects_neither_source():
    with pytest.raises(AssertionError):
        validate_image_body({"img": "x.jpg"})


def test_validator_rejects_non_commercial_license():
    with pytest.raises(AssertionError):
        validate_image_body({"img": "x.jpg", "credit": {"author": "a", "license": "CC-BY-NC-4.0", "source_url": "u", "title": "t"}})


def test_validator_rejects_incomplete_credit():
    with pytest.raises(AssertionError):
        validate_image_body({"img": "x.jpg", "credit": {"license": "CC0-1.0"}})


def test_validator_accepts_valid_setup_and_credit():
    validate_image_body({"img": "s.jpg", "setup": {"region": "Brain", "params": {"TR": 500}}})
    validate_image_body({"img": "c.jpg", "credit": {"author": "Dr X", "license": "CC-BY-4.0", "source_url": "https://commons.wikimedia.org/x", "title": "t"}})


def _image_quiz_items():
    with open(SRC, encoding="utf-8") as f:
        data = json.load(f)
    return [it for it in data["items"] if it.get("kind") == "quiz" and it.get("body", {}).get("img")]


def test_all_image_questions_valid_and_file_present():
    items = _image_quiz_items()
    assert items, "expected at least one image question"
    for it in items:
        b = it["body"]
        validate_image_body(b)
        assert os.path.isfile(os.path.join(IMG_DIR, b["img"])), f"missing image file: {b['img']}"


def test_image_filenames_unique():
    imgs = [it["body"]["img"] for it in _image_quiz_items()]
    assert len(imgs) == len(set(imgs)), "duplicate img filenames"
