# Completion Milestone (Phase 4.1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show a definitive on-screen "course complete" state when every module is mastered and the best practice exam is >= 80%, with the completion record persisted and synced.

**Architecture:** Pure `isCourseComplete` + a `mergeProgress` rule in `web/course_logic.js` (node-tested); a completion record in a new synced `localStorage` key; a completion panel in `renderOverview` (course.js) + CSS. No backend, no content, no cache bump.

**Tech Stack:** Vanilla ES5 browser JS + CSS, CommonJS pure module, node's test runner.

## Global Constraints

- `course.js` / `course_logic.js` are ES5-style: `var`, function expressions, the `h(tag, attrs, kids)` builder with `text:` for strings. Match the files. The `.mjs` test is standard ESM.
- `course.js` reads `CourseLogic` via the existing `var CourseLogic = window.CourseLogic;` alias. No `eslint.config.mjs` edit (config-protection hook; no new globals needed).
- Completion criteria: every module `status === "mastered"` AND best practice exam `>= 80`. Constant `COMPLETE_EXAM_PCT = 80`.
- New synced key: `mrisim_course_completed_v1` (`{at, examPct}`); merged by earlier-`at` wins.
- No em dashes / AI-tell punctuation in learner-facing strings. No emoji, gradients, pills; professional/clinical. No `Co-Authored-By: Claude` trailer. `course.js`/`course.html` are network-first SHELL (no cache bump).
- No certificate / accreditation language (personal completion state only).

## File structure

- `web/course_logic.js` — add `COMPLETE_EXAM_PCT`, `isCourseComplete`, `_earlier`, a `mergeProgress` completed-key rule; export `isCourseComplete`.
- `web/course_logic.test.mjs` — tests.
- `web/course.js` — `COURSE_COMPLETE_KEY`, `loadCompleted`/`saveCompleted`, add key to `PROGRESS_KEYS`, completion detection/record/panel in `renderOverview`.
- `web/course.html` — completion-panel CSS.

---

## Task 1: Pure completion logic + merge rule

**Files:**
- Modify: `web/course_logic.js`
- Modify: `web/course_logic.test.mjs`

**Interfaces:**
- Produces: `isCourseComplete(statuses, bestExamPct) -> bool` (all `"mastered"` AND `bestExamPct >= 80`); a `mergeProgress` rule for `mrisim_course_completed_v1` (earlier `at` wins).

- [ ] **Step 1: Write the failing tests**

In `web/course_logic.test.mjs`, add `isCourseComplete` to the destructure line, then append:

```js
test("isCourseComplete requires all mastered and exam >= 80", () => {
  assert.equal(isCourseComplete(["mastered", "mastered"], 80), true);
  assert.equal(isCourseComplete(["mastered", "mastered"], 79), false);
  assert.equal(isCourseComplete(["mastered", "progress"], 95), false);
  assert.equal(isCourseComplete([], 100), false);
  assert.equal(isCourseComplete(["mastered"], null), false);
});

test("mergeProgress completed record keeps the earlier at", () => {
  const m = mergeProgress(
    { mrisim_course_completed_v1: { at: 200, examPct: 90 } },
    { mrisim_course_completed_v1: { at: 100, examPct: 82 } });
  assert.deepEqual(m.mrisim_course_completed_v1, { at: 100, examPct: 82 });
  assert.deepEqual(mergeProgress({ mrisim_course_completed_v1: { at: 5 } }, {}).mrisim_course_completed_v1, { at: 5 });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `node --test web/course_logic.test.mjs`
Expected: FAIL (`isCourseComplete` undefined).

- [ ] **Step 3: Implement**

In `web/course_logic.js`, immediately before the `return {` line, add:

```js
  var COMPLETE_EXAM_PCT = 80;  // best-mock threshold for course completion

  // Complete = every module status is "mastered" AND the best practice exam >= COMPLETE_EXAM_PCT.
  function isCourseComplete(statuses, bestExamPct) {
    if (!statuses || !statuses.length) return false;
    for (var i = 0; i < statuses.length; i++) { if (statuses[i] !== "mastered") return false; }
    return typeof bestExamPct === "number" && bestExamPct >= COMPLETE_EXAM_PCT;
  }
  // Keep the object with the smaller field value (null-safe; one-sided returns the present one).
  function _earlier(a, b, field) {
    if (!a) return b; if (!b) return a;
    return _num(a[field]) <= _num(b[field]) ? a : b;
  }
```

Then, in `mergeProgress`, immediately after the `mrisim_course_review_v1` line, add:

```js
    if ("mrisim_course_completed_v1" in out) out.mrisim_course_completed_v1 = _earlier(local.mrisim_course_completed_v1, remote.mrisim_course_completed_v1, "at");
```

Then add `isCourseComplete: isCourseComplete,` to the returned export object (after `mergeProgress: mergeProgress,`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `node --test web/course_logic.test.mjs`
Expected: PASS (`# pass 21`, `# fail 0`).

- [ ] **Step 5: Commit**

```bash
git add web/course_logic.js web/course_logic.test.mjs
git commit -m "feat(course): pure isCourseComplete + completed-record merge rule + tests"
```

---

## Task 2: Completion detection, record, and panel

**Files:**
- Modify: `web/course.js`
- Modify: `web/course.html` (CSS)

**Interfaces:**
- Consumes: `CourseLogic.isCourseComplete` (Task 1); existing `queueSync`/`h`/`openExam`/`openModule`; `computeReadiness` result `r` (`r.modules[].status`, `r.exam.bestPct`, `r.next`).
- Produces: `COURSE_COMPLETE_KEY`, `loadCompleted()`/`saveCompleted(rec)`, the key in `PROGRESS_KEYS`, and the completion panel.

- [ ] **Step 1: Add the key**

In `web/course.js`, after the line `var COURSE_REVIEW_KEY = "mrisim_course_review_v1"; // spaced-review queue of missed questions` add:

```js
  var COURSE_COMPLETE_KEY = "mrisim_course_completed_v1"; // first course-completion record (synced)
```

- [ ] **Step 2: Add state helpers**

In `web/course.js`, immediately after the `saveExamBest` function (ends `... } catch (e) { /* storage off */ } }`), add:

```js
  function loadCompleted() { try { return JSON.parse(localStorage.getItem(COURSE_COMPLETE_KEY) || "null"); } catch (e) { return null; } }
  function saveCompleted(rec) { try { localStorage.setItem(COURSE_COMPLETE_KEY, JSON.stringify(rec)); } catch (e) { /* storage off */ } }
```

- [ ] **Step 3: Sync the new key**

In `web/course.js`, change the `PROGRESS_KEYS` line:

```js
  var PROGRESS_KEYS = [CURRICULUM_DONE_KEY, COURSE_QUIZ_KEY, COURSE_READ_KEY, COURSE_EXAM_KEY, COURSE_MASTERY_KEY, COURSE_DIAG_KEY, COURSE_REVIEW_KEY];
```

to:

```js
  var PROGRESS_KEYS = [CURRICULUM_DONE_KEY, COURSE_QUIZ_KEY, COURSE_READ_KEY, COURSE_EXAM_KEY, COURSE_MASTERY_KEY, COURSE_DIAG_KEY, COURSE_REVIEW_KEY, COURSE_COMPLETE_KEY];
```

- [ ] **Step 4: Completion detection + panel in `renderOverview`**

In `web/course.js`, in `renderOverview`, replace this block:

```js
    if (r.next) {
      main.appendChild(h("button", { class: "btn study-next", type: "button",
        onclick: function () { openModule(r.next.mod); } }, [
        document.createTextNode("Study next: " + r.next.mod.title),
        h("span", { class: "sn-why", text: r.next.status === "review" ? "quiz needs work"
          : r.next.c ? "keep going" : "not started yet" }),
      ]));
    } else {
      main.appendChild(h("p", { class: "lede", text: "Every module is mastered. Run a full practice exam to confirm you're ready." }));
    }
```

with:

```js
    var completeRec = loadCompleted();
    var complete = !!completeRec || CourseLogic.isCourseComplete(r.modules.map(function (m) { return m.status; }), r.exam && r.exam.bestPct);
    if (complete && !completeRec && r.exam && r.exam.bestPct != null) {
      completeRec = { at: Date.now(), examPct: r.exam.bestPct };
      saveCompleted(completeRec); queueSync();
    }
    if (complete) {
      var cWhen = (completeRec && completeRec.at) ? new Date(completeRec.at).toLocaleDateString() : new Date().toLocaleDateString();
      var cPct = (completeRec && completeRec.examPct != null) ? completeRec.examPct : (r.exam && r.exam.bestPct);
      main.appendChild(h("div", { class: "complete-panel" }, [
        h("p", { class: "cp-eyebrow", text: "Course complete" }),
        h("h3", { class: "cp-title", text: "You have completed the MRISim guided course" }),
        h("p", { class: "cp-sub", text: "Every module is mastered and your best practice exam is " + cPct + "%. Completed " + cWhen + "." }),
        h("p", { class: "cp-note", text: "Keep reviewing to stay sharp. The practice exam and every module stay open below." }),
      ]));
    } else if (r.next) {
      main.appendChild(h("button", { class: "btn study-next", type: "button",
        onclick: function () { openModule(r.next.mod); } }, [
        document.createTextNode("Study next: " + r.next.mod.title),
        h("span", { class: "sn-why", text: r.next.status === "review" ? "quiz needs work"
          : r.next.c ? "keep going" : "not started yet" }),
      ]));
    } else {
      main.appendChild(h("p", { class: "lede", text: "Every module is mastered. Run a full practice exam to confirm you're ready." }));
    }
```

- [ ] **Step 5: Add the CSS**

In `web/course.html`, after the `.ready-row.mastered .rr-chip { ... }` rule (the readiness dashboard styles), add:

```css
    .complete-panel { background: var(--panel); border: 1px solid var(--ok); border-radius: 2px; padding: 20px 22px; margin: 14px 0; }
    .complete-panel .cp-eyebrow { font-family: var(--mono); font-size: 11px; letter-spacing: .16em; text-transform: uppercase; color: var(--ok); margin: 0 0 6px; }
    .complete-panel .cp-title { margin: 0 0 8px; font-size: 17px; }
    .complete-panel .cp-sub { color: var(--muted); font-size: 13.5px; line-height: 1.6; margin: 0 0 8px; }
    .complete-panel .cp-note { color: var(--dim); font-size: 12.5px; margin: 0; }
```

- [ ] **Step 6: Verify lint + tests**

Run: `npm run lint && npm run test:web`
Expected: ESLint exit 0; test run `# pass 21`, `# fail 0`.

- [ ] **Step 7: Commit**

```bash
git add web/course.js web/course.html
git commit -m "feat(course): course-complete panel + persisted, synced completion record"
```

---

## Manual verification checklist (after all tasks)

Signed-in (owner), since the course is auth-gated:
- [ ] With all modules mastered but no 80%+ mock, the dashboard still shows "Every module is mastered. Run a full practice exam...".
- [ ] Score >= 80% on a full practice exam: the dashboard shows the "Course complete" panel with the best mock % and today's date; the practice exam + module grid remain below.
- [ ] Reload: the panel persists (from the stored record) with the same completion date.
- [ ] The completion record syncs (appears on a second device after its boot merge; the earlier date is kept).

---

## Self-Review

**Spec coverage:**
- Criteria (all mastered + exam >= 80) → Task 1 `isCourseComplete`.
- Persisted record `{at, examPct}` + synced → Task 2 (`COURSE_COMPLETE_KEY`, `save/loadCompleted`, `PROGRESS_KEYS`) + Task 1 merge rule.
- Completion panel replacing the nudge; all-mastered-but-not-complete keeps the nudge → Task 2 Step 4 (3-way).
- Earlier-`at` merge → Task 1.
- No certificate/accreditation language → Task 2 panel copy (personal completion only).
- Node tests → Task 1.

**Placeholder scan:** every code step carries complete code; no vague steps.

**Type consistency:** `isCourseComplete(statuses, bestExamPct)` signature matches its Task 2 call (`r.modules.map(m => m.status)`, `r.exam && r.exam.bestPct`). The record shape `{at, examPct}` is identical across `saveCompleted` (Task 2), the `_earlier(..., "at")` merge rule (Task 1), and the panel read. `COURSE_COMPLETE_KEY`/`mrisim_course_completed_v1` string matches across `PROGRESS_KEYS`, the helpers, and the merge rule.
