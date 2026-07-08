# Cross-Device Progress Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mirror the paid course's seven `localStorage` progress keys to Supabase per signed-in user, merged monotonically so switching devices never loses progress.

**Architecture:** A new `course_progress` table (jsonb `state` per user, RLS self-scoped); `Accounts.loadProgress()`/`saveProgress()` in `accounts.js`; a pure node-tested `mergeProgress(local, remote)` in `course_logic.js`; boot pull-merge-push + debounced push-on-change in `course.js`. All sync best-effort (local-first).

**Tech Stack:** Postgres/RLS (Supabase), vanilla ES5 browser JS, CommonJS pure module, node's test runner.

## Global Constraints

- `course.js` / `course_logic.js` / `accounts.js` are ES5-style: `var`, function expressions, `h(...)` builder. Match the files. The `.mjs` test is standard ESM.
- `course.js` reads `CourseLogic` via the existing `var CourseLogic = window.CourseLogic;` alias and `Accounts` via the declared global. `accounts.js` already defines its helpers on `window.Accounts`. No `eslint.config.mjs` edit (the `config-protection` hook blocks it; no new globals are needed).
- Sync is BEST-EFFORT and LOCAL-FIRST: every Accounts sync call is wrapped so failure/offline/not-signed-in degrades to local-only with no error and no data loss.
- New table `course_progress` only; migration is `supabase/migrations/0005_course_progress.sql`, applied to Supabase (ref idgyjmamxxyddjuaamit) via MCP by the controller (owner approved).
- No em dashes / AI-tell punctuation in learner-facing strings. No `Co-Authored-By: Claude` trailer. `course.js`/`accounts.js` are network-first SHELL (no cache bump).
- The seven keys: `mrisim_curriculum`, `mrisim_course_read_v1`, `mrisim_course_quiz_v1`, `mrisim_course_exam_v1`, `mrisim_course_mastery_v1`, `mrisim_course_diagnostic_v1`, `mrisim_course_review_v1`.

## File structure

- `supabase/migrations/0005_course_progress.sql` — new table + RLS.
- `web/course_logic.js` — add `mergeProgress` (+ internal helpers) to the export.
- `web/course_logic.test.mjs` — merge tests.
- `web/accounts.js` — `loadProgress`/`saveProgress` + export.
- `web/course.js` — `PROGRESS_KEYS`, `readAllProgress`/`writeAllProgress`, `queueSync`/`flushSync`/`bootSync`, page-hide flush, boot merge in `loadCourse`, `queueSync()` in the 7 save helpers.

---

## Task 1: Migration file

**Files:**
- Create: `supabase/migrations/0005_course_progress.sql`

- [ ] **Step 1: Create the migration**

Create `supabase/migrations/0005_course_progress.sql`:

```sql
-- Cross-device course progress: one jsonb state blob per user, self-scoped by RLS.
-- The client merges monotonically, so this is a best-effort mirror of localStorage.
create table course_progress (
  user_id uuid primary key references auth.users on delete cascade,
  state jsonb not null default '{}',
  updated_at timestamptz not null default now()
);

alter table course_progress enable row level security;

create policy course_progress_self_all on course_progress
  for all using (user_id = auth.uid()) with check (user_id = auth.uid());
```

- [ ] **Step 2: Commit**

```bash
git add supabase/migrations/0005_course_progress.sql
git commit -m "feat(course): course_progress table migration (cross-device sync)"
```

Note: the controller applies this migration to Supabase via the MCP `apply_migration` after the code lands. The code degrades to local-only until the table exists, so ordering is not load-bearing.

---

## Task 2: Pure `mergeProgress`

**Files:**
- Modify: `web/course_logic.js`
- Modify: `web/course_logic.test.mjs`

**Interfaces:**
- Produces: `mergeProgress(local, remote) -> merged` — objects keyed by the seven storage keys; merges each key monotonically; one-sided keys pass through.

- [ ] **Step 1: Write the failing tests**

In `web/course_logic.test.mjs`, add `mergeProgress` to the destructure line, then append:

```js
test("mergeProgress unions curriculum + read, keeps higher quiz seen", () => {
  const local = { mrisim_curriculum: ["a", "b"], mrisim_course_read_v1: { x: true }, mrisim_course_quiz_v1: { M: { seen: 5, right: 3 } } };
  const remote = { mrisim_curriculum: ["b", "c"], mrisim_course_read_v1: { y: true }, mrisim_course_quiz_v1: { M: { seen: 8, right: 2 } } };
  const m = mergeProgress(local, remote);
  assert.deepEqual(m.mrisim_curriculum.slice().sort(), ["a", "b", "c"]);
  assert.deepEqual(Object.keys(m.mrisim_course_read_v1).sort(), ["x", "y"]);
  assert.deepEqual(m.mrisim_course_quiz_v1.M, { seen: 8, right: 2 });
});

test("mergeProgress mastery: passed OR, max bestPct/attempts/ts", () => {
  const m = mergeProgress(
    { mrisim_course_mastery_v1: { M: { passed: false, bestPct: 60, attempts: 1, ts: 10 } } },
    { mrisim_course_mastery_v1: { M: { passed: true, bestPct: 90, attempts: 3, ts: 5 } } });
  assert.deepEqual(m.mrisim_course_mastery_v1.M, { passed: true, bestPct: 90, attempts: 3, ts: 10 });
});

test("mergeProgress exam higher bestPct; diagnostic later ts; review later lastSeen", () => {
  const m = mergeProgress(
    { mrisim_course_exam_v1: { bestPct: 70 }, mrisim_course_diagnostic_v1: { ts: 100, order: ["a"] }, mrisim_course_review_v1: { q: { box: 1, lastSeen: 50 } } },
    { mrisim_course_exam_v1: { bestPct: 85 }, mrisim_course_diagnostic_v1: { ts: 200, order: ["b"] }, mrisim_course_review_v1: { q: { box: 0, lastSeen: 80 } } });
  assert.equal(m.mrisim_course_exam_v1.bestPct, 85);
  assert.deepEqual(m.mrisim_course_diagnostic_v1.order, ["b"]);
  assert.deepEqual(m.mrisim_course_review_v1.q, { box: 0, lastSeen: 80 });
});

test("mergeProgress passes through one-sided keys and handles empties", () => {
  assert.deepEqual(mergeProgress({}, {}), {});
  assert.deepEqual(mergeProgress({ mrisim_curriculum: ["a"] }, {}), { mrisim_curriculum: ["a"] });
  assert.deepEqual(mergeProgress({}, { mrisim_course_exam_v1: { bestPct: 50 } }).mrisim_course_exam_v1, { bestPct: 50 });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `node --test web/course_logic.test.mjs`
Expected: FAIL (`mergeProgress` undefined).

- [ ] **Step 3: Implement `mergeProgress` + helpers**

In `web/course_logic.js`, immediately before the `return {` line, add:

```js
  function _num(x) { return typeof x === "number" && !isNaN(x) ? x : 0; }
  function _has(o, k) { return Object.prototype.hasOwnProperty.call(o, k); }
  function _keysUnion(a, b) {
    var keys = {}, k; a = a || {}; b = b || {};
    for (k in a) { if (_has(a, k)) keys[k] = 1; }
    for (k in b) { if (_has(b, k)) keys[k] = 1; }
    return keys;
  }
  function _arrUnion(a, b) {
    var out = (a || []).slice(), seen = {};
    out.forEach(function (x) { seen[x] = 1; });
    (b || []).forEach(function (x) { if (!seen[x]) { seen[x] = 1; out.push(x); } });
    return out;
  }
  function _mapUnion(a, b) {
    var out = {}, k; a = a || {}; b = b || {};
    for (k in a) { if (_has(a, k)) out[k] = a[k]; }
    for (k in b) { if (_has(b, k) && !(k in out)) out[k] = b[k]; }
    return out;
  }
  function _mergeQuiz(a, b) {
    var out = {}, keys = _keysUnion(a, b), k; a = a || {}; b = b || {};
    for (k in keys) {
      var ra = a[k], rb = b[k];
      out[k] = (!rb) ? ra : (!ra) ? rb : (_num(rb.seen) > _num(ra.seen) ? rb : ra);
    }
    return out;
  }
  function _mergeMastery(a, b) {
    var out = {}, keys = _keysUnion(a, b), k; a = a || {}; b = b || {};
    for (k in keys) {
      var ra = a[k] || {}, rb = b[k] || {};
      out[k] = { passed: !!(ra.passed || rb.passed),
        bestPct: Math.max(_num(ra.bestPct), _num(rb.bestPct)),
        attempts: Math.max(_num(ra.attempts), _num(rb.attempts)),
        ts: Math.max(_num(ra.ts), _num(rb.ts)) };
    }
    return out;
  }
  function _mergeReview(a, b) {
    var out = {}, keys = _keysUnion(a, b), k; a = a || {}; b = b || {};
    for (k in keys) {
      var ra = a[k], rb = b[k];
      out[k] = (!rb) ? ra : (!ra) ? rb : (_num(rb.lastSeen) > _num(ra.lastSeen) ? rb : ra);
    }
    return out;
  }
  function _higher(a, b, field) {
    if (!a) return b; if (!b) return a;
    return _num(b[field]) > _num(a[field]) ? b : a;
  }

  // Merge two course-progress states (each keyed by the seven storage keys) so that
  // progress only ever increases. Keys present on one side pass through unchanged.
  function mergeProgress(local, remote) {
    local = local || {}; remote = remote || {};
    var out = {}, k;
    for (k in local) { if (_has(local, k)) out[k] = local[k]; }
    for (k in remote) { if (_has(remote, k) && !(k in out)) out[k] = remote[k]; }
    if ("mrisim_curriculum" in out) out.mrisim_curriculum = _arrUnion(local.mrisim_curriculum, remote.mrisim_curriculum);
    if ("mrisim_course_read_v1" in out) out.mrisim_course_read_v1 = _mapUnion(local.mrisim_course_read_v1, remote.mrisim_course_read_v1);
    if ("mrisim_course_quiz_v1" in out) out.mrisim_course_quiz_v1 = _mergeQuiz(local.mrisim_course_quiz_v1, remote.mrisim_course_quiz_v1);
    if ("mrisim_course_exam_v1" in out) out.mrisim_course_exam_v1 = _higher(local.mrisim_course_exam_v1, remote.mrisim_course_exam_v1, "bestPct");
    if ("mrisim_course_mastery_v1" in out) out.mrisim_course_mastery_v1 = _mergeMastery(local.mrisim_course_mastery_v1, remote.mrisim_course_mastery_v1);
    if ("mrisim_course_diagnostic_v1" in out) out.mrisim_course_diagnostic_v1 = _higher(local.mrisim_course_diagnostic_v1, remote.mrisim_course_diagnostic_v1, "ts");
    if ("mrisim_course_review_v1" in out) out.mrisim_course_review_v1 = _mergeReview(local.mrisim_course_review_v1, remote.mrisim_course_review_v1);
    return out;
  }
```

Then add `mergeProgress: mergeProgress,` to the returned export object (after `dueCount: dueCount,`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `node --test web/course_logic.test.mjs`
Expected: PASS (`# pass 19`, `# fail 0`).

- [ ] **Step 5: Commit**

```bash
git add web/course_logic.js web/course_logic.test.mjs
git commit -m "feat(course): pure monotonic progress merge + tests"
```

---

## Task 3: Accounts sync helpers

**Files:**
- Modify: `web/accounts.js`

**Interfaces:**
- Produces (on `window.Accounts`): `loadProgress() -> Promise<state|null>`; `saveProgress(state) -> Promise` (best-effort upsert).

- [ ] **Step 1: Add the helpers**

In `web/accounts.js`, immediately before the `// --- student` comment (after `logActivity`), add:

```js
  // --- learner: cross-device course progress sync -------------------------- //
  // Best-effort mirror of the course's localStorage state. Never block or error the learner.
  function loadProgress() {
    if (!ENABLED || !signedIn()) return Promise.resolve(null);
    return client().then(function (c) {
      return c.auth.getUser().then(function (r) {
        var u = r.data.user;
        if (!u) return null;
        return c.from("course_progress").select("state").eq("user_id", u.id).maybeSingle()
          .then(function (p) { return p.data ? p.data.state : null; });
      });
    }).catch(function () { return null; });
  }
  function saveProgress(state) {
    if (!ENABLED || !signedIn()) return Promise.resolve();
    return client().then(function (c) {
      return c.auth.getUser().then(function (r) {
        var u = r.data.user;
        if (!u) return null;
        return c.from("course_progress").upsert(
          { user_id: u.id, state: state, updated_at: new Date().toISOString() },
          { onConflict: "user_id" });
      });
    }).catch(function () { /* progress sync is best-effort */ });
  }
```

- [ ] **Step 2: Export them**

In `web/accounts.js`, in the `window.Accounts = { ... }` object, change the line:

```js
    isEntitled: isEntitled, premiumContent: premiumContent, requestRefund: requestRefund,
```

to:

```js
    isEntitled: isEntitled, premiumContent: premiumContent, requestRefund: requestRefund,
    loadProgress: loadProgress, saveProgress: saveProgress,
```

- [ ] **Step 3: Verify lint**

Run: `npm run lint`
Expected: exit 0.

- [ ] **Step 4: Commit**

```bash
git add web/accounts.js
git commit -m "feat(accounts): loadProgress/saveProgress for course sync"
```

---

## Task 4: Sync wiring in course.js

**Files:**
- Modify: `web/course.js`

**Interfaces:**
- Consumes: `CourseLogic.mergeProgress` (Task 2); `Accounts.loadProgress`/`saveProgress` (Task 3).
- Produces: `readAllProgress`/`writeAllProgress`, `queueSync`/`flushSync`/`bootSync`, boot merge in `loadCourse`, `queueSync()` in the 7 save helpers.

- [ ] **Step 1: Add the sync module**

In `web/course.js`, immediately after the `saveExamBest` function (ends `... } catch (e) { /* storage off */ } }`), add:

```js
  // --- cross-device progress sync (best-effort, local-first) --------------- //
  var PROGRESS_KEYS = [CURRICULUM_DONE_KEY, COURSE_QUIZ_KEY, COURSE_READ_KEY, COURSE_EXAM_KEY, COURSE_MASTERY_KEY, COURSE_DIAG_KEY, COURSE_REVIEW_KEY];
  var _syncTimer = null;

  function readAllProgress() {
    var out = {};
    PROGRESS_KEYS.forEach(function (k) {
      try { var v = localStorage.getItem(k); if (v != null) out[k] = JSON.parse(v); } catch (e) { /* skip */ }
    });
    return out;
  }
  function writeAllProgress(state) {
    if (!state) return;
    PROGRESS_KEYS.forEach(function (k) {
      if (state[k] == null) return;
      try { localStorage.setItem(k, JSON.stringify(state[k])); } catch (e) { /* storage off */ }
    });
  }
  function syncOn() { return !!(window.Accounts && Accounts.enabled() && Accounts.signedIn()); }
  // Debounced push of local progress to the server.
  function queueSync() {
    if (!syncOn()) return;
    if (_syncTimer) clearTimeout(_syncTimer);
    _syncTimer = setTimeout(flushSync, 2000);
  }
  function flushSync() {
    if (_syncTimer) { clearTimeout(_syncTimer); _syncTimer = null; }
    if (!syncOn()) return;
    Accounts.saveProgress(readAllProgress());
  }
  // Pull the server copy, merge monotonically into local, write back, and push.
  function bootSync() {
    if (!syncOn()) return Promise.resolve();
    return Accounts.loadProgress().then(function (remote) {
      if (!remote) { flushSync(); return; }
      var merged = CourseLogic.mergeProgress(readAllProgress(), remote);
      writeAllProgress(merged);
      Accounts.saveProgress(merged);
    }).catch(function () { /* best-effort */ });
  }
  if (window.addEventListener) {
    window.addEventListener("pagehide", flushSync);
    document.addEventListener("visibilitychange", function () { if (document.visibilityState === "hidden") flushSync(); });
  }
```

- [ ] **Step 2: Merge on boot in `loadCourse`**

In `web/course.js`, in `loadCourse`, replace:

```js
      courseView(data.curriculum || [], byTitle, byTopic);
    });
  }
```

with (run the merge before rendering so the dashboard reflects merged state):

```js
      return bootSync().then(function () {
        courseView(data.curriculum || [], byTitle, byTopic);
      });
    });
  }
```

- [ ] **Step 3: Call `queueSync()` from the seven save helpers**

In `web/course.js`, add `queueSync();` immediately after the `localStorage.setItem(...)` in each of these functions (each `setItem` line is unique by its key constant):

- `saveExamBest` — after `localStorage.setItem(COURSE_EXAM_KEY, JSON.stringify(b));` add `queueSync();` on the next line.
- `saveReview` — change `... localStorage.setItem(COURSE_REVIEW_KEY, JSON.stringify(map)); } catch` to `... localStorage.setItem(COURSE_REVIEW_KEY, JSON.stringify(map)); queueSync(); } catch`.
- `saveDiagnostic` — change `... localStorage.setItem(COURSE_DIAG_KEY, JSON.stringify(d)); } catch` to `... localStorage.setItem(COURSE_DIAG_KEY, JSON.stringify(d)); queueSync(); } catch`.
- `markRead` — change `... localStorage.setItem(COURSE_READ_KEY, JSON.stringify(r)); } catch` to `... localStorage.setItem(COURSE_READ_KEY, JSON.stringify(r)); queueSync(); } catch`.
- `saveMasteryResult` — after `m[title] = r; localStorage.setItem(COURSE_MASTERY_KEY, JSON.stringify(m));` add `queueSync();`.
- `markDone` — change `if (a.indexOf(title) < 0) { a.push(title); localStorage.setItem(CURRICULUM_DONE_KEY, JSON.stringify(a)); }` to `if (a.indexOf(title) < 0) { a.push(title); localStorage.setItem(CURRICULUM_DONE_KEY, JSON.stringify(a)); queueSync(); }`.
- `bumpScore` — after `localStorage.setItem(COURSE_QUIZ_KEY, JSON.stringify(s));` add `queueSync();`.

- [ ] **Step 4: Verify lint + tests + hook count**

Run: `npm run lint && npm run test:web`
Expected: ESLint exit 0; test run `# pass 19`, `# fail 0`.
Also run: `grep -c "queueSync" web/course.js`
Expected: `>= 9` (the function definition + the `queueSync` reference in `flushSync` note it is not there; count is the definition line + 7 save-helper calls + the `setTimeout(flushSync...)`/queueSync internal — at minimum the 7 hooks + 1 definition + 1 call in itself = 9).

- [ ] **Step 5: Commit**

```bash
git add web/course.js
git commit -m "feat(course): boot merge + debounced push wiring for progress sync"
```

---

## Controller step (after the code tasks): apply the migration

The controller applies `supabase/migrations/0005_course_progress.sql` to Supabase (ref idgyjmamxxyddjuaamit) via the MCP `apply_migration`, then verifies the table + RLS policy exist. Owner-approved.

---

## Manual verification checklist (after all tasks + migration)

Signed-in (owner), two browsers/profiles on the same account:
- [ ] In browser A, complete a lesson / pass a mastery check / miss a quiz question. Within a few seconds it is pushed (or on tab hide).
- [ ] Open the course in browser B (same account): the dashboard reflects A's progress after the boot merge.
- [ ] Make different progress in B, return to A and reload: A shows the union (its own progress plus B's), nothing lost.
- [ ] Signed-out / free use is unaffected (sync is a no-op); offline use still works (best-effort).

---

## Self-Review

**Spec coverage:**
- Table + RLS → Task 1 (+ controller apply).
- Accounts loadProgress/saveProgress → Task 3.
- Monotonic per-key merge → Task 2 (`mergeProgress`).
- Boot pull-merge-push → Task 4 Step 2 (`bootSync` in `loadCourse`).
- Debounced push + page-hide flush → Task 4 Step 1 (`queueSync`/`flushSync` + listeners) + Step 3 (7 hooks).
- Best-effort / no-op when signed out → `syncOn()` guard + `.catch` in Accounts helpers.
- Node tests → Task 2.

**Placeholder scan:** every code step carries complete code; the Task 4 Step 3 hooks are exact per-function anchor edits.

**Type consistency:** the seven storage-key strings are identical across `PROGRESS_KEYS` (Task 4), `mergeProgress`'s key checks (Task 2), and the existing `*_KEY` constants. `mergeProgress(local, remote)` shape (objects keyed by storage keys) matches `readAllProgress()` output and `writeAllProgress()` input. `Accounts.loadProgress()`/`saveProgress(state)` signatures match their `bootSync`/`flushSync` call sites. `queueSync()` is a zero-arg call added at all seven save sites.
