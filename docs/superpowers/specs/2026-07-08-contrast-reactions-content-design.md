# Course content: Contrast reactions & management (PDF phase 1) — Design

**Goal:** Add contrast-reaction recognition & management to the paid course — one reading lesson plus
~15 quiz items — generalized from the "Adverse Reactions for MRI" staff deck, deepening the course's
ARRT Patient Care coverage.

**Status:** Approved 2026-07-08. First of three PDF-derived content phases
(1: contrast reactions → 2: clinical protocols by region → 3: coil & positioning). See
[[project_content_program]], [[project_course_roadmap]].

## Context

The paid course content lives in `data/course_content.json` (the source; seeded to Supabase
`course_content`, served to entitled users by `web/course.js`). Content groups by `topic`; each topic
is surfaced through a fixed 10-module map (`TOPIC_CFG` in `course.js`). Module 10 "Safety & patient
care" already includes the `patient-care` topic (currently 1 education lesson + 21 quiz + 1 reference).
Item shape: `{topic, kind, ord, body}`. A reading lesson's `body` is
`{title, html, keypoints[~5], worked_example, memory_hooks[~3], exam_traps[~3]}`; a quiz `body` is
`{prompt, options[4], answer (0-indexed), explain}`. The answer-length pytest guard
(`tests/test_quiz_length.py`, `scripts/quiz_length_tools.py`) requires that no text-quiz item's keyed
answer exceeds every distractor by >20%.

Because the content attaches to the existing `patient-care` topic, **no `course.js` change is needed** —
the new lesson and quiz surface in module 10 automatically.

## Source & generalization

Source: `pdf education/Adverse Reactions for MRI.pdf` (extracted text at
`$JOBTMP/pdftext/Adverse Reactions for MRI.txt`). The deck is a hospital (NYU) staff training set.
All site-specific detail is **generalized**:

- Remove: phone numbers, "STAT over intercom", named sites/floors, EPIC/PACS, and brand contrast
  names. Frame institutional rules as "per department protocol".
- Keep as generally true: reaction severity tiers, vasovagal vs anaphylaxis physiology, extravasation
  hot/cold compress, the emergency-response sequence (a generic R.A.P.I.D.-style flow), medication-box
  drug->indication, EpiPen mechanics/dose and the tech scope-of-practice point, pre-medication schedule,
  and vitals norms (SpO2 > 95%, adult BP < 120/80).

Clinical claims must be defensible against current general MRI practice (ACR-consistent), not just the
deck; the accuracy reviewer checks this.

## Content to add

1. **One reading lesson** — `{topic:"patient-care", kind:"education"}`, title
   **"Contrast reactions: recognition and management"**, body with all six fields:
   - `html`: 2-3 short paragraphs covering frequency (mild common, anaphylaxis rare; flushing/warmth is
     not a true reaction), the three severity tiers, vasovagal vs anaphylaxis, extravasation, the
     emergency-response sequence, med box + EpiPen (tech may give EpiPen per policy; ER after),
     pre-medication, and vitals norms.
   - `keypoints` (~5), `worked_example` (a short scenario, e.g. hives + wheeze after gadolinium ->
     recognise moderate/severe, stop, call, treat), `memory_hooks` (~3), `exam_traps` (~3, e.g.
     vasovagal bradycardia vs anaphylaxis tachycardia; epinephrine is the anaphylaxis drug).
2. **~15 quiz items** — `{topic:"patient-care", kind:"quiz"}`, each `{prompt, options[4], answer,
   explain}`. Coverage: severity-tier identification, vasovagal vs anaphylaxis, extravasation compress,
   epinephrine indication + adult/junior EpiPen dose, EpiPen scope-of-practice, pre-medication schedule,
   drug->indication (albuterol/atropine/antihistamine/epinephrine), vitals thresholds, and post-EpiPen
   disposition. Board-style, four balanced-length options, no AI-tell punctuation, no em dashes.

Voice per [[feedback_no_ai_tells_content]] and [[feedback_ui_aesthetic]]: natural clinical prose.

## Integration & data flow

- Author produces a JSON patch file: `{ "lesson": <education body>, "quiz": [ <15 quiz bodies> ] }`.
- The controller appends these to `data/course_content.json` `items` with `topic:"patient-care"`, the
  right `kind`, and fresh `ord` values after the current global max ord (byte-stable dump via
  `scripts/quiz_length_tools.py` `dump`, so the diff is only the additions).
- Re-seed: INSERT the new rows into Supabase `course_content` via MCP `execute_sql` (course
  `mri-core`, matched/created by `body->>'prompt'` for quiz and `body->>'title'` for the lesson),
  same pattern as prior content seeds.

## Error handling / edge cases

- **Answer-length tell:** any new quiz item that reintroduces the tell fails the pytest guard; the
  author balances option lengths up front and the controller re-runs the guard before committing.
- **Duplicate prompt:** the new quiz prompts must be unique across the bank (the applier/guard verify).
- **Generalization miss:** the accuracy reviewer flags any surviving NYU/site/brand specific; fixed
  before merge.
- **Re-seed idempotency:** INSERT by unique prompt/title; a failed row can be re-run without dupes
  (guarded by a not-exists check).

## Testing

- **Guard + suite:** `python -m pytest tests/test_quiz_length.py tests/test_course_depth.py
  tests/test_course_images.py` green; `ruff check src/ tests/` clean.
- **Accuracy review** (subagent): medical correctness of the lesson and every quiz item, generalization
  (no NYU/site/brand specifics), distractors wrong-but-plausible, balanced option lengths, no tells.
- **Render:** the lesson appears under module 10 for an entitled user; quiz items join the patient-care
  pool. No engine/JS change, so `npm run test:web` and the Python engine suite are unaffected.

## Out of scope

- Clinical protocols by region (phase 2) and coil/positioning (phase 3).
- Any `course.js` / curriculum-map change (not needed; `patient-care` is already mapped).
- Image-based questions for this topic (text only here).
