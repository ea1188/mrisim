# Completion Milestone (Phase 4.1) — Design

**Goal:** Give the paid course a real finish line: a definitive on-screen "course complete" state
when the learner has mastered every module and demonstrated it on a full practice exam.

**Status:** Approved 2026-07-08. Criteria = every module mastered AND best practice exam >= 80%.
On-screen completion panel only (no printable summary). The completion record syncs across devices.

## Context

`web/course.js` renders an exam-readiness dashboard (`renderOverview`) from `computeReadiness`,
which returns `modules` (each with `status`, incl. `"mastered"`), a `next` (null when all mastered),
and `exam` (`{bestPct,...}` from the practice exam). Today, when `next` is null the overview shows
"Every module is mastered. Run a full practice exam to confirm you're ready." Progress is synced
across devices via `PROGRESS_KEYS` + the pure `mergeProgress` in `web/course_logic.js` (node-tested).
`PASS_PCT = 80` is the mastery-check pass bar.

## Architecture

A pure, node-tested `isCourseComplete(...)` in `course_logic.js`; a completion record persisted in a
new `localStorage` key and added to the synced set; and a completion panel in `renderOverview`. No
backend, no new content, no cache bump.

## Completion criteria

Complete when **every module `status === "mastered"`** AND **`exam.bestPct >= 80`**. Both are already
computed by `computeReadiness`.

## Data model

New `localStorage` key `mrisim_course_completed_v1`:

```json
{ "at": 1720000000000, "examPct": 88 }
```

- `at`: epoch ms of first completion (set once, the true completion date).
- `examPct`: the best practice-exam percent at first completion.

Added to `PROGRESS_KEYS` so it syncs. `mergeProgress` merges it by **earlier `at` wins** (completion
is monotonic; the first date is the real one); a record present on one side passes through.

## Pure logic (`web/course_logic.js`, node-tested)

```js
var COMPLETE_EXAM_PCT = 80;  // best-mock threshold for course completion

// Complete = every module status is "mastered" AND the best practice exam >= COMPLETE_EXAM_PCT.
function isCourseComplete(statuses, bestExamPct) {
  if (!statuses || !statuses.length) return false;
  for (var i = 0; i < statuses.length; i++) { if (statuses[i] !== "mastered") return false; }
  return typeof bestExamPct === "number" && bestExamPct >= COMPLETE_EXAM_PCT;
}
```

Plus a `mergeProgress` rule for the new key: `if ("mrisim_course_completed_v1" in out) out.mrisim_course_completed_v1 = _earlier(local..., remote..., "at")`, where `_earlier(a, b, field)` returns the object with the smaller `field` (null-safe; one-sided → the present one).

Both added to the `course_logic.js` export (`isCourseComplete`; `_earlier` is internal).

## Components (`course.js`)

1. **State helpers.** `COURSE_COMPLETE_KEY = "mrisim_course_completed_v1"`; `loadCompleted()` /
   `saveCompleted(rec)` (try/catch like the existing `load*`/`save*`). Add the key to `PROGRESS_KEYS`.
2. **Detection + record.** In `renderOverview`, compute
   `complete = CourseLogic.isCourseComplete(r.modules.map(function (m) { return m.status; }), r.exam && r.exam.bestPct)`.
   On the first time `complete` is true and no record exists, `saveCompleted({ at: Date.now(),
   examPct: r.exam.bestPct })` and `queueSync()` (so it syncs).
3. **Completion panel.** When `complete`, replace the current "run a practice exam" nudge (the `else`
   branch of `if (r.next)`) with a prominent "Course complete" panel: a heading, a line stating every
   module is mastered and the best mock score, the completion date (from the stored record), and a
   short encouraging note. The practice-exam button and module grid stay below (continued review is
   still possible). Professional/clinical styling (no emoji, gradients, pills).
4. **Not-yet-complete but all-mastered:** if every module is mastered but `bestExamPct < 80` (or no
   exam yet), keep the existing "Every module is mastered. Run a full practice exam..." nudge (it now
   reads as the last step before completion).

## Error handling / edge cases

- **Storage disabled:** `load*/save*` in try/catch; completion just is not persisted (still shows the
  live complete state; the date falls back to "today" if no record).
- **Regression after completion:** completion is not un-set once recorded (the record persists), even
  if the learner later resets progress; the panel keys off the stored record OR the live criteria
  (show complete if either the record exists or the live criteria hold).
- **Sync:** earlier-`at` wins so the true first-completion date survives a cross-device merge.

## Testing

- **Node unit tests** (extend `web/course_logic.test.mjs`): `isCourseComplete` — all mastered +
  exam 80 → true; all mastered + exam 79 → false; a non-mastered module → false; empty → false;
  missing exam → false. `mergeProgress` earlier-`at` rule for the completed key.
- **Render:** `npm run lint` clean; manual signed-in check that mastering all modules + an 80%+ mock
  flips the dashboard to the complete panel with the right date/score, and that it syncs.
- No engine/physics change; the Python suite is unaffected.

## Out of scope

- Printable / downloadable completion summary or certificate (dropped by decision; would also need
  careful non-accreditation framing per the Terms).
- Study schedule and module diagrams (later Phase 4 sub-projects).
