# Spaced Review of Missed Items (Phase 3.3) — Design

**Goal:** Capture every question a learner gets wrong across the course and resurface it for
review on a widening (Leitner-lite) schedule until it sticks.

**Status:** Approved 2026-07-07. Schedule = Leitner-lite (miss due-now; correct-in-review widens
~1/3/7 days then graduates). Diagnostic misses DO feed the queue. Review sessions show immediate
feedback + explanation. Question identity = the (unique) prompt string.

## Context

`web/course.js` (paid course IIFE, no engine) grades answers at four sites: `quizItem` (inline
"Test yourself", `bumpScore` at ~line 499), `submitMastery` (mastery check, per-question at ~569),
`submitExam` (practice exam, ~764), and `submitDiagnostic` (placement test, ~844). There is no
per-question persistence today. All 222 premium quiz prompts are unique, so the prompt string is a
stable question key; the full body (`options`/`answer`/`explain`/`setup`/`img`) is resolvable from
the loaded bank (`CTX.byTopic`). Progress lives in `localStorage`; pure decision logic lives in
`web/course_logic.js` (node-tested, exposed on `window.CourseLogic` via a local alias in course.js).
The practice-exam machine renders no-feedback question sets; the diagnostic (Phase 3.2) is a
snapshot that does not touch progress.

## Architecture

A single `recordAnswer(q, correct, inReview)` in `course.js` is called from all four grading sites
and updates a review schedule keyed by prompt, using pure functions in `course_logic.js`. A "Review"
entry (overview card + rail) shows how many items are due; the review session pulls due items,
resolves each to its full body, and presents them one at a time WITH immediate feedback. State in a
new `localStorage` key. No backend, no content, no cache bump. The review queue is a study aid, not
the "progress" state — so feeding it from the diagnostic keeps the Phase 3.2 snapshot guarantee
intact (the diagnostic still never calls `bumpScore` or changes readiness/quiz/mastery).

## Data model

New `localStorage` key `mrisim_course_review_v1`:

```json
{ "<prompt>": { "box": 0, "due": 1720000000000, "misses": 2, "lastSeen": 1720000000000 } }
```

- `box`: consecutive correct reviews since the last miss (0 = freshly missed). Graduated items are
  removed from the map entirely.
- `due`: epoch ms; an item is due when `now >= due`.
- `misses`, `lastSeen`: bookkeeping (misses count; last time touched).

## Pure logic (`web/course_logic.js`, node-tested)

Add a day constant and three functions to the export:

```js
var DAY_MS = 86400000;
var REVIEW_INTERVALS_DAYS = [1, 3, 7];   // days added at box 1, 2, 3

// A missed question: reset to box 0, due immediately, misses incremented.
function reviewOnMiss(entry, now) {
  return { box: 0, due: now, misses: (entry && entry.misses ? entry.misses : 0) + 1, lastSeen: now };
}

// A correct answer during a review session: advance the box and widen the due date;
// return null once it graduates past the last interval (remove it from the queue).
function reviewOnCorrect(entry, now) {
  var box = (entry && entry.box ? entry.box : 0) + 1;
  if (box > REVIEW_INTERVALS_DAYS.length) return null;               // graduated
  return { box: box, due: now + REVIEW_INTERVALS_DAYS[box - 1] * DAY_MS,
           misses: (entry && entry.misses ? entry.misses : 0), lastSeen: now };
}

// How many entries in the review map are due now.
function dueCount(map, now) {
  var n = 0, k;
  for (k in map) { if (Object.prototype.hasOwnProperty.call(map, k) && map[k] && map[k].due <= now) n += 1; }
  return n;
}
```

Behavior: miss → box 0, due now; correct-in-review → box 1 (+1d) → box 2 (+3d) → box 3 (+7d) → a
further correct graduates (removed). So a freshly missed item is reviewable immediately and spaces
out only once the learner starts getting it right.

## Components (`course.js`)

1. **State helpers.** `loadReview()` / `saveReview(map)` (try/catch, matching existing `load*`
   helpers). `COURSE_REVIEW_KEY = "mrisim_course_review_v1"`.
2. **`recordAnswer(q, correct, inReview)`.** Loads the map, keys by `q.prompt`:
   - `!correct` → `map[prompt] = CourseLogic.reviewOnMiss(map[prompt], Date.now())`.
   - `correct && inReview` → `var e = CourseLogic.reviewOnCorrect(map[prompt], Date.now()); if (e) map[prompt] = e; else delete map[prompt];`.
   - `correct && !inReview` → no change.
   Then `saveReview(map)`. Hooked into `quizItem` (after `bumpScore`, `inReview=false`),
   `submitMastery` (per question in its loop, `false`), `submitExam` (per question in its scoring
   loop, `false`), and `submitDiagnostic` (per question in its loop, `false`). The review session
   calls it with `inReview=true`.
3. **Prompt→body index.** `reviewPool()` builds a map of `prompt -> body` from `CTX.byTopic` (all
   `kind:"quiz"` bodies), so a due prompt resolves to its full question. `dueReviewItems()` returns
   the bodies whose prompt is in the review map and due (`due <= now`), skipping any prompt no longer
   in the bank (aged out).
4. **Review session.** `startReview()` gathers `dueReviewItems()`, shuffles, and renders them one at
   a time (or as a scrollable set) with per-question grading + explanation (reuse the `quizItem`
   feedback pattern + `addQImg`), calling `recordAnswer(body, correct, true)` on each answer. A short
   summary at the end; a "Back to overview" action. If nothing is due, show a "nothing due" state.
5. **Entry points.** On `renderOverview`, a "Review" card showing `dueCount(loadReview(), now)` due
   items with a "Start review" button when the count is > 0 (and a muted "No items due for review"
   line otherwise). A "Review" rail button mirroring the exam/placement entries.

## Error handling / edge cases

- **Storage disabled:** `load*`/`save*` in try/catch; a failed save just means the miss is not
  queued.
- **Prompt aged out** (question text edited/removed): `dueReviewItems()` skips prompts absent from
  the current bank, so a stale entry never breaks the session (it simply never resurfaces; it can be
  pruned opportunistically when encountered).
- **Correct-in-review on an un-queued item:** `reviewOnCorrect(undefined, now)` treats box as 0 and
  advances to box 1 — harmless, but the review session only ever pulls queued due items so this path
  is not normally hit.
- **Graduation:** `reviewOnCorrect` returns null at box > 3; `recordAnswer` deletes the entry.

## Testing

- **Node unit tests** (extend `web/course_logic.test.mjs`): `reviewOnMiss` resets to box 0 due-now
  and increments misses; `reviewOnCorrect` advances box 0→1 (+1d), 1→2 (+3d), 2→3 (+7d), and returns
  null (graduate) from box 3; `dueCount` counts only entries with `due <= now`. No browser.
- **Render:** `npm run lint` clean on `course.js`; the Review card shows the due count; a review
  session grades with feedback and reschedules; manual signed-in run confirms a missed question
  appears as due, and getting it right in review pushes it out.
- No engine/physics change; the Python suite is unaffected.

## Out of scope (later / never)

- Server-side / cross-device sync of the review queue (localStorage only, like all course progress).
- Full SM-2 ease factors (Leitner-lite chosen deliberately).
- Any change to the mastery-check, exam, diagnostic, or quiz-accuracy mechanics beyond adding the
  `recordAnswer` call at each grading site.
