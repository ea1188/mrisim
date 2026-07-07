# Course Mastery Checks + Earned Progress (Phase 1) — Design

**Goal:** Turn the existing browse-anything guided course into a guided path where each
module ends in a real mastery checkpoint, and progress is earned by learner action rather
than granted by scrolling.

**Status:** Approved 2026-07-07. Scope confirmed = "mastery check + earned progress" only
(keep the existing 10-module spine and readiness dashboard; no spine restructuring, no
linear gating).

## Context

`web/course.js` already binds premium content into an ordered path per module
(`renderTopic`: premium **Course material** cards → free **Lessons** → an inline **Test
yourself** quiz), opens on a readiness dashboard (`renderOverview`), tracks per-module
status chips (not-started / progress / review / solid), and nudges "Study next." The 16
premium `education` items are slotted across the 10 curriculum topics via the `TOPIC_CFG`
map. The 205-question premium bank has been accuracy-audited (0 answer-key errors).

Two gaps remain against the intended guided path:

1. There is no deliberate end-of-module **mastery check** — the "you've got this, move on"
   moment.
2. Progress is not earned. A section counts as *read* the instant it scrolls into view
   (`setupReadObserver`, IntersectionObserver threshold 0.2), so the readiness percentage
   inflates just by scrolling past cards.

Phase 1 closes both, reusing existing content and the existing dashboard.

## Architecture

Entirely in `web/course.js` (the existing IIFE) plus a small amount of inline CSS in
`web/course.html`. One new `localStorage` key. No backend change, no Supabase schema
migration, no new course content. The mastery check draws its questions from the premium
quiz bank already fetched via `Accounts.premiumContent` into `CTX.byTopic`.

Both `course.js` and `course.html` are network-first SHELL files in the service worker, so
online users get the fresh files without a `CACHE` version bump.

## Data model

New `localStorage` key `mrisim_course_mastery_v1`:

```json
{ "<mod.title>": { "passed": true, "bestPct": 88, "attempts": 2, "ts": 1720000000000 } }
```

Helpers, matching the existing `loadRead` / `markRead` pattern (try/catch so storage-off
degrades silently):

- `loadMastery()` → object (empty `{}` on parse failure or storage off).
- `saveMasteryResult(title, pct)` → records `passed = pct >= PASS_PCT`, keeps the best
  `bestPct`, increments `attempts`, stamps `ts`.

Constants: `PASS_PCT = 80`, `CHECK_N = 8`, `MIN_POOL = 4`.

## Components

### 1. Module question pool — `modulePool(mod)`

Returns every premium quiz *body* across `TOPIC_CFG[mod.title].premium` keys, mirroring the
existing `examPool` but scoped to one module:

```js
function modulePool(mod) {
  var cfg = TOPIC_CFG[mod.title] || { premium: [], quiz: [] };
  var pool = [];
  cfg.premium.forEach(function (key) {
    (CTX.byTopic[key] || []).forEach(function (it) { if (it.kind === "quiz") pool.push(it.body); });
  });
  return pool;
}
```

All 10 modules currently yield ≥8 questions. If a pool is `< MIN_POOL`, the module hides
the mastery check and completes on its reads + lessons alone (defensive guard only).

### 2. Mastery check UI

Rendered at the end of `renderTopic`, below the existing inline "Test yourself" practice, as
its own `sec` with anchor `mastery-<slug>` and `data-subid="m:<mod.title>"`. State-driven:

- **Unpassed, not started:** a "Take the mastery check · N questions" button. Starting
  samples `min(CHECK_N, pool.length)` questions, shuffled, and presents them inline with
  **no per-question feedback** (options selectable/deselectable, answer stored locally).
  Reuse `shuffleInts` for both question sampling and option order.
- **On submit:** compute `pct = round(100 * correct / asked)`. Call `saveMasteryResult`.
  - `pct >= PASS_PCT` → "Mastered — NN%." plus a "Retake" action.
  - `pct < PASS_PCT` → "Not yet — NN%. Review these and retry." plus the list of missed
    question prompts (with the correct answer + explanation) and a **Retry** button that
    resamples/reshuffles a fresh set from the pool.
- Every answer graded also calls `bumpScore(mod.title, correct)` so the dashboard's quiz
  accuracy reflects mastery-check performance (consistent with inline practice).
- **Already passed on load:** render directly in the "Mastered — NN%. Retake." state.

The check does not auto-advance or lock anything; it updates status and the Study-next
target.

### 3. Earned reading

Remove the scroll-based auto-tick: `setupReadObserver` no longer marks education/quiz
sections read on intersection (delete the call, or reduce the observer to a no-op and stop
observing). Each **Course material** card gains an explicit control:

- Unread: a "Mark as read" button → `markRead("e:" + b.title)` → re-render so the card shows
  its read state and the rail checkbox ticks.
- Read: a "✓ Read" indicator (the existing done styling).

Lessons already earn completion by opening and finishing in the overlay (`markDone`); no
change there.

### 4. Subsections, status, and dashboard wiring

`moduleSubsections(mod)`:

- Keep the education `read` subs (now earned by the explicit button) and the `lesson` subs.
- **Replace** the existing "Test yourself" `read` sub with a **mastery** sub:
  `{ type: "mastery", id: "m:" + mod.title, label: "Mastery check", anchor: "mastery-" + slug(mod.title) }`.
  Only add it when `modulePool(mod).length >= MIN_POOL`.

`isSubDone(s, done, read)` gains a mastery branch: `s.type === "mastery"` → `loadMastery()[mod.title]` is `passed`. (Pass `mastery` in, or read it inside, consistent with how `done`/`read` are threaded today.)

Per-module status (`computeReadiness`), tiers renamed at the top from "solid" to "mastered":

- **not-started:** nothing read, no questions seen, check not attempted.
- **review (Needs review):** mastery check attempted but not passed (`attempts > 0 && !passed`).
- **mastered (Mastered):** mastery check passed **and** all read/lesson subs done.
- **progress (In progress):** anything in between.

`STATUS_LABEL` updates `solid` → `mastered` = "Mastered" (or add a `mastered` key and drop
`solid`). "Study next" targets the first module whose status is not `mastered`.

**Dashboard overall formula is unchanged** (read 45% + quiz 40% + best mock 15%). Reads are
now earned by click and the quiz component includes mastery-check answers, so the same
formula simply reports honest numbers. Mastery-passed drives the status chip and the
Study-next gate, not the weighted percentage. This honors the "keep the dashboard" scope.

### 5. Rail

`buildRail` already renders a checkbox per sub via `isSubDone`; the mastery sub ticks when
passed with no rail-specific code beyond the `isSubDone` branch. A module header shows its
`✓` when all subs (reads + lessons + mastery) are done.

## Pure logic extraction (for testing)

Extract the status decision into a pure, DOM-free function so it can be unit-tested in node
without a browser:

```js
// inputs are plain values; no localStorage or DOM access inside.
// doneCount = number of completed subs (reads + lessons + mastery); subTotal = total subs.
function deriveModuleStatus(doneCount, subTotal, quizSeen, masteryAttempts, masteryPassed) {
  if (doneCount === 0 && quizSeen === 0 && masteryAttempts === 0) return "not-started";
  if (masteryAttempts > 0 && !masteryPassed) return "review";
  if (masteryPassed && subTotal > 0 && doneCount === subTotal) return "mastered";
  return "progress";
}
```

`computeReadiness` calls this instead of computing the tier inline. Expose the pure helpers
on a testable seam (e.g. `window.CourseLogic = { deriveModuleStatus: ... }` guarded so it
does not leak production behavior, plus a tiny CommonJS-style export the node test can
require). The pass computation (`pct >= PASS_PCT`) is trivial and covered by the same test.

## Error handling and edge cases

- **Storage disabled / private mode:** all `localStorage` access stays in try/catch; a
  mastery result simply does not persist, matching current `markRead` behavior.
- **Pool `< MIN_POOL`:** module hides the mastery check and its mastery sub; it completes on
  reads + lessons (guard only; no live module hits this today).
- **Retry:** resamples and reshuffles so answer positions cannot be memorized across
  attempts.
- **Signing out / switching device:** state is local-only in Phase 1 (server-side sync is a
  later roadmap item), consistent with all existing course progress.

## Testing

- **Node unit test** (`web/course_logic.test.mjs` or the existing test convention): cover
  `deriveModuleStatus` across the four tiers and the pass boundary (79% fails, 80% passes).
  No browser, so it runs fast in CI alongside the other `web/*.mjs` checks.
- **Manual signed-in checklist** (owner via magic link — the course is auth-gated, as all
  course verification has been): open a module, mark a card read (confirm scroll alone no
  longer ticks it), take the mastery check, fail it, use Retry, then pass it; confirm the
  status chip flips to Mastered, the rail checkbox ticks, and Study-next advances to the
  next non-mastered module.
- Existing web smoke tests (`home_smoke`, `smoke`, `protocol_smoke`, `quiz_smoke`) are
  unaffected; none exercises the gated course.

## Deployment

Push to `main`; GitHub Pages serves the updated `web/` via the existing workflow. No
`data/lessons.json` change, so the `deploy-web` lessons rebuild is not needed. No SW cache
bump (both changed files are network-first SHELL entries). No Supabase change.

## Out of scope (later phases)

- Held-out mastery question sets distinct from practice (Phase 3 assessment).
- Server-side / cross-device progress sync (roadmap item 4).
- Spine restructuring around the 16 premium modules; linear module gating.
- Any new content authoring (Phase 2 depth).
