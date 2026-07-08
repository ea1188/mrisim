# Diagnostic Pre-Test (Phase 3.2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A ~10-minute placement test (2 questions per module) that scores each module, stores a separate snapshot, and routes the learner to their weakest modules first without touching earned progress.

**Architecture:** All in `web/course.js` (+ CSS in `web/course.html`), plus two pure node-tested functions in `web/course_logic.js`. The diagnostic reuses the existing exam state machine (`EXAM`, `renderExam`, `selectOpt`, `confirmSubmit`) via a `diagnostic` flag, samples 2 questions per module tagged with the module, scores per module on submit, and stores a snapshot in a new `localStorage` key. The snapshot reorders `computeReadiness`'s `next` (Study next) and surfaces an overview entry card. It does not call `bumpScore` or change readiness/mastery state.

**Tech Stack:** Vanilla ES5 browser JS + CSS, CommonJS pure module, node's test runner.

## Global Constraints

- `web/course.js` / `web/course_logic.js` are ES5-style: `var`, function expressions, the `h(tag, attrs, kids)` builder; `text:` for plain strings. Match the files.
- `web/course_logic.js` is read via the `var CourseLogic = window.CourseLogic;` local alias already in `course.js` (no ESLint global — the `config-protection` hook blocks `eslint.config.mjs`; do NOT edit it).
- No em dashes / AI-tell punctuation in any learner-facing string. Use `·`/`:`/plain sentences.
- The diagnostic is a snapshot: its answers must NOT call `bumpScore` and must NOT write quiz/mastery/read state. New key only: `mrisim_course_diagnostic_v1`.
- No emoji, no gradients, no pills; professional/clinical. No `Co-Authored-By: Claude` trailer.
- `course.js`/`course.html` are network-first SHELL files → no service-worker cache bump.
- Constants: `DIAG_PER_MODULE = 2`.

## File structure

- `web/course_logic.js` — add `rankModulesByDiagnostic` + `diagnosticStudyNext` to the export.
- `web/course_logic.test.mjs` — add unit tests for both.
- `web/course.js` — diagnostic run/score/results + storage helpers + dashboard integration.
- `web/course.html` — diagnostic CSS.

---

## Task 1: Pure ranking + study-next logic

**Files:**
- Modify: `web/course_logic.js`
- Modify: `web/course_logic.test.mjs`

**Interfaces:**
- Produces:
  - `rankModulesByDiagnostic(perModule, curriculumTitles) -> [title, ...]` — all `curriculumTitles` ordered by ascending accuracy (`right/asked`; absent or `asked===0` counts as accuracy 1.0), ties broken by curriculum order.
  - `diagnosticStudyNext(order, statusByTitle) -> title | null` — first title in `order` whose status is not `"mastered"`, else null.

- [ ] **Step 1: Write the failing tests**

In `web/course_logic.test.mjs`, change the destructure line:

```js
const { deriveModuleStatus, PASS_PCT, CHECK_N, MIN_POOL } = CourseLogic;
```

to:

```js
const { deriveModuleStatus, PASS_PCT, CHECK_N, MIN_POOL, rankModulesByDiagnostic, diagnosticStudyNext } = CourseLogic;
```

and append these tests to the end of the file:

```js
test("rankModulesByDiagnostic orders weakest-first; absent module counts as 1.0; curriculum tiebreak", () => {
  const per = { B: { asked: 2, right: 0 }, C: { asked: 2, right: 1 }, A: { asked: 2, right: 2 } };
  // B acc 0, C acc 0.5, A acc 1.0, D absent -> 1.0; A before D by curriculum order.
  assert.deepEqual(rankModulesByDiagnostic(per, ["A", "B", "C", "D"]), ["B", "C", "A", "D"]);
});

test("rankModulesByDiagnostic treats asked=0 as accuracy 1.0", () => {
  assert.deepEqual(rankModulesByDiagnostic({ A: { asked: 0, right: 0 } }, ["A", "B"]), ["A", "B"]);
});

test("diagnosticStudyNext returns first non-mastered title in order", () => {
  assert.equal(diagnosticStudyNext(["B", "C", "A"], { B: "mastered", C: "progress", A: "not-started" }), "C");
});

test("diagnosticStudyNext returns null when all mastered", () => {
  assert.equal(diagnosticStudyNext(["A", "B"], { A: "mastered", B: "mastered" }), null);
});

test("diagnosticStudyNext returns null for empty order", () => {
  assert.equal(diagnosticStudyNext([], {}), null);
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `node --test web/course_logic.test.mjs`
Expected: FAIL (`rankModulesByDiagnostic`/`diagnosticStudyNext` are undefined).

- [ ] **Step 3: Implement both functions**

In `web/course_logic.js`, immediately before the `return {` line, add:

```js
  // Rank all module titles weakest-first by diagnostic accuracy (right/asked). A module absent
  // from perModule or with asked===0 counts as accuracy 1.0 so it does not jump ahead of
  // genuinely weak modules. Ties keep original curriculum order (stable).
  function rankModulesByDiagnostic(perModule, curriculumTitles) {
    perModule = perModule || {};
    var rows = curriculumTitles.map(function (t, i) {
      var rec = perModule[t];
      var acc = (rec && rec.asked) ? rec.right / rec.asked : 1;
      return { title: t, acc: acc, i: i };
    });
    rows.sort(function (a, b) { return a.acc - b.acc || a.i - b.i; });
    return rows.map(function (x) { return x.title; });
  }

  // First title in `order` whose status is not "mastered"; null if none (or order empty).
  function diagnosticStudyNext(order, statusByTitle) {
    order = order || [];
    statusByTitle = statusByTitle || {};
    for (var i = 0; i < order.length; i++) {
      if (statusByTitle[order[i]] !== "mastered") return order[i];
    }
    return null;
  }
```

Then change the export from:

```js
  return {
    PASS_PCT: PASS_PCT, CHECK_N: CHECK_N, MIN_POOL: MIN_POOL,
    deriveModuleStatus: deriveModuleStatus,
  };
```

to:

```js
  return {
    PASS_PCT: PASS_PCT, CHECK_N: CHECK_N, MIN_POOL: MIN_POOL,
    deriveModuleStatus: deriveModuleStatus,
    rankModulesByDiagnostic: rankModulesByDiagnostic,
    diagnosticStudyNext: diagnosticStudyNext,
  };
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `node --test web/course_logic.test.mjs`
Expected: PASS (`# pass 12`, `# fail 0`).

- [ ] **Step 5: Commit**

```bash
git add web/course_logic.js web/course_logic.test.mjs
git commit -m "feat(course): pure diagnostic ranking + study-next logic + tests"
```

---

## Task 2: Diagnostic run, scoring, results, and overview entry

**Files:**
- Modify: `web/course.js`
- Modify: `web/course.html` (CSS)

**Interfaces:**
- Consumes: `CourseLogic.rankModulesByDiagnostic` (Task 1); existing `modulePool`, `shuffleInts`, `beginExam`, `renderExam`, `confirmSubmit`, `openModule`, `renderOverview`, `buildRail`, `computeReadiness`, `h`, `clear`.
- Produces: `startDiagnostic()`, `submitDiagnostic()`, `renderDiagnosticResult(...)`, `loadDiagnostic()`, `saveDiagnostic(d)`, the `mrisim_course_diagnostic_v1` snapshot, and a `diagnostic` branch in the reused exam machine.

- [ ] **Step 1: Add the key + constant**

In `web/course.js`, after the line `var COURSE_MASTERY_KEY = "mrisim_course_mastery_v1"; // per-module mastery-check result` add:

```js
  var COURSE_DIAG_KEY = "mrisim_course_diagnostic_v1"; // placement-test snapshot (separate from progress)
  var DIAG_PER_MODULE = 2;                              // questions sampled per module in the placement test
```

- [ ] **Step 2: Thread a `diagnostic` flag through `beginExam`**

In `web/course.js`, replace `beginExam`:

```js
  function beginExam(questions, timed) {
    stopExam();
    EXAM = {
      questions: questions, picks: questions.map(function () { return -1; }),
      timed: timed, remaining: timed ? questions.length * 60 : 0, elapsed: 0,
      reviewing: false, timer: null,
    };
    CTX.mod = null;
    buildRail();
    renderExam(CTX.main);
    EXAM.timer = setInterval(tickExam, 1000);
  }
```

with (adds an optional `diag` arg carrying the per-question module titles):

```js
  function beginExam(questions, timed, diag) {
    stopExam();
    EXAM = {
      questions: questions, picks: questions.map(function () { return -1; }),
      timed: timed, remaining: timed ? questions.length * 60 : 0, elapsed: 0,
      reviewing: false, timer: null,
      diagnostic: !!diag, modTitles: diag ? diag.modTitles : null,
    };
    CTX.mod = null;
    buildRail();
    renderExam(CTX.main);
    EXAM.timer = setInterval(tickExam, 1000);
  }
```

- [ ] **Step 3: Make `renderExam` heading + submit label diagnostic-aware**

In `web/course.js`, in `renderExam`, replace:

```js
    main.appendChild(h("div", { class: "exam-bar" }, [
      EXAM.barCount, h("span", { class: "sp" }), EXAM.barTimer,
      h("button", { class: "btn eb-submit", text: "Submit exam", onclick: confirmSubmit }),
    ]));
    main.appendChild(h("h2", { text: "Practice exam" }));
```

with:

```js
    main.appendChild(h("div", { class: "exam-bar" }, [
      EXAM.barCount, h("span", { class: "sp" }), EXAM.barTimer,
      h("button", { class: "btn eb-submit", text: EXAM.diagnostic ? "Submit placement test" : "Submit exam", onclick: confirmSubmit }),
    ]));
    main.appendChild(h("h2", { text: EXAM.diagnostic ? "Placement test" : "Practice exam" }));
```

- [ ] **Step 4: Route submit to the diagnostic scorer**

In `web/course.js`, in `submitExam`, replace:

```js
  function submitExam() {
    if (!EXAM || EXAM.reviewing) return;
    EXAM.reviewing = true;
    clearExamTimer();
    var correct = 0;
```

with:

```js
  function submitExam() {
    if (!EXAM || EXAM.reviewing) return;
    EXAM.reviewing = true;
    clearExamTimer();
    if (EXAM.diagnostic) { submitDiagnostic(); return; }
    var correct = 0;
```

- [ ] **Step 5: Add the diagnostic run, scorer, results, and storage helpers**

In `web/course.js`, immediately after the `saveExamBest` function (ends `... } catch (e) { /* storage off */ } }`), add:

```js
  // --- diagnostic placement test ------------------------------------------ //
  // Samples DIAG_PER_MODULE questions from each module (tagged with its title), runs them with no
  // feedback until submit (reusing the exam machine), scores per module, and stores a snapshot that
  // reorders "Study next". Does NOT bump quiz score or change readiness/mastery.
  function loadDiagnostic() { try { return JSON.parse(localStorage.getItem(COURSE_DIAG_KEY) || "null"); } catch (e) { return null; } }
  function saveDiagnostic(d) { try { localStorage.setItem(COURSE_DIAG_KEY, JSON.stringify(d)); } catch (e) { /* storage off */ } }

  function startDiagnostic() {
    var questions = [], modTitles = [];
    CTX.curriculum.forEach(function (mod) {
      var pool = modulePool(mod);
      var pick = shuffleInts(pool.length).slice(0, Math.min(DIAG_PER_MODULE, pool.length));
      pick.forEach(function (idx) {
        var q = pool[idx];
        questions.push({ q: q, order: shuffleInts(q.options.length) });
        modTitles.push(mod.title);
      });
    });
    if (!questions.length) { renderOverview(); return; }
    beginExam(questions, false, { modTitles: modTitles });
  }

  function submitDiagnostic() {
    var per = {}, correct = 0;
    EXAM.questions.forEach(function (item, qi) {
      var t = EXAM.modTitles[qi];
      var rec = per[t] || (per[t] = { asked: 0, right: 0 });
      rec.asked += 1;
      if (EXAM.picks[qi] === item.q.answer) { rec.right += 1; correct += 1; }
    });
    var titles = CTX.curriculum.map(function (m) { return m.title; });
    var order = CourseLogic.rankModulesByDiagnostic(per, titles);
    saveDiagnostic({ taken: true, ts: Date.now(), perModule: per, order: order });
    renderDiagnosticResult(per, order, correct, EXAM.questions.length);
    buildRail();
  }

  function renderDiagnosticResult(per, order, correct, total) {
    var main = CTX.main; clear(main);
    var pct = Math.round(100 * correct / total);
    main.appendChild(h("h2", { text: "Placement results" }));
    main.appendChild(h("div", { class: "exam-result" }, [
      h("div", { class: "er-score", text: correct + " / " + total }),
      h("div", { class: "er-pct", text: pct + "%" }),
      h("div", { class: "er-meta", text: "A snapshot to plan your studying. It does not change your progress." }),
    ]));
    main.appendChild(h("h3", { class: "ready-h", text: "By module, weakest first" }));
    var grid = h("div", { class: "diag-grid" });
    order.forEach(function (t) {
      var rec = per[t] || { asked: 0, right: 0 };
      var a = rec.asked ? Math.round(100 * rec.right / rec.asked) : null;
      grid.appendChild(h("div", { class: "diag-row" }, [
        h("span", { class: "dr-title", text: t }),
        h("span", { class: "dr-acc", text: a == null ? "not tested" : a + "%" }),
        h("div", { class: "bar" }, [h("i", { style: "width:" + (a == null ? 0 : a) + "%" })]),
      ]));
    });
    main.appendChild(grid);
    var startMod = null;
    for (var i = 0; i < CTX.curriculum.length; i++) { if (CTX.curriculum[i].title === order[0]) { startMod = CTX.curriculum[i]; break; } }
    var actions = h("div", { class: "er-actions" });
    if (startMod) actions.appendChild(h("button", { class: "btn", type: "button", text: "Start with " + order[0], onclick: function () { openModule(startMod); } }));
    actions.appendChild(h("button", { class: "btn ghost", type: "button", text: "Retake", onclick: startDiagnostic }));
    actions.appendChild(h("button", { class: "btn ghost", type: "button", text: "Back to overview", onclick: renderOverview }));
    main.appendChild(actions);
    window.scrollTo(0, 0);
  }
```

- [ ] **Step 6: Add the overview entry card**

In `web/course.js`, in `renderOverview`, find:

```js
    main.appendChild(h("button", { class: "btn ghost-cta", type: "button", onclick: openExam, text: "Take a practice exam" }));
    main.appendChild(h("h3", { class: "ready-h", text: "By module" }));
```

and insert the diagnostic card between them:

```js
    main.appendChild(h("button", { class: "btn ghost-cta", type: "button", onclick: openExam, text: "Take a practice exam" }));
    if (!loadDiagnostic()) {
      main.appendChild(h("div", { class: "diag-card" }, [
        h("h3", { text: "New here? Take the placement test" }),
        h("p", { text: "20 questions across every topic, about 10 minutes. It finds your weakest areas and points you where to start. It does not affect your progress." }),
        h("button", { class: "btn", type: "button", text: "Start the placement test", onclick: startDiagnostic }),
      ]));
    } else {
      main.appendChild(h("p", { class: "diag-note" }, [
        document.createTextNode("Placement test taken. "),
        h("button", { type: "button", class: "diag-retake", text: "Retake", onclick: startDiagnostic }),
      ]));
    }
    main.appendChild(h("h3", { class: "ready-h", text: "By module" }));
```

- [ ] **Step 7: Add CSS**

In `web/course.html`, after the `.exam-result { ... }` rule, add:

```css
    .diag-card { background: var(--panel); border: 1px solid var(--line); border-radius: 2px; padding: 18px 20px; margin: 14px 0 0; }
    .diag-card h3 { margin: 0 0 6px; font-size: 15px; }
    .diag-card p { color: var(--muted); font-size: 13px; line-height: 1.6; margin: 0 0 12px; }
    .diag-note { color: var(--dim); font-size: 12px; margin: 12px 0 0; }
    .diag-retake { background: none; border: none; color: var(--accent); font: inherit; font-size: 12px; text-decoration: underline; cursor: pointer; padding: 0; }
    .diag-grid { display: flex; flex-direction: column; gap: 6px; margin-top: 6px; }
    .diag-row { display: grid; grid-template-columns: 1fr auto; align-items: center; gap: 8px 12px; padding: 8px 12px; background: var(--panel); border: 1px solid var(--line); border-radius: 2px; }
    .diag-row .dr-title { font-size: 13.5px; }
    .diag-row .dr-acc { font-family: var(--mono); font-size: 11px; color: var(--dim); }
    .diag-row .bar { grid-column: 1 / -1; }
```

- [ ] **Step 8: Verify lint + tests**

Run: `npm run lint && npm run test:web`
Expected: ESLint exit 0; test run `# pass 12`, `# fail 0`. The placement card is reachable from the overview; the diagnostic runs, scores, and shows results.

- [ ] **Step 9: Commit**

```bash
git add web/course.js web/course.html
git commit -m "feat(course): diagnostic placement test run, scoring, results + overview entry"
```

---

## Task 3: Dashboard study-next reorder + rail entry

**Files:**
- Modify: `web/course.js` (`computeReadiness` next-override; `buildRail` rail entry)

**Interfaces:**
- Consumes: `CourseLogic.diagnosticStudyNext` (Task 1); `loadDiagnostic` (Task 2).
- Produces: `computeReadiness` returns `next` respecting the diagnostic order and includes `diagnostic` in its result; a "Placement test" rail button.

- [ ] **Step 1: Reorder `next` by the diagnostic in `computeReadiness`**

In `web/course.js`, in `computeReadiness`, replace:

```js
    var next = null;
    for (var i = 0; i < modules.length; i++) { if (modules[i].status !== "mastered") { next = modules[i]; break; } }
    return { modules: modules, overall: overall, band: band, next: next, exam: exam,
      quizAcc: Math.round(100 * quizAcc), readPct: Math.round(100 * readPct) };
```

with:

```js
    var next = null;
    for (var i = 0; i < modules.length; i++) { if (modules[i].status !== "mastered") { next = modules[i]; break; } }
    var diag = loadDiagnostic();
    if (diag && diag.order) {
      var statusByTitle = {};
      modules.forEach(function (m) { statusByTitle[m.mod.title] = m.status; });
      var t = CourseLogic.diagnosticStudyNext(diag.order, statusByTitle);
      if (t) {
        for (var k = 0; k < modules.length; k++) { if (modules[k].mod.title === t) { next = modules[k]; break; } }
      }
    }
    return { modules: modules, overall: overall, band: band, next: next, exam: exam, diagnostic: diag,
      quizAcc: Math.round(100 * quizAcc), readPct: Math.round(100 * readPct) };
```

- [ ] **Step 2: Add a "Placement test" rail button (and stop the exam button lighting during a diagnostic)**

In `web/course.js`, in `buildRail`, replace:

```js
    rail.appendChild(h("button", { class: "exam-cta" + (EXAM ? " on" : ""), type: "button", onclick: openExam }, [
      document.createTextNode("Practice exam"),
      h("span", { class: "ec-sub", text: "Registry-style run across the whole bank" }),
    ]));
```

with:

```js
    rail.appendChild(h("button", { class: "exam-cta" + (EXAM && !EXAM.diagnostic ? " on" : ""), type: "button", onclick: openExam }, [
      document.createTextNode("Practice exam"),
      h("span", { class: "ec-sub", text: "Registry-style run across the whole bank" }),
    ]));
    rail.appendChild(h("button", { class: "exam-cta" + (EXAM && EXAM.diagnostic ? " on" : ""), type: "button", onclick: startDiagnostic }, [
      document.createTextNode("Placement test"),
      h("span", { class: "ec-sub", text: "Find your weakest areas first" }),
    ]));
```

- [ ] **Step 3: Verify lint + tests**

Run: `npm run lint && npm run test:web`
Expected: ESLint exit 0; test run `# pass 12`, `# fail 0`.

- [ ] **Step 4: Commit**

```bash
git add web/course.js
git commit -m "feat(course): study-next follows diagnostic result + placement rail entry"
```

---

## Manual verification checklist (after all tasks)

Signed-in (owner, via magic link), since the course is auth-gated:
- [ ] The overview shows a "Take the placement test" card (before taking); the rail has a "Placement test" entry.
- [ ] Starting it runs 20 questions with no feedback; image questions show their scan; a submit confirm warns on blanks.
- [ ] Submitting shows a per-module breakdown (weakest first), a "Start with <weakest>" button, and Retake.
- [ ] Back on the overview, the card is replaced by "Placement test taken · Retake", and "Study next" points at the weakest non-mastered module (not necessarily module 1).
- [ ] Quiz accuracy / readiness % are unchanged by the diagnostic (it does not pollute progress).
- [ ] Reload persists the snapshot; Retake overwrites it.

---

## Self-Review

**Spec coverage:**
- Snapshot key + shape → Task 2 (Step 1 key, Step 5 `saveDiagnostic` writes `{taken,ts,perModule,order}`).
- Pure ranking + study-next → Task 1.
- 2/module sampling, no-feedback run, image support → Task 2 (`startDiagnostic` uses `DIAG_PER_MODULE` + reuses `renderExam` which already calls `addQImg`).
- Per-module scoring + results screen → Task 2 (`submitDiagnostic` + `renderDiagnosticResult`).
- No progress pollution → Task 2 (`submitDiagnostic` never calls `bumpScore`).
- Dashboard reorder of Study next + entry card → Task 2 (card) + Task 3 (next-override).
- Retakeable → Task 2 (`startDiagnostic` from the card/results/rail; `saveDiagnostic` overwrites).
- Node test → Task 1.

**Placeholder scan:** every code step carries complete code; no TBD/"similar to"/vague steps.

**Type consistency:** `perModule` shape `{title:{asked,right}}` and `order` (array of titles) are identical across `rankModulesByDiagnostic` (Task 1), `submitDiagnostic`/`saveDiagnostic` (Task 2), and the `computeReadiness` consumer (Task 3). `diagnosticStudyNext(order, statusByTitle)` signature matches its Task 3 call. `EXAM.diagnostic`/`EXAM.modTitles` set in `beginExam` (Task 2 Step 2) are read in `renderExam` (Step 3), `submitExam` (Step 4), `submitDiagnostic` (Step 5), and `buildRail` (Task 3 Step 2). `COURSE_DIAG_KEY`/`DIAG_PER_MODULE` declared in Task 2 Step 1 and used throughout.
