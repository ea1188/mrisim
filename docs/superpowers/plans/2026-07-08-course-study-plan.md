# Study Schedule (Phase 4.2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A "Your study plan" dashboard panel listing the remaining modules in recommended order with a target-date weekly pace.

**Architecture:** Two pure node-tested functions in `web/course_logic.js` (`remainingStudyOrder`, `pacePerWeek`); a study-plan panel in `renderOverview` (course.js) with a local-only target-date input; CSS in course.html. No backend, no content, no cache bump.

**Tech Stack:** Vanilla ES5 browser JS + CSS, CommonJS pure module, node's test runner.

## Global Constraints

- `course.js` / `course_logic.js` are ES5-style: `var`, function expressions, the `h(tag, attrs, kids)` builder with `text:` for strings. Match the files. The `.mjs` test is standard ESM.
- `course.js` reads `CourseLogic` via the existing `var CourseLogic = window.CourseLogic;` alias. No `eslint.config.mjs` edit (config-protection hook; no new globals needed).
- The target date is **local-only** (`mrisim_course_target_v1`, `{date: "YYYY-MM-DD"}`); NOT added to `PROGRESS_KEYS`.
- Pacing is per **week**. Next-action labels: `not-started` → "Start the material", `progress` → "Keep going", `review` → "Retake the mastery check".
- No em dashes / AI-tell punctuation in learner-facing strings. No emoji, gradients, pills. No `Co-Authored-By: Claude` trailer. `course.js`/`course.html` are network-first SHELL (no cache bump).

## File structure

- `web/course_logic.js` — add `remainingStudyOrder`, `pacePerWeek` to the export.
- `web/course_logic.test.mjs` — tests.
- `web/course.js` — `COURSE_TARGET_KEY`, `loadTarget`/`saveTarget`, study-plan panel in `renderOverview`.
- `web/course.html` — panel CSS.

---

## Task 1: Pure study-order + pacing logic

**Files:**
- Modify: `web/course_logic.js`
- Modify: `web/course_logic.test.mjs`

**Interfaces:**
- Produces: `remainingStudyOrder(modules, order) -> [title]` (non-mastered titles, diagnostic-first then module order); `pacePerWeek(remaining, targetMs, nowMs) -> {weeks, perWeek} | null`.

- [ ] **Step 1: Write the failing tests**

In `web/course_logic.test.mjs`, add `remainingStudyOrder, pacePerWeek` to the destructure line, then append:

```js
test("remainingStudyOrder: diagnostic weakest-first, mastered dropped, rest appended in module order", () => {
  const modules = [{ title: "A", status: "mastered" }, { title: "B", status: "progress" }, { title: "C", status: "not-started" }, { title: "D", status: "review" }];
  assert.deepEqual(remainingStudyOrder(modules, ["A", "C", "B"]), ["C", "B", "D"]);
});

test("remainingStudyOrder: no diagnostic falls back to module order; all mastered gives []", () => {
  assert.deepEqual(remainingStudyOrder([{ title: "A", status: "progress" }, { title: "B", status: "not-started" }], null), ["A", "B"]);
  assert.deepEqual(remainingStudyOrder([{ title: "A", status: "mastered" }], ["A"]), []);
});

test("pacePerWeek: math, past date null, zero remaining null, sub-week rounds to 1 week", () => {
  const now = 0, D = 86400000;
  assert.deepEqual(pacePerWeek(8, 28 * D, now), { weeks: 4, perWeek: 2 });
  assert.equal(pacePerWeek(4, -D, now), null);
  assert.equal(pacePerWeek(0, 28 * D, now), null);
  assert.deepEqual(pacePerWeek(3, 2 * D, now), { weeks: 1, perWeek: 3 });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `node --test web/course_logic.test.mjs`
Expected: FAIL (`remainingStudyOrder`/`pacePerWeek` undefined).

- [ ] **Step 3: Implement**

In `web/course_logic.js`, immediately before the `return {` line, add:

```js
  // Non-mastered module titles in recommended study order: diagnostic weakest-first where available
  // (order = the diagnostic order array or null), then any remaining non-mastered in module order.
  // modules = [{ title, status }].
  function remainingStudyOrder(modules, order) {
    modules = modules || [];
    var statusByTitle = {}, remaining = [];
    modules.forEach(function (m) { statusByTitle[m.title] = m.status; if (m.status !== "mastered") remaining.push(m.title); });
    if (!order || !order.length) return remaining;
    var out = [], seen = {};
    order.forEach(function (t) { if (statusByTitle[t] && statusByTitle[t] !== "mastered") { out.push(t); seen[t] = 1; } });
    remaining.forEach(function (t) { if (!seen[t]) out.push(t); });
    return out;
  }

  // Weeks until target and modules/week needed to finish `remaining` modules by targetMs.
  // Returns null when nothing remains or the target is not in the future.
  function pacePerWeek(remaining, targetMs, nowMs) {
    if (!remaining || remaining <= 0) return null;
    var ms = targetMs - nowMs;
    if (!(ms > 0)) return null;
    var weeks = Math.max(1, Math.ceil(ms / (7 * 86400000)));
    return { weeks: weeks, perWeek: Math.ceil(remaining / weeks) };
  }
```

Then add `remainingStudyOrder: remainingStudyOrder, pacePerWeek: pacePerWeek,` to the returned export object (after `isCourseComplete: isCourseComplete,`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `node --test web/course_logic.test.mjs`
Expected: PASS (`# pass 24`, `# fail 0`).

- [ ] **Step 5: Commit**

```bash
git add web/course_logic.js web/course_logic.test.mjs
git commit -m "feat(course): pure remainingStudyOrder + pacePerWeek + tests"
```

---

## Task 2: Study-plan panel

**Files:**
- Modify: `web/course.js`
- Modify: `web/course.html` (CSS)

**Interfaces:**
- Consumes: `CourseLogic.remainingStudyOrder`/`pacePerWeek` (Task 1); existing `renderOverview` locals `r` (with `r.modules[].mod`, `r.modules[].status`, `r.diagnostic.order`), `openModule`, `h`.
- Produces: `COURSE_TARGET_KEY`, `loadTarget()`/`saveTarget(dateStr)`, and the study-plan panel.

- [ ] **Step 1: Add the key + state helpers**

In `web/course.js`, after the line `var COURSE_COMPLETE_KEY = "mrisim_course_completed_v1"; // first course-completion record (synced)` add:

```js
  var COURSE_TARGET_KEY = "mrisim_course_target_v1"; // study-plan target date (local-only, not synced)
```

Then, immediately after the `saveExamBest` function (ends `... } catch (e) { /* storage off */ } }`), add:

```js
  function loadTarget() { try { return JSON.parse(localStorage.getItem(COURSE_TARGET_KEY) || "null"); } catch (e) { return null; } }
  function saveTarget(dateStr) { try { localStorage.setItem(COURSE_TARGET_KEY, JSON.stringify({ date: dateStr })); } catch (e) { /* storage off */ } }
```

- [ ] **Step 2: Render the panel in `renderOverview`**

In `web/course.js`, in `renderOverview`, find:

```js
    main.appendChild(revCard);
    main.appendChild(h("h3", { class: "ready-h", text: "By module" }));
```

and insert the study-plan panel between them:

```js
    main.appendChild(revCard);
    var planOrder = CourseLogic.remainingStudyOrder(
      r.modules.map(function (m) { return { title: m.mod.title, status: m.status }; }),
      r.diagnostic && r.diagnostic.order);
    if (planOrder.length) {
      var modByTitle = {};
      r.modules.forEach(function (m) { modByTitle[m.mod.title] = m; });
      var NEXT_ACTION = { "not-started": "Start the material", "progress": "Keep going", "review": "Retake the mastery check" };
      var plan = h("div", { class: "diag-card" }, [h("h3", { text: "Your study plan" })]);
      var plist = h("div", { class: "plan-list" });
      planOrder.forEach(function (t) {
        var m = modByTitle[t];
        plist.appendChild(h("button", { class: "plan-row", type: "button", onclick: function () { openModule(m.mod); } }, [
          h("span", { class: "pr-title", text: t }),
          h("span", { class: "pr-act", text: NEXT_ACTION[m.status] || "Continue" }),
        ]));
      });
      plan.appendChild(plist);
      var target = loadTarget();
      var tstr = target && target.date ? target.date : "";
      var dinput = h("input", { type: "date", class: "plan-date", value: tstr,
        onchange: function () { saveTarget(dinput.value); renderOverview(); } });
      plan.appendChild(h("div", { class: "plan-target" }, [h("label", { text: "Target date:" }), dinput]));
      var pace = tstr ? CourseLogic.pacePerWeek(planOrder.length, Date.parse(tstr + "T00:00:00"), Date.now()) : null;
      var paceText;
      if (pace) paceText = planOrder.length + " module" + (planOrder.length === 1 ? "" : "s") + " left. To finish by " + tstr + ", cover about " + pace.perWeek + " per week.";
      else if (tstr) paceText = "That date has passed, pick a new one.";
      else paceText = planOrder.length + " module" + (planOrder.length === 1 ? "" : "s") + " left. Pick a target date to see a weekly pace.";
      plan.appendChild(h("p", { class: "plan-pace", text: paceText }));
      main.appendChild(plan);
    }
    main.appendChild(h("h3", { class: "ready-h", text: "By module" }));
```

- [ ] **Step 3: Add the CSS**

In `web/course.html`, after the `.diag-row .bar { ... }` rule (the diagnostic-card styles), add:

```css
    .plan-list { display: flex; flex-direction: column; gap: 6px; margin: 6px 0 12px; }
    .plan-row { display: flex; justify-content: space-between; align-items: center; gap: 12px; width: 100%; text-align: left;
      background: var(--bg-2); border: 1px solid var(--line-2); border-radius: 2px; padding: 9px 12px; color: #c4cad2; font: inherit; font-size: 13px; cursor: pointer; }
    .plan-row:hover { border-color: var(--accent-deep); }
    .plan-row .pr-act { color: var(--accent); font-size: 12px; white-space: nowrap; }
    .plan-target { display: flex; align-items: center; gap: 8px; margin: 0 0 8px; font-size: 13px; color: var(--muted); }
    .plan-target input { background: var(--bg-2); border: 1px solid var(--line-2); border-radius: 2px; color: var(--text); font: inherit; font-size: 13px; padding: 5px 8px; }
    .plan-pace { color: var(--dim); font-size: 12.5px; margin: 0; }
```

- [ ] **Step 4: Verify lint + tests**

Run: `npm run lint && npm run test:web`
Expected: ESLint exit 0; test run `# pass 24`, `# fail 0`.

- [ ] **Step 5: Commit**

```bash
git add web/course.js web/course.html
git commit -m "feat(course): study-plan panel with ordered path + target-date pacing"
```

---

## Manual verification checklist (after all tasks)

Signed-in (owner):
- [ ] With modules left, the overview shows a "Your study plan" panel listing the non-mastered modules in recommended order (diagnostic weakest-first if a placement test was taken), each with a next-action label; clicking a row opens that module.
- [ ] Picking a target date shows "N modules left. To finish by <date>, cover about M per week." A past date shows the "pick a new one" note; clearing it shows the "pick a target date" prompt.
- [ ] The date persists across reloads (local only).
- [ ] Once every module is mastered, the panel disappears (the completion panel covers that state).

---

## Self-Review

**Spec coverage:**
- Ordered remaining path (diagnostic-first, mastered dropped) → Task 1 `remainingStudyOrder` + Task 2 rows.
- Target-date pacing (per week) → Task 1 `pacePerWeek` + Task 2 pace line.
- Local-only target date → Task 2 (`COURSE_TARGET_KEY`, not in `PROGRESS_KEYS`).
- Next-action labels + click-to-open → Task 2 `NEXT_ACTION` + `openModule`.
- Hidden when complete → Task 2 (`if (planOrder.length)`; all-mastered gives `[]`).
- Node tests → Task 1.

**Placeholder scan:** every code step carries complete code; no vague steps.

**Type consistency:** `remainingStudyOrder(modules, order)` is called with `r.modules.map(m => ({title: m.mod.title, status: m.status}))` and `r.diagnostic && r.diagnostic.order` — matching the `{title,status}` shape and the order array. `pacePerWeek(remaining, targetMs, nowMs)` called with `planOrder.length`, `Date.parse(...)`, `Date.now()`. `COURSE_TARGET_KEY`/`mrisim_course_target_v1` matches across the helpers. `NEXT_ACTION` keys match the four `status` values (mastered excluded from `planOrder`).
