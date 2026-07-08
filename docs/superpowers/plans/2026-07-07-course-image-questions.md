# Premium Image-Based Questions (Phase 3.1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add ~16 engine-rendered image questions to the premium bank, shown above the prompt in the course inline quiz, mastery check, and practice exam.

**Architecture:** An image question is a premium quiz item with two optional `body` fields: a render `setup` (same shape as the free read-the-scan quiz) and an `img` filename. `scripts/prerender_course_quiz.py` renders each `setup` via the engine to a committed JPEG under `web/img/course-quiz/` (mirroring `prerender_lessons.py` — no engine in the static course page). `web/course.js` shows the image when `body.img` is set. Backward-compatible: text-only items are unaffected.

**Tech Stack:** JSON data, Python (prerender via `web_adapter` + Pillow), vanilla ES5 browser JS + CSS, pytest (data validation).

## Global Constraints

- **`data/course_content.json` is the SOURCE**, re-seeded to Supabase by the owner (do NOT run the seed in any task).
- **Edit the JSON by load → mutate → dump** with `json.dumps(d, indent=2, ensure_ascii=False) + "\n"` (byte-identical round-trip; minimal diffs). Never hand-edit the raw JSON braces.
- **`web/course.js` is ES5-style**: `var`, function expressions, the `h(tag, attrs, kids)` builder; `text:` for plain strings, `html:` only for trusted premium HTML. Match the file.
- **No em dashes (—) or en dashes (–) / no AI-tell punctuation** in any authored question text.
- **Accuracy is the primary bar** for content: audience = ARRT candidates + new MRI techs; and the rendered image must genuinely support the keyed answer.
- **Do NOT run `scripts/prerender_course_quiz.py` inside a content-authoring task** — the controller runs it and visually verifies the images (Task 4).
- Image files live under `web/img/course-quiz/` and are public (only the Q&A + explanation is the gated premium content, same as the already-public lesson images).
- No `Co-Authored-By: Claude` trailer. `course.js`/`course.html` are network-first SHELL files (no cache bump).

## File structure

- `web/course.js` — one `addQImg(box, q)` helper + 5 call sites (render the scan above the prompt).
- `web/course.html` — `.q-img` CSS.
- `scripts/prerender_course_quiz.py` — new; renders `setup` → `web/img/course-quiz/<img>.jpg`.
- `data/course_content.json` — ~16 new premium quiz items with `setup` + `img`.
- `web/img/course-quiz/*.jpg` — generated, committed.
- `tests/test_course_images.py` — new; validates `img`↔`setup` + file existence.

---

## Task 1: Render the scan image on questions

**Files:**
- Modify: `web/course.js` (add `addQImg` helper + 5 call sites)
- Modify: `web/course.html` (CSS)

**Interfaces:**
- Produces: `addQImg(box, q)` — if `q.img` is set, inserts `<img class="q-img" src="img/course-quiz/<q.img>">` as the first child of `box`. No-op otherwise.

- [ ] **Step 1: Add the helper**

In `web/course.js`, immediately before `function quizItem(` add:

```js
  // Premium image questions carry an `img` (a pre-rendered scan in web/img/course-quiz/).
  // Show it above the prompt; text-only questions have no img and are unaffected.
  function addQImg(box, q) {
    if (q && q.img) {
      box.insertBefore(h("img", { class: "q-img", src: "img/course-quiz/" + q.img, alt: "Scan for this question" }), box.firstChild);
    }
  }
```

- [ ] **Step 2: Call it in the inline quiz (`quizItem`)**

In `web/course.js`, in `quizItem`, find:

```js
    var box = h("div", { class: "q" }, [h("p", { class: "prompt", text: q.prompt })]);
```

and add the call right after it:

```js
    var box = h("div", { class: "q" }, [h("p", { class: "prompt", text: q.prompt })]);
    addQImg(box, q);
```

- [ ] **Step 3: Call it in the mastery run (`renderMasteryRun`)**

In `web/course.js`, in `renderMasteryRun`, find:

```js
      var box = h("div", { class: "q mchk-q" }, [
        h("p", { class: "mq-num", text: "Question " + (qi + 1) + " of " + questions.length }),
        h("p", { class: "prompt", text: item.q.prompt }),
      ]);
```

and add the call right after it:

```js
      var box = h("div", { class: "q mchk-q" }, [
        h("p", { class: "mq-num", text: "Question " + (qi + 1) + " of " + questions.length }),
        h("p", { class: "prompt", text: item.q.prompt }),
      ]);
      addQImg(box, item.q);
```

- [ ] **Step 4: Call it in the mastery review (`renderMasteryResult`)**

In `web/course.js`, in `renderMasteryResult`, find:

```js
        var box = h("div", { class: "q reviewed miss" }, [h("p", { class: "prompt", text: item.q.prompt })]);
```

and add the call right after it:

```js
        var box = h("div", { class: "q reviewed miss" }, [h("p", { class: "prompt", text: item.q.prompt })]);
        addQImg(box, item.q);
```

- [ ] **Step 5: Call it in the practice exam (`renderExam`)**

In `web/course.js`, in `renderExam`, find:

```js
      var box = h("div", { class: "exam-q" }, [
        h("p", { class: "eq-num", text: "Question " + (qi + 1) + " of " + EXAM.questions.length }),
        h("p", { class: "prompt", text: item.q.prompt }),
      ]);
```

and add the call right after it:

```js
      var box = h("div", { class: "exam-q" }, [
        h("p", { class: "eq-num", text: "Question " + (qi + 1) + " of " + EXAM.questions.length }),
        h("p", { class: "prompt", text: item.q.prompt }),
      ]);
      addQImg(box, item.q);
```

- [ ] **Step 6: Call it in the exam review (`renderExamReview`)**

In `web/course.js`, in `renderExamReview`, find:

```js
      var box = h("div", { class: "exam-q reviewed" + (right ? "" : " miss") }, [num, h("p", { class: "prompt", text: item.q.prompt })]);
```

and add the call right after it:

```js
      var box = h("div", { class: "exam-q reviewed" + (right ? "" : " miss") }, [num, h("p", { class: "prompt", text: item.q.prompt })]);
      addQImg(box, item.q);
```

- [ ] **Step 7: Add the CSS**

In `web/course.html`, after the `.q .fb { ... }` rule, add:

```css
    .q-img { display: block; width: 320px; max-width: 100%; margin: 0 0 12px; border: 1px solid var(--line); border-radius: 2px; background: #000; }
```

- [ ] **Step 8: Verify lint**

Run: `npm run lint`
Expected: exit 0. Backward-compatible (no image renders when `img` is absent), safe to land before content exists.

- [ ] **Step 9: Commit**

```bash
git add web/course.js web/course.html
git commit -m "feat(course): show pre-rendered scan image on premium image questions"
```

---

## Task 2: Pre-render script

**Files:**
- Create: `scripts/prerender_course_quiz.py`

**Interfaces:**
- Produces: `web/img/course-quiz/<img>.jpg` for every `kind:"quiz"` item whose `body` has both `setup` and `img`.

- [ ] **Step 1: Create the script**

Create `scripts/prerender_course_quiz.py`:

```python
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

import numpy as np
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
            continue
        try:
            ensure_region(host, setup.get("region", "Brain"))
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
```

- [ ] **Step 2: Verify it runs (no image content yet)**

Run: `.venv/bin/python scripts/prerender_course_quiz.py`
Expected: prints `pre-rendered 0 course-quiz images -> web/img/course-quiz/` (no items carry `setup`+`img` yet, so it renders nothing and errors on nothing). Confirms the script imports the engine and runs cleanly.

- [ ] **Step 3: Commit**

```bash
git add scripts/prerender_course_quiz.py
git commit -m "feat(course): prerender script for premium image-question scans"
```

---

## Task 3: Content — ~16 image questions

**Files:**
- Modify: `data/course_content.json` (append ~16 `kind:"quiz"` items)

**Interfaces:**
- Consumes: the `addQImg` render (Task 1) and prerender (Task 2) — items must use `body.img` (a `cq-*.jpg` filename) and `body.setup` (a render payload).
- Produces: ~16 new premium quiz items with `prompt`/`options`/`answer`/`explain` + `setup` + `img`.

**Valid `setup` catalog (proven to render; from `web/quiz.json`):**
- T1 SE: `{"sequence":"Spin Echo","TR":500,"TE":12}`
- T2 SE: `{"sequence":"Spin Echo","TR":3500,"TE":110}`
- PD SE: `{"sequence":"Spin Echo","TR":3500,"TE":15}`
- FLAIR: `{"sequence":"Inversion Recovery","TR":9000,"TE":100,"TI":2548}`
- TOF MRA: `{"sequence":"MR Angiography","angio_type":"TOF"}`
- DWI (with `"pathology":"stroke"`): `{"sequence":"Diffusion (DWI)","diff_display":"DWI","b_value":1000}`
- SWI (with `"pathology":"hemorrhage"`): `{"sequence":"Susceptibility (SWI)","TR":28,"TE":20,"flip_angle":15}`
- Post-contrast (with `"pathology":"tumor"`): `{"sequence":"Spin Echo","TR":500,"TE":12,"contrast_enabled":true,"contrast_dose":8}`
- Motion artifact: `{"sequence":"Spin Echo","TR":500,"TE":12,"motion_enabled":true,"motion_type":"periodic","motion_amplitude":6}`
- Fat suppression: add `"fatsat_enabled":true` to any SE setup.

Each `setup` is `{"region":"Brain","orientation":"axial","slice_idx":90,"params":{…},"pathology":"…"?}`. Use `slice_idx` 90 for brain axial (as the free quiz does).

**Exemplar item (match this bar):**

```json
{
  "topic": "contrast-weighting", "kind": "quiz", "ord": 900,
  "body": {
    "prompt": "This axial brain image was acquired with TR 500 ms and TE 12 ms. What weighting is shown?",
    "options": ["T1-weighted", "T2-weighted", "Proton density", "FLAIR"],
    "answer": 0,
    "explain": "Short TR with short TE gives T1 weighting: CSF is dark and fat and white matter are relatively bright. A long TR with a long TE would be T2 (bright CSF), a long TR with a short TE would be proton density, and FLAIR is an inversion-recovery sequence that specifically nulls CSF.",
    "setup": {"region":"Brain","orientation":"axial","slice_idx":90,"params":{"sequence":"Spin Echo","TR":500,"TE":12}},
    "img": "cq-weighting-t1-01.jpg"
  }
}
```

- [ ] **Step 1: Author ~16 image questions**

Write ~16 items across image-heavy topics, distributing `topic` across existing topic keys so they join the right module pools: `contrast-weighting` (T1/T2/PD/FLAIR ID), `pulse-sequences` (SE vs GRE/SWI, DWI/ADC), `image-quality` (motion vs clean, SNR), `flow-artifacts` (TOF, motion ghosting, susceptibility), `fat-suppression` (fatsat on vs off), `pathology` (stroke on DWI, hemorrhage on SWI, enhancing tumor). Each item: `{topic, kind:"quiz", ord, body:{prompt, options, answer, explain, setup, img}}`. Use `ord` 900..915 (append range, avoids collision with existing ords). `img` names are kebab-case, `cq-` prefixed, unique, `.jpg` (e.g. `cq-artifact-motion-01.jpg`). The chosen `setup` must make the keyed answer visibly correct. No em dashes.

- [ ] **Step 2: Append the items via a load → mutate → dump script**

```python
python3 - <<'PY'
import json
P = "data/course_content.json"
d = json.load(open(P))
items = [
  # ... your ~16 authored items here, each a full {topic, kind, ord, body{...}} dict ...
]
assert len(items) >= 15, len(items)
for it in items:
    assert it["kind"] == "quiz" and it["body"].get("setup") and it["body"].get("img")
d["items"].extend(items)
open(P, "w").write(json.dumps(d, indent=2, ensure_ascii=False) + "\n")
print("appended", len(items), "image questions; total items", len(d["items"]))
PY
```

- [ ] **Step 3: Verify (schema, dash-free, unique img)**

```python
python3 - <<'PY'
import json, re
d = json.load(open("data/course_content.json"))
DASH = re.compile(r"[—–]")
imgs = [it["body"]["img"] for it in d["items"] if it.get("kind")=="quiz" and it["body"].get("img")]
assert len(imgs) == len(set(imgs)), "duplicate img filenames"
n = 0
for it in d["items"]:
    if it.get("kind") != "quiz":
        continue
    b = it["body"]
    if not b.get("img"):
        continue
    n += 1
    assert b.get("setup") and b["setup"].get("region") and b["setup"].get("params"), b["img"]
    assert isinstance(b["options"], list) and 2 <= len(b["options"]) <= 6, b["img"]
    assert isinstance(b["answer"], int) and 0 <= b["answer"] < len(b["options"]), b["img"]
    blob = b["prompt"] + " " + " ".join(b["options"]) + " " + b["explain"]
    assert not DASH.search(blob), ("dash in", b["img"])
print("image questions:", n, "(all schema-valid, dash-free, unique imgs)")
PY
```

Expected: `image questions: 16` (or your count), all valid.

- [ ] **Step 4: Commit**

```bash
git add data/course_content.json
git commit -m "content(course): ~16 premium image-based questions (setup + img)"
```

---

## Task 4: Generate + visually verify the images (controller-executed)

This task is executed by the controller, not dispatched to an implementer subagent, because it requires visual judgment (confirming each rendered scan matches its keyed answer).

**Files:**
- Create (generated): `web/img/course-quiz/*.jpg`

- [ ] **Step 1: Render the images**

Run: `.venv/bin/python scripts/prerender_course_quiz.py`
Expected: `pre-rendered 16 course-quiz images -> web/img/course-quiz/` (matching the Task 3 count), no `render skipped` lines.

- [ ] **Step 2: Visually verify each image against its keyed answer**

Open each `web/img/course-quiz/*.jpg` and confirm the scan genuinely supports its question's `answer` (e.g. a "which weighting?" item keyed T1 shows dark CSF; a motion-artifact item shows visible ghosting; a DWI stroke item shows a bright lesion). For any mismatch, fix the item's `setup` (or the `answer`) in `data/course_content.json`, re-run the prerender, and re-check. Do not proceed until every image matches.

- [ ] **Step 3: Commit the images (and any content fixes)**

```bash
git add web/img/course-quiz data/course_content.json
git commit -m "content(course): pre-rendered scans for image questions (visually verified)"
```

---

## Task 5: Data validation test

**Files:**
- Create: `tests/test_course_images.py`

**Interfaces:**
- Consumes: `data/course_content.json` (image items) + `web/img/course-quiz/` (generated files from Task 4).

- [ ] **Step 1: Write the test**

Create `tests/test_course_images.py`:

```python
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
```

- [ ] **Step 2: Run the test**

Run: `.venv/bin/python -m pytest tests/test_course_images.py -q`
Expected: PASS (2 passed). A failure means an image question is missing its `setup` or its rendered file — fix the content or re-run the prerender, not the test.

- [ ] **Step 3: Commit**

```bash
git add tests/test_course_images.py
git commit -m "test(course): validate image questions have setup + committed file"
```

---

## Self-Review

**Spec coverage:**
- `setup` + `img` body fields → Task 3 (content) + data model in the exemplar.
- Render above the prompt in inline quiz + mastery + practice exam → Task 1 (5 call sites via `addQImg`).
- Prerender script mirroring `prerender_lessons.py` → Task 2.
- ~16 questions on image-heavy topics, accuracy + image-matches-answer → Task 3 + Task 4 visual verification.
- Owner-gated seed (not run here) → Global Constraints.
- Public image files → Global Constraints.
- Validation (img↔setup + file exists) → Task 5.

**Placeholder scan:** The `# ...` in Task 3 Step 2's `items` list is the generative deliverable the content agent authors (16 accurate questions cannot be pre-written in the plan); the schema, exemplar, valid setup catalog, exact append/verify scripts, `ord` range, and `img` naming are all concrete. Tasks 1, 2, 5 carry complete code.

**Type consistency:** `body.img` (string) and `body.setup` (dict with `region`/`orientation`/`params`) are identical across the render (`addQImg` reads `q.img`), the prerender (`body.get("setup")`/`body.get("img")`), the content append, and the test. Image path `img/course-quiz/<img>` (browser) matches `web/img/course-quiz/<img>` (prerender OUT + test IMG_DIR). The 5 render call sites all pass the item's question object (`q` in quizItem, `item.q` in the mastery/exam renderers).
