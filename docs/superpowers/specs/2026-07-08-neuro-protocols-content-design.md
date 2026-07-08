# Course content: Neuro clinical protocols (PDF phase 2, region 1) — Design

**Goal:** Add neuro clinical-protocol content to the paid course — two reading lessons plus ~18 quiz
items — generalized from the "MR Intern Competency" staff deck's neuro section, deepening the course's
ARRT Procedures coverage (brain routine, plus pituitary, IAC, and stereotactic planning).

**Status:** Approved 2026-07-08. First region of PDF phase 2 (clinical protocols by region). Phase 2
decomposes into five regional sub-projects: **Neuro (this)** → Spine → Neurovascular → MSK → Body, each
its own spec → plan → build → review → merge. See [[project_pdf_content_phases]],
[[project_content_program]], [[project_course_roadmap]].

## Context

The paid course content lives in `data/course_content.json` (the source; seeded to Supabase
`course_content`, served to entitled users by `web/course.js`). Content groups by `topic`; each topic is
surfaced through a fixed 10-module map (`TOPIC_CFG` in `course.js`). Two existing topics are the homes
for this content and are **already mapped**, so no `course.js` change is needed:

- `procedures-anatomy` — Module 4 "Reading pathology" (regional anatomy: planes and sequences by body
  part). Currently 1 education lesson + 11 quiz.
- `procedures-protocols` — Module 9 "Putting it together" (building a protocol: why each sequence is
  there). Currently 1 education lesson + 14 quiz.

Item shape: `{topic, kind, ord, body}`. A reading lesson's `body` is
`{title, html, keypoints[~5], worked_example, memory_hooks[~3], exam_traps[~3]}`; a quiz `body` is
`{prompt, options[4], answer (0-indexed), explain}`. The answer-length pytest guard
(`tests/test_quiz_length.py`, `scripts/quiz_length_tools.py`) requires that no text-quiz item's keyed
answer exceeds every distractor by more than 20%. All quiz items are keyed to index 0 by convention;
`course.js` shuffles options at render, so the fixed key is not a tell.

## Source & generalization

Source: `pdf education/MR Intern Competency 2025.pdf`, neuro section (pages 6-34; extracted text cached
under the job tmp `pdftext/`). The deck is a hospital (NYU) staff training set. All site-specific detail
is **generalized** to representative practice that varies by site:

- Brand contrast name "Vueway" → "weight-based gadolinium contrast (per department protocol)".
- "EPIC" / "the dose is calculated in EPIC" → "the dose calculator" / "per the department's
  weight-based protocol".
- "GRASP" (the vendor DCE sequence) → "a dynamic contrast-enhanced (DCE) sequence".
- "BrainLab" → "stereotactic / neuronavigation surgical-planning".
- Phone numbers, named floors/sites, PACS/EPIC workflow specifics, "greaseboard" → removed or framed as
  "per department protocol".

Kept as generally true (ACR-consistent, defensible against current general MRI practice, not merely the
deck): head coil for brain/IAC/pituitary; skull-base-to-vertex coverage; **AC-PC line** axial
angulation; the **diffusion (compare high-b, e.g. b1000, to ADC) → acute stroke** rule (acute:
bright on high-b, dark on ADC), **SWI → hemorrhage / microbleed**, **FLAIR (CSF-nulled inversion
recovery) → MS / white-matter disease** triad; weight-based enhancement and which structures normally
enhance (pituitary, choroid plexus, vessels, nasal mucosa); **micro- vs macroadenoma at the 10 mm
threshold** and why microadenomas need **dynamic / delayed** post-contrast imaging; posterior pituitary
is T1-bright, gland sits in the sella turcica; **IAC images cranial nerves VII (facial) and VIII
(vestibulocochlear)**, indications include acoustic neuroma / vestibular schwannoma and sensorineural
hearing loss, technique uses **thin-section heavily-T2 (CISS-type)** cisternal imaging; **stereotactic /
pre-surgical planning rules** (head straight, do not angle the slice package, do not clip nose / ears /
occiput, keep full coverage for accurate registration); trigeminal-neuralgia / facial-nerve (Bell's
palsy) is a thin-section CN VII variant.

The accuracy reviewer checks every clinical claim against current general MRI practice and flags any
surviving site/brand specific.

## Content to add

1. **Lesson 1 — "Brain MRI: routine protocol and when to enhance"** —
   `{topic:"procedures-anatomy", kind:"education"}`, body with all six fields:
   - `html`: 2-3 short paragraphs — the routine non-contrast brain build (head coil, coverage,
     AC-PC angulation, the core sequence set), the stroke/hemorrhage/MS diffusion-SWI-FLAIR triad and
     what each demonstrates, and when/how enhancement is added (weight-based gadolinium; routine vs
     tumor / pre-op / post-op / mets / demyelinating indications; structures that normally enhance).
   - `keypoints` (~5), `worked_example` (a short scenario, e.g. acute hemiparesis → diffusion positive
     with low ADC → acute infarct), `memory_hooks` (~3), `exam_traps` (~3, e.g. FLAIR nulls CSF vs
     T2; high-b bright alone is not enough without ADC; flushing/warmth is normal, not enhancement).
2. **Lesson 2 — "Specialized neuro studies: pituitary, IAC, and stereotactic planning"** —
   `{topic:"procedures-protocols", kind:"education"}`, body with all six fields:
   - `html`: 2-3 short paragraphs — dynamic pituitary (micro/macro 10 mm, why dynamic/delayed finds
     microadenomas, sella/posterior-lobe anatomy), IAC (CN VII/VIII, acoustic neuroma indications,
     thin-section CISS-type cisternal technique, facial-nerve variant), and stereotactic / neuro-
     navigation planning (head straight, no package angulation, full coverage rules).
   - `keypoints` (~5), `worked_example`, `memory_hooks` (~3), `exam_traps` (~3).
3. **~18 quiz items** — `{topic, kind:"quiz"}`, each `{prompt, options[4], answer, explain}`, split
   ~9 to `procedures-anatomy` (brain-routine set) and ~9 to `procedures-protocols` (specialized set):
   - *anatomy (~9):* head coil; skull-base-to-vertex coverage; AC-PC axial angulation; diffusion →
     acute stroke (high-b vs ADC direction); SWI → hemorrhage/microbleed; FLAIR nulls CSF / MS; 3D sag
     reformats; weight-based enhancement; which structures normally enhance.
   - *protocols (~9):* micro- vs macroadenoma 10 mm; dynamic/delayed imaging finds microadenoma;
     posterior pituitary T1-bright / sella turcica; IAC = CN VII/VIII; acoustic neuroma / hearing-loss
     indication; thin-section CISS-type cisternal technique; stereotactic no-angulation rule;
     stereotactic full-coverage (don't clip) rule; trigeminal / facial-nerve variant.
   Board-style, four balanced-length options, no AI-tell punctuation, no em dashes.

Voice per [[feedback_no_ai_tells_content]] and [[feedback_ui_aesthetic]]: natural clinical prose.

## Integration & data flow

- Author produces a JSON patch file: `{ "lesson1": <edu body>, "lesson2": <edu body>, "quiz": [ ... ] }`
  where each quiz entry carries its intended topic (`procedures-anatomy` or `procedures-protocols`).
- The controller appends these to `data/course_content.json` `items` with the right `topic`/`kind` and
  fresh `ord` values after the current global max ord (byte-stable dump via
  `scripts/quiz_length_tools.py` `dump`, so the diff is only the additions).
- Re-seed: idempotent INSERT of the new rows into Supabase `course_content` via MCP `execute_sql`
  (course `mri-core`, matched/created by `body->>'title'` for the lessons and `body->>'prompt'` for
  quiz), same pattern as prior content seeds; a not-exists guard makes re-runs safe.

## Error handling / edge cases

- **Answer-length tell:** any new quiz item that reintroduces the tell fails the pytest guard; the
  author balances option lengths up front and the controller re-runs the guard before committing.
- **Duplicate prompt / title:** new prompts and lesson titles must be unique across the bank; the
  applier and reseed not-exists guard verify.
- **Generalization miss:** the accuracy reviewer flags any surviving NYU/site/brand specific (Vueway,
  EPIC, GRASP, BrainLab, phone numbers, floor/site names); fixed before merge.
- **Depth-count drift:** `tests/test_course_depth.py` hardcodes the education-module count; adding two
  lessons bumps it 17 → 19. The two new lessons must carry all depth fields (worked_example,
  memory_hooks 1-3, exam_traps 1-3, no em dashes) or the depth test fails.

## Testing

- **Guard + suite:** `python3 -m pytest tests/test_quiz_length.py tests/test_course_depth.py
  tests/test_course_images.py` green; `ruff check src/ tests/` clean.
- **Accuracy review** (subagent): medical correctness of both lessons and every quiz item, full
  generalization (no NYU/site/brand specifics), distractors wrong-but-plausible, balanced option
  lengths, no AI-tell punctuation.
- **Render:** Lesson 1 appears under Module 4 and Lesson 2 under Module 9 for an entitled user; the
  quiz items join their topic pools. No engine/JS change, so `npm run test:web` and the Python engine
  suite are unaffected.

## Out of scope

- The other four regions of phase 2 (Spine, Neurovascular, MSK, Body) — future sub-projects.
- Any `course.js` / curriculum-map change (not needed; both topics are already mapped).
- Image-based questions for this topic (text only here).
