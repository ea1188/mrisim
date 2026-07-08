# Course Mastery Checks + Earned Progress (Phase 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a real end-of-module mastery checkpoint to the paid course and make progress earned by action instead of granted by scrolling.

**Architecture:** All work is in the existing browser build (`web/`). A tiny new pure-logic module (`web/course_logic.js`) holds the DOM-free status decision so it can be unit-tested in node; everything else is in the existing `web/course.js` IIFE plus inline CSS in `web/course.html`. One new `localStorage` key. No backend, no Supabase change, no new course content — the mastery check draws from the already-fetched 205-question premium bank.

**Tech Stack:** Vanilla browser JavaScript (classic script, ES5-style), CommonJS for the shared logic module, node's built-in test runner (`node --test`) for the unit test, ESLint for static analysis, GitHub Actions (`web-lint.yml`) for CI.

## Global Constraints

- **Match `course.js` style exactly:** `var` only (no `const`/`let`/arrow functions), function expressions, the existing `h(tag, attrs, kids)` DOM builder. Use `text:` (textContent-safe) for all strings; `html:` only for trusted premium bodies as the file already does.
- **No em dashes and no AI-tell punctuation in any learner-facing string.** Use `·`, `:`, or plain sentences, matching the existing exam copy (e.g. `" · best "`).
- **Professional/clinical aesthetic:** no emoji, no gradient, no pill shapes. The `✓` glyph is already used in this file (`.lcard .lk`) and is allowed.
- **Display name is "MRISim".**
- **Never add `Co-Authored-By: Claude` trailers to commits.**
- **`npm run lint` must pass on `web/`** (course.js is linted; any new global must be declared in `eslint.config.mjs`).
- **Constants live once** in `course_logic.js`: `PASS_PCT = 80`, `CHECK_N = 8`, `MIN_POOL = 4`. `course.js` reads them from `CourseLogic`.
- **New `localStorage` key:** `mrisim_course_mastery_v1`, shape `{ "<mod.title>": { passed, bestPct, attempts, ts } }`.
- **Deployment note (no action, just awareness):** `course.js` and `course.html` are network-first SHELL files in `sw.js`, so **no `CACHE` version bump is needed**.

---

## File Structure

- **Create** `web/course_logic.js` — pure, DOM-free decision logic + shared constants. UMD: `window.CourseLogic` in the browser, `module.exports` in node.
- **Create** `web/course_logic.test.mjs` — node unit test for `deriveModuleStatus` and the pass boundary.
- **Modify** `web/course.js` — mastery state helpers, `modulePool`/`hasMastery`, status via `CourseLogic`, mastery-check UI, earned-reading control, subsection wiring.
- **Modify** `web/course.html` — load `course_logic.js`; add mastery-check + mark-as-read CSS; rename `.ready-row.solid` → `.ready-row.mastered`.
- **Modify** `eslint.config.mjs` — lint block for `course_logic.js`; declare `CourseLogic` global for the `course.js` group.
- **Modify** `package.json` — add a `test:web` script.
- **Modify** `.github/workflows/web-lint.yml` — run the unit test after ESLint.

---

## Task 1: Pure logic module + unit test + CI wiring

**Files:**
- Create: `web/course_logic.js`
- Create: `web/course_logic.test.mjs`
- Modify: `eslint.config.mjs` (add a lint block for `web/course_logic.js`)
- Modify: `package.json` (add `test:web` script)
- Modify: `.github/workflows/web-lint.yml` (add unit-test step)

**Interfaces:**
- Produces: `CourseLogic` object with `PASS_PCT` (number `80`), `CHECK_N` (number `8`), `MIN_POOL` (number `4`), and `deriveModuleStatus(doneCount, subTotal, quizSeen, masteryAttempts, masteryPassed) -> "not-started" | "review" | "mastered" | "progress"`. In the browser it is `window.CourseLogic`; in node it is the CommonJS `module.exports`.

- [ ] **Step 1: Write the failing test**

Create `web/course_logic.test.mjs`:

```js
import test from "node:test";
import assert from "node:assert/strict";
import CourseLogic from "./course_logic.js";

const { deriveModuleStatus, PASS_PCT, CHECK_N, MIN_POOL } = CourseLogic;

test("constants match the spec", () => {
  assert.equal(PASS_PCT, 80);
  assert.equal(CHECK_N, 8);
  assert.equal(MIN_POOL, 4);
});

test("not-started when nothing done, seen, or attempted", () => {
  assert.equal(deriveModuleStatus(0, 5, 0, 0, false), "not-started");
});

test("progress when some subs done but mastery not passed", () => {
  assert.equal(deriveModuleStatus(2, 5, 3, 0, false), "progress");
});

test("review when mastery attempted but not passed", () => {
  assert.equal(deriveModuleStatus(5, 5, 8, 1, false), "review");
});

test("mastered when passed and every sub done", () => {
  assert.equal(deriveModuleStatus(5, 5, 8, 1, true), "mastered");
});

test("passed but not all subs done stays progress, not mastered", () => {
  assert.equal(deriveModuleStatus(4, 5, 8, 1, true), "progress");
});

test("pass boundary is 80 percent inclusive", () => {
  assert.equal(79 >= PASS_PCT, false);
  assert.equal(80 >= PASS_PCT, true);
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `node --test web/course_logic.test.mjs`
Expected: FAIL — cannot find module `./course_logic.js` (it does not exist yet).

- [ ] **Step 3: Create the pure logic module**

Create `web/course_logic.js`:

```js
/* Pure, DOM-free course logic shared by course.js (browser) and the node unit test.
 * No localStorage, no DOM — just decisions over plain values, so it is unit-testable.
 * UMD: attaches window.CourseLogic in the browser, module.exports under node. */
(function (root, factory) {
  var api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.CourseLogic = api;
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  var PASS_PCT = 80;   // mastery-check pass threshold, percent
  var CHECK_N = 8;     // questions drawn per mastery check
  var MIN_POOL = 4;    // below this many questions, a module hides its mastery check

  // Per-module status tier from plain progress counts.
  // doneCount   = completed subsections (reads + lessons + mastery)
  // subTotal    = total subsections in the module
  // quizSeen    = questions answered anywhere in the module
  // masteryAttempts / masteryPassed = mastery-check state
  function deriveModuleStatus(doneCount, subTotal, quizSeen, masteryAttempts, masteryPassed) {
    if (doneCount === 0 && quizSeen === 0 && masteryAttempts === 0) return "not-started";
    if (masteryAttempts > 0 && !masteryPassed) return "review";
    if (masteryPassed && subTotal > 0 && doneCount === subTotal) return "mastered";
    return "progress";
  }

  return {
    PASS_PCT: PASS_PCT, CHECK_N: CHECK_N, MIN_POOL: MIN_POOL,
    deriveModuleStatus: deriveModuleStatus,
  };
});
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `node --test web/course_logic.test.mjs`
Expected: PASS — all 7 tests pass (`# pass 7`, `# fail 0`).

- [ ] **Step 5: Add the ESLint block for the new module**

In `eslint.config.mjs`, immediately after the block whose `files` array contains `"web/course.js"` (the `accounts.js`/`account.js`/`course.js` group), add a new config object:

```js
  // Pure shared logic: a tiny UMD module (browser window.CourseLogic + CommonJS export),
  // consumed by course.js and by the node unit test — so it needs both global sets.
  {
    files: ["web/course_logic.js"],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "script",
      globals: { ...globals.browser, ...globals.node },
    },
    rules: {
      ...js.configs.recommended.rules,
      "no-unused-vars": ["error", { args: "none", caughtErrors: "none" }],
    },
  },
```

- [ ] **Step 6: Add the `test:web` script**

In `package.json`, change the `scripts` block from:

```json
  "scripts": {
    "lint": "eslint web/"
  },
```

to:

```json
  "scripts": {
    "lint": "eslint web/",
    "test:web": "node --test web/course_logic.test.mjs"
  },
```

- [ ] **Step 7: Wire the unit test into CI**

In `.github/workflows/web-lint.yml`, after the final `ESLint` step, add:

```yaml
      - name: Unit test (pure course logic)
        run: npm run test:web
```

- [ ] **Step 8: Verify lint and test both pass locally**

Run: `npm run lint && npm run test:web`
Expected: ESLint prints nothing (exit 0); the test run reports `# pass 7`, `# fail 0`.

- [ ] **Step 9: Commit**

```bash
git add web/course_logic.js web/course_logic.test.mjs eslint.config.mjs package.json .github/workflows/web-lint.yml
git commit -m "feat(course): pure mastery status logic + node unit test + CI"
```

---

## Task 2: Mastery state + status wiring (model layer)

**Files:**
- Modify: `web/course.js` (constants, state helpers, `modulePool`/`hasMastery`, `isSubDone`, `computeReadiness`, `STATUS_LABEL`, "study next" gate, overview wording, `buildRail`)
- Modify: `web/course.html` (load `course_logic.js`; rename `.ready-row.solid` → `.ready-row.mastered`)
- Modify: `eslint.config.mjs` (declare `CourseLogic` global for the `course.js` group)

**Interfaces:**
- Consumes: `CourseLogic.PASS_PCT`, `CourseLogic.MIN_POOL`, `CourseLogic.deriveModuleStatus` from Task 1.
- Produces (used by Task 3 and Task 4):
  - `loadMastery() -> { "<title>": { passed, bestPct, attempts, ts } }`
  - `saveMasteryResult(title, pct) -> resultObject` (records attempt, best, passed at `pct >= PASS_PCT`)
  - `modulePool(mod) -> [quizBody, ...]` (premium quiz bodies for the module's topic keys)
  - `hasMastery(mod) -> boolean` (`modulePool(mod).length >= MIN_POOL`)
  - `isSubDone(s, done, read, mastery) -> boolean` (now includes a `type === "mastery"` branch keyed on `s.modTitle`)

- [ ] **Step 1: Load `course_logic.js` before `course.js`**

In `web/course.html`, change the script block (currently lines 281-283) from:

```html
  <script src="config.js"></script>
  <script src="accounts.js"></script>
  <script src="course.js"></script>
```

to:

```html
  <script src="config.js"></script>
  <script src="accounts.js"></script>
  <script src="course_logic.js"></script>
  <script src="course.js"></script>
```

- [ ] **Step 2: Declare the `CourseLogic` global for ESLint**

In `eslint.config.mjs`, in the config object whose `files` array contains `"web/course.js"`, change:

```js
      globals: { ...globals.browser, Accounts: "readonly" },
```

to:

```js
      globals: { ...globals.browser, Accounts: "readonly", CourseLogic: "readonly" },
```

- [ ] **Step 3: Add the mastery key and constants in `course.js`**

In `web/course.js`, after the line `var COURSE_EXAM_KEY = "mrisim_course_exam_v1";` add:

```js
  var COURSE_MASTERY_KEY = "mrisim_course_mastery_v1"; // per-module mastery-check result
```

Then after the line `var STRIPE = window.MRISIM_STRIPE || {};` add:

```js
  var PASS_PCT = CourseLogic.PASS_PCT, CHECK_N = CourseLogic.CHECK_N, MIN_POOL = CourseLogic.MIN_POOL;
```

- [ ] **Step 4: Add mastery state helpers**

In `web/course.js`, directly after the `markRead` function (which ends `... } catch (e) { /* storage off */ } }`), add:

```js
  function loadMastery() { try { return JSON.parse(localStorage.getItem(COURSE_MASTERY_KEY) || "{}") || {}; } catch (e) { return {}; } }
  function saveMasteryResult(title, pct) {
    try {
      var m = loadMastery(), r = m[title] || { passed: false, bestPct: 0, attempts: 0 };
      r.attempts += 1;
      if (pct > r.bestPct) r.bestPct = pct;
      if (pct >= PASS_PCT) r.passed = true;
      r.ts = Date.now();
      m[title] = r; localStorage.setItem(COURSE_MASTERY_KEY, JSON.stringify(m));
      return r;
    } catch (e) { return { passed: pct >= PASS_PCT, bestPct: pct, attempts: 1 }; }
  }
```

- [ ] **Step 5: Add `modulePool` and `hasMastery`**

In `web/course.js`, directly after the `examPool` function (ends `... return pool; }`), add:

```js
  // Premium quiz bodies for one module (its TOPIC_CFG premium keys) — the mastery-check pool.
  function modulePool(mod) {
    var cfg = TOPIC_CFG[mod.title] || { premium: [], quiz: [] };
    var pool = [];
    cfg.premium.forEach(function (key) {
      (CTX.byTopic[key] || []).forEach(function (it) { if (it.kind === "quiz") pool.push(it.body); });
    });
    return pool;
  }
  function hasMastery(mod) { return modulePool(mod).length >= MIN_POOL; }
```

- [ ] **Step 6: Extend `isSubDone` with a mastery branch**

In `web/course.js`, replace the current one-liner:

```js
  function isSubDone(s, done, read) { return s.type === "lesson" ? !!done[s.id] : !!read[s.id]; }
```

with:

```js
  function isSubDone(s, done, read, mastery) {
    if (s.type === "lesson") return !!done[s.id];
    if (s.type === "mastery") { var r = mastery && mastery[s.modTitle]; return !!(r && r.passed); }
    return !!read[s.id];
  }
```

- [ ] **Step 7: Update `STATUS_LABEL` (solid → mastered)**

In `web/course.js`, replace:

```js
  var STATUS_LABEL = { "not-started": "Not started", "progress": "In progress", "review": "Needs review", "solid": "Solid" };
```

with:

```js
  var STATUS_LABEL = { "not-started": "Not started", "progress": "In progress", "review": "Needs review", "mastered": "Mastered" };
```

- [ ] **Step 8: Route `computeReadiness` status through `CourseLogic` and thread mastery**

In `web/course.js`, in `computeReadiness`, replace this block:

```js
    var done = loadDone(), read = loadRead(), quiz = loadQuiz(), exam = loadExamBest();
    var rSum = 0, rTot = 0, qRight = 0, qSeen = 0;
    var modules = CTX.curriculum.map(function (mod) {
      var subs = moduleSubsections(mod);
      var c = subs.filter(function (s) { return isSubDone(s, done, read); }).length;
      var q = quiz[mod.title] || { seen: 0, right: 0 };
      var acc = q.seen ? q.right / q.seen : null;
      rSum += c; rTot += subs.length; qRight += q.right; qSeen += q.seen;
      var status;
      if (c === 0 && !q.seen) status = "not-started";
      else if (q.seen >= 3 && acc != null && acc < 0.7) status = "review";              // read but missing questions
      else if (subs.length && c === subs.length && acc != null && acc >= 0.7) status = "solid";
      else status = "progress";
      return { mod: mod, subs: subs, c: c, total: subs.length, acc: acc, status: status };
    });
```

with:

```js
    var done = loadDone(), read = loadRead(), quiz = loadQuiz(), exam = loadExamBest(), mastery = loadMastery();
    var rSum = 0, rTot = 0, qRight = 0, qSeen = 0;
    var modules = CTX.curriculum.map(function (mod) {
      var subs = moduleSubsections(mod);
      var c = subs.filter(function (s) { return isSubDone(s, done, read, mastery); }).length;
      var q = quiz[mod.title] || { seen: 0, right: 0 };
      var acc = q.seen ? q.right / q.seen : null;
      var mr = mastery[mod.title] || { passed: false, attempts: 0 };
      rSum += c; rTot += subs.length; qRight += q.right; qSeen += q.seen;
      var status = CourseLogic.deriveModuleStatus(c, subs.length, q.seen, mr.attempts, mr.passed);
      return { mod: mod, subs: subs, c: c, total: subs.length, acc: acc, status: status };
    });
```

- [ ] **Step 9: Update the "study next" gate**

In `web/course.js`, in `computeReadiness`, replace:

```js
    for (var i = 0; i < modules.length; i++) { if (modules[i].status !== "solid") { next = modules[i]; break; } }
```

with:

```js
    for (var i = 0; i < modules.length; i++) { if (modules[i].status !== "mastered") { next = modules[i]; break; } }
```

- [ ] **Step 10: Update the all-done overview wording**

In `web/course.js`, in `renderOverview`, replace:

```js
      main.appendChild(h("p", { class: "lede", text: "Every module is solid — run a full practice exam to confirm you're ready." }));
```

with (no em dash):

```js
      main.appendChild(h("p", { class: "lede", text: "Every module is mastered. Run a full practice exam to confirm you're ready." }));
```

- [ ] **Step 11: Thread mastery into `buildRail`**

In `web/course.js`, in `buildRail`, replace:

```js
    var curriculum = CTX.curriculum, rail = CTX.rail, done = loadDone(), read = loadRead();
```

with:

```js
    var curriculum = CTX.curriculum, rail = CTX.rail, done = loadDone(), read = loadRead(), mastery = loadMastery();
```

Then, still in `buildRail`, replace the `perMod` filter line:

```js
      var c = subs.filter(function (s) { return isSubDone(s, done, read); }).length;
```

with:

```js
      var c = subs.filter(function (s) { return isSubDone(s, done, read, mastery); }).length;
```

And replace the per-sub done check inside `subs.forEach`:

```js
        var d = isSubDone(s, done, read);
```

with:

```js
        var d = isSubDone(s, done, read, mastery);
```

- [ ] **Step 12: Rename the status CSS**

In `web/course.html`, replace these two rules (currently lines 245-246):

```css
    .ready-row.solid { border-left-color: var(--ok); }
    .ready-row.solid .rr-chip { color: var(--ok); border-color: var(--ok); }
```

with:

```css
    .ready-row.mastered { border-left-color: var(--ok); }
    .ready-row.mastered .rr-chip { color: var(--ok); border-color: var(--ok); }
```

- [ ] **Step 13: Verify lint and the unit test still pass**

Run: `npm run lint && npm run test:web`
Expected: ESLint exit 0 (no `CourseLogic`/`no-undef` errors); test run `# pass 7`, `# fail 0`.

Note: this task alone never produces a "mastered" status yet (no mastery UI exists), so modules that were "solid" now read "In progress" until Task 3 lands. That is expected inside this branch; nothing ships until the whole branch merges.

- [ ] **Step 14: Commit**

```bash
git add web/course.js web/course.html eslint.config.mjs
git commit -m "feat(course): mastery state + status via CourseLogic (model wiring)"
```

---

## Task 3: Mastery-check UI + subsection tracking

**Files:**
- Modify: `web/course.js` (`moduleSubsections` mastery sub; `masterySection` + render/run/submit/result functions; insert into `renderTopic`)
- Modify: `web/course.html` (mastery-check CSS)

**Interfaces:**
- Consumes: `modulePool`, `hasMastery`, `saveMasteryResult`, `loadMastery`, `PASS_PCT`, `CHECK_N` (Task 2); `shuffleInts`, `bumpScore`, `buildRail`, `h`, `clear`, `slug` (existing).
- Produces: a `masterySection(mod) -> HTMLElement` rendered at the end of each module, and a `moduleSubsections` mastery sub `{ type: "mastery", id: "m:"+title, modTitle: title, label: "Mastery check", anchor: "mastery-"+slug(title) }`.

- [ ] **Step 1: Emit a mastery subsection instead of the "Test yourself" read sub**

In `web/course.js`, in `moduleSubsections`, replace:

```js
    mod.lessons.forEach(function (t) { subs.push({ type: "lesson", id: t, label: t, anchor: "lesson-" + slug(t) }); });
    var hasQuiz = cfg.premium.some(function (key) { return (byTopic[key] || []).some(function (it) { return it.kind === "quiz"; }); });
    if (hasQuiz) subs.push({ type: "read", id: "q:" + mod.title, label: "Test yourself", anchor: "quiz-" + slug(mod.title) });
    return subs;
```

with:

```js
    mod.lessons.forEach(function (t) { subs.push({ type: "lesson", id: t, label: t, anchor: "lesson-" + slug(t) }); });
    if (hasMastery(mod)) subs.push({ type: "mastery", id: "m:" + mod.title, modTitle: mod.title, label: "Mastery check", anchor: "mastery-" + slug(mod.title) });
    return subs;
```

- [ ] **Step 2: Add the mastery-check UI functions**

In `web/course.js`, directly after the `quizItem` function (ends `... return box; }`), add:

```js
  // --- end-of-module mastery check ---------------------------------------- //
  // N questions from the module pool, no feedback until submit, >= PASS_PCT passes.
  // Reuses the exam shuffle; every answer bumps the dashboard quiz score.
  function masterySection(mod) {
    var sec = h("div", { class: "sec mchk", id: "mastery-" + slug(mod.title), "data-subid": "m:" + mod.title },
      [h("h3", { text: "Mastery check" })]);
    var body = h("div", { class: "mchk-body" });
    sec.appendChild(body);
    renderMasteryIntro(mod, body);
    return sec;
  }
  function renderMasteryIntro(mod, body) {
    clear(body);
    var pool = modulePool(mod), n = Math.min(CHECK_N, pool.length);
    var m = loadMastery()[mod.title];
    if (m && m.passed) {
      body.appendChild(h("p", { class: "mchk-status pass", text: "Mastered · best " + m.bestPct + "%." }));
    } else if (m && m.attempts) {
      body.appendChild(h("p", { class: "mchk-status fail", text: "Not passed yet · best " + m.bestPct + "%. You need " + PASS_PCT + "%." }));
    } else {
      body.appendChild(h("p", { class: "mchk-intro", text: "Answer " + n + " questions from this module with no feedback until you submit. Score " + PASS_PCT + "% or higher to master it." }));
    }
    body.appendChild(h("button", { class: "btn", type: "button",
      text: (m && (m.passed || m.attempts)) ? "Retake the mastery check" : "Take the mastery check · " + n + " questions",
      onclick: function () { startMastery(mod, body); } }));
  }
  function startMastery(mod, body) {
    var pool = modulePool(mod);
    var order = shuffleInts(pool.length).slice(0, Math.min(CHECK_N, pool.length));
    var questions = order.map(function (idx) { var q = pool[idx]; return { q: q, order: shuffleInts(q.options.length) }; });
    renderMasteryRun(mod, body, questions);
  }
  function renderMasteryRun(mod, body, questions) {
    clear(body);
    var picks = questions.map(function () { return -1; });
    questions.forEach(function (item, qi) {
      var box = h("div", { class: "q mchk-q" }, [
        h("p", { class: "mq-num", text: "Question " + (qi + 1) + " of " + questions.length }),
        h("p", { class: "prompt", text: item.q.prompt }),
      ]);
      item.order.forEach(function (orig) {
        var opt = h("button", { class: "opt", type: "button", onclick: function () {
          picks[qi] = orig;
          [].forEach.call(box.querySelectorAll(".opt"), function (o) { o.classList.remove("sel"); });
          opt.classList.add("sel");
        } }, [document.createTextNode(item.q.options[orig])]);
        box.appendChild(opt);
      });
      body.appendChild(box);
    });
    body.appendChild(h("button", { class: "btn", type: "button", text: "Submit mastery check", onclick: function () {
      var blank = picks.filter(function (p) { return p < 0; }).length;
      if (blank > 0 && !window.confirm(blank + " unanswered question(s) will be marked wrong. Submit now?")) return;
      submitMastery(mod, body, questions, picks);
    } }));
  }
  function submitMastery(mod, body, questions, picks) {
    var correct = 0;
    questions.forEach(function (item, qi) {
      var right = picks[qi] === item.q.answer;
      if (right) correct += 1;
      bumpScore(mod.title, right);
    });
    var pct = Math.round(100 * correct / questions.length);
    saveMasteryResult(mod.title, pct);
    renderMasteryResult(mod, body, questions, picks, correct, pct);
    buildRail();
  }
  function renderMasteryResult(mod, body, questions, picks, correct, pct) {
    clear(body);
    var passed = pct >= PASS_PCT;
    body.appendChild(h("div", { class: "mchk-score " + (passed ? "pass" : "fail") }, [
      h("div", { class: "ms-pct", text: pct + "%" }),
      h("div", { class: "ms-line", text: correct + " of " + questions.length + (passed ? " · mastered" : " · need " + PASS_PCT + "%") }),
    ]));
    var missed = [];
    questions.forEach(function (item, qi) { if (picks[qi] !== item.q.answer) missed.push({ item: item, pick: picks[qi] }); });
    if (missed.length) {
      body.appendChild(h("h4", { class: "mchk-rev-h", text: "Review these" }));
      missed.forEach(function (mm) {
        var item = mm.item;
        var box = h("div", { class: "q reviewed miss" }, [h("p", { class: "prompt", text: item.q.prompt })]);
        item.order.forEach(function (orig) {
          var cls = "opt"; if (orig === item.q.answer) cls += " correct"; else if (orig === mm.pick) cls += " wrong";
          box.appendChild(h("button", { class: cls, type: "button", disabled: true }, [document.createTextNode(item.q.options[orig])]));
        });
        box.appendChild(h("div", { class: "fb", text: item.q.explain }));
        body.appendChild(box);
      });
    }
    var actions = h("div", { class: "mchk-actions" });
    if (!passed) actions.appendChild(h("button", { class: "btn", type: "button", text: "Retry", onclick: function () { startMastery(mod, body); } }));
    actions.appendChild(h("button", { class: "btn ghost", type: "button", text: passed ? "Done" : "Back to module", onclick: function () { renderMasteryIntro(mod, body); } }));
    body.appendChild(actions);
  }
```

- [ ] **Step 3: Render the mastery check at the end of each module**

In `web/course.js`, in `renderTopic`, find the quiz/link block just before `setupReadObserver(main);`:

```js
    if (cfg.quiz.length) {
      var link = h("p", { class: "quiz-foot" }, [
        document.createTextNode("Also practice the "),
        h("a", { class: "linkout", href: "quiz.html?topic=" + encodeURIComponent(cfg.quiz[0]), text: "free interactive " + cfg.quiz[0] + " quiz" }),
        document.createTextNode(" (read-the-scan)."),
      ]);
      main.appendChild(link);
    }
    setupReadObserver(main);
```

and insert the mastery section between the link block and `setupReadObserver`:

```js
    if (cfg.quiz.length) {
      var link = h("p", { class: "quiz-foot" }, [
        document.createTextNode("Also practice the "),
        h("a", { class: "linkout", href: "quiz.html?topic=" + encodeURIComponent(cfg.quiz[0]), text: "free interactive " + cfg.quiz[0] + " quiz" }),
        document.createTextNode(" (read-the-scan)."),
      ]);
      main.appendChild(link);
    }
    if (hasMastery(mod)) main.appendChild(masterySection(mod));
    setupReadObserver(main);
```

- [ ] **Step 4: Add the mastery-check CSS**

In `web/course.html`, after the `.q .fb { ... }` rule (currently line 111), add:

```css
    .mchk .mchk-intro, .mchk .mchk-status { font-size: 13px; color: #c4cad2; line-height: 1.6; margin: 0 0 12px; }
    .mchk .mchk-status.pass { color: var(--ok); }
    .mchk .mchk-status.fail { color: var(--warn); }
    .mchk .mq-num { font-family: var(--mono); font-size: 11px; color: var(--dim); margin: 0 0 8px; letter-spacing: .04em; }
    .mchk .opt.sel { border-color: var(--accent-deep); background: var(--panel-2); }
    .mchk-score { display: flex; align-items: baseline; gap: 12px; padding: 14px 0 8px; }
    .mchk-score .ms-pct { font-size: 32px; font-weight: 680; line-height: 1; letter-spacing: -1px; }
    .mchk-score.pass .ms-pct { color: var(--ok); }
    .mchk-score.fail .ms-pct { color: var(--warn); }
    .mchk-score .ms-line { font-size: 13px; color: var(--muted); }
    .mchk-rev-h { font-family: var(--mono); font-size: 11px; text-transform: uppercase; letter-spacing: .12em; color: var(--dim); margin: 18px 0 10px; }
    .mchk-actions { display: flex; gap: 10px; margin-top: 14px; }
```

- [ ] **Step 5: Verify lint and unit test pass**

Run: `npm run lint && npm run test:web`
Expected: ESLint exit 0; test run `# pass 7`, `# fail 0`.

- [ ] **Step 6: Commit**

```bash
git add web/course.js web/course.html
git commit -m "feat(course): inline end-of-module mastery check UI + subsection"
```

---

## Task 4: Earned reading (retire scroll-to-read, add Mark as read)

**Files:**
- Modify: `web/course.js` (remove `setupReadObserver` and its call and CTX `_obs`; add a Mark-as-read control to each education card)
- Modify: `web/course.html` (education footer / mark-as-read CSS)

**Interfaces:**
- Consumes: `loadRead`, `markRead`, `buildRail`, `h`, `clear`, `slug` (existing).
- Produces: education cards now carry an explicit read control; scroll no longer marks anything read.

- [ ] **Step 1: Stop building the read-observer**

In `web/course.js`, in `renderTopic`, remove the observer call. Change the tail of `renderTopic` from:

```js
    if (hasMastery(mod)) main.appendChild(masterySection(mod));
    setupReadObserver(main);
    window.scrollTo(0, 0);
  }
```

to:

```js
    if (hasMastery(mod)) main.appendChild(masterySection(mod));
    window.scrollTo(0, 0);
  }
```

- [ ] **Step 2: Delete the `setupReadObserver` function**

In `web/course.js`, delete the entire `setupReadObserver` function block (its header comment `// Tick education/question sections off once they scroll into view ...` through its closing brace), i.e. remove:

```js
  // Tick education/question sections off once they scroll into view (checks them in the rail).
  function setupReadObserver(main) {
    if (CTX._obs) { CTX._obs.disconnect(); CTX._obs = null; }
    if (typeof IntersectionObserver !== "function") return;
    var obs = new IntersectionObserver(function (entries) {
      var changed = false;
      entries.forEach(function (e) {
        if (!e.isIntersecting) return;
        var id = e.target.getAttribute("data-subid");
        if (id && !loadRead()[id]) { markRead(id); obs.unobserve(e.target); changed = true; }
      });
      if (changed) buildRail();
    }, { threshold: 0.2 });
    CTX._obs = obs;
    [].forEach.call(main.querySelectorAll("[data-subid]"), function (el) { obs.observe(el); });
  }
```

- [ ] **Step 3: Remove the now-unused `_obs` field**

In `web/course.js`, in `courseView`, change:

```js
    CTX = { curriculum: curriculum, byTitle: lessonsByTitle, byTopic: premiumByTopic,
      rail: rail, main: main, mod: curriculum[0],
      expanded: new Set([curriculum[0].title]),  // which modules are expanded in the TOC
      _obs: null };                              // IntersectionObserver marking sections read
```

to:

```js
    CTX = { curriculum: curriculum, byTitle: lessonsByTitle, byTopic: premiumByTopic,
      rail: rail, main: main, mod: curriculum[0],
      expanded: new Set([curriculum[0].title]) };  // which modules are expanded in the TOC
```

- [ ] **Step 4: Add a Mark-as-read control to each education card**

In `web/course.js`, in `renderTopic`, replace the education-cards block:

```js
    if (edu.length) {
      var esec = h("div", { class: "sec" }, [h("h3", { text: "Course material" })]);
      edu.forEach(function (b) {
        var card = h("div", { class: "edu", id: "edu-" + slug(b.title), "data-subid": "e:" + b.title }, [h("h4", { text: b.title }), h("div", { class: "body", html: b.html })]);
        if (b.keypoints && b.keypoints.length) {
          var kp = h("div", { class: "keypoints" }, [h("b", { text: "Key points" })]);
          var ul = h("ul");
          b.keypoints.forEach(function (p) { ul.appendChild(h("li", { text: p })); });
          kp.appendChild(ul); card.appendChild(kp);
        }
        esec.appendChild(card);
      });
      main.appendChild(esec);
    }
```

with:

```js
    if (edu.length) {
      var readState = loadRead();
      var esec = h("div", { class: "sec" }, [h("h3", { text: "Course material" })]);
      edu.forEach(function (b) {
        var rid = "e:" + b.title, isRead = !!readState[rid];
        var card = h("div", { class: "edu" + (isRead ? " read" : ""), id: "edu-" + slug(b.title), "data-subid": rid }, [h("h4", { text: b.title }), h("div", { class: "body", html: b.html })]);
        if (b.keypoints && b.keypoints.length) {
          var kp = h("div", { class: "keypoints" }, [h("b", { text: "Key points" })]);
          var ul = h("ul");
          b.keypoints.forEach(function (p) { ul.appendChild(h("li", { text: p })); });
          kp.appendChild(ul); card.appendChild(kp);
        }
        var foot = h("div", { class: "edu-foot" });
        if (isRead) {
          foot.appendChild(h("span", { class: "edu-read-tag", text: "✓ Read" }));
        } else {
          foot.appendChild(h("button", { class: "mark-read", type: "button", text: "Mark as read", onclick: function () {
            markRead(rid);
            card.classList.add("read");
            clear(foot); foot.appendChild(h("span", { class: "edu-read-tag", text: "✓ Read" }));
            buildRail();
          } }));
        }
        card.appendChild(foot);
        esec.appendChild(card);
      });
      main.appendChild(esec);
    }
```

- [ ] **Step 5: Add the education-footer CSS**

In `web/course.html`, after the `.keypoints { ... }` rule (currently line 93), add:

```css
    .edu-foot { margin-top: 14px; padding-top: 12px; border-top: 1px solid var(--line); }
    .edu.read { border-color: #2a4a37; }
    .edu .edu-read-tag { color: var(--ok); font-size: 12px; font-family: var(--mono); letter-spacing: .04em; }
    .edu .mark-read { background: var(--bg-2); border: 1px solid var(--line-2); color: var(--accent); font: inherit;
      font-size: 12.5px; padding: 6px 12px; border-radius: 2px; cursor: pointer; }
    .edu .mark-read:hover { border-color: var(--accent-deep); }
```

- [ ] **Step 6: Verify lint and unit test pass**

Run: `npm run lint && npm run test:web`
Expected: ESLint exit 0 (no unused-var errors from the removed observer); test run `# pass 7`, `# fail 0`.

- [ ] **Step 7: Commit**

```bash
git add web/course.js web/course.html
git commit -m "feat(course): earned reading via explicit Mark as read (retire scroll observer)"
```

---

## Manual verification checklist (after all tasks)

The course is auth-gated, so browser smokes do not cover it; verify signed-in (owner, via magic link) on the deployed branch or a local `python -m http.server --directory web` with a configured backend:

- [ ] Open a module: **Course material** cards show a **Mark as read** button; scrolling past a card does **not** tick it.
- [ ] Click **Mark as read**: the card flips to **✓ Read** and the rail checkbox ticks.
- [ ] The module ends with a **Mastery check** card offering N questions.
- [ ] Take the check and score below 80%: it shows the score, lists missed questions with explanations, and offers **Retry** (fresh/reshuffled questions).
- [ ] Score 80% or higher: the card shows **Mastered · best NN%**, the rail **Mastery check** sub ticks, the module chip on the overview reads **Mastered**, and **Study next** advances to the next non-mastered module.
- [ ] Reload the page: read marks and mastery result persist (localStorage).

---

## Self-Review

**Spec coverage:**
- Data model (`mrisim_course_mastery_v1`, helpers, constants) → Task 1 (constants) + Task 2 (key, `loadMastery`, `saveMasteryResult`).
- `modulePool` / `MIN_POOL` guard → Task 2 (`modulePool`, `hasMastery`) + Task 3 (`hasMastery` gates sub + UI).
- Mastery-check UI (no feedback until submit, >=80% pass, missed-items + reshuffled retry, passed state, `bumpScore`) → Task 3.
- Earned reading (retire `setupReadObserver`, explicit Mark as read) → Task 4.
- Subsections + `isSubDone` mastery branch + status tiers + `STATUS_LABEL` + Study-next + dashboard unchanged formula → Task 2 (branch/status/labels/gate) + Task 3 (sub emission).
- Pure `deriveModuleStatus` extraction + node unit test + CI → Task 1.
- CSS `.solid` -> `.mastered` and new styles → Task 2 (rename) + Task 3/4 (new blocks).
- Deployment/no-cache-bump → Global Constraints note (no code action).

**Placeholder scan:** No TBD/TODO/"handle edge cases"/"similar to" — every code step carries full code.

**Type consistency:** `deriveModuleStatus(doneCount, subTotal, quizSeen, masteryAttempts, masteryPassed)` identical in the Task 1 module, the Task 1 test, and the Task 2 call site. `isSubDone(s, done, read, mastery)` consistent across its definition (Task 2) and all call sites (Task 2 `computeReadiness`/`buildRail`). The mastery sub shape (`type`, `id`, `modTitle`, `label`, `anchor`) matches `isSubDone`'s `s.modTitle` read and the `mastery-`+slug anchor produced by `masterySection`. `saveMasteryResult(title, pct)` / `loadMastery()` shapes (`passed`, `bestPct`, `attempts`, `ts`) consistent across the producer (Task 2) and consumers (Task 3 `renderMasteryIntro`/`renderMasteryResult`).
