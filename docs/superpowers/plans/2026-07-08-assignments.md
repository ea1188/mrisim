# Assignments (owner sub-project C) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a class owner assign a lesson, quiz topic, or whole module (optional due date) to their class, surfaced to enrolled students on the account page and inline in the course page, with completion derived from the existing `activity` table.

**Architecture:** A new `assignments` table with owner-write / enrolled-read RLS (reusing the existing `is_class_owner`/`is_enrolled` helpers). A new pure UMD module `web/assignments.js` (mirroring `web/class_insight.js`) holds all catalog-building and completion logic, unit-tested with `node --test`. Thin `web/accounts.js` data methods wrap the Supabase reads/writes, and DOM layers in `web/account.js` (owner form + learner panel) and `web/course.js` (inline badges) render over the pure module. Completion is derived, never stored.

**Tech Stack:** Postgres/Supabase (RLS), vanilla ES5-style browser JS (UMD, no build step), `node --test` for pure logic, ESLint, Supabase MCP for applying the migration and RLS verification.

**Spec:** `docs/superpowers/specs/2026-07-08-assignments-design.md`

## Global Constraints

- Never add `Co-Authored-By: Claude` trailers to commits (repo rule).
- UI is professional/clinical: no emoji, no gradients, 2px corners, flat solid accents. (Note: `course.js` already uses `✓`/`▶` glyphs — matching that file's existing style is fine; do not introduce emoji.)
- No AI-tell punctuation (no em dashes) in any user-facing copy.
- `web/assignments.js` is UMD, no DOM, no network — same shape as `web/class_insight.js`: `window.Assignments` in the browser, `module.exports` under Node.
- Every new network read returns `[]` (or resolves) on error / signed-out — best-effort, never blocks a page (matches `accounts.js`).
- Completion is DERIVED from `activity`, never stored in `assignments`.
- Assignments target the whole class only (`class_id`, never `student_id`). Overdue is visual only (no locking/grading).
- Module completion = all its lessons done (quiz topics are NOT folded into module completion).
- Run `ruff` on `src/` AND `tests/`, plus `npm run test:web` and `npm run lint`, before merge.
- Assignable refs match activity refs exactly: lesson ref = lesson title (`lessons.json` `.curriculum[].lessons[]`), quiz ref = topic id (`quiz.json` `.categories[].id`), module ref = module title (`.curriculum[].title`).

---

### Task 1: Migration `0007_assignments.sql` + RLS verification

**Files:**
- Create: `supabase/migrations/0007_assignments.sql`

**Interfaces:**
- Consumes: existing SECURITY DEFINER helpers `is_class_owner(uuid)`, `is_enrolled(uuid)` and table `classes(id)` from migration 0001.
- Produces: table `assignments(id uuid, class_id uuid, kind text, ref text, due_at timestamptz, created_at timestamptz)` with RLS policies `assignments_owner_all` (owner full CRUD) and `assignments_enrolled_read` (enrolled read). Later tasks (`accounts.js`) read/write it.

- [ ] **Step 1: Write the migration file**

Create `supabase/migrations/0007_assignments.sql`:

```sql
-- Owner-assigned work for a class: a lesson, a quiz topic, or a whole curriculum
-- module, with an optional due date. Completion is NOT stored here; it is derived
-- client-side from the existing `activity` table (see docs/superpowers/specs/2026-07-08-assignments-design.md).
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

- [ ] **Step 2: Apply the migration to the live project**

Use the Supabase MCP tool `mcp__plugin_supabase_supabase__apply_migration` with `project_id: idgyjmamxxyddjuaamit`, `name: "0007_assignments"`, and the SQL body above.
Expected: success (no error). If it reports the table already exists, stop and report — do not silently continue.

- [ ] **Step 3: Verify the table + policies exist**

Run via `mcp__plugin_supabase_supabase__execute_sql` (`project_id: idgyjmamxxyddjuaamit`):

```sql
select policyname, cmd from pg_policies where tablename = 'assignments' order by policyname;
```
Expected: two rows — `assignments_enrolled_read` (SELECT) and `assignments_owner_all` (ALL).

- [ ] **Step 4: RLS smoke (policies present, RLS enabled)**

This is a read-only sanity check that the policies exist and RLS is on (full role-based verification is done manually/Playwright before merge, per the spec). Run:

```sql
select
  (select count(*) from pg_policies where tablename='assignments' and cmd='ALL')    as owner_all,
  (select count(*) from pg_policies where tablename='assignments' and cmd='SELECT') as enrolled_read,
  (select relrowsecurity from pg_class where relname='assignments')                 as rls_enabled;
```
Expected: `owner_all=1`, `enrolled_read=1`, `rls_enabled=true`.

- [ ] **Step 5: Commit**

```bash
git add supabase/migrations/0007_assignments.sql
git commit -m "feat(assignments): 0007 migration — assignments table + owner/enrolled RLS"
```

---

### Task 2: Pure `web/assignments.js` module + unit tests

**Files:**
- Create: `web/assignments.js`
- Create: `web/assignments.test.mjs`
- Modify: `package.json` (append the test file to the `test:web` script)

**Interfaces:**
- Consumes: nothing (pure). Test fixtures only.
- Produces (used by Tasks 4, 5, 6):
  - `catalog(lessonsData, quizData)` -> `{ modules: [{ ref, label, lessons: [<title>] }], lessons: [{ ref, label, module }], quizzes: [{ ref, label }] }`
  - `studentStatus(assignments, activity, catalog)` -> array parallel to `assignments`, each `{ id, kind, ref, label, dueAt, done, doneAt }`
  - `classCompletion(assignments, roster, activity, catalog)` -> array, each `{ id, kind, ref, label, dueAt, doneCount, total }`
  - `dueLabel(dueAt, now)` -> `null` or `{ text, overdue }`
  - Input row shapes: assignment `{ id, kind, ref, due_at }`; activity `{ student_id, kind, ref, created_at }` where kind is `"lesson_complete"` or `"quiz_attempt"`; roster `{ student_id }`.

- [ ] **Step 1: Write the failing test**

Create `web/assignments.test.mjs`:

```js
import { test } from "node:test";
import assert from "node:assert/strict";
import A from "./assignments.js";

const lessonsData = {
  curriculum: [
    { title: "1 · Basics", lessons: ["What is MRI", "T1 vs T2"] },
    { title: "2 · Safety", lessons: ["Zones", "Screening"] },
  ],
};
const quizData = { categories: [{ id: "safety" }, { id: "image-quality", name: "Image Quality" }] };

test("catalog builds modules, lessons (with owning module), and humanized quiz labels", () => {
  const cat = A.catalog(lessonsData, quizData);
  assert.equal(cat.modules.length, 2);
  assert.deepEqual(cat.modules[0].lessons, ["What is MRI", "T1 vs T2"]);
  assert.equal(cat.lessons.length, 4);
  assert.deepEqual(cat.lessons[0], { ref: "What is MRI", label: "What is MRI", module: "1 · Basics" });
  assert.equal(cat.quizzes[0].label, "Safety");            // humanized from id
  assert.equal(cat.quizzes[1].label, "Image Quality");     // explicit name wins
});

test("catalog tolerates empty / missing inputs", () => {
  const cat = A.catalog({}, undefined);
  assert.deepEqual(cat, { modules: [], lessons: [], quizzes: [] });
});

test("studentStatus: lesson done uses earliest matching lesson_complete", () => {
  const cat = A.catalog(lessonsData, quizData);
  const assignments = [{ id: "a1", kind: "lesson", ref: "Zones", due_at: null }];
  const activity = [
    { kind: "lesson_complete", ref: "Zones", created_at: "2026-07-03T00:00:00Z" },
    { kind: "lesson_complete", ref: "Zones", created_at: "2026-07-01T00:00:00Z" },
    { kind: "lesson_complete", ref: "Other", created_at: "2026-07-02T00:00:00Z" },
  ];
  const s = A.studentStatus(assignments, activity, cat)[0];
  assert.equal(s.done, true);
  assert.equal(s.doneAt, "2026-07-01T00:00:00Z");
  assert.equal(s.label, "Zones");
});

test("studentStatus: quiz done on any quiz_attempt for the topic", () => {
  const cat = A.catalog(lessonsData, quizData);
  const s = A.studentStatus(
    [{ id: "a2", kind: "quiz", ref: "safety", due_at: null }],
    [{ kind: "quiz_attempt", ref: "safety", created_at: "2026-07-05T00:00:00Z" }],
    cat
  )[0];
  assert.equal(s.done, true);
  assert.equal(s.doneAt, "2026-07-05T00:00:00Z");
});

test("studentStatus: module done needs ALL its lessons; doneAt is the latest", () => {
  const cat = A.catalog(lessonsData, quizData);
  const asg = [{ id: "a3", kind: "module", ref: "1 · Basics", due_at: null }];
  const partial = A.studentStatus(asg, [
    { kind: "lesson_complete", ref: "What is MRI", created_at: "2026-07-01T00:00:00Z" },
  ], cat)[0];
  assert.equal(partial.done, false);          // "T1 vs T2" not done
  assert.equal(partial.doneAt, null);
  const full = A.studentStatus(asg, [
    { kind: "lesson_complete", ref: "What is MRI", created_at: "2026-07-01T00:00:00Z" },
    { kind: "lesson_complete", ref: "T1 vs T2", created_at: "2026-07-04T00:00:00Z" },
  ], cat)[0];
  assert.equal(full.done, true);
  assert.equal(full.doneAt, "2026-07-04T00:00:00Z");   // latest of the two
});

test("studentStatus: unknown module is not done; unknown ref label falls back to ref", () => {
  const cat = A.catalog(lessonsData, quizData);
  const s = A.studentStatus([{ id: "a4", kind: "module", ref: "9 · Ghost", due_at: null }], [], cat)[0];
  assert.equal(s.done, false);
  assert.equal(s.label, "9 · Ghost");
});

test("classCompletion counts members satisfying each assignment (incl. a member with no activity)", () => {
  const cat = A.catalog(lessonsData, quizData);
  const roster = [{ student_id: "s1" }, { student_id: "s2" }, { student_id: "s3" }];
  const activity = [
    { student_id: "s1", kind: "quiz_attempt", ref: "safety", created_at: "2026-07-01T00:00:00Z" },
    { student_id: "s2", kind: "quiz_attempt", ref: "safety", created_at: "2026-07-02T00:00:00Z" },
    // s3: nothing
  ];
  const c = A.classCompletion([{ id: "a5", kind: "quiz", ref: "safety", due_at: null }], roster, activity, cat)[0];
  assert.equal(c.total, 3);
  assert.equal(c.doneCount, 2);
});

test("dueLabel: null when no due; overdue flag compares to now", () => {
  assert.equal(A.dueLabel(null, "2026-07-08T00:00:00Z"), null);
  const future = A.dueLabel("2026-07-12T23:59:59Z", "2026-07-08T00:00:00Z");
  assert.equal(future.overdue, false);
  assert.ok(/^due /.test(future.text));
  const past = A.dueLabel("2026-07-05T23:59:59Z", "2026-07-08T00:00:00Z");
  assert.equal(past.overdue, true);
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `node --test web/assignments.test.mjs`
Expected: FAIL — cannot find module `./assignments.js` (not created yet).

- [ ] **Step 3: Write the module**

Create `web/assignments.js`:

```js
/*
 * Assignments — pure logic for owner-assigned work (owner sub-project C). UMD like
 * class_insight.js: window.Assignments in the browser, module.exports under Node.
 * Builds the assignable catalog from the shared curriculum + quiz categories, and
 * derives completion from the existing `activity` table. No DOM, no network.
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.Assignments = factory();
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  function humanize(id) {
    return String(id || "").replace(/[-_]+/g, " ")
      .replace(/\b\w/g, function (c) { return c.toUpperCase(); });
  }

  // Assignable catalog, shared by the owner picker and the learner status surfaces.
  function catalog(lessonsData, quizData) {
    var curriculum = (lessonsData && lessonsData.curriculum) || [];
    var modules = [], lessons = [];
    curriculum.forEach(function (m) {
      var mlessons = (m.lessons || []).slice();
      modules.push({ ref: m.title, label: m.title, lessons: mlessons });
      mlessons.forEach(function (t) { lessons.push({ ref: t, label: t, module: m.title }); });
    });
    var cats = (quizData && quizData.categories) || [];
    var quizzes = cats.map(function (c) { return { ref: c.id, label: c.name || humanize(c.id) }; });
    return { modules: modules, lessons: lessons, quizzes: quizzes };
  }

  function _labelOf(cat, kind, ref) {
    var list = kind === "module" ? cat.modules : kind === "quiz" ? cat.quizzes : cat.lessons;
    for (var i = 0; i < (list || []).length; i++) { if (list[i].ref === ref) return list[i].label; }
    return ref;
  }
  function _moduleLessons(cat, ref) {
    var mods = (cat && cat.modules) || [];
    for (var i = 0; i < mods.length; i++) { if (mods[i].ref === ref) return mods[i].lessons || []; }
    return null;   // unknown module
  }

  // Earliest created_at where the student's activity matches (kind, ref); null if never.
  function _firstDone(activity, kind, ref) {
    var at = null;
    (activity || []).forEach(function (a) {
      if (a.kind === kind && a.ref === ref && (at == null || a.created_at < at)) at = a.created_at;
    });
    return at;
  }

  // done/doneAt for ONE assignment against ONE student's activity.
  function _statusOne(a, activity, cat) {
    if (a.kind === "lesson") {
      var l = _firstDone(activity, "lesson_complete", a.ref);
      return { done: l != null, doneAt: l };
    }
    if (a.kind === "quiz") {
      var q = _firstDone(activity, "quiz_attempt", a.ref);
      return { done: q != null, doneAt: q };
    }
    var lessons = _moduleLessons(cat, a.ref);      // module
    if (!lessons || !lessons.length) return { done: false, doneAt: null };
    var latest = null;
    for (var i = 0; i < lessons.length; i++) {
      var d = _firstDone(activity, "lesson_complete", lessons[i]);
      if (d == null) return { done: false, doneAt: null };
      if (latest == null || d > latest) latest = d;
    }
    return { done: true, doneAt: latest };
  }

  function studentStatus(assignments, activity, cat) {
    cat = cat || { modules: [], lessons: [], quizzes: [] };
    return (assignments || []).map(function (a) {
      var s = _statusOne(a, activity, cat);
      return {
        id: a.id, kind: a.kind, ref: a.ref,
        label: _labelOf(cat, a.kind, a.ref),
        dueAt: a.due_at || null,
        done: s.done, doneAt: s.doneAt,
      };
    });
  }

  function classCompletion(assignments, roster, activity, cat) {
    cat = cat || { modules: [], lessons: [], quizzes: [] };
    var byStudent = {};
    (activity || []).forEach(function (a) {
      (byStudent[a.student_id] || (byStudent[a.student_id] = [])).push(a);
    });
    var members = (roster || []).map(function (r) { return r.student_id; });
    return (assignments || []).map(function (a) {
      var doneCount = 0;
      members.forEach(function (sid) {
        if (_statusOne(a, byStudent[sid] || [], cat).done) doneCount++;
      });
      return {
        id: a.id, kind: a.kind, ref: a.ref,
        label: _labelOf(cat, a.kind, a.ref),
        dueAt: a.due_at || null,
        doneCount: doneCount, total: members.length,
      };
    });
  }

  var MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  function dueLabel(dueAt, now) {
    if (!dueAt) return null;
    var d = new Date(dueAt);
    if (isNaN(d.getTime())) return null;
    var n = now ? new Date(now) : new Date();
    return { text: "due " + MON[d.getMonth()] + " " + d.getDate(), overdue: d.getTime() < n.getTime() };
  }

  return {
    catalog: catalog, studentStatus: studentStatus,
    classCompletion: classCompletion, dueLabel: dueLabel,
  };
});
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `node --test web/assignments.test.mjs`
Expected: PASS — all 8 tests.

- [ ] **Step 5: Wire the test into CI and lint**

In `package.json`, append ` web/assignments.test.mjs` to the end of the `test:web` script value (which currently ends with `web/class_insight.test.mjs`), so it reads:

```json
    "test:web": "node --test web/course_logic.test.mjs web/auth_url.test.mjs web/join_link.test.mjs web/class_insight.test.mjs web/assignments.test.mjs"
```

Run: `npm run test:web` (expect all suites pass) and `npm run lint` (expect clean; `assignments.js` follows the ES5/UMD style ESLint already accepts for `class_insight.js`).

- [ ] **Step 6: Commit**

```bash
git add web/assignments.js web/assignments.test.mjs package.json
git commit -m "feat(assignments): pure catalog + completion module with node --test"
```

---

### Task 3: `web/accounts.js` data methods

**Files:**
- Modify: `web/accounts.js` (add methods after `classActivity` near line 242, and add them to the `window.Accounts` export block near line 286)

**Interfaces:**
- Consumes: the `client()` promise, `ENABLED`, and `signedIn()` already in `accounts.js`; the `assignments` table + RLS from Task 1.
- Produces (used by Tasks 4, 5): on `window.Accounts` —
  - `classAssignments(classId)` -> Promise<array of `{ id, kind, ref, due_at, created_at }`> (owner read; `[]` on error)
  - `createAssignment(classId, kind, ref, dueAt)` -> Promise resolving the supabase `{ data, error }` (owner upsert)
  - `deleteAssignment(id)` -> Promise resolving `{ data, error }` (owner delete)
  - `myAssignments()` -> Promise<array of `{ id, class_id, kind, ref, due_at, created_at }`> (enrolled read; `[]` on error/signed-out)
  - `myActivityRefs()` -> Promise<array of `{ kind, ref, created_at }`> (own activity, uncapped; `[]` on error/signed-out)

- [ ] **Step 1: Add the methods**

In `web/accounts.js`, immediately after the `classActivity` function (ends near line 242, before the `// --- paid course` comment), add:

```js
  // --- assignments (owner sub-project C) ----------------------------------- //
  // Owner: assignments for a class you own (owner RLS scopes to your classes).
  function classAssignments(classId) {
    return client().then(function (c) {
      return c.from("assignments").select("id,kind,ref,due_at,created_at")
        .eq("class_id", classId).order("created_at", { ascending: false });
    }).then(function (r) { return r.data || []; }).catch(function () { return []; });
  }
  // Owner: create or re-date an assignment. Upsert on (class_id, kind, ref) so
  // re-assigning the same item updates its due date instead of duplicating.
  function createAssignment(classId, kind, ref, dueAt) {
    return client().then(function (c) {
      return c.from("assignments").upsert(
        { class_id: classId, kind: kind, ref: String(ref), due_at: dueAt || null },
        { onConflict: "class_id,kind,ref" });
    });
  }
  // Owner: remove an assignment you own (owner RLS).
  function deleteAssignment(id) {
    return client().then(function (c) { return c.from("assignments").delete().eq("id", id); });
  }
  // Learner: assignments across every class you're enrolled in (enrolled-read RLS
  // returns exactly those). Best-effort; [] when off / signed out / on error.
  function myAssignments() {
    if (!ENABLED || !signedIn()) return Promise.resolve([]);
    return client().then(function (c) {
      return c.from("assignments").select("id,class_id,kind,ref,due_at,created_at")
        .order("created_at", { ascending: false });
    }).then(function (r) { return r.data || []; }).catch(function () { return []; });
  }
  // Learner: your OWN activity refs, uncapped (RLS scopes to you), for deriving
  // assignment completion regardless of history size. Best-effort; [] otherwise.
  function myActivityRefs() {
    if (!ENABLED || !signedIn()) return Promise.resolve([]);
    return client().then(function (c) {
      return c.auth.getUser().then(function (r) {
        var u = r.data.user;
        if (!u) return [];
        return c.from("activity").select("kind,ref,created_at").eq("student_id", u.id)
          .then(function (res) { return res.data || []; });
      });
    }).catch(function () { return []; });
  }
```

- [ ] **Step 2: Export the methods**

In the `window.Accounts = { ... }` object (near line 286), add to the list (e.g. right after the `roster: roster, classActivity: classActivity,` line):

```js
    classAssignments: classAssignments, createAssignment: createAssignment,
    deleteAssignment: deleteAssignment, myAssignments: myAssignments, myActivityRefs: myActivityRefs,
```

- [ ] **Step 3: Verify syntax + lint**

Run: `node -e "global.window={};require('./web/accounts.js');console.log(Object.keys(window.Accounts).filter(k=>/[Aa]ssign|ActivityRefs/.test(k)))"`
Expected: prints `[ 'classAssignments', 'createAssignment', 'deleteAssignment', 'myAssignments', 'myActivityRefs' ]` (the IIFE runs under Node; `client()` is never called, so no supabase import).
Run: `npm run lint`
Expected: clean.

- [ ] **Step 4: Commit**

```bash
git add web/accounts.js
git commit -m "feat(assignments): accounts.js data methods (owner CRUD + learner reads)"
```

---

### Task 4: Owner assignments UI in `web/account.js` (+ `account.html` wiring)

**Files:**
- Modify: `web/account.html` (add `<script src="assignments.js"></script>` before `account.js`; add a minimal `.assign-form` CSS rule)
- Modify: `web/account.js` (add `Assignments` ref; add shared `assignableCatalog()` helper; add `KIND_LABEL` + `assignmentsSection(...)`; extend `classCard`)

**Interfaces:**
- Consumes: `window.Assignments` (Task 2: `catalog`, `classCompletion`, `dueLabel`); `Accounts.classAssignments/createAssignment/deleteAssignment` (Task 3); the existing `h`, `clear`, `th`, `td`, `tdNum`, `card` helpers in `account.js`.
- Produces: `assignableCatalog()` (a cached `Promise<catalog>`) and `KIND_LABEL` reused by Task 5.

- [ ] **Step 1: Load `assignments.js` on the account page**

In `web/account.html`, find the line loading `class_insight.js` (added in sub-project B) and add, immediately after it and before the `account.js` script:

```html
    <script src="assignments.js"></script>
```

- [ ] **Step 2: Add a minimal form-layout CSS rule**

In `web/account.html`'s existing `<style>` block, near the `.chip` rule sub-project B added, add:

```css
    .assign-form { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin: 8px 0; }
    .assign-form select, .assign-form input { padding: 4px 6px; }
```

- [ ] **Step 3: Reference `Assignments` and add the shared catalog helper**

In `web/account.js`, after the `var ClassInsight = window.ClassInsight;` line (line 12), add:

```js
  var Assignments = window.Assignments;   // pure assignment catalog + completion (assignments.js)
```

Then, immediately after the `curriculumTotals()` function (ends near line 93), add:

```js
  // The assignable catalog ({ modules, lessons, quizzes }) from the same lessons.json
  // and quiz.json the learner loads. Fetched once per page (cached), best-effort — an
  // empty catalog just yields empty pickers.
  var catalogPromise = null;
  function assignableCatalog() {
    if (!catalogPromise) {
      var lessons = fetch("lessons.json").then(function (r) { return r.json(); }).catch(function () { return {}; });
      var quiz = fetch("quiz.json").then(function (r) { return r.json(); }).catch(function () { return {}; });
      catalogPromise = Promise.all([lessons, quiz]).then(function (v) { return Assignments.catalog(v[0], v[1]); });
    }
    return catalogPromise;
  }
```

- [ ] **Step 4: Add `KIND_LABEL` and the owner assignments section builder**

In `web/account.js`, immediately before `function classCard(` (line 113), add:

```js
  var KIND_LABEL = { lesson: "Lesson", quiz: "Quiz topic", module: "Module" };

  // Owner: the "Assignments" block for one class — an add form + a list with X/N done.
  function assignmentsSection(cl, roster, acts, cat, assignments, reload) {
    var box = h("div", { class: "assign" }, [h("h3", { text: "Assignments" })]);

    var kindSel = h("select", {}, [
      h("option", { value: "lesson" }, ["Lesson"]),
      h("option", { value: "quiz" }, ["Quiz topic"]),
      h("option", { value: "module" }, ["Module"]),
    ]);
    var itemSel = h("select");
    function fillItems() {
      clear(itemSel);
      var list = kindSel.value === "module" ? cat.modules : kindSel.value === "quiz" ? cat.quizzes : cat.lessons;
      (list || []).forEach(function (it) { itemSel.appendChild(h("option", { value: it.ref }, [it.label])); });
    }
    kindSel.addEventListener("change", fillItems);
    fillItems();
    var dueIn = h("input", { type: "date" });
    var amsg = h("div", { class: "msg" });
    var add = h("button", { class: "ghost", text: "Assign", onclick: function () {
      if (!itemSel.value) return;
      add.disabled = true; amsg.className = "msg"; amsg.textContent = "";
      var dueAt = dueIn.value ? new Date(dueIn.value + "T23:59:59").toISOString() : null;
      Accounts.createAssignment(cl.id, kindSel.value, itemSel.value, dueAt).then(function (res) {
        add.disabled = false;
        if (res && res.error) { amsg.className = "msg err"; amsg.textContent = res.error.message; return; }
        reload();
      }).catch(function () { add.disabled = false; });
    } });
    box.appendChild(h("div", { class: "assign-form" }, [kindSel, itemSel, dueIn, add]));
    box.appendChild(amsg);

    var comp = Assignments.classCompletion(assignments, roster, acts, cat);
    if (!comp.length) { box.appendChild(h("p", { class: "muted", text: "No assignments yet." })); return box; }
    var tbl = h("table", {}, [h("thead", {}, [h("tr", {}, [
      th("Assigned"), th("Type"), th("Due"), th("Done"), th(""),
    ])])]);
    var tb = h("tbody");
    comp.forEach(function (a) {
      var due = Assignments.dueLabel(a.dueAt);
      var dueCell = h("td", {}, [document.createTextNode(due ? due.text : "—")]);
      if (due && due.overdue) dueCell.appendChild(h("span", { class: "chip", text: "overdue" }));
      var rm = h("button", { class: "ghost", text: "Remove", onclick: function () {
        rm.disabled = true;
        Accounts.deleteAssignment(a.id).then(function (res) {
          if (res && res.error) { rm.disabled = false; return; }
          reload();
        }).catch(function () { rm.disabled = false; });
      } });
      tb.appendChild(h("tr", {}, [
        td(a.label), td(KIND_LABEL[a.kind] || a.kind), dueCell,
        tdNum(a.doneCount + "/" + a.total), h("td", {}, [rm]),
      ]));
    });
    tbl.appendChild(tb);
    box.appendChild(tbl);
    return box;
  }
```

- [ ] **Step 5: Fetch assignments + catalog in `classCard` and render the section**

In `web/account.js` `classCard`, change the `Promise.all([...])` at line 158 to also fetch assignments + catalog, and render the section. Within the `.then(function (res) {` callback (lines 158-218):

1. Change the `Promise.all` array to:
```js
    Promise.all([Accounts.roster(cl.id), Accounts.classActivity(cl.id), curriculumTotals(),
      Accounts.classAssignments(cl.id), assignableCatalog()]).then(function (res) {
```
2. After `var roster = res[0], acts = res[1], totals = res[2];` add:
```js
      var assignments = res[3], cat = res[4];
```
3. Replace the empty-roster early return line:
```js
      if (!roster.length) { body.appendChild(h("p", { class: "muted", text: "No members yet. Share the join code above." })); return; }
```
with:
```js
      if (!roster.length) {
        body.appendChild(h("p", { class: "muted", text: "No members yet. Share the join code above." }));
        body.appendChild(assignmentsSection(cl, roster, acts, cat, assignments, reload));
        return;
      }
```
4. At the very end of the callback (after the existing "Download CSV" button `body.appendChild(...)` closes, just before the callback's closing `});`), add:
```js
      body.appendChild(assignmentsSection(cl, roster, acts, cat, assignments, reload));
```

Leave the rest of `classCard` (insight table, class-summary line, CSV button) unchanged.

- [ ] **Step 6: Verify lint + manual smoke**

Run: `npm run lint`
Expected: clean.
Manual smoke (describe for the reviewer; run if a configured backend is available): sign in as a class owner, open a class card, pick Lesson/Quiz/Module + optional due, click Assign; the assignment appears with `0/N done` and (if past) an "overdue" chip; Remove deletes it. With zero members the form still renders.

- [ ] **Step 7: Commit**

```bash
git add web/account.html web/account.js
git commit -m "feat(assignments): owner assign form + completion list in classCard"
```

---

### Task 5: Learner "Assigned to you" panel in `web/account.js`

**Files:**
- Modify: `web/account.js` (`signedInView`: add `loadAssigned()` + a card + boot call)

**Interfaces:**
- Consumes: `Assignments.studentStatus` + `dueLabel` (Task 2); `Accounts.myAssignments` + `myActivityRefs` (Task 3); `assignableCatalog()` + `KIND_LABEL` (Task 4); the `.chip` CSS (sub-project B).
- Produces: nothing consumed downstream.

- [ ] **Step 1: Add the `assigned` panel node**

In `web/account.js` `signedInView`, change the `var teachList = h("div"), joinedList = h("div"), recent = h("div");` line (line 226) to also declare `assigned`:

```js
    var teachList = h("div"), joinedList = h("div"), assigned = h("div"), recent = h("div");
```

- [ ] **Step 2: Add the learner panel loader**

In `signedInView`, immediately before the `wrap.appendChild(card([` block that renders "Classes you teach" (line 301), add:

```js
    // -- work assigned to you (across the classes you've joined) --
    function loadAssigned() {
      clear(assigned); assigned.appendChild(h("p", { class: "muted", text: "Loading…" }));
      Promise.all([Accounts.myAssignments(), Accounts.myActivityRefs(), assignableCatalog()]).then(function (res) {
        clear(assigned);
        var rows = Assignments.studentStatus(res[0], res[1], res[2]);
        assigned.appendChild(h("h2", { text: "Assigned to you" }));
        if (!rows.length) {
          assigned.appendChild(h("p", { class: "muted", text: "No assignments yet. When a class you've joined assigns work, it shows up here." }));
          return;
        }
        var tbl = h("table", {}, [h("thead", {}, [h("tr", {}, [
          th("Done"), th("Assigned"), th("Type"), th("Due"), th(""),
        ])])]);
        var tb = h("tbody");
        rows.forEach(function (a) {
          var due = Assignments.dueLabel(a.dueAt);
          var dueCell = h("td", {}, [document.createTextNode(due ? due.text : "—")]);
          if (due && due.overdue && !a.done) dueCell.appendChild(h("span", { class: "chip", text: "overdue" }));
          var link = a.kind === "lesson" ? "index.html?lesson=" + encodeURIComponent(a.ref)
            : a.kind === "quiz" ? "course.html?topic=" + encodeURIComponent(a.ref)
              : "course.html";
          var doneCell = h("td", {}, [a.done ? h("span", { class: "chip", text: "done" }) : document.createTextNode("—")]);
          tb.appendChild(h("tr", {}, [
            doneCell, td(a.label), td(KIND_LABEL[a.kind] || a.kind), dueCell,
            h("td", {}, [h("a", { class: "linkout", href: link, text: "open" })]),
          ]));
        });
        tbl.appendChild(tb); assigned.appendChild(tbl);
      });
    }
```

- [ ] **Step 3: Mount the panel and call the loader**

After the `wrap.appendChild(card([ ... joinedList ]));` block (ends line 312) and before `wrap.appendChild(card([recent]));` (line 313), add:

```js
    wrap.appendChild(card([assigned]));
```

Then, on the final boot line `loadTeach(); loadJoined(); loadRecent();` (line 315), add `loadAssigned();`:

```js
    loadTeach(); loadJoined(); loadAssigned(); loadRecent();
```

- [ ] **Step 4: Verify lint + manual smoke**

Run: `npm run lint`
Expected: clean.
Manual smoke: as a student enrolled in a class that has assignments, the "Assigned to you" panel lists each item with a "done" chip when the student's activity satisfies it, the due date (with "overdue" chip when past and not done), and an "open" link. A student with no assignments sees the empty state.

- [ ] **Step 5: Commit**

```bash
git add web/account.js
git commit -m "feat(assignments): learner 'Assigned to you' panel on account page"
```

---

### Task 6: Inline "ASSIGNED" badges in `web/course.js` (+ `course.html` wiring)

**Files:**
- Modify: `web/course.html` (add `<script src="assignments.js"></script>` before `course.js`; add a minimal `.abadge` CSS rule)
- Modify: `web/course.js` (fetch `myAssignments` in `loadCourse`; store a lookup on `CTX`; add `assignIndex` + `assignBadge`; inject at the module header, lesson cards, and the topic-quiz link)

**Interfaces:**
- Consumes: `window.Assignments.dueLabel` (Task 2); `Accounts.myAssignments` (Task 3). `TOPIC_CFG[mod.title].quiz` gives a module's assignable quiz topic ids.
- Produces: nothing consumed downstream.

- [ ] **Step 1: Load `assignments.js` on the course page + add badge CSS**

In `web/course.html`, add before the `course.js` script:

```html
    <script src="assignments.js"></script>
```

In `web/course.html`'s `<style>` block, add (reuse the accent token names the page's existing buttons/links use; if the page has no `--accent`, match the exact color the existing primary button uses rather than inventing a hue):

```css
    .abadge { display: inline-block; margin-left: 8px; padding: 1px 6px; border-radius: 2px;
      background: var(--accent, #1f6feb); color: var(--accent-ink, #fff); font-size: 11px;
      text-transform: uppercase; letter-spacing: 0.04em; vertical-align: middle; }
    .abadge .due { text-transform: none; letter-spacing: 0; opacity: 0.85; margin-left: 4px; }
```

- [ ] **Step 2: Fetch assignments in `loadCourse` and pass to `courseView`**

In `web/course.js`, replace the body of `loadCourse` (lines 1175-1189) with:

```js
  function loadCourse() {
    return Promise.all([
      fetch("lessons.json").then(function (r) { return r.json(); }),
      Accounts.premiumContent(COURSE),
      Accounts.myAssignments ? Accounts.myAssignments() : Promise.resolve([]),
    ]).then(function (res) {
      var data = res[0], premium = res[1], assignments = res[2];
      var byTitle = {}; (data.lessons || []).forEach(function (L) { byTitle[L.title] = L; });
      var byTopic = {}; (premium || []).forEach(function (it) {
        (byTopic[it.topic] = byTopic[it.topic] || []).push(it);
      });
      return bootSync().then(function () {
        courseView(data.curriculum || [], byTitle, byTopic, assignments);
      });
    });
  }
```

- [ ] **Step 3: Store the assignment lookup on `CTX` in `courseView`**

In `web/course.js` `courseView` (line 140), add an `assignments` parameter and set `assign` on `CTX`. Change the signature line and the `CTX = {...}` object head:

```js
  function courseView(curriculum, lessonsByTitle, premiumByTopic, assignments) {
    var wrap = h("div", { class: "course" });
    var rail = h("div", { class: "rail" });
    var main = h("div", { class: "main" });
    CTX = { curriculum: curriculum, byTitle: lessonsByTitle, byTopic: premiumByTopic,
      rail: rail, main: main, mod: curriculum[0],
      assign: assignIndex(assignments),
      expanded: new Set([curriculum[0].title]) };  // which modules are expanded in the TOC
```

(leave the rest of `courseView` unchanged.)

- [ ] **Step 4: Add the `assignIndex` + `assignBadge` helpers**

In `web/course.js`, immediately after the `slug` function (line 154), add:

```js
  // Index the learner's assignments by "kind ref" -> the assignment row, for O(1)
  // badge lookup during render. Best-effort: absent/[] means no badges.
  function assignIndex(assignments) {
    var idx = {};
    (assignments || []).forEach(function (a) { idx[a.kind + " " + a.ref] = a; });
    return idx;
  }
  // A small "ASSIGNED" badge (+ due) if this (kind, ref) is assigned to the learner,
  // else null. Uses the pure dueLabel for the date text.
  function assignBadge(kind, ref) {
    var a = CTX && CTX.assign && CTX.assign[kind + " " + ref];
    if (!a) return null;
    var badge = h("span", { class: "abadge", text: "Assigned" });
    var due = window.Assignments ? window.Assignments.dueLabel(a.due_at) : null;
    if (due) badge.appendChild(h("span", { class: "due", text: due.text }));
    return badge;
  }
```

- [ ] **Step 5: Inject the badge at the module header, lessons, and quiz link**

In `web/course.js` `renderTopic`:

1. **Module header** — replace line 433 (`main.appendChild(h("h2", { text: mod.title }));`) with:
```js
      var modH = h("h2", { text: mod.title });
      var modBadge = assignBadge("module", mod.title);
      if (modBadge) modH.appendChild(modBadge);
      main.appendChild(modH);
```

2. **Lesson cards** — in the `mod.lessons.forEach(function (title) {` block (line 492), change the `.lt` div children (lines 497-500) from:
```js
          h("div", { class: "lt" }, [
            isDone ? h("span", { class: "lk", text: "✓ " }) : document.createTextNode(""),
            document.createTextNode(title),
          ]),
```
to:
```js
          h("div", { class: "lt" }, [
            isDone ? h("span", { class: "lk", text: "✓ " }) : document.createTextNode(""),
            document.createTextNode(title),
            assignBadge("lesson", title) || document.createTextNode(""),
          ]),
```

3. **Quiz topic** — in the `if (cfg.quiz.length) {` block (line 519), after the `var link = h("p", { class: "quiz-foot" }, [ ... ]);` statement (ends line 524) and before `main.appendChild(link);` (line 525), add:
```js
      cfg.quiz.forEach(function (topic) {
        var qb = assignBadge("quiz", topic);
        if (qb) link.appendChild(qb);
      });
```

- [ ] **Step 6: Verify lint + manual smoke**

Run: `npm run lint`
Expected: clean.
Manual smoke: as an entitled student in a class with assignments, open the course page and navigate to an assigned module — the module heading shows an "ASSIGNED" badge (with due date if set), an assigned lesson shows the badge in its row, and an assigned quiz topic shows the badge by the free-quiz link. A signed-out visitor or a course with no assignments renders exactly as before (no badges, `[]` fetch).

- [ ] **Step 7: Commit**

```bash
git add web/course.html web/course.js
git commit -m "feat(assignments): inline ASSIGNED badges on the course page"
```

---

## Notes for the executor

- After all tasks: run the full guard set before opening the PR — `~/Library/Python/3.9/bin/ruff check src/ tests/`, `npm run test:web`, `npm run lint`. (No Python is touched, but the repo convention runs ruff on `src/` AND `tests/` before merge.)
- The migration (Task 1) is applied to the live Supabase project as part of that task; it is not re-applied at merge.
- Do RLS role verification (owner CRUD / enrolled read / non-member none) manually or via Playwright before merge, as sub-project A did — the Task 1 SQL check only confirms the policies exist.
- PR body ends with the standard `🤖 Generated with [Claude Code](https://claude.com/claude-code)` line (PR body only — never a commit trailer).
