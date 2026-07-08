# Spaced Review of Missed Items (Phase 3.3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Capture every missed question across the course and resurface it on a Leitner-lite spaced schedule until it graduates.

**Architecture:** Pure scheduling in `web/course_logic.js` (node-tested); a `recordAnswer(q, correct, inReview)` in `web/course.js` hooked into all four grading sites updates a review map keyed by prompt in a new `localStorage` key; a Review session surfaces due items with immediate feedback. No backend, no content, no cache bump.

**Tech Stack:** Vanilla ES5 browser JS + CSS, CommonJS pure module, node's test runner.

## Global Constraints

- `web/course.js` / `web/course_logic.js` are ES5-style: `var`, function expressions, the `h(tag, attrs, kids)` builder; `text:` for plain strings. Match the files.
- `course.js` reads `CourseLogic` via the existing `var CourseLogic = window.CourseLogic;` local alias (no ESLint global; the `config-protection` hook blocks `eslint.config.mjs` — do NOT edit it).
- The `.mjs` test file is standard ESM (const/arrow fine); the browser files stay ES5.
- No em dashes / AI-tell punctuation in learner-facing strings. No emoji, gradients, pills.
- New key only: `mrisim_course_review_v1`. The review queue is a study aid; adding `recordAnswer` at the diagnostic grading site must NOT otherwise change the diagnostic's snapshot behavior (still no `bumpScore`, still no readiness/quiz/mastery writes).
- No `Co-Authored-By: Claude` trailer. `course.js`/`course.html` are network-first SHELL (no cache bump).
- Scheduling constants (verbatim): `DAY_MS = 86400000`, `REVIEW_INTERVALS_DAYS = [1, 3, 7]`.

## File structure

- `web/course_logic.js` — add `reviewOnMiss`, `reviewOnCorrect`, `dueCount` to the export.
- `web/course_logic.test.mjs` — add unit tests.
- `web/course.js` — key + `loadReview`/`saveReview` + `recordAnswer` + 4 grading hooks + review session + entry card + rail button.
- `web/course.html` — reuses existing `.q`/`.opt`/`.fb`/`.diag-card` styles (no new CSS expected).

---

## Task 1: Pure spaced-review scheduling

**Files:**
- Modify: `web/course_logic.js`
- Modify: `web/course_logic.test.mjs`

**Interfaces:**
- Produces:
  - `reviewOnMiss(entry, now) -> {box:0, due:now, misses:(prev+1), lastSeen:now}`.
  - `reviewOnCorrect(entry, now) -> newEntry | null` (advance box; +1/+3/+7 day due; null once graduated past box 3).
  - `dueCount(map, now) -> number` of entries with `due <= now`.

- [ ] **Step 1: Write the failing tests**

In `web/course_logic.test.mjs`, change the destructure line to also pull the three functions:

```js
const { deriveModuleStatus, PASS_PCT, CHECK_N, MIN_POOL, rankModulesByDiagnostic, diagnosticStudyNext, reviewOnMiss, reviewOnCorrect, dueCount } = CourseLogic;
```

and append these tests to the end of the file:

```js
test("reviewOnMiss resets to box 0 due-now and increments misses", () => {
  assert.deepEqual(reviewOnMiss(undefined, 1000), { box: 0, due: 1000, misses: 1, lastSeen: 1000 });
  assert.deepEqual(reviewOnMiss({ box: 2, misses: 1 }, 5000), { box: 0, due: 5000, misses: 2, lastSeen: 5000 });
});

test("reviewOnCorrect advances box, widens due (1/3/7 days), then graduates", () => {
  const D = 86400000;
  assert.deepEqual(reviewOnCorrect(undefined, 0), { box: 1, due: 1 * D, misses: 0, lastSeen: 0 });
  assert.deepEqual(reviewOnCorrect({ box: 1, misses: 2 }, 0), { box: 2, due: 3 * D, misses: 2, lastSeen: 0 });
  assert.deepEqual(reviewOnCorrect({ box: 2, misses: 2 }, 0), { box: 3, due: 7 * D, misses: 2, lastSeen: 0 });
  assert.equal(reviewOnCorrect({ box: 3, misses: 2 }, 0), null);
});

test("dueCount counts only entries with due <= now", () => {
  assert.equal(dueCount({ a: { due: 100 }, b: { due: 300 }, c: { due: 200 } }, 200), 2);
  assert.equal(dueCount({}, 999), 0);
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `node --test web/course_logic.test.mjs`
Expected: FAIL (`reviewOnMiss`/`reviewOnCorrect`/`dueCount` undefined).

- [ ] **Step 3: Implement the functions**

In `web/course_logic.js`, immediately before the `return {` line, add:

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
    if (box > REVIEW_INTERVALS_DAYS.length) return null;
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

Then change the export from:

```js
  return {
    PASS_PCT: PASS_PCT, CHECK_N: CHECK_N, MIN_POOL: MIN_POOL,
    deriveModuleStatus: deriveModuleStatus,
    rankModulesByDiagnostic: rankModulesByDiagnostic,
    diagnosticStudyNext: diagnosticStudyNext,
  };
```

to:

```js
  return {
    PASS_PCT: PASS_PCT, CHECK_N: CHECK_N, MIN_POOL: MIN_POOL,
    deriveModuleStatus: deriveModuleStatus,
    rankModulesByDiagnostic: rankModulesByDiagnostic,
    diagnosticStudyNext: diagnosticStudyNext,
    reviewOnMiss: reviewOnMiss,
    reviewOnCorrect: reviewOnCorrect,
    dueCount: dueCount,
  };
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `node --test web/course_logic.test.mjs`
Expected: PASS (`# pass 15`, `# fail 0`).

- [ ] **Step 5: Commit**

```bash
git add web/course_logic.js web/course_logic.test.mjs
git commit -m "feat(course): pure spaced-review scheduling (Leitner-lite) + tests"
```

---

## Task 2: Capture misses at every grading site

**Files:**
- Modify: `web/course.js`

**Interfaces:**
- Consumes: `CourseLogic.reviewOnMiss`, `CourseLogic.reviewOnCorrect` (Task 1).
- Produces: `COURSE_REVIEW_KEY`, `loadReview()`, `saveReview(map)`, `recordAnswer(q, correct, inReview)` (writes `mrisim_course_review_v1`). Task 3 consumes these + calls `recordAnswer(body, correct, true)` in the review session.

- [ ] **Step 1: Add the key**

In `web/course.js`, after the line `var COURSE_DIAG_KEY = "mrisim_course_diagnostic_v1"; // placement-test snapshot (separate from progress)` add:

```js
  var COURSE_REVIEW_KEY = "mrisim_course_review_v1"; // spaced-review queue of missed questions
```

- [ ] **Step 2: Add state helpers + `recordAnswer`**

In `web/course.js`, immediately after the `saveExamBest` function (ends `... } catch (e) { /* storage off */ } }`), add:

```js
  // --- spaced review of missed items -------------------------------------- //
  function loadReview() { try { return JSON.parse(localStorage.getItem(COURSE_REVIEW_KEY) || "{}") || {}; } catch (e) { return {}; } }
  function saveReview(map) { try { localStorage.setItem(COURSE_REVIEW_KEY, JSON.stringify(map)); } catch (e) { /* storage off */ } }

  // Record a graded answer into the spaced-review queue, keyed by the (unique) question prompt.
  // A miss enqueues/resets the question (due now). A correct answer during a review session
  // advances or graduates it. A correct answer anywhere else leaves the queue unchanged.
  function recordAnswer(q, correct, inReview) {
    if (!q || !q.prompt) return;
    var map = loadReview(), now = Date.now(), p = q.prompt;
    if (!correct) {
      map[p] = CourseLogic.reviewOnMiss(map[p], now);
    } else if (inReview) {
      var e = CourseLogic.reviewOnCorrect(map[p], now);
      if (e) map[p] = e; else delete map[p];
    } else {
      return;
    }
    saveReview(map);
  }
```

- [ ] **Step 3: Hook the inline quiz (`quizItem`)**

In `web/course.js`, in `quizItem`'s option `onclick`, replace:

```js
        bumpScore(topicTitle, correct);
      } });
```

with:

```js
        bumpScore(topicTitle, correct);
        recordAnswer(q, correct, false);
      } });
```

- [ ] **Step 4: Hook the mastery check (`submitMastery`)**

In `web/course.js`, in `submitMastery`, replace:

```js
    questions.forEach(function (item, qi) {
      var right = picks[qi] === item.q.answer;
      if (right) correct += 1;
      bumpScore(mod.title, right);
    });
```

with:

```js
    questions.forEach(function (item, qi) {
      var right = picks[qi] === item.q.answer;
      if (right) correct += 1;
      bumpScore(mod.title, right);
      recordAnswer(item.q, right, false);
    });
```

- [ ] **Step 5: Hook the practice exam (`submitExam`)**

In `web/course.js`, in `submitExam`, replace:

```js
    var correct = 0;
    EXAM.questions.forEach(function (item, qi) { if (EXAM.picks[qi] === item.q.answer) correct += 1; });
```

with:

```js
    var correct = 0;
    EXAM.questions.forEach(function (item, qi) {
      var right = EXAM.picks[qi] === item.q.answer;
      if (right) correct += 1;
      recordAnswer(item.q, right, false);
    });
```

- [ ] **Step 6: Hook the diagnostic (`submitDiagnostic`)**

In `web/course.js`, in `submitDiagnostic`, replace:

```js
    EXAM.questions.forEach(function (item, qi) {
      var t = EXAM.modTitles[qi];
      var rec = per[t] || (per[t] = { asked: 0, right: 0 });
      rec.asked += 1;
      if (EXAM.picks[qi] === item.q.answer) { rec.right += 1; correct += 1; }
    });
```

with:

```js
    EXAM.questions.forEach(function (item, qi) {
      var t = EXAM.modTitles[qi];
      var rec = per[t] || (per[t] = { asked: 0, right: 0 });
      rec.asked += 1;
      var right = EXAM.picks[qi] === item.q.answer;
      if (right) { rec.right += 1; correct += 1; }
      recordAnswer(item.q, right, false);
    });
```

- [ ] **Step 7: Verify lint + tests**

Run: `npm run lint && npm run test:web`
Expected: ESLint exit 0; test run `# pass 15`, `# fail 0`. Missing a question in any surface now writes an entry to `mrisim_course_review_v1`.

- [ ] **Step 8: Commit**

```bash
git add web/course.js
git commit -m "feat(course): capture missed questions into the spaced-review queue"
```

---

## Task 3: Review session + entry points

**Files:**
- Modify: `web/course.js`

**Interfaces:**
- Consumes: `loadReview`, `recordAnswer` (Task 2); `CourseLogic.dueCount` (Task 1); existing `shuffleInts`, `addQImg`, `stopExam`, `renderOverview`, `buildRail`, `h`, `clear`, `CTX.byTopic`.
- Produces: `reviewPool()`, `dueReviewItems()`, `startReview()`, `reviewCard(q)`, an overview Review card, and a Review rail button.

- [ ] **Step 1: Add the prompt index, due-items query, session, and card**

In `web/course.js`, immediately after the `recordAnswer` function (added in Task 2), add:

```js
  // prompt -> full quiz body, from the loaded premium bank.
  function reviewPool() {
    var idx = {};
    Object.keys(CTX.byTopic).forEach(function (key) {
      (CTX.byTopic[key] || []).forEach(function (it) { if (it.kind === "quiz") idx[it.body.prompt] = it.body; });
    });
    return idx;
  }
  // Due question bodies (due <= now), skipping prompts no longer in the bank.
  function dueReviewItems() {
    var map = loadReview(), pool = reviewPool(), now = Date.now(), out = [];
    Object.keys(map).forEach(function (p) { if (map[p] && map[p].due <= now && pool[p]) out.push(pool[p]); });
    return out;
  }

  function startReview() {
    stopExam();
    CTX.mod = null;
    var main = CTX.main; clear(main);
    main.appendChild(h("h2", { text: "Review" }));
    var items = dueReviewItems();
    if (!items.length) {
      main.appendChild(h("p", { class: "lede", text: "Nothing is due for review right now. Questions you miss in the quizzes, mastery checks, exams and placement test show up here on a spaced schedule." }));
      main.appendChild(h("button", { class: "btn ghost", type: "button", text: "Back to overview", onclick: renderOverview }));
      buildRail(); window.scrollTo(0, 0); return;
    }
    main.appendChild(h("p", { class: "lede", text: items.length + " item" + (items.length === 1 ? "" : "s") + " due. Answer each to reschedule it. Get it right a few times and it graduates out of review." }));
    var order = shuffleInts(items.length);
    order.forEach(function (idx) { main.appendChild(reviewCard(items[idx])); });
    main.appendChild(h("button", { class: "btn ghost", type: "button", text: "Done", onclick: renderOverview }));
    buildRail(); window.scrollTo(0, 0);
  }

  // One review question: shuffled options, immediate feedback, and reschedule on answer.
  // Mirrors quizItem's feedback pattern, but reschedules via recordAnswer(inReview=true) and
  // does not touch the per-module quiz score.
  function reviewCard(q) {
    var order = shuffleInts(q.options.length);
    var answered = false;
    var fb = h("div", { class: "fb", hidden: true });
    var box = h("div", { class: "q" }, [h("p", { class: "prompt", text: q.prompt })]);
    addQImg(box, q);
    order.forEach(function (orig) {
      var b = h("button", { class: "opt", text: q.options[orig], onclick: function () {
        if (answered) return; answered = true;
        var correct = orig === q.answer;
        b.classList.add(correct ? "correct" : "wrong");
        if (!correct) {
          [].forEach.call(box.querySelectorAll(".opt"), function (o, k) { if (order[k] === q.answer) o.classList.add("correct"); });
        }
        [].forEach.call(box.querySelectorAll(".opt"), function (o) { o.disabled = true; });
        fb.hidden = false; fb.textContent = (correct ? "Correct. " : "Not quite. ") + q.explain;
        recordAnswer(q, correct, true);
      } });
      box.appendChild(b);
    });
    box.appendChild(fb);
    return box;
  }
```

- [ ] **Step 2: Add the overview Review card**

In `web/course.js`, in `renderOverview`, immediately before this line:

```js
    main.appendChild(h("h3", { class: "ready-h", text: "By module" }));
```

insert:

```js
    var reviewDue = CourseLogic.dueCount(loadReview(), Date.now());
    var revCard = h("div", { class: "diag-card" }, [h("h3", { text: "Spaced review" })]);
    if (reviewDue > 0) {
      revCard.appendChild(h("p", { text: reviewDue + " question" + (reviewDue === 1 ? "" : "s") + " you missed " + (reviewDue === 1 ? "is" : "are") + " due for review." }));
      revCard.appendChild(h("button", { class: "btn", type: "button", text: "Start review", onclick: startReview }));
    } else {
      revCard.appendChild(h("p", { text: "No items due for review. Questions you miss show up here on a spaced schedule." }));
    }
    main.appendChild(revCard);
```

- [ ] **Step 3: Add the Review rail button**

In `web/course.js`, in `buildRail`, immediately after the "Placement test" rail button block (the `rail.appendChild(h("button", { class: "exam-cta" + (EXAM && EXAM.diagnostic ? " on" : "") ... "Placement test" ... }));`), add:

```js
    var railDue = CourseLogic.dueCount(loadReview(), Date.now());
    rail.appendChild(h("button", { class: "exam-cta", type: "button", onclick: startReview }, [
      document.createTextNode("Review" + (railDue ? " (" + railDue + ")" : "")),
      h("span", { class: "ec-sub", text: "Missed items, spaced" }),
    ]));
```

- [ ] **Step 4: Verify lint + tests**

Run: `npm run lint && npm run test:web`
Expected: ESLint exit 0; test run `# pass 15`, `# fail 0`.

- [ ] **Step 5: Commit**

```bash
git add web/course.js
git commit -m "feat(course): spaced-review session + overview card + rail entry"
```

---

## Manual verification checklist (after all tasks)

Signed-in (owner, via magic link), since the course is auth-gated:
- [ ] Miss a question in the inline quiz / a mastery check / the practice exam / the placement test; the overview "Spaced review" card then shows a due count (and the rail "Review" shows the count).
- [ ] Start review: due questions appear with immediate feedback + explanation.
- [ ] Answer a review question correctly: it reschedules (won't reappear this session); answer it wrong: it stays due.
- [ ] With nothing due, the card says "No items due for review" and the session shows the empty state.
- [ ] Reload persists the queue; quiz accuracy / readiness are unchanged by reviewing (review does not call `bumpScore`).

---

## Self-Review

**Spec coverage:**
- Leitner-lite scheduling (miss due-now; correct-in-review 1/3/7 then graduate) → Task 1 pure functions.
- Capture at all four grading sites → Task 2 (quizItem, submitMastery, submitExam, submitDiagnostic hooks).
- Diagnostic misses feed the queue without changing its snapshot behavior → Task 2 Step 6 (adds only `recordAnswer`; `saveDiagnostic`/no-bumpScore untouched).
- Review session with immediate feedback → Task 3 (`startReview` + `reviewCard`).
- Prompt→body resolution + aged-out skip → Task 3 (`reviewPool`/`dueReviewItems`).
- Due-count entry card + rail → Task 3.
- Node tests → Task 1.

**Placeholder scan:** every code step carries complete code; no TBD/vague steps.

**Type consistency:** the entry shape `{box, due, misses, lastSeen}` is identical across `reviewOnMiss`/`reviewOnCorrect` (Task 1), `recordAnswer` (Task 2), and `dueReviewItems`/`dueCount` consumers (Task 3). `recordAnswer(q, correct, inReview)` signature matches all call sites (four with `false` in Task 2, one with `true` in Task 3). `loadReview`/`saveReview`/`COURSE_REVIEW_KEY` declared in Task 2 and consumed in Task 3. The review map is keyed by `q.prompt` everywhere.
