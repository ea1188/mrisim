"""Render labeled *teaching figures* for the premium course and save them to
web/img/course/<slug>.jpg. Unlike scripts/prerender_lessons.py and
scripts/prerender_course_quiz.py (one engine render per file), a course figure is
a COMPOSITE: several engine renders of the same anatomy tiled side by side with
per-panel headers and parameter captions, so a single image can teach a contrast
comparison (T1 vs PD vs T2), a suppression comparison (STIR vs FLAIR), etc.

Every panel is a real MRISim engine render (zero license risk — the user's own
engine), so the figures match the app's look exactly and are safe for the paid
course. Run locally (needs numpy/matplotlib/Pillow), commit the JPEGs. Not wired
into CI; a guard test (tests/test_course_figures.py) checks every figure the
course html references actually exists on disk.

    python3.11 scripts/render_course_figures.py
"""
import base64
import io
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

import matplotlib  # noqa: E402
matplotlib.use("Agg")
import web_adapter  # noqa: E402

OUT = os.path.join(ROOT, "web", "img", "course")

# Real body-region atlases the browser lazy-fetches; inject them the way
# load_region would on the build host (L/R flip on axis 2). Mirrors the sibling
# prerender scripts so build figures match the browser.
_BODY_SRC = {
    "Knee": "data/knee_kb3d/atlas.npy",
    "Spine": "data/spider_spine/atlas.npy",
    "Abdomen": "data/TotalsegmentatorMRI_dataset_v200/s0246/atlas_iso_adapt_256.npy",
    "Pelvis": "data/TotalsegmentatorMRI_dataset_v200/s0187/atlas_iso_adapt_256.npy",
    "Torso": "data/TotalsegmentatorMRI_dataset_v200/s0250/atlas_iso_adapt_256.npy",
}

# --- visual style (matches the app's dark clinical theme: flat, no gradients) ---
BG = (13, 15, 18)          # figure background (~ app --bg)
PANEL_BG = (0, 0, 0)       # behind each MR tile
ACCENT = (122, 162, 247)   # panel header (app accent blue)
CAPTION = (150, 158, 168)  # param caption (app --muted)
LINE = (38, 43, 51)        # hairline separators (app --line)
TILE = 300                 # rendered MR tile size, px
GAP = 2                    # gap between tiles
PAD = 14                   # outer padding
HEAD_H = 30                # header strip height (weighting name)
CAP_H = 26                 # caption strip height (params)


def _font(size, bold=False):
    """A sans TTF if present (local build host), else PIL's bitmap default."""
    for path in (
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def ensure_region(host, region):
    if region == "Brain" or region in host._region_cache:
        host.load_region(region)
        return
    src = _BODY_SRC.get(region)
    if src and os.path.exists(os.path.join(ROOT, src)):
        vol = np.load(os.path.join(ROOT, src))
        if region in web_adapter._BODY_REGIONS:
            vol = np.ascontiguousarray(np.flip(vol, axis=2))
        host._region_cache[region] = vol
        host._region_tex_cache[region] = None
        host._region_aux_cache[region] = (None, None)
    host.load_region(region)


def render_tile(host, region, state):
    """Render one panel and return a TILE x TILE RGB image on black."""
    ensure_region(host, region)
    payload = dict(state)
    payload.setdefault("region", region)
    # Accept lesson-style aliases and map them to the keys host.render() reads
    # (orientation / slice_idx / label_anatomy). Without this a spec's `orient`
    # or `slice` is silently ignored and the engine falls back to its defaults.
    if "orient" in payload:
        payload.setdefault("orientation", payload.pop("orient"))
    if "slice" in payload:
        payload.setdefault("slice_idx", payload.pop("slice"))
    if "labelanat" in payload:
        payload.setdefault("label_anatomy", payload.pop("labelanat"))
    payload.setdefault("orientation", "axial")
    params = dict(payload.get("params", {}))
    params.setdefault("snr_level", 120)   # clean render so anatomy reads clearly
    payload["params"] = params
    res = host.render(payload)
    png = base64.b64decode(res["image"].split(",")[-1])
    im = Image.open(io.BytesIO(png)).convert("RGB")
    # square center-crop, then resize to the tile size
    s = min(im.size)
    im = im.crop(((im.width - s) // 2, (im.height - s) // 2,
                  (im.width + s) // 2, (im.height + s) // 2))
    tile = Image.new("RGB", (TILE, TILE), PANEL_BG)
    tile.paste(im.resize((TILE, TILE), Image.LANCZOS), (0, 0))
    return tile


def _centered(draw, cx, y, text, font, fill):
    w = draw.textlength(text, font=font)
    draw.text((cx - w / 2, y), text, font=font, fill=fill)


def compose(host, fig):
    """Build a multi-panel figure from its spec and return an RGB image."""
    panels = fig["panels"]
    n = len(panels)
    cell_w = TILE
    cell_h = HEAD_H + TILE + CAP_H
    W = PAD * 2 + n * cell_w + (n - 1) * GAP
    H = PAD * 2 + cell_h
    canvas = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(canvas)
    head_font = _font(15, bold=True)
    cap_font = _font(13)

    for i, p in enumerate(panels):
        x = PAD + i * (cell_w + GAP)
        cx = x + cell_w / 2
        _centered(draw, cx, PAD + 6, p["label"], head_font, ACCENT)
        tile = render_tile(host, fig.get("region", "Brain"), p["state"])
        canvas.paste(tile, (x, PAD + HEAD_H))
        _centered(draw, cx, PAD + HEAD_H + TILE + 6, p["caption"], cap_font, CAPTION)
        if i:                             # hairline between tiles
            lx = x - GAP // 2 - 1
            draw.line([(lx, PAD + HEAD_H), (lx, PAD + HEAD_H + TILE)], fill=LINE, width=1)
    return canvas


# --- figure specs -----------------------------------------------------------
# Proof-first: start with ONE figure (M2 contrast panel) end to end, then scale.
# Each panel is the SAME brain slice; only TR/TE change, so the contrast shift is
# the only visible variable — exactly the M2 teaching point.
_BRAIN_AX = {"region": "Brain", "orientation": "axial", "slice_idx": 90}


def _brain(tr, te, **params):
    st = dict(_BRAIN_AX)
    st["params"] = {"sequence": "Spin Echo", "TR": tr, "TE": te, **params}
    return st


def _brain_mx(mx):
    """Same T1 brain slice at one acquisition matrix — for the resolution/SNR trade."""
    return _brain(600, 12, matrix_size=mx)


# The demo tumor is painted into brain white matter (web_adapter._PATHOLOGY /
# rendering.paint_brain_pathology) and enhances only on post-gadolinium T1.
def _tumor_t1(gd):
    st = _brain(500, 12, contrast_enabled=gd, contrast_dose=5 if gd else 0)
    st["pathology"] = "tumor"
    return st


FIGURES = [
    {
        "slug": "m2-contrast-t1-pd-t2",
        "region": "Brain",
        "panels": [
            {"label": "T1-weighted", "caption": "short TR 500 / short TE 12 ms", "state": _brain(500, 12)},
            {"label": "PD-weighted", "caption": "long TR 4000 / short TE 12 ms", "state": _brain(4000, 12)},
            {"label": "T2-weighted", "caption": "long TR 4000 / long TE 100 ms", "state": _brain(4000, 100)},
        ],
    },
    {
        # M5 image quality: same slice, only the acquisition matrix changes, so the
        # resolution-up / SNR-down trade is the single visible variable.
        "slug": "m5-resolution-snr",
        "region": "Brain",
        "panels": [
            {"label": "Matrix 128", "caption": "coarse voxels, high SNR", "state": _brain_mx(128)},
            {"label": "Matrix 256", "caption": "standard resolution", "state": _brain_mx(256)},
            {"label": "Matrix 512", "caption": "fine detail, lower SNR", "state": _brain_mx(512)},
        ],
    },
    {
        # M4/M10: why we give gadolinium — an enhancing mass is near-invisible on
        # pre-contrast T1 and lights up on post-Gd T1 (Gd shortens T1 where the BBB
        # is broken).
        "slug": "m4-gd-enhancement",
        "region": "Brain",
        "panels": [
            {"label": "T1 pre-contrast", "caption": "mass isointense, easy to miss", "state": _tumor_t1(False)},
            {"label": "T1 post-gadolinium", "caption": "enhancing mass lights up", "state": _tumor_t1(True)},
        ],
    },
]


def main():
    os.makedirs(OUT, exist_ok=True)
    host = web_adapter._host()
    n = 0
    for fig in FIGURES:
        try:
            img = compose(host, fig)
        except Exception as e:            # never let one figure kill the batch
            print(f"  {fig['slug']}: skipped ({e})")
            continue
        img.save(os.path.join(OUT, fig["slug"] + ".jpg"), format="JPEG", quality=88, optimize=True)
        n += 1
        print(f"  {fig['slug']}.jpg  ({img.width}x{img.height})")
    print(f"rendered {n} course figures -> web/img/course/")


if __name__ == "__main__":
    main()
