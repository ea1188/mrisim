# Exam-realistic image questions — Phase B: curated commercial-safe image bank — Design

**Goal:** Source real, commercial-safe clinical images (CC0 / public-domain / CC-BY / CC-BY-SA) for the
pathology and real-world-artifact concepts the simulator cannot faithfully depict, and wire them into the
paid course as image questions using the `credit` schema shipped in Phase A. Restores the concepts Phase A
converted to text and adds new high-yield registry image-IDs.

**Status:** Approved 2026-07-08. Licensing bar: commercial-safe, now including **CC-BY-SA** under a
no-derivatives guardrail (see below). Sourcing: I source + license-verify + resize + stage; the user
approves each batch before it is committed/seeded. First batch = 5 concepts (below).

## Context

Phase A (PR #404) shipped the rail this phase fills:
- Quiz body schema: a `kind:"quiz"` body carries exactly one image source — `setup` (simulator) XOR
  `credit` `{author, license, source_url, title}` (curated image). Enforced by
  `tests/test_course_images.py` `validate_image_body` (XOR + commercial-safe license allow-list +
  image-exists).
- `web/course.js` `addQImg` already renders an attribution caption `Image: <author> · <license> · source`
  beneath any image whose body has a `credit`.
- `scripts/prerender_course_quiz.py` skips `credit` items (curated images ship as committed files).
- Live course content is served from Supabase `course_content` (course `mri-core`), so every content edit
  must be RESEEDED there, not just committed.
- Phase A converted 8 questions to text-only (3 pathology, spin-echo/ghosting/susceptibility, fat-sat
  pair); Phase B re-adds image versions where a real image genuinely helps.

**Feasibility confirmed in this environment:** the Wikimedia Commons API returns structured
`LicenseShortName` + `Artist` + canonical `url`; `curl` downloads the image binary; PIL opens/resizes it.
So license verification is programmatic and auditable, and the full source -> verify -> download -> resize
-> stage pipeline runs here.

## Licensing (commercial-safe, incl. CC-BY-SA under a guardrail)

Allow-list (extends Phase A): `CC0-1.0`, `Public-Domain`, `CC-BY-4.0/3.0/2.0`, **`CC-BY-SA-4.0/3.0/2.0`**.
Excluded: any `-NC` (non-commercial) or `-ND` (no-derivatives), and "free for education" wording.

**CC-BY-SA guardrail** (why it is safe for a paid product): ShareAlike obligations attach only to
*adaptations* (derivative works), not to *collections*. Placing an unaltered image next to our own quiz
text is a collection, so our quiz/course stays under our own terms. Therefore:
- Use images **unaltered** — resize only (a technical, non-creative change). **Never** annotate, crop
  creatively, or overlay labels on a BY-SA image (that would make a derivative that must itself be BY-SA).
- Attribute every curated image with author + exact license + link to source. The credits.html policy
  line states images are shown **resized**.

`tests/test_course_images.py` `ALLOWED_LICENSES` gains the three BY-SA entries. The license string from the
Wikimedia API (e.g. `"CC BY-SA 4.0"`) is normalized to the allow-list form (`"CC-BY-SA-4.0"`) at intake.

## Architecture — a sourcing pipeline, not new schema

No schema change. The new machinery is a repeatable per-concept pipeline:

1. **Find:** query the Wikimedia Commons API (`action=query&prop=imageinfo&iiprop=url|extmetadata`) for
   candidate files matching the concept; read `url`, `LicenseShortName`, `Artist`, and the file
   description/categories.
2. **Verify license:** reject anything whose normalized license is not in the allow-list. Record the exact
   license string, author, and source URL.
3. **Download + normalize:** `curl -L` the canonical `url`; open with PIL; resize to <=600px wide (matching
   the existing sim images); save JPEG quality 85 to `web/img/course-quiz/<file>`.
4. **QA — two gates, both required before ship:**
   - *License:* verified from the API (auditable), in the allow-list.
   - *Accuracy:* the image genuinely shows the claimed finding, confirmed from the source
     caption/categories plus my own read — the same accuracy bar as the text content. A question's answer
     must be true of the specific image shown.
5. **Approval gate (the user):** present each batch as a table — concept · staged thumbnail · proposed
   question · author/license/source — and the user approves or rejects each item. Rejected items are
   re-sourced or dropped for the round.
6. **Wire in:** for each approved item, add (or update) the `course_content.json` quiz body with the
   `credit` block + `img`, byte-stable via `scripts/quiz_length_tools.py`; reseed the changed Supabase
   `course_content` rows; the Phase A caption renders attribution automatically.

**Filename convention:** `cq-<concept>-<modality>-NN.jpg` (e.g. `cq-infarct-dwi-01.jpg`), lower-case,
matching the existing `cq-*` set.

**Question design:** each curated question follows the existing quiz body shape (`prompt`, 4 `options`,
`answer` index 0 keyed, `explain`), option lengths balanced so the answer-length guard
(`tests/test_quiz_length.py`) passes. Where Phase A left a text-only question for the same concept, the
curated version replaces it (drops nothing — the concept simply regains its image).

## First batch (5 concepts)

1. **Acute infarct** — DWI bright lesion (restricted diffusion; pair the teaching point with ADC if a
   matched image is available). Topic: `pathology`.
2. **Multiple sclerosis** — periventricular FLAIR plaques / Dawson's fingers. Topic: `pathology`.
3. **Fat suppression** — a fat-saturated (or STIR) image vs its non-suppressed counterpart, or a single
   image where suppressed fat is unambiguous. Restores the concept Phase A pulled. Topic: `fat-suppression`.
4. **Susceptibility / microhemorrhage** — GRE or SWI blooming. Topic: `flow-artifacts` (or `pathology`).
5. **Enhancing tumor** — post-contrast T1 mass/ring enhancement. Topic: `pathology`.

**Batch 2 (later, its own approval round):** real-world artifacts — motion ghosting, aliasing/wrap-around,
Gibbs/truncation, chemical shift — plus any remaining Phase-A conversions worth an image.

## Testing & guards

- `tests/test_course_images.py`: allow-list gains BY-SA; every curated `credit` validates (author,
  source_url, title present; license in the allow-list); image files exist; filenames unique.
- `tests/test_quiz_length.py`: curated questions balanced so the keyed answer is not the sole longest
  option.
- Full `pytest` (python3.11), `npm run test:web`, `ruff check src/ tests/`, `eslint web/` before PR.
- Reseed Supabase and confirm the curated rows carry their `img` + `credit`.
- Manual/Playwright smoke: an entitled learner sees the curated image with its attribution caption.

## Out of scope

- **Annotated / cropped / derivative images** — as-is (resize-only) use only, to keep the BY-SA guardrail
  clean.
- **Non-Wikimedia sources** (NLM Open-i, PMC CC-BY) — allowed by the licensing bar but deferred; Batch 1
  sources from Wikimedia Commons, which has a clean license API. Add others only if a concept lacks a
  Commons candidate.
- **Expanding the simulator-rendered physics set / balancing thin topics** — Phase C.
- Any change to entitlements, mock-exam sampling, the free quiz, or the `credit` schema itself.

## Edge cases

- **No commercial-safe candidate for a concept:** leave that concept as its Phase A text-only question this
  round; note it for a later batch. Do not ship a weak or wrongly-licensed image to fill the slot.
- **License not in the allow-list (NC/ND):** reject at step 2, never downloaded into the repo.
- **Image too small / low quality after resize:** reject; find a better candidate.
- **A candidate's finding does not clearly match the intended answer:** reject (accuracy gate); pick a
  clearer image or reword the question to the image actually shown.
- **BY-SA attribution:** the caption shows author + license + source link; the credits.html policy line
  states images are resized. No creative modification is ever made.
