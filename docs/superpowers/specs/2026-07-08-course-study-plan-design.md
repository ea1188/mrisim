# Study Schedule (Phase 4.2) — Design

**Goal:** A "Your study plan" panel that lists the remaining modules in recommended order and paces
them to a target date the learner picks.

**Status:** Approved 2026-07-08. Ordered remaining path + target-date pacing (per week). Target date
is a local-only preference (not synced); the plan/pace derive from the already-synced progress.

## Context

`web/course.js` `renderOverview` renders the dashboard from `computeReadiness`, which returns
`r.modules` (`[{mod, status, ...}]`), `r.next`, `r.exam`, and `r.diagnostic` (the placement snapshot
with `order`, the weakest-first module titles). Module `status` is one of `not-started` / `progress`
/ `review` / `mastered`. The overview already shows readiness, a completion panel (when complete),
"Study next", diagnostic + spaced-review cards, and a module grid. `web/course_logic.js` holds pure,
node-tested logic. Progress is synced; this feature adds no synced state.

## Architecture

Two pure, node-tested functions in `course_logic.js` (`remainingStudyOrder`, `pacePerWeek`); a
"Your study plan" panel in `renderOverview` with a target-date input persisted local-only. No
backend, no content, no cache bump.

## Pure logic (`web/course_logic.js`, node-tested)

```js
// Non-mastered module titles in recommended study order: diagnostic weakest-first where available
// (order is the diagnostic order array or null), then any remaining non-mastered in module order.
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

Both added to the `course_logic.js` export.

## Components (`course.js`)

1. **Target-date persistence (local only).** `COURSE_TARGET_KEY = "mrisim_course_target_v1"`;
   `loadTarget()` / `saveTarget(dateStr)` (try/catch). Stores `{ date: "YYYY-MM-DD" }` from the date
   input. **Not** added to `PROGRESS_KEYS` (per-device preference).
2. **Study-plan panel** in `renderOverview`, inserted after the spaced-review card and before the
   "By module" grid:
   - Compute `order = CourseLogic.remainingStudyOrder(r.modules.map(function (m) { return { title: m.mod.title, status: m.status }; }), r.diagnostic && r.diagnostic.order)`.
   - **If `order.length === 0`** (all mastered / complete): render nothing (no plan needed).
   - Else render a "Your study plan" panel:
     - One clickable row per title in `order`: the module title, its status label
       (`STATUS_LABEL[status]`), and a next-action label from status
       (`not-started` → "Start the material", `progress` → "Keep going", `review` → "Retake the
       mastery check"), clicking opens the module (`openModule` for the matching `r.modules[i].mod`).
     - A target-date `<input type="date">` (value from `loadTarget()`); on change, `saveTarget(value)`
       and re-render the overview.
     - A pacing line: `pace = CourseLogic.pacePerWeek(order.length, Date.parse(target + "T00:00:00"),
       Date.now())`; if `pace`, show "`order.length` modules left. To finish by `<date>`, cover about
       `pace.perWeek` per week." If no target set, show "`order.length` modules left. Pick a target
       date to see a weekly pace." If the target is in the past, show a gentle "That date has passed,
       pick a new one."
3. Styling reuses the existing `.diag-card` / `.ready-row` look (no or minimal new CSS).

## Error handling / edge cases

- **Storage disabled:** `loadTarget/saveTarget` in try/catch; the date just is not remembered.
- **Invalid / empty date:** `Date.parse` yields NaN → `pacePerWeek` gets a non-future `targetMs` →
  returns null → the "pick a target date" prompt shows.
- **All mastered:** panel hidden (the completion panel already covers that state).
- **No diagnostic:** `remainingStudyOrder` falls back to module (curriculum) order.

## Testing

- **Node unit tests** (extend `web/course_logic.test.mjs`): `remainingStudyOrder` — diagnostic
  weakest-first ordering, mastered dropped, non-diagnostic modules appended in order, no-diagnostic
  fallback, all-mastered → `[]`. `pacePerWeek` — a 4-week/8-module target → `{weeks:4, perWeek:2}`,
  a past date → null, zero remaining → null, sub-week future → `weeks:1`.
- **Render:** `npm run lint` clean; manual signed-in check that the panel lists remaining modules in
  order, the date input pacing updates, and the panel disappears once every module is mastered.
- No engine/physics change; the Python suite is unaffected.

## Out of scope

- Syncing the target date across devices (local-only by decision).
- Calendar export / reminders / per-day scheduling (per-week pacing only).
- Module diagrams (the remaining Phase 4 sub-project).
