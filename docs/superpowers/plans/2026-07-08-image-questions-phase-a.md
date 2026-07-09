# Image Questions Phase A (foundation + honesty fix) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the `credit` (curated-image) schema + attribution plumbing alongside the existing simulator-rendered image questions, and correct the current 17 so every image faithfully and distinctly represents its concept — de-duplicating the physics images and converting the questions the simulator cannot faithfully depict to text-only.

**Architecture:** A quiz `body` carries exactly one image source: `setup` (simulator render payload, rendered at build time by `scripts/prerender_course_quiz.py`) OR `credit` (a committed curated image with `{author, license, source_url, title}`, license restricted to CC0/PD/CC-BY). A content-guard test enforces the XOR + license allow-list + image-exists. `course.js addQImg` shows an attribution caption for curated images. Phase A adds NO external images — it builds the rails and fixes the existing set in-repo. Phase B sources curated images; Phase C expands the simulator set.

**Tech Stack:** Python (pytest guard; `scripts/prerender_course_quiz.py` uses numpy/matplotlib/Pillow + `src/` simulator to render), byte-stable JSON via `scripts/quiz_length_tools.py` (`load`/`dump`, indent=2, ensure_ascii=False, trailing newline), Supabase MCP for reseed, vanilla browser JS (course.js) + ESLint.

**Spec:** `docs/superpowers/specs/2026-07-08-image-questions-phase-a-design.md`

## Global Constraints

- Never add `Co-Authored-By: Claude` trailers to commits.
- Credibility/accuracy is the point: every retained/re-rendered image must faithfully AND distinctly show the concept its question tests; no two questions may share an image (by content hash); no image may misrepresent (e.g. a synthetic phantom labeled as real pathology).
- `credit.license` MUST be in the commercial-safe allow-list: `CC0-1.0`, `Public-Domain`, `CC-BY-4.0`, `CC-BY-3.0`, `CC-BY-2.0`. No `-NC` / `-ND` / "free for education".
- A quiz `body` has EXACTLY ONE of `setup` / `credit` (never both, never neither for an `img` item).
- `data/course_content.json` is the SOURCE; write it byte-stable via `scripts/quiz_length_tools.py` `dump` and reseed the changed rows to Supabase (`course_content`, course `mri-core`, project `idgyjmamxxyddjuaamit`).
- No em dashes / AI-tell punctuation in any user-facing copy (prompts, explanations, captions, credits page).
- Converting a question to text-only changes ONLY its `prompt` and removes `img`+`setup`; `options`, `answer`, and `explain` are left untouched (preserves the index-0 keying and the answer-length balance guard).
- Run `ruff check src/ tests/`, `pytest`, `npm run test:web`, `npm run lint` before merge.

---

### Task 1: Relax + extend the image guard to the setup-XOR-credit schema

**Files:**
- Modify: `tests/test_course_images.py`

**Interfaces:**
- Consumes: `data/course_content.json` (`items[]`, quiz bodies with `img` + `setup`|`credit`), `web/img/course-quiz/`.
- Produces: a reusable validator `validate_image_body(body) -> None` (raises `AssertionError` with a message on any violation) that Task 3 relies on staying green after the content edits.

- [ ] **Step 1: Write the failing unit tests + validator**

Replace the whole body of `tests/test_course_images.py` with:

```python
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
```

- [ ] **Step 2: Run the tests**

Run: `python3 -m pytest tests/test_course_images.py -v`
Expected: all pass. (Current data is all-`setup` items with files present; the four `validate_*` unit tests exercise the invariant directly.)

- [ ] **Step 3: Ruff**

Run: `~/Library/Python/3.9/bin/ruff check tests/test_course_images.py`
Expected: clean.

- [ ] **Step 4: Commit**

```bash
git add tests/test_course_images.py
git commit -m "test(course-images): guard setup-XOR-credit schema + commercial-safe license allow-list"
```

---

### Task 2: Attribution caption for curated images in course.js

**Files:**
- Modify: `web/course.js` (`addQImg`, currently ~lines 533-537)
- Modify: `web/course.html` (add a `.q-credit` CSS rule)

**Interfaces:**
- Consumes: a quiz `body` that may carry `credit: {author, license, source_url, title}`.
- Produces: nothing downstream. No `credit` items exist in Phase A data; the caption is guarded by `if (q.credit)`, so behavior is unchanged for every current sim-rendered image.

- [ ] **Step 1: Update `addQImg`**

In `web/course.js`, replace the current `addQImg`:

```js
  function addQImg(box, q) {
    if (q && q.img) {
      box.insertBefore(h("img", { class: "q-img", src: "img/course-quiz/" + q.img, alt: "Scan for this question" }), box.firstChild);
    }
  }
```

with:

```js
  function addQImg(box, q) {
    if (!q || !q.img) return;
    var img = h("img", { class: "q-img", src: "img/course-quiz/" + q.img, alt: "Scan for this question" });
    box.insertBefore(img, box.firstChild);
    if (q.credit) {
      var c = q.credit;
      var cap = h("p", { class: "q-credit" }, [
        document.createTextNode("Image: " + c.author + " · " + c.license + " · "),
        h("a", { class: "linkout", href: c.source_url, target: "_blank", rel: "noopener", text: "source" }),
      ]);
      box.insertBefore(cap, img.nextSibling);   // caption directly under the image
    }
  }
```

- [ ] **Step 2: Add the caption CSS**

In `web/course.html`'s `<style>` block (near the `.q-img` rule if present, else with the other quiz rules), add:

```css
    .q-credit { font-size: 11px; color: var(--muted, #8a94a7); margin: 4px 0 8px; }
```

- [ ] **Step 3: Lint + confirm no behavior change**

Run: `npm run lint` (expect clean) and `npm run test:web` (expect all suites still pass). Reason through: every current image question has `setup`, not `credit`, so the `if (q.credit)` branch never fires and the DOM is identical to before.

- [ ] **Step 4: Commit**

```bash
git add web/course.js web/course.html
git commit -m "feat(course-images): attribution caption under curated (credit) images"
```

---

### Task 3: Honesty fix of the existing 17 (re-render distinct physics, convert non-faithful to text) + reseed

**Files:**
- Modify: `data/course_content.json` (edit the 17 image-question bodies per the disposition table)
- Modify: `web/img/course-quiz/` (re-render kept images; delete the 6 now-unused files)
- Modify: `scripts/prerender_course_quiz.py` (one clarifying comment — it already skips no-setup items)
- Reseed: Supabase `course_content`

**Interfaces:**
- Consumes: `validate_image_body` (Task 1) must stay green after the edits.
- Produces: a corrected image set; each remaining image unique by content hash and faithful to its concept.

**Disposition — convert to TEXT-ONLY (remove `img` + `setup`, set `prompt` verbatim, keep `options`/`answer`/`explain`):**

| ord | topic | new prompt (verbatim) |
|---|---|---|
| 904 | pulse-sequences | `On a spin echo sequence acquired with TR 500 ms and TE 12 ms, which statement about this technique is correct compared to a susceptibility-weighted gradient echo scan?` |
| 910 | flow-artifacts | `A routine brain exam shows discrete repeating ghost bands spread across the phase-encoding direction. What is the most likely source of this artifact?` |
| 911 | flow-artifacts | `On a susceptibility-weighted sequence, what causes the pronounced signal loss (blooming) seen at sites of blood products?` |
| 914 | pathology | `A diffusion-weighted scan (b-value 1000) in a patient with acute onset neurologic symptoms shows a focal area of markedly high signal. What does this finding most likely represent?` |
| 915 | pathology | `A susceptibility-weighted scan shows a focal area of pronounced signal dropout (blooming). In the correct clinical context, what does this finding most likely represent?` |
| 916 | pathology | `On a post-contrast T1-weighted spin echo scan, a focal area of abnormal enhancement is seen in a mass lesion. What does contrast enhancement typically indicate?` |

**Disposition — KEEP + ensure DISTINCT/faithful sim render:**

| ord | concept | action |
|---|---|---|
| 900 | T1 weighting (SE 500/12 Brain) | keep setup; after 904/908/912 change it uniquely holds the plain T1-SE image |
| 901 | T2 weighting | keep (unique/correct) |
| 902 | PD weighting | keep |
| 903 | FLAIR | keep |
| 905 | SWI sequence | keep (unique) |
| 906 | DWI sequence / b-value | keep (normal-brain DWI is fine for a b-value concept) |
| 907 | motion artifact | keep; after 910 -> text it uniquely holds the motion image; add the same distinct `slice` as 908 (see below) |
| 908 | clean vs motion quality | re-setup as the CLEAN MATCH of 907 (same region + slice, motion disabled) so it pairs with 907 and does not collide with 900; use a `slice` different from the weighting series so 908 != 900 by content hash |
| 909 | TOF angiography | keep (unique) |
| 912 | fat-sat OFF | re-setup on `region: "Knee"`, params identical to 913 except no fat-sat; rewrite prompt to reference the knee image (accurate to its existing `options`/`answer`) |
| 913 | fat-sat ON | re-setup on `region: "Knee"`, identical params to 912 plus the fat-sat flag; rewrite prompt to reference the knee image |

- [ ] **Step 1: Confirm simulator param names before editing**

Read `src/web_adapter.py` (`render`/`_host`) and `src/simulator.py` to confirm the accepted `params` keys for a slice index and the fat-sat flag (the existing 913 already uses `fatsat_enabled: true`; find the slice-selection key). Do not guess — use the real key names in Step 2.

- [ ] **Step 2: Apply all `course_content.json` edits byte-stable (one scratch script)**

Write `edit_phase_a.py` at repo root (run once, then delete). It must: for each convert `ord`, drop `img`+`setup` and set the verbatim `prompt`; for 907/908 set the matched slice + (908) drop motion; for 912/913 set `region:"Knee"` + the fat-sat pair + new prompts. Use the byte-stable dumper:

```python
import sys; sys.path.insert(0, "scripts")
import quiz_length_tools as q
doc = q.load()
CONVERT = {
    904: "On a spin echo sequence acquired with TR 500 ms and TE 12 ms, which statement about this technique is correct compared to a susceptibility-weighted gradient echo scan?",
    910: "A routine brain exam shows discrete repeating ghost bands spread across the phase-encoding direction. What is the most likely source of this artifact?",
    911: "On a susceptibility-weighted sequence, what causes the pronounced signal loss (blooming) seen at sites of blood products?",
    914: "A diffusion-weighted scan (b-value 1000) in a patient with acute onset neurologic symptoms shows a focal area of markedly high signal. What does this finding most likely represent?",
    915: "A susceptibility-weighted scan shows a focal area of pronounced signal dropout (blooming). In the correct clinical context, what does this finding most likely represent?",
    916: "On a post-contrast T1-weighted spin echo scan, a focal area of abnormal enhancement is seen in a mass lesion. What does contrast enhancement typically indicate?",
}
SLICE_KEY = "slice"          # <-- replace with the real key confirmed in Step 1
PAIR_SLICE = 100             # a slice distinct from the weighting series' default
for it in doc["items"]:
    o = it.get("ord"); b = it.get("body", {})
    if o in CONVERT:
        b.pop("img", None); b.pop("setup", None); b["prompt"] = CONVERT[o]
    elif o == 907:
        b["setup"]["params"][SLICE_KEY] = PAIR_SLICE
    elif o == 908:
        p = b["setup"]["params"]
        for k in ("motion_enabled", "motion_type", "motion_amplitude"): p.pop(k, None)
        p.update({"sequence": "Spin Echo", "TR": 500, "TE": 12, SLICE_KEY: PAIR_SLICE})
    elif o == 912:
        b["setup"]["region"] = "Knee"
        b["setup"]["params"] = {"sequence": "Spin Echo", "TR": 500, "TE": 12}
        b["prompt"] = "On a T1-weighted spin echo knee image acquired without any fat-suppression pulse, how does subcutaneous and marrow fat appear, and what changes when fat saturation is added?"
    elif o == 913:
        b["setup"]["region"] = "Knee"
        b["setup"]["params"] = {"sequence": "Spin Echo", "TR": 500, "TE": 12, "fatsat_enabled": True}
        b["prompt"] = "On a T1-weighted spin echo knee image acquired with a fat-saturation pulse enabled, what is the expected appearance of the fatty tissue?"
q.dump(doc)
```
Run: `python3 edit_phase_a.py && rm edit_phase_a.py`
(If a rewritten 912/913 prompt does not match its existing `options`/`answer`, adjust the prompt wording to stay accurate — never change `answer`.)

- [ ] **Step 3: Delete the six unused images and re-render**

```bash
cd /Users/erolakkoc/mrisim
git rm web/img/course-quiz/cq-sequence-se-01.jpg web/img/course-quiz/cq-flow-ghosting-01.jpg \
  web/img/course-quiz/cq-flow-susceptibility-01.jpg web/img/course-quiz/cq-pathology-stroke-dwi-01.jpg \
  web/img/course-quiz/cq-pathology-hemorrhage-swi-01.jpg web/img/course-quiz/cq-pathology-tumor-contrast-01.jpg
python3 scripts/prerender_course_quiz.py
```
Expected: prints `pre-rendered 11 course-quiz images`. The 6 converted questions have no `setup`, so they are skipped (the script already `continue`s when `setup` is absent).

- [ ] **Step 4: Verify distinctness + accuracy (this visual check IS the gate)**

```bash
cd web/img/course-quiz && md5 -r *.jpg | awk '{print $1}' | sort | uniq -d
```
Expected: NO output (every remaining image unique by content hash).
Then Read each re-rendered .jpg and confirm:
- fat-sat OFF (912) shows bright fat; fat-sat ON (913) shows that same fat now dark — the ONLY visible difference between the pair.
- clean (908) is the motion-free counterpart of 907 (same anatomy) and differs from the T1 image (900).
- every other kept image still faithfully shows its concept.
If any image fails, adjust its `setup` and re-render until it passes. Do not proceed on a failing image.

- [ ] **Step 5: Run the guards**

```bash
python3 -m pytest tests/test_course_images.py tests/test_quiz_length.py tests/test_course_depth.py -v
~/Library/Python/3.9/bin/ruff check src/ tests/
```
Expected: all pass.

- [ ] **Step 6: Reseed Supabase**

For each changed quiz row (ords 900-916), update `body` in `course_content` (project `idgyjmamxxyddjuaamit`, course `mri-core`) to match `data/course_content.json` via `execute_sql` `update course_content set body = '<json>'::jsonb where course='mri-core' and ord=<n>` (one per changed row). Verify: `select ord, body->>'img' as img from course_content where course='mri-core' and ord between 900 and 916 order by ord` shows null `img` for the 6 converted rows and the filename for the 11 kept rows.

- [ ] **Step 7: Clarifying comment in the prerender script**

In `scripts/prerender_course_quiz.py`, at the `if not setup or not img: continue` line, append the comment: `# curated (credit) images have no setup -> skipped; they ship as committed files`.

- [ ] **Step 8: Commit**

```bash
git add data/course_content.json web/img/course-quiz scripts/prerender_course_quiz.py
git commit -m "content(course-images): de-duplicate physics renders; convert non-faithful pathology/artifact questions to text (honesty fix)"
```

---

### Task 4: "Course question images" subsection on credits.html

**Files:**
- Modify: `web/credits.html`

**Interfaces:**
- Consumes: nothing. Produces: the attribution rail Phase B fills in.

- [ ] **Step 1: Add the subsection**

In `web/credits.html`, after the "Anatomical datasets" section and before "Software", add (mirroring the existing `<h2>` + `<p>` markup):

```html
      <h2>Course question images</h2>
      <p>Some course questions use clinical images to test image recognition. Simulator-rendered
        images are generated by MRISim itself. Any real clinical image used is openly licensed for
        commercial use (CC0, public domain, or CC BY) and is credited beneath the image where it
        appears in the course, with a link to its source. No non-commercial or education-only
        licensed images are used.</p>
```

- [ ] **Step 2: Confirm render**

Run: `npm run lint`. The new section sits between "Anatomical datasets" and "Software", styled by the existing rules.

- [ ] **Step 3: Commit**

```bash
git add web/credits.html
git commit -m "docs(credits): add Course question images licensing subsection"
```

---

## Notes for the executor

- **Task 3 is visual + iterative** (render -> Read the .jpg -> adjust setup -> re-render). Execute it inline with image review; do not delegate the render-judgment to a subagent that cannot see the images. Tasks 1, 2, 4 are mechanical and delegate cleanly.
- The render (`prerender_course_quiz.py`) needs numpy/matplotlib/Pillow and the body-region atlases already in `data/` (the Knee atlas is referenced by the script's `_BODY_SRC`). Confirm `params` key names against `src/web_adapter.py` / `src/simulator.py` before editing (Task 3 Step 1).
- Final guard set before PR: `~/Library/Python/3.9/bin/ruff check src/ tests/`, `python3 -m pytest`, `npm run test:web`, `npm run lint`.
- PR body ends with the standard `🤖 Generated with [Claude Code](https://claude.com/claude-code)` line (PR body only, never a commit trailer).
