"""Premium image questions must have a render setup and a committed image file
(no broken image references). Source: data/course_content.json + web/img/course-quiz/."""
import json
import os

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(HERE, "data", "course_content.json")
IMG_DIR = os.path.join(HERE, "web", "img", "course-quiz")


def _image_quiz_items():
    with open(SRC, encoding="utf-8") as f:
        data = json.load(f)
    return [it for it in data["items"] if it.get("kind") == "quiz" and it.get("body", {}).get("img")]


def test_image_questions_have_setup_and_file():
    items = _image_quiz_items()
    assert items, "expected at least one image question"
    for it in items:
        b = it["body"]
        setup = b.get("setup")
        assert isinstance(setup, dict) and setup.get("region") and setup.get("params"), b.get("img")
        path = os.path.join(IMG_DIR, b["img"])
        assert os.path.isfile(path), f"missing rendered image: {b['img']}"


def test_image_filenames_unique():
    imgs = [it["body"]["img"] for it in _image_quiz_items()]
    assert len(imgs) == len(set(imgs)), "duplicate img filenames"
