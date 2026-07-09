# ARRT Blueprint Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show the student their registry readiness mapped to the real ARRT MRI content categories, weighted the way the actual exam is weighted, as a panel on the course page.

**Architecture:** A pure, unit-tested logic module (`web/blueprint.js`) holds the verified ARRT blueprint constant and computes readiness from the quiz progress already in `localStorage`. A render function in `web/course.js` reads that key, calls the module, and injects a "Registry readiness" panel into the existing course overview. No backend, no migration, no network.

**Tech Stack:** Vanilla ES5-style UMD JavaScript (matches `web/assignments.js`), Node's built-in test runner (`node --test`, `.mjs`), plain CSS with the site's design tokens.

## Global Constraints

- No backend: pure client-side from `localStorage`. No Supabase migration, no reseed.
- Blueprint numbers verbatim from the verified ARRT spec: scored 16 / 21 / 106 / 57 (total 200); weights 0.080 / 0.105 / 0.530 / 0.285.
- Mapping (each of the 8 quiz categories in exactly one ARRT category): Image Production = `sequences`, `image-quality`, `artifacts`, `perfusion`; Procedures = `pathology`, `anatomy`; Safety = `safety`; Patient Care = `patient-care`.
- Procedures row carries the exact note: "Covers pathology and anatomy. Positioning, coils, and protocol are practiced in Protocol Planning."
- Copy: no em dashes, no AI-tell punctuation; natural prose.
- Aesthetic: clinical/professional. No emoji, no gradients. 2px corners, flat solid accent bars, tabular numerals. Use existing CSS tokens (`--accent`, `--line`, `--line-2`, `--panel`, `--muted`, `--dim`, `--text`, `--mono`).
- Code style matches `web/assignments.js`: `var`, function expressions, UMD wrapper. Must pass `eslint web/`.
- No `Co-Authored-By: Claude` trailers on commits.
- Before merge: `ruff check src/ tests/` (CI gate; no Python changes expected) and `npm run test:web` + `npm run lint`.

---

### Task 1: `web/blueprint.js` pure module + tests

**Files:**
- Create: `web/blueprint.js`
- Test: `web/blueprint.test.mjs`
- Modify: `package.json` (add the new test file to the `test:web` script)

**Interfaces:**
- Consumes: nothing (leaf module).
- Produces:
  - `ARRT_BLUEPRINT` — array of 4 objects, each `{ key: string, name: string, scored: number, weight: number, members: string[], note?: string }`, ordered by `weight` descending (Image Production first).
  - `readiness(progress)` where `progress` is the parsed `mrisim_quiz_progress_v1` object `{ [categoryId]: { best: number, total: number, runs: number } }`. Returns:
    ```
    {
      categories: [ { key, name, scored, weight, note|null,
                      accuracy: number|null, coverage: number,
                      attempted: number, memberCount: number } ],  // 4, weight-desc
      projected: number,   // 0..1, sum of (accuracyOrZero * weight)
      coverage: number     // 0..1, sum of (categoryCoverage * weight)
    }
    ```
  - Browser global `window.Blueprint`; Node `module.exports` (UMD, like `web/assignments.js`).

- [ ] **Step 1: Write the failing tests**

Create `web/blueprint.test.mjs`:

```js
import { test } from "node:test";
import assert from "node:assert/strict";
import B from "./blueprint.js";

const KNOWN_CATEGORIES = [
  "sequences", "pathology", "perfusion", "artifacts",
  "anatomy", "image-quality", "safety", "patient-care",
];

test("blueprint integrity: scored sums to 200, weights to 1.0, 8 categories mapped once", () => {
  const scored = B.ARRT_BLUEPRINT.reduce((s, c) => s + c.scored, 0);
  assert.equal(scored, 200);
  const weight = B.ARRT_BLUEPRINT.reduce((s, c) => s + c.weight, 0);
  assert.ok(Math.abs(weight - 1.0) < 1e-9, `weights sum to ${weight}`);
  const members = B.ARRT_BLUEPRINT.flatMap((c) => c.members).sort();
  assert.deepEqual(members, [...KNOWN_CATEGORIES].sort());
});

test("blueprint is ordered by weight descending (Image Production first)", () => {
  assert.equal(B.ARRT_BLUEPRINT[0].name, "Image Production");
  const w = B.ARRT_BLUEPRINT.map((c) => c.weight);
  for (let i = 1; i < w.length; i++) assert.ok(w[i] <= w[i - 1]);
});

test("Procedures carries the honesty note; single-member categories carry none", () => {
  const proc = B.ARRT_BLUEPRINT.find((c) => c.name === "Procedures");
  assert.match(proc.note, /Positioning, coils, and protocol are practiced in Protocol Planning/);
  const safety = B.ARRT_BLUEPRINT.find((c) => c.name === "Safety");
  assert.ok(!safety.note);
});

test("empty progress: every category not-started, overall zero", () => {
  const r = B.readiness({});
  assert.equal(r.projected, 0);
  assert.equal(r.coverage, 0);
  r.categories.forEach((c) => {
    assert.equal(c.accuracy, null);
    assert.equal(c.coverage, 0);
    assert.equal(c.attempted, 0);
  });
});

test("full progress: per-category accuracy and weighted overall match hand math", () => {
  const progress = {
    sequences: { best: 8, total: 10, runs: 1 },
    "image-quality": { best: 6, total: 10, runs: 1 },
    artifacts: { best: 5, total: 10, runs: 1 },
    perfusion: { best: 1, total: 10, runs: 1 },
    pathology: { best: 7, total: 10, runs: 1 },
    anatomy: { best: 3, total: 10, runs: 1 },
    safety: { best: 9, total: 10, runs: 1 },
    "patient-care": { best: 8, total: 10, runs: 1 },
  };
  const r = B.readiness(progress);
  const ip = r.categories.find((c) => c.key === "image-production");
  assert.ok(Math.abs(ip.accuracy - 0.5) < 1e-9);   // (8+6+5+1)/(40) = 0.5
  assert.equal(ip.coverage, 1);                     // 4 of 4 members
  const proc = r.categories.find((c) => c.key === "procedures");
  assert.ok(Math.abs(proc.accuracy - 0.5) < 1e-9);  // (7+3)/20
  // projected = .5*.53 + .5*.285 + .9*.105 + .8*.08 = 0.566
  assert.ok(Math.abs(r.projected - 0.566) < 1e-9);
  assert.ok(Math.abs(r.coverage - 1.0) < 1e-9);
});

test("partial: only one member of Image Production attempted", () => {
  const r = B.readiness({ sequences: { best: 8, total: 10, runs: 1 } });
  const ip = r.categories.find((c) => c.key === "image-production");
  assert.ok(Math.abs(ip.accuracy - 0.8) < 1e-9);   // only sequences counted
  assert.equal(ip.coverage, 0.25);                  // 1 of 4 members
  assert.equal(ip.attempted, 1);
  assert.ok(Math.abs(r.projected - 0.8 * 0.53) < 1e-9);
});

test("unattempted category contributes null accuracy and 0 to projected", () => {
  const r = B.readiness({ safety: { best: 9, total: 10, runs: 1 } });
  const pc = r.categories.find((c) => c.key === "patient-care");
  assert.equal(pc.accuracy, null);
  const safety = r.categories.find((c) => c.key === "safety");
  assert.ok(Math.abs(r.projected - safety.accuracy * 0.105) < 1e-9);
});

test("thin sample reads as high accuracy but low coverage", () => {
  const r = B.readiness({ artifacts: { best: 3, total: 3, runs: 1 } });
  const ip = r.categories.find((c) => c.key === "image-production");
  assert.equal(ip.accuracy, 1);
  assert.equal(ip.coverage, 0.25);
});

test("readiness tolerates missing/garbage progress", () => {
  assert.doesNotThrow(() => B.readiness(undefined));
  assert.doesNotThrow(() => B.readiness(null));
  // a member with total 0 or missing is not attempted
  const r = B.readiness({ safety: { best: 0, total: 0, runs: 2 } });
  assert.equal(r.categories.find((c) => c.key === "safety").accuracy, null);
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `node --test web/blueprint.test.mjs`
Expected: FAIL — cannot resolve `./blueprint.js` (module does not exist yet).

- [ ] **Step 3: Write `web/blueprint.js`**

```js
/*
 * Blueprint — pure logic mapping the course's quiz categories onto the official
 * ARRT MRI content categories and computing weighted registry readiness. UMD like
 * assignments.js: window.Blueprint in the browser, module.exports under Node.
 * Numbers are verbatim from the ARRT MRI Content Specifications (Board Approved
 * January 2024, implementation February 1, 2025): 200 scored questions.
 * No DOM, no network.
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.Blueprint = factory();
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  // Ordered by exam weight, descending, so the render mirrors where the exam's mass sits.
  var ARRT_BLUEPRINT = [
    { key: "image-production", name: "Image Production", scored: 106, weight: 0.530,
      members: ["sequences", "image-quality", "artifacts", "perfusion"] },
    { key: "procedures", name: "Procedures", scored: 57, weight: 0.285,
      members: ["pathology", "anatomy"],
      note: "Covers pathology and anatomy. Positioning, coils, and protocol are practiced in Protocol Planning." },
    { key: "safety", name: "Safety", scored: 21, weight: 0.105,
      members: ["safety"] },
    { key: "patient-care", name: "Patient Care", scored: 16, weight: 0.080,
      members: ["patient-care"] },
  ];

  function isAttempted(entry) {
    return !!entry && typeof entry.total === "number" && entry.total > 0;
  }

  // progress = mrisim_quiz_progress_v1: { categoryId: { best, total, runs } }
  function readiness(progress) {
    var prog = progress || {};
    var categories = ARRT_BLUEPRINT.map(function (c) {
      var right = 0, asked = 0, attempted = 0;
      c.members.forEach(function (m) {
        var e = prog[m];
        if (!isAttempted(e)) return;
        attempted += 1;
        right += (typeof e.best === "number" ? e.best : 0);
        asked += e.total;
      });
      return {
        key: c.key, name: c.name, scored: c.scored, weight: c.weight, note: c.note || null,
        accuracy: asked > 0 ? right / asked : null,
        coverage: c.members.length ? attempted / c.members.length : 0,
        attempted: attempted, memberCount: c.members.length,
      };
    });
    var projected = 0, coverage = 0;
    categories.forEach(function (c) {
      projected += (c.accuracy || 0) * c.weight;
      coverage += c.coverage * c.weight;
    });
    return { categories: categories, projected: projected, coverage: coverage };
  }

  return { ARRT_BLUEPRINT: ARRT_BLUEPRINT, readiness: readiness };
});
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `node --test web/blueprint.test.mjs`
Expected: PASS — all tests green.

- [ ] **Step 5: Wire the test file into the suite**

In `package.json`, the `test:web` script currently ends with `web/assignments.test.mjs`. Append ` web/blueprint.test.mjs`:

```json
    "test:web": "node --test web/course_logic.test.mjs web/auth_url.test.mjs web/join_link.test.mjs web/class_insight.test.mjs web/assignments.test.mjs web/blueprint.test.mjs"
```

- [ ] **Step 6: Run the full web suite and lint**

Run: `npm run test:web && npm run lint`
Expected: all web tests PASS (including the existing ones), eslint reports no errors.

- [ ] **Step 7: Commit**

```bash
git add web/blueprint.js web/blueprint.test.mjs package.json
git commit -m "feat(course): ARRT blueprint readiness module (pure logic + tests)"
```

---

### Task 2: Registry readiness panel on the course page

**Files:**
- Modify: `web/course.html` (add `blueprint.js` script tag before `course.js`; add panel CSS)
- Modify: `web/course.js` (`renderOverview` injects the panel via a new `appendReadiness` helper)

**Interfaces:**
- Consumes: `window.Blueprint.readiness(progress)` and `window.Blueprint.ARRT_BLUEPRINT` from Task 1; the existing `h(tag, attrs, kids)` DOM helper and `CTX.main` in `course.js`.
- Produces: no exported API. A visual panel appended to the overview.

- [ ] **Step 1: Add the script tag in `web/course.html`**

The script block (near line 337-341) loads `config.js`, `accounts.js`, `course_logic.js`, `assignments.js`, `course.js`. Insert `blueprint.js` immediately before `course.js`:

```html
    <script src="assignments.js"></script>
    <script src="blueprint.js"></script>
    <script src="course.js"></script>
```

- [ ] **Step 2: Add the panel CSS in `web/course.html`**

Inside the existing `<style>` block (append near the other overview styles, e.g. after the `.ready` / `.diag-card` rules). All colors come from existing tokens; bars are flat solid accent, corners 2px:

```css
    .blueprint { margin: 30px 0 8px; }
    .bp-h { font-family: var(--mono); font-size: 10.5px; text-transform: uppercase;
      letter-spacing: .12em; color: var(--dim); margin: 0 0 14px; }
    .bp-head { display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 20px; margin-bottom: 8px; }
    .bp-num { font-size: 30px; font-weight: 650; color: var(--text); line-height: 1;
      font-variant-numeric: tabular-nums; }
    .bp-lbl { font-size: 12px; color: var(--muted); margin-top: 5px; }
    .bp-cov { font-size: 12.5px; color: var(--muted); }
    .bp-row { padding: 13px 0; border-top: 1px solid var(--line); }
    .bp-row:first-of-type { border-top: none; }
    .bp-row-top { display: flex; align-items: baseline; gap: 10px; margin-bottom: 8px; }
    .bp-name { font-size: 14px; color: var(--text); }
    .bp-chip { font-family: var(--mono); font-size: 10px; letter-spacing: .04em; color: var(--accent);
      border: 1px solid var(--line-2); border-radius: 2px; padding: 2px 7px; white-space: nowrap; }
    .bp-acc { margin-left: auto; font-size: 13px; color: var(--muted); font-variant-numeric: tabular-nums; }
    .bp-acc.none { color: var(--dim); }
    .blueprint .bar { height: 6px; background: var(--line); border-radius: 2px; overflow: hidden; }
    .blueprint .bar > i { display: block; height: 100%; background: var(--accent); }
    .bp-cov-line { font-size: 11.5px; color: var(--dim); margin-top: 7px; }
    .bp-note { font-size: 11.5px; color: var(--muted); margin-top: 7px; }
```

- [ ] **Step 3: Add the `appendReadiness` helper and the quiz-progress reader in `web/course.js`**

Near the other localStorage helpers (e.g. right after `loadQuiz`/`COURSE_QUIZ_KEY` around line 196), add a reader for the standalone quiz's progress key and the panel builder. `mrisim_quiz_progress_v1` is written by `web/quiz.js`.

```js
  var QUIZ_PROGRESS_KEY = "mrisim_quiz_progress_v1";
  function loadQuizProgress() {
    try { return JSON.parse(localStorage.getItem(QUIZ_PROGRESS_KEY) || "{}"); }
    catch (e) { return {}; }
  }

  // "Registry readiness" panel: quiz accuracy mapped onto the ARRT content categories,
  // weighted by each category's exam share. Reads the standalone quiz's local progress.
  function appendReadiness(main) {
    if (!window.Blueprint) return;
    var rd = Blueprint.readiness(loadQuizProgress());
    var panel = h("div", { class: "blueprint" }, [
      h("h3", { class: "bp-h", text: "Readiness by ARRT content category" }),
      h("div", { class: "bp-head" }, [
        h("div", {}, [
          h("div", { class: "bp-num", text: Math.round(rd.projected * 100) + "%" }),
          h("div", { class: "bp-lbl", text: "projected, weighted by ARRT exam share" }),
        ]),
        h("div", { class: "bp-cov", text: "You have practiced " + Math.round(rd.coverage * 100)
          + "% of the weighted blueprint" }),
      ]),
    ]);
    rd.categories.forEach(function (c) {
      var pct = c.accuracy == null ? null : Math.round(c.accuracy * 100);
      var row = h("div", { class: "bp-row" }, [
        h("div", { class: "bp-row-top" }, [
          h("span", { class: "bp-name", text: c.name }),
          h("span", { class: "bp-chip", text: Math.round(c.weight * 100) + "% of exam" }),
          h("span", { class: "bp-acc" + (pct == null ? " none" : ""),
            text: pct == null ? "Not started" : pct + "%" }),
        ]),
        h("div", { class: "bar" }, [h("i", { style: "width:" + (pct == null ? 0 : pct) + "%" })]),
        h("div", { class: "bp-cov-line", text: c.attempted + " of " + c.memberCount
          + " topic" + (c.memberCount === 1 ? "" : "s") + " practiced" }),
      ]);
      if (c.note) row.appendChild(h("div", { class: "bp-note", text: c.note }));
      panel.appendChild(row);
    });
    main.appendChild(panel);
  }
```

- [ ] **Step 4: Call `appendReadiness` in `renderOverview`**

In `renderOverview` (around line 338), the "By module" heading is appended with
`main.appendChild(h("h3", { class: "ready-h", text: "By module" }));`. Insert the
readiness panel on the line immediately before it, so the flow is: progress number,
practice CTAs, placement/review cards, ARRT readiness breakdown, then By module.

```js
    appendReadiness(main);
    main.appendChild(h("h3", { class: "ready-h", text: "By module" }));
```

- [ ] **Step 5: Verify in a browser**

Open `web/course.html` in a browser (signed in / entitled, or via the usual local flow). Confirm:
- The "Readiness by ARRT content category" panel renders under the progress section.
- Four rows appear in this order: Image Production (53% of exam), Procedures (28% of exam), Safety (10% of exam), Patient Care (8% of exam).
- With no quiz progress, every row shows "Not started" and the headline reads 0% projected, 0% practiced.
- After a quiz run on one topic (via `quiz.html`), that topic's ARRT category shows an accuracy bar and coverage line, the projected/coverage headline moves, and the Procedures row shows the positioning/coils/protocol note.

- [ ] **Step 6: Run lint and the web suite**

Run: `npm run lint && npm run test:web`
Expected: eslint clean; all web tests pass (Task 1's still green; no new node tests here since this task is DOM rendering).

- [ ] **Step 7: Commit**

```bash
git add web/course.html web/course.js
git commit -m "feat(course): render ARRT registry-readiness panel on the course overview"
```

---

## Self-Review

**1. Spec coverage:**
- Verified blueprint numbers (16/21/106/57, weights .080/.105/.530/.285) → Task 1 `ARRT_BLUEPRINT` + integrity test. Covered.
- Mapping (8 categories → 4, each once) → Task 1 constant + integrity test asserting the member union equals the 8 known ids. Covered.
- Procedures honesty note → Task 1 constant + test; Task 2 renders `.bp-note`. Covered.
- Readiness signal from `mrisim_quiz_progress_v1`, accuracy = right/asked, coverage = attempted/members → Task 1 `readiness` + tests. Covered.
- Overall `projected` (unattempted = 0) and `coverage` (weighted) → Task 1 + full/partial/unattempted tests. Covered.
- Unattempted shows "Not started", never 0 → Task 1 (`accuracy: null`) + Task 2 (`.bp-acc.none` / "Not started"). Covered.
- Placement: panel on the course page, ordered by exam weight → Task 2 + browser check. Covered.
- Aesthetic (flat bars, 2px corners, tabular nums, no emoji/gradients) → Task 2 CSS from tokens. Covered.
- No backend / no migration → whole plan is client-side. Covered.

**2. Placeholder scan:** No TBD/TODO/"handle edge cases"/"similar to". Every code step shows complete code. Clean.

**3. Type consistency:** `readiness` return shape (`categories[].{key,name,scored,weight,note,accuracy,coverage,attempted,memberCount}`, `projected`, `coverage`) is defined identically in the Interfaces block, produced by Task 1's implementation, and consumed field-by-field by Task 2's `appendReadiness`. Category `key` values (`image-production`, `procedures`, `safety`, `patient-care`) are used consistently in tests and constant. Consistent.
