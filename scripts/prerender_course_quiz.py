"""Pre-render each premium image-question's scan to a static JPEG under
web/img/course-quiz/, so the course can show image questions without loading the
engine in the browser. Mirrors scripts/prerender_lessons.py.

For every kind:"quiz" item in data/course_content.json whose body has both a
`setup` (the engine render payload) and an `img` filename, we call web_adapter's
render on the setup and write web/img/course-quiz/<img>. Idempotent; run locally
(needs numpy/matplotlib/Pillow), commit the images. Not wired into CI.
"""
import base64
import io
import json
import os
import sys

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

import matplotlib  # noqa: E402
matplotlib.use("Agg")
import web_adapter  # noqa: E402

OUT = os.path.join(ROOT, "web", "img", "course-quiz")

# Real body-region atlases the browser lazy-fetches; inject them the way
# load_region would on the build host (L/R flip on axis 2). Mirrors prerender_lessons.py.
_BODY_SRC = {
    "Knee": "data/knee_kb3d/atlas.npy",
    "Spine": "data/spider_spine/atlas.npy",
    "Abdomen": "data/TotalsegmentatorMRI_dataset_v200/s0246/atlas_iso_adapt_256.npy",
    "Pelvis": "data/TotalsegmentatorMRI_dataset_v200/s0187/atlas_iso_adapt_256.npy",
    "Torso": "data/TotalsegmentatorMRI_dataset_v200/s0250/atlas_iso_adapt_256.npy",
}


from prerender_lessons import ensure_region  # noqa: E402  (full-fidelity: atlas+texture+mixel, straighten+flip)


def main():
    data = json.load(open(os.path.join(ROOT, "data", "course_content.json")))
    host = web_adapter._host()
    os.makedirs(OUT, exist_ok=True)
    n = 0
    for it in data.get("items", []):
        if it.get("kind") != "quiz":
            continue
        body = it.get("body", {})
        setup, img = body.get("setup"), body.get("img")
        if not setup or not img:
            continue  # curated (credit) images have no setup -> skipped; they ship as committed files
        try:
            ensure_region(host, setup.get("region", "Brain"))
            # Render clean (like the free read-the-scan quiz's SNR 120) unless the question
            # sets its own snr_level, so the anatomy/pathology reads clearly instead of grainy.
            setup.setdefault("params", {}).setdefault("snr_level", 120)
            res = host.render(setup)
            png = base64.b64decode(res["image"].split(",")[-1])
        except Exception as e:            # never fail the whole build on one image
            print(f"  {img}: render skipped ({e})")
            continue
        im = Image.open(io.BytesIO(png)).convert("RGB")
        if im.width > 600:
            im = im.resize((600, round(im.height * 600 / im.width)), Image.LANCZOS)
        im.save(os.path.join(OUT, img), format="JPEG", quality=85, optimize=True)
        n += 1
    print(f"pre-rendered {n} course-quiz images -> web/img/course-quiz/")


if __name__ == "__main__":
    main()
