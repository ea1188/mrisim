# Cross-Device Progress Sync — Design

**Goal:** A signed-in, entitled learner's course progress (all seven `localStorage` keys) follows
them across devices, merged so switching devices never loses work.

**Status:** Approved 2026-07-07. Reconciliation = monotonic merge ("more progress wins", never lose
work). Cadence = pull-merge-push once on boot + debounced (~2s) push on change + flush on page hide.
Migration applied to Supabase via MCP with owner approval.

## Context

The paid course (`web/course.js`, gated: not-configured → signed-out → not-entitled → entitled)
keeps all progress in `localStorage`: `mrisim_curriculum` (done lessons, array), `mrisim_course_read_v1`
(read sections, map→true), `mrisim_course_quiz_v1` (per-module `{seen,right}`), `mrisim_course_exam_v1`
(`{bestPct,...}`), `mrisim_course_mastery_v1` (per-module `{passed,bestPct,attempts,ts}`),
`mrisim_course_diagnostic_v1` (`{taken,ts,perModule,order}`), `mrisim_course_review_v1` (per-prompt
`{box,due,misses,lastSeen}`). None of it syncs. `web/accounts.js` owns Supabase access
(`client()`, `getUser()`, table helpers like `logActivity`/`profile`/`myActivity`, and the export
`window.Accounts` at line 229). `course.js` loads via `loadCourse()` (~line 1076) after the
entitlement gate. `web/course_logic.js` holds pure, node-tested logic.

## Architecture

A new `course_progress` table (one jsonb `state` row per user, RLS self-scoped). The Accounts layer
gains `loadProgress()` / `saveProgress(state)`. A pure `mergeProgress(local, remote)` in
`course_logic.js` reconciles two states by "more progress wins" per key. `course.js` runs a
pull→merge→push once on boot (entitled only) and a debounced push from each save helper. All sync is
best-effort: any failure, offline, not-signed-in, or not-entitled degrades to local-only with no
blocking and no data loss.

## 1. Schema (`supabase/migrations/0005_course_progress.sql`)

```sql
create table course_progress (
  user_id uuid primary key references auth.users on delete cascade,
  state jsonb not null default '{}',
  updated_at timestamptz not null default now()
);
alter table course_progress enable row level security;
create policy course_progress_self_all on course_progress
  for all using (user_id = auth.uid()) with check (user_id = auth.uid());
```

Additive; each user reads/writes only their own row (`user_id = auth.uid()`). Applied to Supabase
(project ref idgyjmamxxyddjuaamit) via the Supabase MCP `apply_migration`.

## 2. Accounts helpers (`web/accounts.js`)

Matching the existing `logActivity`/`profile` pattern, and added to the `window.Accounts` export:

- `loadProgress()` → resolves the signed-in user's `state` object, or `null` if no row / not signed
  in / on error.
- `saveProgress(state)` → upserts `{ user_id, state, updated_at: new Date().toISOString() }` into
  `course_progress` (conflict target `user_id`). Best-effort; resolves regardless of outcome.

## 3. Merge (`web/course_logic.js`, pure + node-tested)

`mergeProgress(local, remote) -> merged` — both args are objects keyed by the seven storage keys
(each may be absent). Per-key monotonic rules:

- `mrisim_curriculum` (array of titles): union (dedup).
- `mrisim_course_read_v1` (map title→true): union of keys.
- `mrisim_course_quiz_v1` (map title→`{seen,right}`): per title, keep the record with the higher
  `seen` (ties keep local).
- `mrisim_course_exam_v1` (`{bestPct,...}`): keep the object with the higher `bestPct` (null-safe).
- `mrisim_course_mastery_v1` (map title→`{passed,bestPct,attempts,ts}`): per title, `passed = a||b`,
  `bestPct/attempts/ts = max`.
- `mrisim_course_diagnostic_v1` (`{ts,...}`): keep the object with the later `ts`.
- `mrisim_course_review_v1` (map prompt→`{box,due,misses,lastSeen}`): per prompt, keep the entry with
  the later `lastSeen`.

A key present on only one side passes through unchanged. Every rule is monotonic, so progress can
only ever increase. Added to the `course_logic.js` export.

## 4. Sync flow (`web/course.js`)

- **State accessors:** `readAllProgress()` reads the seven keys from localStorage into one object;
  `writeAllProgress(merged)` writes each key back (only the keys present in `merged`).
- **Boot (in `loadCourse`, entitled path):** `Accounts.loadProgress()` → `merged =
  CourseLogic.mergeProgress(readAllProgress(), remote || {})` → `writeAllProgress(merged)` →
  `Accounts.saveProgress(merged)`. Done before/while rendering so the dashboard reflects merged
  state. Best-effort: if `loadProgress` rejects or returns null, skip the merge and render local.
- **Push on change:** a `queueSync()` (debounced ~2s via a module timer; also flushed on `pagehide`
  and `visibilitychange==hidden`) reads `readAllProgress()` and calls `Accounts.saveProgress(...)`.
  `queueSync()` is called at the end of each save helper: `markRead`, `markDone`, `bumpScore`,
  `saveMasteryResult`, `saveExamBest`, `saveDiagnostic`, `saveReview`.
- **No-op guard:** `queueSync`/boot-sync only act when `Accounts.enabled()` and signed in; otherwise
  they return immediately (unchanged local-only behavior for the free/no-account case).

## 5. Error handling / edge cases

- **Offline / Supabase down / RLS deny:** every Accounts sync call is wrapped so a rejection is
  swallowed and the course continues on local state. No user-visible error.
- **First device, no remote row:** `loadProgress()` returns null → merge is a no-op → the first
  `saveProgress` creates the row.
- **Concurrent devices:** each pushes its full local state; because the server value is only ever
  read through `mergeProgress` on the next boot, and every rule is monotonic, neither device can
  clobber the other's gains (worst case a gain is briefly not reflected on the other device until its
  next boot-merge).
- **Storage disabled:** `readAllProgress` returns `{}`; nothing to sync.
- **Signed out / not entitled:** sync is a no-op.

## 6. Testing

- **Node unit tests** (extend `web/course_logic.test.mjs`): `mergeProgress` for each key's rule
  (union arrays/maps; higher-seen quiz; higher exam bestPct; mastery passed-OR + max; later-ts
  diagnostic; later-lastSeen review), plus one-sided-absent and both-empty cases. No browser.
- **Render/lint:** `npm run lint` clean on `course.js` + `accounts.js`; boot merge does not block
  rendering.
- **Manual two-context check** (owner, signed in): make progress in browser A, open the course in
  browser B (same account), confirm B shows the merged progress; make different progress in B, return
  to A, confirm A gains B's progress without losing its own.
- No engine/physics change; the Python suite is unaffected.

## Out of scope

- Realtime/live sync (a periodic pull or Supabase realtime) — boot-merge + push is enough.
- Conflict UI (there is no conflict to resolve under a monotonic merge).
- Syncing non-course localStorage (simulator/protocol state stays local).
