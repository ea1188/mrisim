"""Guard the course teaching figures referenced by education modules in
data/course_content.json (every <img src="img/course/...">).

Two kinds of figure:
  * ENGINE figures — rendered by scripts/render_course_figures.py (its FIGURES
    slugs). Ours; no attribution needed.
  * CURATED figures — real photos/anatomy the engine can't make. Each MUST be
    logged in data/course_image_credits.json with a commercial-safe license
    (route B), so the paid/free course never ships a -NC / -ND image, and any
    CC-BY image must actually render its attribution to the reader.

The curated checks are fail-closed: a referenced image that is neither an engine
slug nor a logged credit fails the build. Source of truth: course_content.json
education bodies, web/img/course/, scripts/render_course_figures.py, and
data/course_image_credits.json."""
import json
import os
import re

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(HERE, "data", "course_content.json")
IMG_DIR = os.path.join(HERE, "web", "img", "course")
RENDER_SCRIPT = os.path.join(HERE, "scripts", "render_course_figures.py")
CREDITS = os.path.join(HERE, "data", "course_image_credits.json")

_IMG_RE = re.compile(r'img/course/([A-Za-z0-9._-]+)')
_SLUG_RE = re.compile(r'"slug":\s*"([A-Za-z0-9._-]+)"')

# Commercial-safe only (mirrors tests/test_course_images.py): a paid product may
# not use -NC / -ND / "free for education". Kept strict even while the course is
# free, so re-paywalling later needs no relicensing.
ALLOWED_LICENSES = {"CC0-1.0", "Public-Domain", "CC-BY-4.0", "CC-BY-3.0", "CC-BY-2.0", "Owner-Original"}
# Licenses whose attribution must be visible to the reader (rendered in the html).
_ATTRIBUTION_REQUIRED = {"CC-BY-4.0", "CC-BY-3.0", "CC-BY-2.0"}


def _education_modules():
    with open(SRC, encoding="utf-8") as f:
        data = json.load(f)
    return [it for it in data["items"] if it.get("kind") == "education"]


def _figure_refs():
    """List of (img_name, module_title, module_html) for every course figure ref."""
    out = []
    for it in _education_modules():
        html = it.get("body", {}).get("html", "")
        title = it.get("body", {}).get("title", "")
        for name in _IMG_RE.findall(html):
            out.append((name, title, html))
    return out


def _engine_slugs():
    """The image filenames scripts/render_course_figures.py produces (its slugs)."""
    with open(RENDER_SCRIPT, encoding="utf-8") as f:
        return {s + ".jpg" for s in _SLUG_RE.findall(f.read())}


def _credits():
    with open(CREDITS, encoding="utf-8") as f:
        return json.load(f)["credits"]


def validate_credit(name, c):
    """Raise AssertionError if a curated-image credit entry is invalid."""
    assert c.get("title"), f"{name}: credit needs a title"
    lic = c.get("license")
    assert lic in ALLOWED_LICENSES, f"{name}: license {lic!r} not commercial-safe"
    if lic != "Owner-Original":
        assert c.get("author") and c.get("source_url"), f"{name}: {lic} credit needs author + source_url"


# --- structural guards ------------------------------------------------------
def test_every_referenced_figure_exists():
    refs = _figure_refs()
    assert refs, "expected at least one course figure to be wired in"
    for name, _title, _html in refs:
        assert os.path.isfile(os.path.join(IMG_DIR, name)), f"missing course figure: {name}"


def test_figure_references_unique_per_module():
    for it in _education_modules():
        names = _IMG_RE.findall(it.get("body", {}).get("html", ""))
        assert len(names) == len(set(names)), f"duplicate figure ref in module: {it['body'].get('title')}"


# --- route-B licensing guards (fail-closed) ---------------------------------
def test_curated_images_are_licensed():
    """Any referenced image that is not an engine render must be a logged,
    commercial-safe curated credit. Fail-closed: unknown image => failure."""
    engine = _engine_slugs()
    credits = _credits()
    for name, title, _html in _figure_refs():
        if name in engine:
            continue                                     # engine figure, ours
        assert name in credits, (
            f"curated image {name!r} (module {title!r}) is not an engine render and has no "
            f"entry in data/course_image_credits.json — add a commercial-safe credit or it cannot ship")
        validate_credit(name, credits[name])


def test_cc_by_images_render_attribution():
    """A CC-BY image must show its attribution to the reader: the figcaption of
    the module that uses it must contain the credited source_url."""
    credits = _credits()
    for name, title, html in _figure_refs():
        c = credits.get(name)
        if not c or c.get("license") not in _ATTRIBUTION_REQUIRED:
            continue
        assert c["source_url"] in html, (
            f"CC-BY image {name!r} in module {title!r} must render its attribution "
            f"(the source_url) in the figure so the license is satisfied")


def test_logged_credits_are_all_valid():
    """Every entry in the log is well-formed and commercial-safe, even before it
    is wired into a module."""
    for name, c in _credits().items():
        validate_credit(name, c)


# --- validator unit tests (prove the guard rejects bad licenses) ------------
def _pytest_raises():
    import pytest
    return pytest.raises(AssertionError)


def test_validator_accepts_cc_by():
    validate_credit("x.jpg", {"title": "t", "author": "Dr X", "license": "CC-BY-4.0",
                              "source_url": "https://commons.wikimedia.org/x"})


def test_validator_accepts_owner_original_without_source():
    validate_credit("o.jpg", {"title": "our photo", "author": "MRISim", "license": "Owner-Original"})


def test_validator_rejects_non_commercial():
    with _pytest_raises():
        validate_credit("x.jpg", {"title": "t", "author": "a", "license": "CC-BY-NC-4.0",
                                  "source_url": "https://u"})


def test_validator_rejects_no_derivatives():
    with _pytest_raises():
        validate_credit("x.jpg", {"title": "t", "author": "a", "license": "CC-BY-ND-4.0",
                                  "source_url": "https://u"})


def test_validator_rejects_missing_source_for_cc_by():
    with _pytest_raises():
        validate_credit("x.jpg", {"title": "t", "author": "a", "license": "CC-BY-4.0"})


def test_validator_rejects_missing_title():
    with _pytest_raises():
        validate_credit("x.jpg", {"author": "a", "license": "CC0-1.0", "source_url": "https://u"})
