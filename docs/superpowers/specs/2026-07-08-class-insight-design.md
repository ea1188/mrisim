# Class insight (owner sub-project B) — Design

**Goal:** Give a class owner a read-only insight view of their students' formative practice: a per-student
table (practice coverage, best score, weakest topic, a struggling flag, last active), a click-to-expand
per-student drill-down (per-topic best / latest / attempts and the lessons completed), class-level stats
(class average, average practice coverage, weakest topics across the class), and a CSV export. This is
**owner sub-project B**, following A (roster & class management, PR #391). See [[project_owner_abilities]].

**Status:** Approved 2026-07-08. User chose the full per-student-insight framing and the blended
practice-coverage metric.

## Context

The owner/class backend already exists (migration 0001: `classes`, `enrollments`, `activity`, `profiles`
with owner-read RLS). The account page `web/account.html` loads `web/accounts.js` (`window.Accounts`, the
data layer) and `web/account.js` (the DOM/UI). `classCard(cl, reload)` in `web/account.js` already renders
a basic per-student table from two existing reads:

- `Accounts.roster(classId)` -> `[{ student_id, joined_at, profiles: { display_name, institution } }]`
- `Accounts.classActivity(classId)` -> `[{ student_id, kind, ref, score, total, created_at }]` (class-
  stamped rows, newest first, capped at 1000)

Owner RLS already permits both (migration 0001: `profiles_instructor_read`, `enroll_instructor_read`,
`activity_instructor_read`). **B needs no schema, RLS, or new backend function** — it is richer client-side
aggregation plus UI over the two reads that `classCard` already performs.

**Scope boundary (important, and reflected in the UI copy).** The `activity` table receives only two kinds
of events: `quiz_attempt` (written by `web/quiz.js`, `ref` = quiz topic id, with `score`/`total`) and
`lesson_complete` (written by `web/app.js`, `ref` = lesson title). It does **not** receive mastery-check
results, mock-exam scores, or the learner's authoritative module-mastered / course-complete state — those
live in `localStorage` mirrored to `course_progress`, which RLS scopes to the student, so the owner cannot
read them. B therefore reports **formative practice only**, consistent with migration 0001's own framing
("practice signal, NOT trusted grades"). The UI labels the coverage number as formative, not graded
completion.

## Architecture

Three pieces, matching the repo's existing conventions (a pure UMD logic module with a co-located
`node --test` file, plus a thin DOM layer):

1. **`web/class_insight.js`** (new, pure, UMD like `web/course_logic.js` / `web/join_link.js`: assigns
   `window.ClassInsight` in the browser and `module.exports` under Node). All aggregation and formatting,
   no DOM, no network. Functions (exact interfaces):

   - `perStudent(roster, activity, opts)` -> array of one row per roster member, each:
     `{ studentId, name, quizRuns, lessonsDone (distinct count), topics: { <topicId>: { best, latest,
     attempts } }, bestPct (max over topics, or null), weakestTopic (topicId of lowest best, or null),
     lastActive (iso or null), struggling (bool) }`. `opts = { passPct: 80, struggleAttempts: 2 }`
     (defaults). `struggling` = some topic has `attempts >= struggleAttempts` and `best < passPct`.
     `best`/`latest` are percentages (0-100) computed from `score`/`total`; rows with `total == 0` or null
     are ignored for scoring. Repeats are handled: `attempts` counts quiz_attempt rows for that topic,
     `best` is the max percentage, `latest` is the most recent by `created_at`; lessons are de-duplicated
     by `ref`.
   - `coverage(row, totals)` -> integer percent = round(100 * (row.lessonsDone + topicsPassed) /
     (totals.lessons + totals.topics)), where `topicsPassed` = count of `row.topics` whose `best >=
     passPct`; returns 0 when the denominator is 0. `totals = { lessons, topics }`.
   - `classStats(rows, totals)` -> `{ members, avgBestPct (mean of rows' bestPct, ignoring nulls),
     avgCoverage (mean of coverage over rows), weakestTopics (array of { topic, avgBest } sorted ascending,
     top 3) }`.
   - `toCSV(rows, totals)` -> string. Header:
     `Member,Practice coverage %,Best score %,Lessons done,Weakest topic,Struggling,Last active`. One row
     per student, values escaped (wrap in quotes and double any embedded quote), newline `\n`. This is a
     pure string; the DOM layer turns it into a download.

2. **`web/class_insight.test.mjs`** (new, `node --test`) added to the `test:web` script in `package.json`
   (which `.github/workflows/web-lint.yml` runs in CI). Covers: best-vs-latest-vs-attempts aggregation,
   distinct-lesson counting, blended coverage math (incl. zero denominator), weakest-topic selection,
   struggling flag at the threshold boundary, empty class / empty activity, a student in the roster with no
   activity, and CSV escaping (a name containing a comma and a quote).

3. **`web/account.js`** (`classCard` extended) + **`web/account.html`** (add `<script src="class_insight.js">`
   before `account.js`, mirroring `join_link.js`). `classCard` continues to `Promise.all([roster,
   classActivity])`, then:
   - builds `rows = ClassInsight.perStudent(roster, acts)` and `totals` (see denominator below);
   - renders the enriched member table: Member, Practice coverage %, Best score, Weakest topic, Struggling
     (a small flat chip when true), Last active, and the existing Remove button; a row is clickable to
     expand;
   - on expand, renders an inline drill-down under the row: per-topic best / latest / attempts, and the
     list of completed lessons;
   - renders a class-summary line (members, class average best, average coverage, up to 3 weakest topics)
     from `ClassInsight.classStats`;
   - adds a "Download CSV" button that turns `ClassInsight.toCSV(rows, totals)` into a Blob download
     (`<a download>` with an object URL);
   - keeps the existing formative footnote and adds the "practice coverage is formative, not graded
     completion" wording next to the coverage column/summary.

**Denominator source.** `totals.lessons` and `totals.topics` are the curriculum size. The account page does
not currently load the curriculum; the plan will have `classCard` (or its caller) obtain the counts the
same way the learner surfaces them: `totals.lessons` from the lessons dataset the app uses (`web/` lessons
JSON, `data.lessons.length`) and `totals.topics` from the distinct quiz topic ids (quiz categories). These
are fetched once per account-page load (not per class) and passed into `perStudent`/`coverage`. If a fetch
fails, coverage falls back to lessons-only totals so the table still renders (best-effort, like the rest of
the account page).

## UI / copy

- Flat, clinical styling consistent with the existing account page (no emoji, no gradients, 2px corners);
  the struggling chip is a flat solid accent, not a pill with a gradient.
- Coverage column header carries a tooltip / muted subtext: "practice coverage (formative, not a graded
  grade)".
- The drill-down is an inline expandable region under the member row (not a modal), matching the page's
  simple structure.

## Testing & guards

- `npm run test:web` (adds `web/class_insight.test.mjs`) — pure-logic unit tests, run in CI by
  `web-lint.yml`.
- `npm run lint` (eslint `web/`) must stay clean; `class_insight.js` follows the UMD/ES5-ish style of
  `join_link.js`.
- Existing Python guards (`ruff`, pytest) are unaffected (no Python touched) but are still run before merge
  per the repo convention.
- Manual/Playwright smoke: the account page still renders for an owner with a class; a class with zero
  members shows the existing empty-state; CSV downloads.

## Edge cases

- **Multi-class students:** `logActivity` stamps `class_id` from the student's *first* enrollment only, so a
  student in two classes attributes all activity to one. B surfaces what is stamped; it does not attempt to
  re-attribute. Noted, not fixed here.
- **1000-row cap:** `classActivity` caps at 1000 rows. For a very active class this can truncate history;
  acceptable for the MVP, and the aggregation degrades gracefully (older attempts simply absent). A
  paginated fetch is a later enhancement, out of scope.
- **No activity / unnamed student:** a roster member with no activity shows zeros and a dash; a missing
  `display_name` shows "(unnamed)", as today.
- **total == 0 quiz rows:** ignored for scoring (no divide-by-zero), still counted as a quiz run.

## Out of scope

- Any schema, RLS, or new backend function (all reads already exist and are owner-permitted).
- Mastery-check, mock-exam, or authoritative course-completion visibility (not in `activity`; RLS-blocked
  in `course_progress`).
- Assigning or directing work (new `assignments` table, learner-facing) — that is sub-project **C**.
- True email invitations, enrollment caps, sections, co-instructors (deferred per
  [[project_owner_abilities]]).
