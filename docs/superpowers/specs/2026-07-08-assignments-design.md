# Assignments (owner sub-project C) — Design

**Goal:** Let a class owner assign work — a lesson, a quiz topic, or a whole curriculum module,
with an optional due date — to their class, and surface those assignments to the enrolled students
on both the account page (an "Assigned to you" checklist) and inline in the paid course page (an
"ASSIGNED" badge in context), with completion derived from activity the platform already records.
This is **owner sub-project C**, the last in the locked A -> B -> C owner sequence, following A
(roster & class management, PR #391) and B (class insight, PR #402). See [[project_owner_abilities]].

**Status:** Approved 2026-07-08. User chose both learner surfaces (account panel + inline course
badges), all three assignable kinds (lesson / quiz / module), and Approach A (completion derived from
the existing `activity` table, no new write paths).

## Context

The owner/class backend already exists (migration 0001: `classes`, `enrollments`, `activity`,
`profiles` with owner-read RLS; the SECURITY DEFINER helpers `is_class_owner(uuid)` and
`is_enrolled(uuid)` that let a policy on one table ask about another without tripping Postgres policy
recursion). The account page `web/account.html` loads `web/accounts.js` (`window.Accounts`, the data
layer) and `web/account.js` (the DOM/UI). Sub-project B added `web/class_insight.js` (a pure UMD
aggregation module) and its `web/class_insight.test.mjs`; this design follows that exact shape.

**The two facts that make Approach A work:**

1. **The assignable catalog is fully derivable from data both pages already load.** `web/lessons.json`
   holds `.curriculum` — an array of `{ title, lessons: [<lesson title>, ...] }` (10 modules). Both
   `web/course.js` (`courseView(data.curriculum ...)`) and `web/app.js` (`CURRICULUM = data.curriculum`)
   already load it. `web/quiz.json` holds `.categories` — `[{ id, ... }]` (8 topics). Sub-project B's
   `curriculumTotals()` already fetches both on the account page.

2. **Completion is already observed, for exactly the assignable universe.** `activity` receives only
   two event kinds: `lesson_complete` (written by `web/app.js:409`, `ref` = the free lesson's title)
   and `quiz_attempt` (written by `web/quiz.js:234`, `ref` = the quiz topic id). A lesson's assignment
   ref equals the lesson title; a quiz's assignment ref equals the topic id — so a student's own
   activity rows tell us, with no new writes, whether an assigned lesson or quiz is done. A module's
   completion is derived from its lessons (see "Module completion" below).

**Scope boundary (reflected in UI copy, consistent with B).** The premium course page (`web/course.js`)
does **not** write to `activity` — mastery checks, mock-exam scores, and premium-reading state live in
`localStorage` mirrored to `course_progress`, which RLS scopes to the student. So the platform can only
observe completion for **free lessons and quiz topics**. That is precisely the assignable universe with
a completion signal; module completion is inferred from its lessons. Assignments and their completion
are therefore **formative practice signal, not graded completion** — the same framing B and migration
0001 already use, carried into the assignment UI copy.

## Architecture

Five pieces, mirroring the A/B convention (a new migration, a pure UMD logic module with a co-located
`node --test` file, thin data-layer methods, and DOM layers over them):

### 1. `supabase/migrations/0007_assignments.sql` (new)

```sql
-- Owner-assigned work for a class: a lesson, a quiz topic, or a whole curriculum
-- module, with an optional due date. Completion is NOT stored here; it is derived
-- client-side from the existing `activity` table (see the assignments design doc).
create table assignments (
  id         uuid        primary key default gen_random_uuid(),
  class_id   uuid        not null references classes(id) on delete cascade,
  kind       text        not null check (kind in ('lesson', 'quiz', 'module')),
  ref        text        not null,          -- lesson title / quiz topic id / module title
  due_at     timestamptz,                   -- nullable = no due date
  created_at timestamptz not null default now()
);
create index assignments_class_idx on assignments (class_id);
-- one assignment per (class, kind, ref); a re-assign updates the due date via upsert.
create unique index assignments_class_kind_ref_idx on assignments (class_id, kind, ref);

alter table assignments enable row level security;

-- Owner of the class does full CRUD; enrolled students may read their classes' rows.
create policy assignments_owner_all on assignments for all
  using (is_class_owner(class_id)) with check (is_class_owner(class_id));
create policy assignments_enrolled_read on assignments for select
  using (is_enrolled(class_id));
```

No new helper functions, no change to any existing table. The unique index makes "assign the same
item again with a new due date" an upsert rather than a duplicate.

### 2. `web/assignments.js` (new, pure UMD like `web/class_insight.js`)

Assigns `window.Assignments` in the browser and `module.exports` under Node. No DOM, no network. Exact
interfaces:

- `catalog(lessonsData, quizData)` -> the assignable catalog, built once and shared by owner picker and
  learner surfaces:
  `{ modules: [{ ref, label, lessons: [<title>...] }], lessons: [{ ref, label, module }], quizzes: [{ ref, label }] }`.
  `modules`/`lessons` come from `lessonsData.curriculum` (`ref` = title, `label` = title; each lesson
  records its owning `module` title). `quizzes` come from `quizData.categories` (`ref` = `id`,
  `label` = a humanized id when no name is present). Missing/omitted inputs yield empty arrays (the page
  still renders).
- `studentStatus(assignments, activity, catalog)` -> for ONE student's activity, an array parallel to
  `assignments`, each `{ id, kind, ref, label, dueAt, done, doneAt }`. `done`/`doneAt`:
  - `lesson`: true iff some `activity` row has `kind === 'lesson_complete' && ref === a.ref`; `doneAt` =
    earliest such `created_at`.
  - `quiz`: true iff some row has `kind === 'quiz_attempt' && ref === a.ref`; `doneAt` = earliest such.
  - `module`: true iff EVERY lesson in `catalog.modules[ref].lessons` has a matching `lesson_complete`
    row; `doneAt` = the latest of those lesson completions (the moment the module became complete).
    A module with zero known lessons (not in catalog) is treated as not done.
  `label` resolves from the catalog (falls back to `ref`).
- `classCompletion(assignments, roster, activity, catalog)` -> for the OWNER view, an array parallel to
  `assignments`, each `{ id, kind, ref, label, dueAt, doneCount, total }` where `total` = roster length
  and `doneCount` = number of roster members whose activity satisfies the assignment (reusing the same
  per-student rule as `studentStatus`, grouping `activity` by `student_id`).
- `dueLabel(dueAt, now)` -> a small display helper: `null` when `dueAt` is null; otherwise
  `{ text, overdue }` where `text` is a short date (e.g. "due Jul 12") and `overdue` is `dueAt < now`
  (the DOM layer only styles overdue on incomplete rows). Kept pure and date-only; the caller decides
  styling.

### 3. `web/assignments.test.mjs` (new, `node --test`, added to `test:web` in `package.json`)

Covers: catalog build from a small lessons/quiz fixture (module/lesson/quiz shapes, humanized quiz
label, empty inputs); `studentStatus` for each kind incl. module all-lessons-done boundary (one lesson
missing => module not done) and `doneAt` selection; `classCompletion` counts across a multi-student
roster incl. a member with no activity; `dueLabel` null / future / overdue. `web-lint.yml` runs
`npm run test:web`.

### 4. `web/accounts.js` (data layer — thin methods)

- `classAssignments(classId)` -> `c.from("assignments").select("id,kind,ref,due_at,created_at").eq("class_id", classId).order("created_at", { ascending: false })`; returns `[]` on error. (Owner reads via owner RLS.)
- `createAssignment(classId, kind, ref, dueAt)` -> `c.from("assignments").upsert({ class_id, kind, ref, due_at: dueAt || null }, { onConflict: "class_id,kind,ref" })`. Owner-write RLS. `dueAt` is an ISO string or null.
- `deleteAssignment(id)` -> `c.from("assignments").delete().eq("id", id)`. Owner-delete RLS.
- `myAssignments()` (learner) -> `c.from("assignments").select("id,class_id,kind,ref,due_at,created_at")` (no `.eq`; RLS `assignments_enrolled_read` returns exactly the caller's enrolled classes' rows), newest first; returns `[]` on error / signed-out.
- `myActivityRefs()` (learner) -> `c.from("activity").select("kind,ref,created_at").eq("student_id", <self>)` with no row cap (RLS `activity_self_all` scopes to the caller); returns `[]` on error / signed-out. Feeds `studentStatus` so completion is correct regardless of activity history size.

All follow the existing `accounts.js` promise style and are exported on `window.Accounts`.

### 5. DOM layers

**Owner — `web/account.js`, inside `classCard`.** A new "Assignments" sub-section under the existing
roster/insight table. `classCard` already `Promise.all([roster, classActivity, curriculumTotals])` for
B; add `classAssignments(cl.id)` and the shared `catalog` (built once per account-page load from the
lessons/quiz fetches B already does). Render:
  - an **add form**: a `kind` select (Lesson / Quiz topic / Module); an item `<select>` populated from
    `catalog` for the chosen kind; an optional date input; an "Assign" button calling `createAssignment`
    then reloading the card. (The item select repopulates when the kind changes.)
  - a **list** of current assignments, each: label, kind, due (via `dueLabel`), `X/N done` from
    `classCompletion`, and a "Remove" button calling `deleteAssignment`. Empty state: "No assignments
    yet."
Flat/clinical styling consistent with the page (no emoji, no gradients, 2px corners); the "X/N done"
and any overdue marker are flat solid accents, reusing the `.chip` rule B added.

**Learner — `web/account.js`, "Assigned to you" panel.** In the student area (near where enrolled
classes render), a panel built from `Promise.all([myAssignments(), <the student's own activity>])` and
the shared `catalog`, passed through `Assignments.studentStatus`. Each row: a done checkbox glyph
(derived, read-only), the label, due (via `dueLabel`, overdue muted on incomplete rows), and an "open"
link. Open targets use the existing deep-links:
  - lesson -> `simulator.html?lesson=<title>` (parsed by app.js, which loads on simulator.html),
  - quiz -> `quiz.html?topic=<id>` (parsed by quiz.js, which loads on quiz.html),
  - module -> `course.html` (opens the course; module context is the whole page).
The student's own activity: the existing `Accounts.myActivity()` caps at the 50 most recent rows, which
could drop an older completion and read as "not done" for a very active student. To keep completion
correct regardless of history size, add a narrow learner read `myActivityRefs()` ->
`c.from("activity").select("kind,ref,created_at").eq("student_id", <self>)` with **no 50-row cap** (RLS
`activity_self_all` scopes it to the caller), returning `[]` on error; the panel derives done from that.
Empty state: "No assignments yet." Panel hidden when the student has no enrolled classes / no
assignments.

**Learner — `web/course.js`, inline badges.** Fetch `Accounts.myAssignments()` once during course load
(best-effort; `[]` when off/signed-out so the page is unchanged without a backend). Build a lookup by
`(kind, ref)`. During the existing render, add a small flat "ASSIGNED" badge (+ `dueLabel` text) to:
  - a module header when a `module` assignment matches its title,
  - a lesson sub-section when a `lesson` assignment matches its title,
  - a quiz sub-section when a `quiz` assignment matches its topic id.
Read-only and additive: no change to course progress, mastery, or exam logic. When there are no
assignments (or no backend), nothing renders and course.js behaves exactly as today.

## Module completion

A `module` assignment is complete for a student when **every lesson in that module** (per the current
`catalog.modules[ref].lessons`, sourced from the shared `lessons.json` `.curriculum`) has a matching
`lesson_complete` activity row. Quiz topics are **not** folded into module completion: the module->quiz
mapping lives only in course.js's `TOPIC_CFG`, not the shared curriculum, and a topic can belong to
more than one module (e.g. `image-quality` -> modules 5 and 6), which would make module completion
ambiguous and pull course.js-only config into shared logic. Lessons belong to exactly one module in the
shared curriculum, giving module completion a single, unambiguous source. Quiz topics remain
independently assignable on their own.

## Data flow

```
Owner picks kind+item+due  ->  Accounts.createAssignment  ->  assignments (owner RLS)
                                                                     |
Enrolled student loads   ->  Accounts.myAssignments  <---- assignments_enrolled_read (RLS)
account.html / course.html         + Accounts.myActivityRefs (own activity rows, uncapped)
                                          |
                           Assignments.studentStatus(assignments, activity, catalog)
                                          |
                            account panel checklist + course.js inline badges

Owner loads classCard    ->  classAssignments + roster + classActivity
                                          |
                           Assignments.classCompletion(...)  ->  "X/N done" per assignment
```

## Error handling

Every new read returns `[]` (or resolves) on error or signed-out, matching the best-effort posture of
the rest of `accounts.js` — an assignments failure never blocks the roster, the class insight, or the
course page. `createAssignment`/`deleteAssignment` surface their promise so the owner UI can reflect
success/failure and reload; a failure leaves the existing list intact. The pure module tolerates
missing catalog entries (unknown ref -> label falls back to ref; unknown module -> not done).

## Testing & guards

- `npm run test:web` (adds `web/assignments.test.mjs`) — pure-logic unit tests, run in CI by
  `web-lint.yml`.
- `npm run lint` (eslint `web/`) stays clean; `assignments.js` follows the UMD/ES5-ish style of
  `class_insight.js` / `join_link.js`.
- **RLS verification** (as sub-project A did for roster): confirm with the Supabase MCP that (a) an
  enrolled student can `select` their class's assignments but cannot `insert`/`delete`; (b) a
  non-enrolled user sees none; (c) the owner has full CRUD on their own class only.
- Existing Python guards (`ruff` on `src/` and `tests/`, pytest) are unaffected (no Python touched) but
  still run before merge per repo convention.
- Manual/Playwright smoke: owner creates and removes an assignment; the enrolled student sees it in the
  account panel and as an inline course badge; a signed-out visitor's course page is unchanged.

## Edge cases

- **Re-assigning the same item:** the `(class_id, kind, ref)` unique index + `upsert` updates the due
  date rather than duplicating. Removing an assignment deletes the row; completion is derived, so no
  orphaned completion state.
- **Module with a renamed/removed lesson:** module completion uses the current `catalog` lessons; if the
  curriculum changes, completion reflects the current module definition (acceptable — the catalog is the
  live source).
- **Multi-class student:** `myAssignments()` returns rows across all the student's enrolled classes (RLS
  scopes to their enrollments); the account panel groups/labels by class. Activity attribution quirks
  (B's note: `logActivity` stamps the student's first enrollment) do not affect completion here, because
  completion matches on `kind`+`ref` from the student's OWN activity, independent of `class_id`.
- **No due date:** allowed; `dueLabel` returns null and the row shows no due text, never "overdue".
- **Signed-out / no backend:** every surface degrades to its current behavior (`[]` reads); the course
  page and account page render exactly as today.

## Out of scope

- **Per-student assignments** (assignment carries only `class_id`, never `student_id`) — whole-class
  only; individual targeting is a much larger feature, deferred.
- **Enforcement / locking / grading** — overdue is visual only; nothing is blocked, and no grade is
  recorded (consistent with the formative-only framing).
- **Assigning premium-only items** (mock exam, reference entries, individual premium education pieces) —
  no `activity` completion signal exists for them; not assignable in this iteration.
- **Notifications / email reminders** for due dates — deferred.
- **Ordering / weighting / sub-tasks** within an assignment — a flat list is the MVP.
