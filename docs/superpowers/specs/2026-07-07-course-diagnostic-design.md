# Diagnostic Pre-Test (Phase 3.2) — Design

**Goal:** Let a learner take a ~10-minute placement test that scores each of the 10 course
modules and routes them to their weakest areas first, without touching earned progress.

**Status:** Approved 2026-07-07. Result behavior = reorder the study path via a separate snapshot
(does NOT bump quiz accuracy or readiness %). Length = 2 questions per module (20 total). Includes
image questions naturally when a module's pool has them. Retakeable, latest snapshot wins.

## Context

`web/course.js` (the paid course IIFE, no engine) renders an exam-readiness dashboard
(`renderOverview`) driven by `computeReadiness`, which returns per-module `status`
(via `CourseLogic.deriveModuleStatus`) plus a `next` = the first non-mastered module in curriculum
order. The overview shows the readiness score, a "Study next" button, "Take a practice exam", and a
module grid. The practice-exam machinery (`examPool`, `startExam`, `beginExam`, `renderExam`,
`submitExam`, `renderExamReview`) runs a no-feedback-until-submit question set. `modulePool(mod)`
(Phase 1) returns a module's premium quiz pool; `addQImg(box, q)` (Phase 3.1) shows a scan on image
questions. Progress lives in `localStorage` (`mrisim_course_quiz_v1`, `_read_v1`, `_exam_v1`,
`_mastery_v1`, `mrisim_curriculum`). `CourseLogic` (`web/course_logic.js`) holds the pure, node-tested
decision logic.

## Architecture

A self-contained diagnostic flow in `course.js`: sample 2 questions from each of the 10 modules
(tagged with their module), run them with no feedback until submit (reusing the exam's option +
`addQImg` rendering), score per module, and store a **separate snapshot** in a new `localStorage`
key. The snapshot reorders "Study next" and surfaces a recommended path. It does not modify the quiz
/ mastery / readiness state. The ranking + study-next selection are pure functions in
`course_logic.js` (node-tested). No backend, no new content, no cache bump.

## Data model

New `localStorage` key `mrisim_course_diagnostic_v1`:

```json
{ "taken": true, "ts": 1720000000000,
  "perModule": { "<module title>": { "asked": 2, "right": 1 } },
  "order": ["<weakest title>", "<next weakest>", "..."] }
```

- `perModule`: per-module asked/right from the latest run.
- `order`: all 10 module titles ranked weakest-first (accuracy ascending; ties broken by curriculum
  order so the earlier module wins).

## Pure logic (`web/course_logic.js`, node-tested)

- `rankModulesByDiagnostic(perModule, curriculumTitles) -> [title, ...]`: returns all
  `curriculumTitles` ordered by ascending accuracy (`right/asked`; a module absent from `perModule`
  or with `asked === 0` sorts as if accuracy 1.0 so it does not jump the queue ahead of genuinely
  weak modules), ties broken by original curriculum order (stable). This produces the stored
  `order`.
- `diagnosticStudyNext(order, statusByTitle) -> title | null`: given the diagnostic `order` and a
  map of title -> status, returns the first title in `order` whose status is not `"mastered"`, or
  `null` if all are mastered (or `order` is empty).

`course_logic.js` currently exports `{ PASS_PCT, CHECK_N, MIN_POOL, deriveModuleStatus }`; add the
two new functions to that export.

## Components (in `course.js`)

1. **Entry points.** On the overview (`renderOverview`), a prominent "Take the placement test" card
   when no diagnostic exists; once taken, a "Recommended path" panel (the weakest modules first) with
   a jump-to-weakest button and a "Retake placement test" action. A rail entry mirrors the practice
   exam's rail button.
2. **Run.** `startDiagnostic()` builds 20 questions: for each of the 10 modules, `shuffleInts` its
   `modulePool` and take up to 2, tagging each question object with its `modTitle`. Options are
   shuffled per question. Rendered with no feedback until submit (model on `renderExam`: select
   toggles a `.sel` class, a submit button with an unanswered-count confirm). Image questions render
   their scan via `addQImg`.
3. **Submit + score.** `submitDiagnostic()` tallies per-module `asked`/`right`, builds `perModule`,
   computes `order = CourseLogic.rankModulesByDiagnostic(perModule, curriculumTitles)`, saves the
   snapshot (`saveDiagnostic`), and renders a results screen: overall score, a per-module accuracy
   breakdown (bars), the recommended path (weakest first), and Retake. Answers do NOT call
   `bumpScore` (no readiness pollution).
4. **Dashboard integration.** In `computeReadiness`, after computing per-module `status`, if a
   diagnostic snapshot exists, set `next` to the module named by
   `CourseLogic.diagnosticStudyNext(diagnostic.order, statusByTitle)` (fall back to the existing
   first-non-mastered-in-curriculum-order when there is no diagnostic or the helper returns null).
   `renderOverview` shows the "Take the placement test" card vs the "Recommended path" panel based on
   whether a snapshot exists.

## Error handling / edge cases

- **Storage disabled:** `loadDiagnostic`/`saveDiagnostic` use try/catch like the existing
  `load*`/`save*` helpers; a failed save just means no snapshot (dashboard falls back to curriculum
  order).
- **Module pool < 2:** take whatever the pool has (all modules currently have >= 8). A module with 0
  pool contributes no questions and is treated as accuracy 1.0 in the ranking (does not jump the
  queue).
- **Retake:** overwrites the snapshot (latest wins).
- **Mastered modules in the recommendation:** `diagnosticStudyNext` skips mastered modules, so a
  learner who has already mastered their weakest-diagnosed area is routed to the next weakest.

## Testing

- **Node unit test** (extend `web/course_logic.test.mjs`): `rankModulesByDiagnostic` orders
  weakest-first with the accuracy-1.0-for-absent rule and curriculum-order tie-break;
  `diagnosticStudyNext` returns the first non-mastered title in order, skips mastered, returns null
  when all mastered. No browser.
- **Render:** `npm run lint` clean on `course.js`; the "Take the placement test" card shows only
  without a snapshot; manual signed-in run confirms a 20-question no-feedback flow, a per-module
  results screen, and that "Study next" then points at the weakest non-mastered module.
- No engine/physics change; the Python suite is unaffected.

## Out of scope (later)

- Phase 3.3 spaced review of missed items.
- Server-side / cross-device sync of the diagnostic snapshot (localStorage only, like all course
  progress).
- Any change to the mastery-check, practice-exam, or quiz-accuracy mechanics.
