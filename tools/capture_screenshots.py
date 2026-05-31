#!/usr/bin/env python3
"""Capture README screenshots from the running Gradio app.

Drives the live UI (default http://127.0.0.1:7860) with Playwright and saves
four PNGs into ``assets/``: the single-panel brain, the T1-vs-T2 Compare view,
the STIR lesson (with the "Fat is nulled." annotation), and the SE-vs-FSE lesson
(with the ~16x scan-time captions). This is a developer tool, not a test — it
lives in tools/ (outside tests/) and is never collected by pytest.

Usage:
    python app.py &                 # serve the app on :7860
    python tools/capture_screenshots.py

Requires: pip install playwright && python -m playwright install chromium
"""
import os
import sys
import time

from playwright.sync_api import sync_playwright

URL = os.environ.get("APP_URL", "http://127.0.0.1:7860")
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")

# Geometry padding (CSS px): above image to catch the "Panel A/B" header, to the
# sides, and below the scan-time caption to catch the italic annotation line —
# while stopping short of the parameter sliders underneath.
HEADER_PAD, SIDE_PAD, BELOW_CAPTION = 52, 18, 32


def panel_boxes(pg):
    """Bounding boxes of the rendered MRI panels — large <img>s, not icons."""
    return pg.evaluate(
        """() => [...document.querySelectorAll('img')]
                 .map(i => i.getBoundingClientRect())
                 .filter(r => r.width > 150 && r.height > 150)
                 .map(r => ({x:r.x, y:r.y, w:r.width, h:r.height}))
                 .sort((a,b) => a.x - b.x)"""
    )


def caption_bottoms(pg):
    """Bottom-y of each scan-time caption (the annotation sits just below)."""
    return pg.evaluate(
        """() => [...document.querySelectorAll('div')]
                 .filter(d => d.textContent.includes('Estimated scan time')
                              && d.children.length === 0)
                 .map(d => d.getBoundingClientRect().bottom)"""
    )


def wait_render(pg, n_images, text, timeout=45000):
    # Wait until all panels have a painted MRI image and the expected annotation
    # text is present. Note: under headless automation Gradio's SSE-driven
    # spinner overlay can stay stuck even though the image underneath is fully
    # rendered, so we do NOT gate on .generating clearing — strip_overlay()
    # removes the cosmetic overlay just before the screenshot instead.
    pg.wait_for_function(
        f"""() => [...document.querySelectorAll('img')]
                  .map(i => i.getBoundingClientRect())
                  .filter(r => r.width > 150 && r.height > 150).length >= {n_images}""",
        timeout=timeout,
    )
    pg.get_by_text(text, exact=False).first.wait_for(state="visible", timeout=timeout)
    time.sleep(1.5)  # let the image actually paint


def strip_overlay(pg):
    """Remove Gradio's (occasionally stuck) loading overlay so the rendered image
    shows. The underlying panel image is the correct render; only the cosmetic
    spinner/dimming is removed."""
    pg.evaluate(
        """() => {
            document.querySelectorAll('.generating, .translucent')
                .forEach(e => e.classList.remove('generating', 'translucent'));
            document.querySelectorAll('.wrap.default.full, .eta-bar, .progress-text')
                .forEach(e => e.style.display = 'none');
        }"""
    )
    time.sleep(0.4)


def shot(pg, name, n_images, captions=True):
    """Screenshot the n leftmost MRI panels. With ``captions``, the clip extends
    down to include the scan-time + annotation line beneath each image; without,
    it stops just below the images (used for the Compare shot, whose Panel-B
    caption is swallowed by Gradio's stuck loading wrap — see strip_overlay)."""
    strip_overlay(pg)
    pg.evaluate("window.scrollTo(0, 0)")
    time.sleep(0.2)
    boxes = panel_boxes(pg)[:n_images]
    x1 = min(b["x"] for b in boxes) - SIDE_PAD
    x2 = max(b["x"] + b["w"] for b in boxes) + SIDE_PAD
    y1 = min(b["y"] for b in boxes) - HEADER_PAD
    img_bottom = max(b["y"] + b["h"] for b in boxes)
    if captions:
        caps = [c for c in caption_bottoms(pg) if c >= img_bottom - 40]
        y2 = (max(caps) if caps else img_bottom) + BELOW_CAPTION
    else:
        y2 = img_bottom + 14
    clip = {"x": max(0, x1), "y": max(0, y1), "width": x2 - x1, "height": y2 - y1}
    path = os.path.join(OUT, name)
    pg.screenshot(path=path, clip=clip)
    print(f"saved {path}  ({int(clip['width'])}x{int(clip['height'])})")


def main():
    os.makedirs(OUT, exist_ok=True)
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1820, "height": 1200}, device_scale_factor=2)
        pg.goto(URL, wait_until="domcontentloaded")

        # 1) Single-panel brain (default Free Explore: Brain, T1-weighted SE).
        wait_render(pg, 1, "T1-weighted")
        shot(pg, "single_panel_brain.png", 1)

        # 2) Compare T1 vs T2 (same brain): enable Compare; left T1, right T2.
        # Captions off: Panel B's caption is lost to the stuck loading wrap, so
        # the two contrasts are labelled in the README text instead (symmetric).
        pg.get_by_label("Compare mode").click()
        wait_render(pg, 2, "T2-weighted")
        shot(pg, "compare_t1_t2.png", 2, captions=False)

        # 3) STIR lesson: Abdomen IR at the fat null -> "Fat is nulled." annotation.
        pg.get_by_role("button", name="Nulling fat with STIR").click()
        wait_render(pg, 1, "Fat is nulled.")
        shot(pg, "lesson_stir_fat_nulled.png", 1)

        # 4) SE vs FSE lesson: same T2 brain, ~16x scan-time gap in the captions.
        pg.get_by_role("button", name="SE vs FSE").click()
        wait_render(pg, 2, "T2-weighted")
        shot(pg, "lesson_se_vs_fse.png", 2)

        b.close()
    print("done.")


if __name__ == "__main__":
    sys.exit(main())
