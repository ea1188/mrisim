# Image Questions Phase B (owner-supplied) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the rail for owner-supplied course images — an `Owner-Original` license that needs no attribution and shows no caption — plus a committed image requirements list and four fully-drafted new questions, so each image the owner later supplies drops into a ready slot.

**Architecture:** Extend the Phase A `credit` schema with an `Owner-Original` license value (guard accepts it, `source_url` optional for it, `addQImg` suppresses the caption for it). No live images ship in this PR; the deliverable is the rail + the list. Each supplied image is a later small wire-in (place file, set `credit`+`img`, reseed).

**Tech Stack:** Python (pytest guard), vanilla browser JS (`course.js`) + ESLint, Markdown manifest. `data/course_content.json` is NOT edited in this PR; the four new questions are held in the manifest until their images arrive.

**Spec:** `docs/superpowers/specs/2026-07-08-course-images-phase-b-design.md`

## Global Constraints

- Never add `Co-Authored-By: Claude` trailers to commits.
- `Owner-Original` images: no `source_url` required, `author` defaults to the course owner, and NO attribution caption is rendered. External licenses (`CC0-1.0`, `Public-Domain`, `CC-BY-*`) still require `author`+`source_url`+`title` and still show the Phase A caption.
- The `setup` XOR `credit` invariant and image-file-exists guard from Phase A remain unchanged.
- No em dashes / AI-tell punctuation in user-facing copy (drafted questions, credits line).
- Drafted questions keep the quiz body shape (`prompt`, 4 `options`, `answer` index 0 keyed, `explain`) with option lengths balanced so the answer-length guard would pass once the question is added with an image.
- No live curated image ships in this PR (there are none yet); do not add image rows to `course_content.json` or reseed Supabase in this phase.
- Run `ruff check src/ tests/`, `pytest` (python3.11 for the full suite), `npm run test:web`, `npm run lint` before merge.

---

### Task 1: `Owner-Original` support in the image guard

**Files:**
- Modify: `tests/test_course_images.py`

**Interfaces:**
- Consumes: `data/course_content.json`, `web/img/course-quiz/`.
- Produces: `ALLOWED_LICENSES` includes `Owner-Original`; `validate_image_body` treats it as owner-owned (no `source_url` required).

- [ ] **Step 1: Update the validator + allow-list and add unit cases**

In `tests/test_course_images.py`, change `ALLOWED_LICENSES` to add `Owner-Original`:

```python
ALLOWED_LICENSES = {"CC0-1.0", "Public-Domain", "CC-BY-4.0", "CC-BY-3.0", "CC-BY-2.0", "Owner-Original"}
```

Replace the `else:` branch of `validate_image_body` (the `credit` branch) with:

```python
    else:
        c = body["credit"]
        assert c.get("title"), f"{img}: credit needs a title"
        assert c.get("license") in ALLOWED_LICENSES, f"{img}: license {c.get('license')!r} not commercial-safe"
        if c.get("license") != "Owner-Original":
            assert c.get("author") and c.get("source_url"), f"{img}: external-licensed credit needs author + source_url"
```

Add these unit tests (after `test_validator_accepts_valid_setup_and_credit`):

```python
def test_validator_accepts_owner_original_without_source():
    validate_image_body({"img": "o.jpg", "credit": {"author": "MRISim", "license": "Owner-Original", "title": "our own scan"}})


def test_validator_owner_original_still_needs_title():
    with pytest.raises(AssertionError):
        validate_image_body({"img": "o.jpg", "credit": {"author": "MRISim", "license": "Owner-Original"}})


def test_validator_external_license_still_needs_source():
    with pytest.raises(AssertionError):
        validate_image_body({"img": "e.jpg", "credit": {"author": "a", "license": "CC-BY-4.0", "title": "t"}})
```

- [ ] **Step 2: Run the tests**

Run: `python3 -m pytest tests/test_course_images.py -v`
Expected: all pass (the real data still validates — it has no `credit` items yet; the new unit cases exercise the `Owner-Original` relaxation and the still-strict external path).

- [ ] **Step 3: Ruff**

Run: `~/Library/Python/3.9/bin/ruff check tests/test_course_images.py`
Expected: clean.

- [ ] **Step 4: Commit**

```bash
git add tests/test_course_images.py
git commit -m "test(course-images): accept Owner-Original license (owner-owned, no source required)"
```

---

### Task 2: Suppress the attribution caption for owner-owned images

**Files:**
- Modify: `web/course.js` (`addQImg`)

**Interfaces:**
- Consumes: a quiz `body.credit.license`.
- Produces: no caption when `license === "Owner-Original"`; the Phase A caption for any external license.

- [ ] **Step 1: Gate the caption on an external license**

In `web/course.js` `addQImg`, change the caption condition from `if (q.credit) {` to exclude owner-owned images. The function becomes:

```js
  function addQImg(box, q) {
    if (!q || !q.img) return;
    var img = h("img", { class: "q-img", src: "img/course-quiz/" + q.img, alt: "Scan for this question" });
    box.insertBefore(img, box.firstChild);
    if (q.credit && q.credit.license !== "Owner-Original") {
      var c = q.credit;
      var cap = h("p", { class: "q-credit" }, [
        document.createTextNode("Image: " + c.author + " · " + c.license + " · "),
        h("a", { class: "linkout", href: c.source_url, target: "_blank", rel: "noopener", text: "source" }),
      ]);
      box.insertBefore(cap, img.nextSibling);   // caption directly under the image
    }
  }
```

- [ ] **Step 2: Lint + web tests**

Run: `npm run lint` (expect clean) and `npm run test:web` (expect all suites still pass). Reason through: no `credit` items exist yet, so rendering is unchanged today; the new clause only changes behavior for a future `Owner-Original` image (no caption) versus an external one (Phase A caption).

- [ ] **Step 3: Commit**

```bash
git add web/course.js
git commit -m "feat(course-images): no attribution caption for Owner-Original (owner-owned) images"
```

---

### Task 3: Image requirements manifest + credits.html note

**Files:**
- Create: `docs/course-quiz-image-wishlist.md`
- Modify: `web/credits.html`

**Interfaces:**
- Consumes: nothing. Produces: the owner-facing shopping list + the four drafted new-question bodies, ready to wire in when images arrive.

- [ ] **Step 1: Write the manifest**

Create `docs/course-quiz-image-wishlist.md` with the wire-in steps at the top, then the 10-slot table from the spec (concept, image type, must-show, target filename, wiring), then the four NEW-question drafts as ready-to-paste JSON quiz bodies. The four drafts (verbatim):

```json
// #4 Multiple sclerosis (topic: pathology) — file cq-ms-flair-01.jpg
{
  "prompt": "This axial FLAIR image of the brain shows multiple ovoid white-matter lesions arranged perpendicular to the ventricles. In the right clinical setting, what do these most likely represent?",
  "options": [
    "Demyelinating plaques of multiple sclerosis, which are typically periventricular and bright on a FLAIR sequence",
    "Normal enlarged perivascular spaces, which always follow cerebrospinal fluid signal and suppress on every sequence",
    "Acute cortical infarcts that are confined strictly to the gray matter of the cortex",
    "Calcifications, which characteristically bloom and darken on a standard FLAIR sequence"
  ],
  "answer": 0,
  "explain": "Multiple sclerosis plaques are foci of demyelination that appear as bright ovoid white-matter lesions on FLAIR, classically periventricular and oriented perpendicular to the ventricles (Dawson's fingers). FLAIR suppresses cerebrospinal fluid so periventricular lesions stand out. Perivascular spaces follow fluid and suppress on FLAIR, infarcts are not confined to white matter, and calcification is better shown on susceptibility imaging."
}
```

```json
// #8 Chemical shift artifact (topic: image-quality) — file cq-chemshift-01.jpg
{
  "prompt": "This image shows a dark and a bright band at the border between a kidney and the surrounding fat, misregistered along the frequency-encoding direction. What artifact does this represent?",
  "options": [
    "Chemical shift artifact, from the small frequency difference between fat and water protons shifting fat signal along the readout axis",
    "Aliasing artifact, caused by a field of view smaller than the imaged anatomy so tissue wraps onto the opposite side of the image",
    "Zipper artifact, produced by stray radiofrequency energy leaking into the scan room during acquisition",
    "Patient motion, which spreads discrete ghost copies along the phase-encoding direction"
  ],
  "answer": 0,
  "explain": "Fat and water protons precess at slightly different frequencies, so the scanner mismaps fat signal along the frequency-encoding (readout) direction, producing a dark and bright band at fat-water interfaces such as the kidney border. It worsens at higher field strength and lower readout bandwidth. Aliasing, zipper, and motion artifacts have distinct causes and appearances."
}
```

```json
// #9 Gibbs / truncation artifact (topic: image-quality) — file cq-gibbs-01.jpg
{
  "prompt": "This sagittal T2 image of the spine shows several thin parallel lines running alongside the high-contrast border of the spinal cord, mimicking a syrinx. What artifact is this?",
  "options": [
    "Gibbs (truncation) artifact, from finite sampling of high spatial frequencies at a sharp signal boundary",
    "A true syrinx, which is a fluid-filled cavity within the cord that must always be surgically drained without delay",
    "Flow artifact from pulsating cerebrospinal fluid moving through the spinal canal during the acquisition",
    "Magnetic susceptibility from spinal hardware placed far outside the imaged field of view"
  ],
  "answer": 0,
  "explain": "Gibbs, or truncation, artifact arises because k-space is sampled over a finite extent, so sharp high-contrast borders such as the cord and cerebrospinal fluid interface are reconstructed with parallel ripple lines. These can mimic a cord syrinx but follow the border and change with matrix size. Increasing the acquisition matrix reduces it."
}
```

```json
// #10 Aliasing / wrap-around (topic: image-quality) — file cq-aliasing-01.jpg
{
  "prompt": "This image was acquired with a field of view smaller than the body part, and tissue from one edge appears overlapped onto the opposite side. What is this artifact and its cause?",
  "options": [
    "Aliasing (wrap-around), because anatomy outside the field of view is undersampled and mapped back onto the opposite side of the image",
    "Chemical shift, because fat and water protons resonate at slightly different frequencies and their signals misregister along the readout axis",
    "Gibbs artifact, because high spatial frequencies are truncated at a sharp signal boundary",
    "Gradient nonlinearity, because the gradient fields grow weaker toward the edges of the magnet bore"
  ],
  "answer": 0,
  "explain": "Aliasing, or wrap-around, occurs when the field of view is smaller than the imaged anatomy, so signal from outside the field of view is undersampled and folds back onto the opposite side of the image, usually along the phase-encoding direction. Enlarging the field of view, using phase oversampling, or applying a saturation band corrects it."
}
```

- [ ] **Step 2: Add the credits.html policy line**

In `web/credits.html`, update the "Course question images" paragraph (added in Phase A) to reflect owner-owned images. Replace its text with:

```html
      <p>Some course questions use clinical images to test image recognition. Simulator-rendered
        images are generated by MRISim itself. Any other clinical image is either owned by MRISim or
        openly licensed for commercial use (CC0, public domain, or CC BY); openly licensed images are
        credited beneath the image where they appear, with a link to the source. Images are shown
        resized. No non-commercial or education-only licensed images are used.</p>
```

- [ ] **Step 3: Lint (habit) + confirm manifest renders**

Run: `npm run lint` (no JS change here, but keep the habit; expect clean). Confirm the manifest is valid Markdown and the four JSON blocks parse (they are illustrative code blocks, not loaded by code).

- [ ] **Step 4: Commit**

```bash
git add docs/course-quiz-image-wishlist.md web/credits.html
git commit -m "docs(course-images): image requirements manifest + owner-owned credits note"
```

---

## Notes for the executor

- This phase ships NO images and edits NO `course_content.json` rows — it builds the rail and the list. Do not reseed Supabase in this phase (nothing changed there).
- When the owner later supplies an image: place it at the target filename (resize to <=600px wide, JPEG q85 if needed), set the question's `credit` (`Owner-Original` for an owned image; a PD source otherwise) and `img`; for a NEW slot add the drafted body from the manifest to `course_content.json`, for an upgrade slot add `img`+`credit` to the existing ord; verify the image shows the finding; byte-stable dump; reseed the changed rows; run guards. That wire-in is a follow-up, not part of this PR.
- Final guard set before PR: `~/Library/Python/3.9/bin/ruff check src/ tests/`, `python3.11 -m pytest -q`, `npm run test:web`, `npm run lint`.
- PR body ends with the standard `🤖 Generated with [Claude Code](https://claude.com/claude-code)` line (PR body only, never a commit trailer).
