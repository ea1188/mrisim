# Class Insight (owner sub-project B) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give a class owner a read-only insight view of their students' formative practice — enriched per-student table, per-student drill-down, class summary, and CSV export — built as a pure aggregation module plus a UI extension, with no backend/schema/RLS change.

**Architecture:** New pure UMD module `web/class_insight.js` (all aggregation/CSV, no DOM/network), unit-tested with `node --test` in `web/class_insight.test.mjs`. `web/account.js`'s `classCard` consumes it over the existing `Accounts.roster` + `Accounts.classActivity` reads; `web/account.html` loads the new script. Read-only over the existing `activity` table.

**Tech Stack:** Browser ES5-ish UMD JS (like `web/join_link.js` / `web/course_logic.js`), Node built-in test runner, eslint.

## Global Constraints

- `web/class_insight.js` is UMD: `module.exports` under Node, `window.ClassInsight` in the browser — mirror the wrapper in `web/join_link.js`. Pure: no DOM, no network, no globals.
- Defaults: `passPct = 80`, `struggleAttempts = 2`.
- Blended coverage = `round(100 * (lessonsDone + topicsPassed) / (totals.lessons + totals.topics))`, and `0` when the denominator is 0. `topicsPassed` = count of a student's topics whose `best >= passPct`.
- Scores are percentages from `score`/`total`; a quiz row with `total` null or 0 is ignored for scoring but still counts as a quiz run. Lessons de-duplicated by `ref`. `best` = max %, `latest` = most recent by `created_at`, `attempts` = count of quiz rows for that topic.
- CSV header EXACTLY: `Member,Practice coverage %,Best score %,Lessons done,Weakest topic,Struggling,Last active`. Every cell quoted, embedded `"` doubled, rows joined with `\n`.
- No backend/schema/RLS/edge-function change. No Python touched.
- UI: flat/clinical, no emoji, no gradients, 2px corners; the struggling indicator is a flat solid chip. Coverage is labeled formative ("practice coverage, formative — not graded completion").
- `npm run test:web` and `npm run lint` (eslint `web/`) must pass; the new test file is added to the `test:web` script so `web-lint.yml` runs it in CI.

---

### Task 1: Pure aggregation module `web/class_insight.js` + tests

**Files:**
- Create: `web/class_insight.js`
- Create: `web/class_insight.test.mjs`
- Modify: `package.json` (append the new test file to the `test:web` script)

**Interfaces:**
- Produces (consumed by Task 2):
  - `ClassInsight.perStudent(roster, activity, opts?)` -> `[{ studentId, name, quizRuns, lessonsDone, topics: { <topicId>: { best, latest, attempts } }, topicsPassed, bestPct, weakestTopic, lastActive, struggling }]`
  - `ClassInsight.coverage(row, totals)` -> integer percent
  - `ClassInsight.classStats(rows, totals)` -> `{ members, avgBestPct, avgCoverage, weakestTopics: [{ topic, avgBest }] }`
  - `ClassInsight.toCSV(rows, totals)` -> string
  - `roster` row shape: `{ student_id, profiles: { display_name } }`; `activity` row shape: `{ student_id, kind: "quiz_attempt"|"lesson_complete", ref, score, total, created_at }`; `totals` = `{ lessons, topics }`.

- [ ] **Step 1: Write the failing tests** — `web/class_insight.test.mjs`:

```js
import { test } from "node:test";
import assert from "node:assert/strict";
import CI from "./class_insight.js";

const roster = [
  { student_id: "s1", profiles: { display_name: "Ada" } },
  { student_id: "s2", profiles: { display_name: "Bo" } },
  { student_id: "s3", profiles: {} }, // unnamed, no activity
];
const activity = [
  { student_id: "s1", kind: "quiz_attempt", ref: "safety", score: 6, total: 10, created_at: "2026-07-01T10:00:00Z" },
  { student_id: "s1", kind: "quiz_attempt", ref: "safety", score: 9, total: 10, created_at: "2026-07-02T10:00:00Z" },
  { student_id: "s1", kind: "quiz_attempt", ref: "flow", score: 5, total: 10, created_at: "2026-07-03T10:00:00Z" },
  { student_id: "s1", kind: "lesson_complete", ref: "Lesson A", score: null, total: null, created_at: "2026-07-01T09:00:00Z" },
  { student_id: "s1", kind: "lesson_complete", ref: "Lesson A", score: null, total: null, created_at: "2026-07-04T09:00:00Z" },
  { student_id: "s2", kind: "quiz_attempt", ref: "safety", score: 2, total: 10, created_at: "2026-07-01T10:00:00Z" },
  { student_id: "s2", kind: "quiz_attempt", ref: "safety", score: 3, total: 10, created_at: "2026-07-05T10:00:00Z" },
  { student_id: "s2", kind: "quiz_attempt", ref: "zero", score: 0, total: 0, created_at: "2026-07-06T10:00:00Z" },
];

test("perStudent aggregates best/latest/attempts and distinct lessons", () => {
  const rows = CI.perStudent(roster, activity);
  const a = rows.find((r) => r.studentId === "s1");
  assert.equal(a.name, "Ada");
  assert.equal(a.topics.safety.attempts, 2);
  assert.equal(a.topics.safety.best, 90);
  assert.equal(a.topics.safety.latest, 90); // 2026-07-02 is latest of the two safety runs
  assert.equal(a.lessonsDone, 1); // "Lesson A" twice = 1 distinct
  assert.equal(a.quizRuns, 3);
  assert.equal(a.bestPct, 90);
  assert.equal(a.weakestTopic, "flow"); // 50 < 90
  assert.equal(a.lastActive, "2026-07-04T09:00:00Z");
});

test("struggling flags a topic retaken >= struggleAttempts still below passPct", () => {
  const rows = CI.perStudent(roster, activity);
  assert.equal(rows.find((r) => r.studentId === "s2").struggling, true); // safety 2 attempts, best 30 < 80
  assert.equal(rows.find((r) => r.studentId === "s1").struggling, false); // safety passed; flow only 1 attempt
});

test("a roster member with no activity is all zeros", () => {
  const rows = CI.perStudent(roster, activity);
  const c = rows.find((r) => r.studentId === "s3");
  assert.equal(c.name, "(unnamed)");
  assert.equal(c.quizRuns, 0);
  assert.equal(c.lessonsDone, 0);
  assert.equal(c.bestPct, null);
  assert.equal(c.struggling, false);
});

test("total==0 quiz row counts as a run but not for scoring", () => {
  const s2 = CI.perStudent(roster, activity).find((r) => r.studentId === "s2");
  assert.equal(s2.quizRuns, 3);
  assert.equal(s2.topics.zero.best, null);
  assert.equal(s2.topicsPassed, 0);
});

test("coverage blends lessons and topics passed over totals; 0 on empty denom", () => {
  const a = CI.perStudent(roster, activity).find((r) => r.studentId === "s1");
  // lessonsDone 1 + topicsPassed 1 (safety 90>=80; flow 50 no) = 2; totals 40+8=48 -> round(100*2/48)=4
  assert.equal(CI.coverage(a, { lessons: 40, topics: 8 }), 4);
  assert.equal(CI.coverage(a, { lessons: 0, topics: 0 }), 0);
});

test("classStats averages and picks up to 3 weakest topics ascending", () => {
  const rows = CI.perStudent(roster, activity);
  const st = CI.classStats(rows, { lessons: 40, topics: 8 });
  assert.equal(st.members, 3);
  // flow avgBest 50 (s1 only) < safety avgBest 60 (90,30) -> flow is weakest, first
  assert.equal(st.weakestTopics[0].topic, "flow");
  assert.equal(st.weakestTopics[0].avgBest <= st.weakestTopics[st.weakestTopics.length - 1].avgBest, true);
});

test("toCSV emits the exact header and escapes commas and quotes", () => {
  const rows = CI.perStudent(
    [{ student_id: "x", profiles: { display_name: 'De, "Q"' } }],
    [{ student_id: "x", kind: "quiz_attempt", ref: "t", score: 8, total: 10, created_at: "2026-07-01T00:00:00Z" }]
  );
  const csv = CI.toCSV(rows, { lessons: 10, topics: 4 });
  const lines = csv.split("\n");
  assert.equal(lines[0], '"Member","Practice coverage %","Best score %","Lessons done","Weakest topic","Struggling","Last active"');
  assert.ok(lines[1].startsWith('"De, ""Q"""')); // comma preserved, quotes doubled
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `node --test web/class_insight.test.mjs`
Expected: FAIL — cannot find module `./class_insight.js`.

- [ ] **Step 3: Implement `web/class_insight.js`** (UMD, pure):

```js
/*
 * ClassInsight — pure aggregation of formative class activity for the owner
 * dashboard. UMD like join_link.js: window.ClassInsight in the browser,
 * module.exports under Node. No DOM, no network.
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.ClassInsight = factory();
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  var DEFAULTS = { passPct: 80, struggleAttempts: 2 };

  function pct(score, total) { return total ? (100 * score) / total : null; }

  function perStudent(roster, activity, opts) {
    opts = opts || {};
    var passPct = opts.passPct == null ? DEFAULTS.passPct : opts.passPct;
    var struggleAttempts = opts.struggleAttempts == null ? DEFAULTS.struggleAttempts : opts.struggleAttempts;

    var byStudent = {};
    (activity || []).forEach(function (a) {
      (byStudent[a.student_id] || (byStudent[a.student_id] = [])).push(a);
    });

    return (roster || []).map(function (r) {
      var acts = byStudent[r.student_id] || [];
      var topics = {};   // ref -> { best, latest, latestAt, attempts }
      var lessons = {};
      var quizRuns = 0;
      var lastActive = null;

      acts.forEach(function (a) {
        if (!lastActive || a.created_at > lastActive) lastActive = a.created_at;
        if (a.kind === "quiz_attempt") {
          quizRuns++;
          var t = topics[a.ref] || (topics[a.ref] = { best: null, latest: null, latestAt: null, attempts: 0 });
          t.attempts++;
          var p = pct(a.score, a.total);
          if (p != null) {
            if (t.best == null || p > t.best) t.best = p;
            if (t.latestAt == null || a.created_at > t.latestAt) { t.latest = p; t.latestAt = a.created_at; }
          }
        } else if (a.kind === "lesson_complete") {
          lessons[a.ref] = true;
        }
      });

      var outTopics = {};
      var bestPct = null, weakestTopic = null, weakestBest = null, topicsPassed = 0, struggling = false;
      Object.keys(topics).forEach(function (k) {
        var t = topics[k];
        outTopics[k] = { best: t.best, latest: t.latest, attempts: t.attempts };
        if (t.best != null) {
          if (bestPct == null || t.best > bestPct) bestPct = t.best;
          if (weakestBest == null || t.best < weakestBest) { weakestBest = t.best; weakestTopic = k; }
          if (t.best >= passPct) topicsPassed++;
          else if (t.attempts >= struggleAttempts) struggling = true;
        }
      });

      return {
        studentId: r.student_id,
        name: (r.profiles && r.profiles.display_name) || "(unnamed)",
        quizRuns: quizRuns,
        lessonsDone: Object.keys(lessons).length,
        topics: outTopics,
        topicsPassed: topicsPassed,
        bestPct: bestPct,
        weakestTopic: weakestTopic,
        lastActive: lastActive,
        struggling: struggling,
      };
    });
  }

  function coverage(row, totals) {
    var denom = ((totals && totals.lessons) || 0) + ((totals && totals.topics) || 0);
    if (!denom) return 0;
    return Math.round((100 * (row.lessonsDone + row.topicsPassed)) / denom);
  }

  function mean(arr) {
    return arr.length ? Math.round(arr.reduce(function (a, b) { return a + b; }, 0) / arr.length) : null;
  }

  function classStats(rows, totals) {
    rows = rows || [];
    var bests = rows.map(function (r) { return r.bestPct; }).filter(function (v) { return v != null; });
    var covs = rows.map(function (r) { return coverage(r, totals); });
    var agg = {};
    rows.forEach(function (r) {
      Object.keys(r.topics).forEach(function (k) {
        var b = r.topics[k].best;
        if (b == null) return;
        (agg[k] || (agg[k] = [])).push(b);
      });
    });
    var weakestTopics = Object.keys(agg).map(function (k) {
      return { topic: k, avgBest: mean(agg[k]) };
    }).sort(function (a, b) { return a.avgBest - b.avgBest; }).slice(0, 3);
    return {
      members: rows.length,
      avgBestPct: bests.length ? mean(bests) : null,
      avgCoverage: covs.length ? mean(covs) : 0,
      weakestTopics: weakestTopics,
    };
  }

  function csvCell(v) {
    v = v == null ? "" : String(v);
    return '"' + v.replace(/"/g, '""') + '"';
  }

  function toCSV(rows, totals) {
    var header = ["Member", "Practice coverage %", "Best score %", "Lessons done", "Weakest topic", "Struggling", "Last active"];
    var lines = [header.map(csvCell).join(",")];
    (rows || []).forEach(function (r) {
      lines.push([
        r.name,
        coverage(r, totals),
        r.bestPct == null ? "" : Math.round(r.bestPct),
        r.lessonsDone,
        r.weakestTopic || "",
        r.struggling ? "yes" : "no",
        r.lastActive || "",
      ].map(csvCell).join(","));
    });
    return lines.join("\n");
  }

  return { perStudent: perStudent, coverage: coverage, classStats: classStats, toCSV: toCSV };
});
```

- [ ] **Step 4: Add the test file to the `test:web` script** in `package.json`:

Change `"test:web": "node --test web/course_logic.test.mjs web/auth_url.test.mjs web/join_link.test.mjs"` to also list `web/class_insight.test.mjs` at the end.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `npm run test:web`
Expected: PASS — all `class_insight` tests green, existing suites still green.

- [ ] **Step 6: Lint and commit**

Run: `npm run lint` (expect clean).
```bash
git add web/class_insight.js web/class_insight.test.mjs package.json
git commit -m "feat(owner): class-insight aggregation module + tests"
```

---

### Task 2: Owner UI — enriched table, drill-down, class summary, CSV

**Files:**
- Modify: `web/account.js` (`classCard`)
- Modify: `web/account.html` (add `<script src="class_insight.js"></script>` before `account.js`)

**Interfaces:**
- Consumes from Task 1: `ClassInsight.perStudent`, `ClassInsight.coverage`, `ClassInsight.classStats`, `ClassInsight.toCSV`.
- Reuses existing `Accounts.roster(classId)` and `Accounts.classActivity(classId)` (already called in `classCard`).

- [ ] **Step 1: Add the script tag** in `web/account.html` immediately before `<script src="account.js"></script>`:

```html
  <script src="class_insight.js"></script>
```

- [ ] **Step 2: Obtain the curriculum totals once.** In `web/account.js`, add a best-effort loader that fetches the lessons dataset and quiz categories the learner app uses, and computes `{ lessons, topics }`. Cache the promise at module scope so it runs once per page, not once per class. On any failure, resolve to `{ lessons: <lessons count or 0>, topics: 0 }` so coverage falls back to lessons-only. (Follow the existing fetch/JSON patterns in the repo for the dataset paths; the learner app loads lessons via the same JSON `app.js` uses and quiz categories via `quiz.js` — reuse those paths.)

- [ ] **Step 3: Extend `classCard`'s render.** After `Promise.all([roster, classActivity])` resolves (and once totals resolve), replace the hand-rolled per-student aggregation with:
  - `var rows = ClassInsight.perStudent(roster, acts);`
  - Build the table with columns: Member, Practice coverage %, Best score, Weakest topic, Struggling (flat chip when `row.struggling`), Last active, Remove.
  - Coverage cell uses `ClassInsight.coverage(row, totals)`; header carries the muted "formative, not graded" subtext.
  - Each member row is clickable to toggle an inline drill-down row beneath it showing per-topic `best / latest / attempts` and the count/list of completed lessons.
  - Add a class-summary line from `ClassInsight.classStats(rows, totals)` (members, avg best, avg coverage, up to 3 weakest topics).
  - Add a "Download CSV" button that builds `ClassInsight.toCSV(rows, totals)`, wraps it in a `Blob(["...text/csv"])`, and triggers an `<a download="<classname>-insight.csv">` object-URL click.
  - Keep the existing empty-roster state and the formative footnote.

- [ ] **Step 4: Manual verification**

Run: `npm run lint` (expect clean). Load `web/account.html` as an owner with a class; confirm the enriched table renders, a row expands to its drill-down, the summary line shows, and the CSV downloads with the exact header. A zero-member class shows the existing empty state.

- [ ] **Step 5: Commit**

```bash
git add web/account.js web/account.html
git commit -m "feat(owner): class-insight dashboard (table, drill-down, summary, CSV)"
```

---

## Self-Review

- **Spec coverage:** per-student table (Task 2 Step 3), drill-down (Step 3), class stats (Step 3), CSV (Steps 1/3), blended coverage + struggling + weakest topic + formative labeling (Task 1 + Task 2). All spec sections map to a task.
- **No placeholders:** Task 1 ships complete code and tests; Task 2's only soft spot is the dataset paths for totals, deliberately delegated to "reuse the paths app.js/quiz.js already use" with a lessons-only fallback so it cannot break the page.
- **Type consistency:** `perStudent` row fields (`topicsPassed`, `bestPct`, `weakestTopic`, `topics[k].best/latest/attempts`) are used identically in `coverage`, `classStats`, `toCSV`, and Task 2's render.
