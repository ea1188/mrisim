# Registry-readiness premium blend — design

**Goal:** Make the course-page "Registry readiness" panel reflect the paid, ARRT-weighted
premium quiz bank, not just the free 100-question diagnostic. User decision (2026-07-09):
**blend free + premium** per ARRT category.

## Why
The premium bank is now fully ARRT-weighted (538 Q, topic-count rebalance batches
1–5). But `web/blueprint.js readiness()` reads only the FREE pool
(`mrisim_quiz_progress_v1`), so a paying student grinding premium sees zero movement in
their readiness. Highest-value credibility fix now that the premium weighting exists.

## Current storage (verified in course.js)
- **Free quiz** → `mrisim_quiz_progress_v1` = `{ freeCategory: { best, total, runs } }`
  (written by quiz.js). Blueprint members are these free categories.
- **Premium quiz** (mastery checks, per-module quiz, practice exam) → `bumpScore()` writes
  `mrisim_course_quiz_v1` = `{ moduleTitle: { right, seen } }` — **per module**, synced via
  `queueSync()`. `recordAnswer()` only feeds the spaced-review queue, not an accuracy store.

## The constraint (why this is not a one-line readiness tweak)
ARRT categories do not align to curriculum modules. Per `TOPIC_CFG`, modules **8**
(`flow-artifacts` → Image Production, `procedures-vascular` → Procedures) and **10**
(`safety` → Safety, `patient-care`/`contrast-agents` → Patient Care) each straddle two ARRT
categories, but `mrisim_course_quiz_v1` aggregates their answers per module. So module-level
premium signal cannot be cleanly attributed to ARRT categories. A correct blend needs
**per-premium-topic** accuracy, which is not stored today.

## Approach (recommended)
1. **Record premium answers by topic.** Add a synced store
   `mrisim_premium_topic_progress_v1 = { premiumTopic: { right, seen } }`, bumped wherever a
   premium quiz item is graded (the three `bumpScore(...)` call sites: per-module quiz ~642,
   mastery ~713, exam ~912). Requires the item's `topic` at grade time — TASK 1 verifies it is
   in scope (item wrapper carries `topic`; the `.q` body may not — thread it through if needed).
   Keep `bumpScore`/`mrisim_course_quiz_v1` as-is (module completion logic depends on it);
   this is an ADDITIVE second store.
2. **Add the premium→ARRT map to blueprint.js**, audited to match `project_quiz_rebalance`:
   Image Production = instrumentation, pulse-sequences, data-acquisition, contrast-weighting,
   image-quality, flow-artifacts, fat-suppression, three-d-recon. Procedures =
   procedures-anatomy, procedures-protocols, procedures-vascular, pathology. Safety = safety.
   Patient Care = patient-care, contrast-agents.
3. **Extend `readiness(freeProgress, premiumProgress)`** (second arg optional → back-compatible).
   For each ARRT category, sum (right, asked) across BOTH its free-category members and its
   premium-topic members, accuracy = Σright/Σasked over attempted sources. Coverage: decide
   whether to count premium topics toward the coverage denominator (recommend: yes, so grinding
   premium raises coverage). `projected` unchanged formula (unattempted = 0, can't be gamed).
4. **course.js** `appendReadiness()` passes both stores; add a one-line caption that the panel
   now reflects free + premium quiz performance.
5. **Cross-device sync:** `mrisim_premium_topic_progress_v1` should ride the same sync path as
   `mrisim_course_quiz_v1` (add to `PROGRESS_KEYS` + merge logic). Confirm the merge is
   monotonic (max right/seen) like other counters.

## Tests
- blueprint.test.mjs: extend for the 2-arg `readiness`; premium-only progress; free+premium
  blend hand-math; premium→ARRT map integrity (every premium topic mapped once). Keep all 9
  existing free-only cases green (2nd arg omitted).
- A course_logic test for the premium-topic merge if merge logic is added there.

## Out of scope
Changing how `projected`/`coverage` are displayed; the Procedures honesty note (still true —
positioning/coils/protocol have no quiz signal). No visual redesign.

## Resolved: coverage denominator (2026-07-09)
Premium topics **count toward** per-category coverage. Rationale: a paying student grinding
the premium bank should see the coverage ring fill; keeping coverage free-pool-only would make
the panel look stalled for exactly the students doing the most work. So each category's coverage
= (attempted free members + attempted premium topics) / (total free members + total premium
topics). Attempting either kind of source counts once. `projected` (the weighted accuracy
headline) is unchanged: unattempted categories still contribute 0, so grinding one low-weight
source cannot inflate it.
