# Registry-Readiness Premium Blend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the course-page "Registry readiness" panel reflect the ARRT-weighted premium quiz bank (538 Q), not just the free 100-question diagnostic, by blending a new per-premium-topic progress store into `readiness()` per ARRT category.

**Architecture:** `web/blueprint.js` gains a `PREMIUM_MAP` (premium topic → ARRT category) and a 2-arg `readiness(freeProgress, premiumProgress)` that sums accuracy and coverage across both free-category and premium-topic sources per category. `web/course.js` records premium quiz answers into a new synced localStorage store `mrisim_premium_topic_progress_v1` (`{ premiumTopic: { right, seen } }`) at the three forward-practice grade sites, and passes it to `readiness()`. `web/course_logic.js` merges the new store monotonically for cross-device sync. Pure logic (blueprint, course_logic) is unit-tested; `course.js` is DOM wiring verified by lint + regression suite.

**Tech Stack:** Vanilla ES5-style browser JS (UMD modules, no build step), `node:test` for `.test.mjs` unit tests, eslint.

## Global Constraints

- **Backward compatibility (hard):** all 9 existing `readiness(progress)` single-arg tests in `web/blueprint.test.mjs` MUST stay green. Legacy single-arg behavior = free-pool-only denominators, premium excluded entirely. Blend is opt-in via supplying the 2nd arg.
- **Coverage denominator (resolved 2026-07-09):** premium topics DO count toward per-category coverage. Category coverage = (attempted free members + attempted premium topics) / (total free members + total premium topics for that category). Attempting either kind of source counts once.
- **`projected` formula unchanged:** unattempted categories contribute 0; grinding one low-weight source cannot inflate the headline.
- **Premium→ARRT map (audited against the quiz topic-count rebalance), exactly these 15 topics:** Image Production = `instrumentation, pulse-sequences, data-acquisition, contrast-weighting, image-quality, flow-artifacts, fat-suppression, three-d-recon` (8). Procedures = `procedures-anatomy, procedures-protocols, procedures-vascular, pathology` (4). Safety = `safety` (1). Patient Care = `patient-care, contrast-agents` (2).
- **Two store shapes differ:** free store `mrisim_quiz_progress_v1` = `{ cat: { best, total, runs } }` (attempted ⇔ `total > 0`, correct = `best`, asked = `total`). Premium store `mrisim_premium_topic_progress_v1` = `{ topic: { right, seen } }` (attempted ⇔ `seen > 0`, correct = `right`, asked = `seen`).
- **No `Co-Authored-By: Claude` trailers on commits.** No emoji/gradients in any copy. No AI-tell punctuation (no em dashes) in user-facing strings.
- **`ARRT_BLUEPRINT` numbers are frozen** — do not touch scored counts or weights (guarded by an existing test).
- Test command (single file): `node --test web/blueprint.test.mjs`. Full web suite: `npm run test:web`. Lint: `npm run lint`.

---

### Task 1: blueprint.js — PREMIUM_MAP + blended 2-arg readiness

**Files:**
- Modify: `web/blueprint.js:16-60` (add `PREMIUM_MAP`, rewrite `readiness`, extend exports)
- Test: `web/blueprint.test.mjs` (add blend + map-integrity tests; keep existing)

**Interfaces:**
- Consumes: nothing new.
- Produces:
  - `PREMIUM_MAP` — object `{ premiumTopicString: arrtCategoryKeyString }`, 15 entries. Exported on the module.
  - `readiness(freeProgress, premiumProgress)` — 2nd arg optional. Returns the SAME shape as today: `{ categories: [{ key, name, scored, weight, note, accuracy, coverage, attempted, memberCount }], projected, coverage }`. When `premiumProgress` is `undefined`/`null`, behaves exactly as the legacy single-arg version (premium excluded). When supplied (even `{}`), premium topics are added to each category's denominator and any attempted ones contribute to accuracy/coverage. `memberCount` is the blended slot count (free members + premium topics) in blend mode; `attempted` counts attempted sources of both kinds.

- [ ] **Step 1: Add the two blended failing tests + the map-integrity test**

Append to `web/blueprint.test.mjs` (after the last existing test, before EOF):

```js
test("PREMIUM_MAP: exactly the 15 audited premium topics, each mapped to a valid category", () => {
  const EXPECTED_TOPICS = [
    "instrumentation", "pulse-sequences", "data-acquisition", "contrast-weighting",
    "image-quality", "flow-artifacts", "fat-suppression", "three-d-recon",
    "procedures-anatomy", "procedures-protocols", "procedures-vascular", "pathology",
    "safety", "patient-care", "contrast-agents",
  ];
  assert.deepEqual(Object.keys(B.PREMIUM_MAP).sort(), [...EXPECTED_TOPICS].sort());
  const validKeys = new Set(B.ARRT_BLUEPRINT.map((c) => c.key));
  for (const t of Object.keys(B.PREMIUM_MAP)) {
    assert.ok(validKeys.has(B.PREMIUM_MAP[t]), `${t} -> unknown category ${B.PREMIUM_MAP[t]}`);
  }
  const counts = {};
  for (const t of Object.keys(B.PREMIUM_MAP)) counts[B.PREMIUM_MAP[t]] = (counts[B.PREMIUM_MAP[t]] || 0) + 1;
  assert.deepEqual(counts, { "image-production": 8, procedures: 4, safety: 1, "patient-care": 2 });
});

test("blend: premium-only progress fills a category the free pool never touched", () => {
  // Safety free members = [safety] (unattempted); premium topics for safety = [safety] (attempted).
  const r = B.readiness({}, { safety: { right: 9, seen: 10 } });
  const s = r.categories.find((c) => c.key === "safety");
  assert.ok(Math.abs(s.accuracy - 0.9) < 1e-9);   // 9/10 from the premium source
  assert.equal(s.attempted, 1);                    // one of two sources attempted
  assert.equal(s.memberCount, 2);                  // 1 free member + 1 premium topic
  assert.ok(Math.abs(s.coverage - 0.5) < 1e-9);
  assert.ok(Math.abs(r.projected - 0.9 * 0.105) < 1e-9);
});

test("blend: free + premium sum per category with the enlarged denominator", () => {
  const free = { sequences: { best: 8, total: 10, runs: 1 }, "image-quality": { best: 6, total: 10, runs: 1 } };
  const premium = { instrumentation: { right: 5, seen: 10 }, "three-d-recon": { right: 3, seen: 10 } };
  const r = B.readiness(free, premium);
  const ip = r.categories.find((c) => c.key === "image-production");
  assert.ok(Math.abs(ip.accuracy - 0.55) < 1e-9);  // (8+6+5+3)/(10+10+10+10) = 22/40
  assert.equal(ip.attempted, 4);                    // 2 free members + 2 premium topics
  assert.equal(ip.memberCount, 12);                 // 4 free members + 8 premium topics
  assert.ok(Math.abs(ip.coverage - 4 / 12) < 1e-9);
  assert.ok(Math.abs(r.projected - 0.55 * 0.53) < 1e-9);
});

test("blend is opt-in: omitting the 2nd arg keeps legacy free-only denominators", () => {
  const oneFree = { sequences: { best: 8, total: 10, runs: 1 } };
  const r = B.readiness(oneFree);            // no premium arg
  const ip = r.categories.find((c) => c.key === "image-production");
  assert.equal(ip.memberCount, 4);           // 4 free members only, premium NOT in denominator
  assert.equal(ip.coverage, 0.25);
});
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `node --test web/blueprint.test.mjs`
Expected: FAIL — `B.PREMIUM_MAP` is undefined and `readiness` ignores the 2nd arg (blend tests fail on memberCount/accuracy). The `blend is opt-in` test may pass by luck (legacy path); the others fail.

- [ ] **Step 3: Add PREMIUM_MAP and rewrite readiness in `web/blueprint.js`**

Replace lines 28-59 (the `isAttempted` helper, `readiness`, and the return statement) with:

```js
  // Premium quiz topic -> ARRT category key. Audited against the quiz topic-count
  // rebalance: every premium topic maps to exactly one category. Names that also
  // appear as free members (image-quality, pathology, safety, patient-care) are a
  // SEPARATE question bank here, so they count as their own practiceable source.
  var PREMIUM_MAP = {
    "instrumentation": "image-production",
    "pulse-sequences": "image-production",
    "data-acquisition": "image-production",
    "contrast-weighting": "image-production",
    "image-quality": "image-production",
    "flow-artifacts": "image-production",
    "fat-suppression": "image-production",
    "three-d-recon": "image-production",
    "procedures-anatomy": "procedures",
    "procedures-protocols": "procedures",
    "procedures-vascular": "procedures",
    "pathology": "procedures",
    "safety": "safety",
    "patient-care": "patient-care",
    "contrast-agents": "patient-care",
  };

  function isAttempted(entry) {            // free store: { best, total, runs }
    return !!entry && typeof entry.total === "number" && entry.total > 0;
  }
  function isAttemptedPremium(entry) {     // premium store: { right, seen }
    return !!entry && typeof entry.seen === "number" && entry.seen > 0;
  }

  // freeProgress   = mrisim_quiz_progress_v1:            { freeCategory: { best, total, runs } }
  // premiumProgress = mrisim_premium_topic_progress_v1:  { premiumTopic: { right, seen } }
  // Omit premiumProgress for the legacy free-only model (denominators unchanged).
  // Supply it (even {}) to blend the premium bank into each category's accuracy and
  // coverage, with premium topics added to the coverage denominator.
  function readiness(freeProgress, premiumProgress) {
    var prog = freeProgress || {};
    var blend = premiumProgress !== undefined && premiumProgress !== null;
    var prem = premiumProgress || {};
    var premByCat = {};                    // category key -> [premium topics], computed once
    Object.keys(PREMIUM_MAP).forEach(function (t) {
      (premByCat[PREMIUM_MAP[t]] = premByCat[PREMIUM_MAP[t]] || []).push(t);
    });
    var categories = ARRT_BLUEPRINT.map(function (c) {
      var right = 0, asked = 0, attempted = 0, slots = c.members.length;
      c.members.forEach(function (m) {
        var e = prog[m];
        if (!isAttempted(e)) return;
        attempted += 1;
        right += (typeof e.best === "number" ? e.best : 0);
        asked += e.total;
      });
      if (blend) {
        var topics = premByCat[c.key] || [];
        slots += topics.length;
        topics.forEach(function (t) {
          var e = prem[t];
          if (!isAttemptedPremium(e)) return;
          attempted += 1;
          right += (typeof e.right === "number" ? e.right : 0);
          asked += e.seen;
        });
      }
      return {
        key: c.key, name: c.name, scored: c.scored, weight: c.weight, note: c.note || null,
        accuracy: asked > 0 ? right / asked : null,
        coverage: slots ? attempted / slots : 0,
        attempted: attempted, memberCount: slots,
      };
    });
    var projected = 0, coverage = 0;
    categories.forEach(function (c) {
      projected += (c.accuracy || 0) * c.weight;
      coverage += c.coverage * c.weight;
    });
    return { categories: categories, projected: projected, coverage: coverage };
  }

  return { ARRT_BLUEPRINT: ARRT_BLUEPRINT, PREMIUM_MAP: PREMIUM_MAP, readiness: readiness };
```

- [ ] **Step 4: Run the full blueprint suite to verify all pass (new + legacy)**

Run: `node --test web/blueprint.test.mjs`
Expected: PASS — all existing tests (single-arg legacy) plus the 4 new tests green.

- [ ] **Step 5: Lint**

Run: `npm run lint`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add web/blueprint.js web/blueprint.test.mjs
git commit -m "feat(blueprint): PREMIUM_MAP + blended 2-arg readiness (premium topics in coverage)"
```

---

### Task 2: course_logic.js — merge the premium-topic store for cross-device sync

**Files:**
- Modify: `web/course_logic.js:129-143` (add one merge line inside `mergeProgress`)
- Test: `web/course_logic.test.mjs` (add one monotonic-merge test)

**Interfaces:**
- Consumes: existing `_mergeQuiz(a, b)` helper (picks the side with higher `seen`; the new store shares the `{ right, seen }` shape, so it reuses this directly).
- Produces: `mergeProgress` now merges the key `mrisim_premium_topic_progress_v1` monotonically. Keys still pass through unchanged when present on only one side.

- [ ] **Step 1: Write the failing test**

Append to `web/course_logic.test.mjs` (after the existing `mergeProgress` tests, e.g. after the block ending near line 96):

```js
test("mergeProgress keeps higher premium-topic seen (monotonic)", () => {
  const local = { mrisim_premium_topic_progress_v1: { safety: { seen: 5, right: 3 } } };
  const remote = { mrisim_premium_topic_progress_v1: { safety: { seen: 8, right: 2 }, "image-quality": { seen: 2, right: 2 } } };
  const m = mergeProgress(local, remote);
  assert.deepEqual(m.mrisim_premium_topic_progress_v1.safety, { seen: 8, right: 2 });
  assert.deepEqual(m.mrisim_premium_topic_progress_v1["image-quality"], { seen: 2, right: 2 });
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `node --test web/course_logic.test.mjs`
Expected: FAIL — `m.mrisim_premium_topic_progress_v1` is the raw local value `{ safety: { seen: 5, right: 3 } }` (pass-through), so `safety` is `{seen:5,right:3}` not `{seen:8,right:2}`, and `image-quality` is missing.

- [ ] **Step 3: Add the merge line**

In `web/course_logic.js`, immediately after the `mrisim_course_quiz_v1` line (currently line 136), add:

```js
    if ("mrisim_premium_topic_progress_v1" in out) out.mrisim_premium_topic_progress_v1 = _mergeQuiz(local.mrisim_premium_topic_progress_v1, remote.mrisim_premium_topic_progress_v1);
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `node --test web/course_logic.test.mjs`
Expected: PASS — new test green, all existing merge tests still green.

- [ ] **Step 5: Commit**

```bash
git add web/course_logic.js web/course_logic.test.mjs
git commit -m "feat(course-logic): merge mrisim_premium_topic_progress_v1 monotonically"
```

---

### Task 3: course.js — record premium-topic answers, sync, and feed readiness

**Files:**
- Modify: `web/course.js` — add store key/helpers, stamp topic onto pooled bodies, bump at 3 grade sites, add key to sync, pass premium store to `readiness`.

**Interfaces:**
- Consumes: `window.Blueprint.readiness(free, premium)` (Task 1); `CourseLogic.mergeProgress` now handling the new key (Task 2).
- Produces: new synced localStorage store `mrisim_premium_topic_progress_v1`. No new exports (course.js is an IIFE).

**Note on grade sites:** exactly the three FORWARD-practice sites feed the store — inline topic quiz (grade at `course.js:642`), mastery check (`course.js:713`), practice exam (`course.js:912`). The diagnostic placement test (its own submit path) and the spaced-review re-test (`inReview=true`) are intentionally EXCLUDED: the diagnostic is a pre-test snapshot and review re-tests already-counted misses.

**Note on threading:** all pool builders (`examPool`, `modulePool`, and the inline `pq` at line 581) push `it.body`, dropping `it.topic`. We stamp `it.body._ptopic = it.topic` once at index time (line ~1265) so every graded body self-identifies its premium topic.

- [ ] **Step 1: Add the store key constant**

In `web/course.js`, immediately after line 32 (`var COURSE_QUIZ_KEY = "mrisim_course_quiz_v1";`), add:

```js
  var PREMIUM_TOPIC_KEY = "mrisim_premium_topic_progress_v1"; // per-premium-topic { right, seen }; feeds the ARRT readiness blend
```

- [ ] **Step 2: Add the loader next to loadQuizProgress**

In `web/course.js`, immediately after `loadQuizProgress` (ends at line 207 `}`), add:

```js
  function loadPremiumTopicProgress() {
    try { return JSON.parse(localStorage.getItem(PREMIUM_TOPIC_KEY) || "{}"); }
    catch (e) { return {}; }
  }
```

- [ ] **Step 3: Add the bumper next to bumpScore**

In `web/course.js`, immediately after `bumpScore` (ends at line 1203 `}`), add:

```js
  // Record one graded premium quiz answer by its ARRT premium topic (see PREMIUM_MAP
  // in blueprint.js). No-op when the body has no topic (e.g. free lessons).
  function bumpPremiumTopic(topicKey, correct) {
    if (!topicKey) return;
    try {
      var s = JSON.parse(localStorage.getItem(PREMIUM_TOPIC_KEY) || "{}");
      var r = s[topicKey] || { right: 0, seen: 0 };
      r.seen += 1; if (correct) r.right += 1; s[topicKey] = r;
      localStorage.setItem(PREMIUM_TOPIC_KEY, JSON.stringify(s));
      queueSync();
    } catch (e) { /* storage off */ }
  }
```

- [ ] **Step 4: Stamp the premium topic onto each pooled body at index time**

In `web/course.js`, replace the `byTopic` build (currently lines 1264-1266):

```js
      var byTopic = {}; (premium || []).forEach(function (it) {
        (byTopic[it.topic] = byTopic[it.topic] || []).push(it);
      });
```

with:

```js
      var byTopic = {}; (premium || []).forEach(function (it) {
        if (it.body) it.body._ptopic = it.topic;   // carry the premium topic onto pooled bodies for readiness
        (byTopic[it.topic] = byTopic[it.topic] || []).push(it);
      });
```

- [ ] **Step 5: Bump at grade site 1 — inline topic quiz**

In `web/course.js` `quizItem`, after the line `bumpScore(topicTitle, correct);` (line 642), add on the next line (same indentation):

```js
        bumpPremiumTopic(q._ptopic, correct);
```

- [ ] **Step 6: Bump at grade site 2 — mastery check**

In `web/course.js` `submitMastery`, after the line `bumpScore(mod.title, right);` (line 713), add on the next line (same indentation):

```js
      bumpPremiumTopic(item.q._ptopic, right);
```

- [ ] **Step 7: Bump at grade site 3 — practice exam**

In `web/course.js` `submitExam`, inside the `EXAM.questions.forEach` loop, after the line `recordAnswer(item.q, right, false);` (line 912), add on the next line (same indentation):

```js
      bumpPremiumTopic(item.q._ptopic, right);
```

- [ ] **Step 8: Add the store to the sync key list**

In `web/course.js` line 971, append `PREMIUM_TOPIC_KEY` to `PROGRESS_KEYS`:

```js
  var PROGRESS_KEYS = [CURRICULUM_DONE_KEY, COURSE_QUIZ_KEY, COURSE_READ_KEY, COURSE_EXAM_KEY, COURSE_MASTERY_KEY, COURSE_DIAG_KEY, COURSE_REVIEW_KEY, COURSE_COMPLETE_KEY, PREMIUM_TOPIC_KEY];
```

- [ ] **Step 9: Pass the premium store to readiness + add a caption**

In `web/course.js` `appendReadiness`, replace line 213:

```js
    var rd = window.Blueprint.readiness(loadQuizProgress());
```

with:

```js
    var rd = window.Blueprint.readiness(loadQuizProgress(), loadPremiumTopicProgress());
```

Then, in the same function, add a caption line. Replace the header `h("h3", ...)` line (line 215):

```js
      h("h3", { class: "bp-h", text: "Readiness by ARRT content category" }),
```

with:

```js
      h("h3", { class: "bp-h", text: "Readiness by ARRT content category" }),
      h("div", { class: "bp-lbl", text: "Blends your free diagnostic quiz and premium course questions." }),
```

(`bp-lbl` is an already-styled class reused from the header block, so no CSS change is needed.)

- [ ] **Step 10: Regression — run the full web suite and lint**

Run: `npm run test:web`
Expected: PASS — all suites green (blueprint + course_logic changes from Tasks 1-2 covered; course.js has no unit suite).

Run: `npm run lint`
Expected: no errors (watch for unused-var on any helper — all three new helpers are referenced).

- [ ] **Step 11: Sanity-check the wiring is present**

Run:
```bash
grep -n "bumpPremiumTopic(\|_ptopic\|loadPremiumTopicProgress\|PREMIUM_TOPIC_KEY" web/course.js
```
Expected: `bumpPremiumTopic(` appears 4 times (1 definition + 3 grade sites); `_ptopic` appears at the stamp site plus the 3 grade reads; `loadPremiumTopicProgress` twice (def + call in appendReadiness); `PREMIUM_TOPIC_KEY` in the const, the two helpers, and `PROGRESS_KEYS`.

- [ ] **Step 12: Commit**

```bash
git add web/course.js
git commit -m "feat(course): record premium-topic quiz results and blend them into ARRT readiness"
```

---

## Self-Review

**1. Spec coverage:**
- Spec "Approach 1 (record premium answers by topic)" → Task 3 Steps 1-7 (store, helpers, stamp, 3 grade sites). ✓
- Spec "Approach 2 (premium→ARRT map)" → Task 1 Step 3 `PREMIUM_MAP`, audited to the spec's 15 topics. ✓
- Spec "Approach 3 (extend readiness, 2nd arg optional)" → Task 1 Step 3, back-compat via `blend` flag. ✓
- Spec "Approach 4 (course.js passes both stores + caption)" → Task 3 Step 9. ✓
- Spec "Approach 5 (cross-device sync, PROGRESS_KEYS + merge, monotonic)" → Task 3 Step 8 (PROGRESS_KEYS) + Task 2 (merge via `_mergeQuiz`, which is monotonic on `seen`). ✓
- Spec "Tests: 2-arg readiness, premium-only, blend hand-math, map integrity, existing 9 green" → Task 1 Step 1 (4 tests) + existing suite. ✓
- Spec "Tests: course_logic merge test" → Task 2 Step 1. ✓
- Spec "Resolved: coverage denominator includes premium topics" → Task 1 Step 3 `slots += topics.length`; Global Constraints pins it; asserted by the premium-only test (`memberCount === 2`) and blend test (`memberCount === 12`). ✓
- Spec "Out of scope: projected/coverage display, Procedures honesty note, visual redesign" → untouched; caption is one reused-class line, `projected` formula unchanged. ✓

**2. Placeholder scan:** No TBD/TODO/"handle edge cases"/"similar to". Every code step shows complete code. ✓

**3. Type consistency:** `readiness(freeProgress, premiumProgress)` signature consistent across Task 1 (def) and Task 3 Step 9 (call). Store shape `{ right, seen }` consistent across Task 2 (`_mergeQuiz`), Task 3 (`bumpPremiumTopic`), and Task 1 (`isAttemptedPremium` reads `seen`/`right`). `_ptopic` field name consistent across the stamp (Task 3 Step 4) and the three reads (Steps 5-7). `PREMIUM_TOPIC_KEY` / `mrisim_premium_topic_progress_v1` string consistent across all files. Returned category fields (`attempted`, `memberCount`, `coverage`) match what `appendReadiness` renders (`c.attempted`, `c.memberCount` at course.js:235). ✓
