"""Guard the protocol planner's reference-angulation images: every "*.jpg" that
web/protocol.js names (the ANGLE_REFS table) must exist under web/img/angles/,
so the "Reference angulation" overlay never points at a missing file. Every .jpg
literal in protocol.js is an angle-reference image."""
import os
import re

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROTOCOL_JS = os.path.join(HERE, "web", "protocol.js")
ANGLES_DIR = os.path.join(HERE, "web", "img", "angles")

_JPG_RE = re.compile(r'"([A-Za-z0-9_]+\.jpg)"')


def _referenced():
    with open(PROTOCOL_JS, encoding="utf-8") as f:
        return sorted(set(_JPG_RE.findall(f.read())))


def test_every_angle_ref_image_exists():
    refs = _referenced()
    assert refs, "expected protocol.js to reference angle images"
    for name in refs:
        assert os.path.isfile(os.path.join(ANGLES_DIR, name)), f"missing angle reference image: {name}"
