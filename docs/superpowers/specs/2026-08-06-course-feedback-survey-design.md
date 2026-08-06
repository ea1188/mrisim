# Course feedback survey — design

**Date:** 2026-08-06
**Status:** approved (design), pending implementation plan
**Author:** brainstormed with the owner

## Purpose

Collect **end-of-course feedback** from the first cohort (modules due through late
Aug 2026) to improve the program. Focus is program improvement, not grading or
student knowledge. Responses are **anonymous**.

## Decisions (locked)

- **Type:** end-of-course feedback survey (taken after the modules wrap).
- **Delivery:** a standalone, shareable page (`mrisimlab.com/feedback.html`) — same
  served-root pattern as `web/walkthrough.html` / `web/course.html`. Shared by link,
  not linked from the nav (a nav/email link is an optional follow-up).
- **Access:** sign-in required (uses the existing `window.Accounts` Supabase auth)
  so only real, signed-in users can submit — but the identity is **not stored**.
- **Anonymity:** the stored row carries **no `user_id`** and no PII. This is
  enforced structurally (the table has no user column) and by RLS (clients can
  `INSERT` but never `SELECT`). Trade-off accepted: no dedup, no correlation with a
  student's progress, a person could submit twice.
- **Results:** the owner reads responses in the **Supabase dashboard** (SQL / CSV,
  service_role). No in-app owner results page in this iteration.

## Question set

Short (~2–3 min). One page, submit at the end.

**Overall**
1. `recommend` — "How likely are you to recommend this course to a classmate?" — integer 0–10 (NPS).
2. `prepared` — "How well did the course prepare you for what you needed?" — integer 1–5.
3. `pace` — "Pace over the 4 weeks" — enum: `too_slow` | `about_right` | `too_fast`.
4. `workload` — "Workload" — enum: `too_light` | `about_right` | `too_heavy`.

**How useful was each part?** — each integer 1–5 (allow "didn't use" = null/0)
5. `useful_simulator` · 6. `useful_planner` · 7. `useful_quiz` · 8. `useful_lessons` · 9. `useful_reference`

**Modules**
10. `hardest_module` — "Which module was hardest to follow?" — enum of the 10 module
    titles + `none`. Stored as a short stable key (e.g. `m1`…`m10`, `none`), not the
    display string, so re-labeling a module doesn't break stored data.

**Open-ended** (free text, each capped, e.g. 2000 chars; all optional)
11. `helped_most` · 12. `improve` · 13. `other`

All questions optional client-side except we require at least one answer to submit
(prevents empty spam rows); exact required set finalized in the plan.

## Data model

New migration `supabase/migrations/0015_course_feedback.sql`:

```sql
create table course_feedback (
  id           uuid primary key default gen_random_uuid(),
  cohort       text not null default '2026-08',   -- separates future classes
  recommend    smallint check (recommend between 0 and 10),
  prepared     smallint check (prepared between 1 and 5),
  pace         text check (pace in ('too_slow','about_right','too_fast')),
  workload     text check (workload in ('too_light','about_right','too_heavy')),
  useful_simulator smallint check (useful_simulator between 0 and 5),
  useful_planner   smallint check (useful_planner between 0 and 5),
  useful_quiz      smallint check (useful_quiz between 0 and 5),
  useful_lessons   smallint check (useful_lessons between 0 and 5),
  useful_reference smallint check (useful_reference between 0 and 5),
  hardest_module   text,          -- 'm1'..'m10' | 'none' | null
  helped_most  text,
  improve      text,
  other        text,
  created_at   timestamptz not null default now()
);

alter table course_feedback enable row level security;

-- Authenticated users may INSERT. No one may SELECT/UPDATE/DELETE via the client
-- (anonymity: the owner reads with the service_role in the dashboard).
create policy course_feedback_insert on course_feedback
  for insert to authenticated with check (true);
```

Notes: `cohort` default keeps the first class isolated from later runs. No `user_id`
column at all — anonymity can't regress by accident. Free-text length is enforced
client-side and (optionally) with a `check (char_length(...) <= 2000)` per text
column, TBD in the plan.

## Components

- **`web/feedback.html`** — self-contained page: inline styles matching the site
  theme (reuse `styles.css` + `theme.css` + a small inline block like the other
  pages), the form markup, sign-in gate container, thank-you state. Loads
  `config.js`, `accounts.js`, `feedback.js`.
- **`web/feedback.js`** — reads the form, validates (at least one answer; numeric
  ranges; text caps), builds the payload, calls a new
  `Accounts.submitCourseFeedback(payload)`, shows success/error. Gate: if signed
  out, show "Sign in to leave feedback" with the Google button (reuse the existing
  accounts sign-in call used elsewhere).
- **`window.Accounts.submitCourseFeedback(payload)`** in `web/accounts.js` — mirrors
  the existing `insert` helpers (e.g. `logActivity`): `client().from('course_feedback').insert(payload)`, returns `{error}`; never throws to the caller.
- **`web/sw.js`** — no change required (page is network-served; navigations are
  network-first). Not added to the precache SHELL.

## Data flow

open link → `accounts.js` session check → (signed out) sign-in prompt → (signed in)
render form → user fills → validate client-side → `submitCourseFeedback` → one
`INSERT` (RLS: `authenticated` allowed) → thank-you state. Owner later runs a query
in the Supabase dashboard.

## Reading results (owner, dashboard)

Ship a short `docs/` note (or a comment block) with ready-made queries:
- NPS: `% promoters (9–10) − % detractors (0–6)` over `recommend`.
- Averages of `prepared` and each `useful_*` (ignoring nulls/0).
- `pace` / `workload` distributions.
- `hardest_module` counts.
- Latest free-text (`helped_most` / `improve` / `other`).
All filtered by `cohort = '2026-08'`.

## Error handling

- Insert failure: show a non-technical error ("Couldn't submit — please try again")
  and keep the form filled so nothing is lost. Log the real error to console only.
- Signed-out submit is impossible (form gated), but the RLS `authenticated` check is
  the real guard.
- Double-submit: allowed by design (anonymity > dedup). The UI disables the button
  after a successful submit and shows the thank-you state to discourage it.

## Testing

- **`web/feedback.test.mjs`** — unit-test the pure validation/payload builder
  (mirrors `assignments.test.mjs`): rejects an all-empty form, clamps/validates
  numeric ranges, maps enum choices to stored keys, caps text length, and produces a
  correct payload for a filled form.
- **Guard:** a lightweight check that `feedback.html` references `feedback.js` +
  `accounts.js` and that migration `0015` exists (optional; finalize in plan).
- No engine / Python involvement.

## Out of scope (this iteration)

- In-app owner results page / charts (dashboard queries suffice for the first class).
- Nav or onboarding-email link to the survey (can add after it's validated).
- Per-module or recurring pulse surveys (this is a one-time end-of-course form).
- Dedup / one-submission-per-student (conflicts with anonymity).

## Deploy

Static page → live on the next site deploy at `mrisimlab.com/feedback.html`. The
migration must be applied to Supabase (owner runs it, like the seed steps) before
submissions can succeed.
