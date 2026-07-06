# Paid guided course

An optional **paid** guided curriculum layered on the free MRISim. The free simulator,
quiz, and lessons stay open (the funnel); the course adds a structured, gated learning
path plus **exclusive** premium material (extra education + ARRT MRI registry-style
questions) that non-payers cannot access.

Status: **Phase 1** (entitlements + `course_content` + accounts helpers) and the premium
content (`data/course_content.json` + seeder) are in. The gated `course.html` page is a
later phase.

## Model
- **Sell the packaged experience + exclusive material**, not the free content. The free
  lessons/quiz remain public; the course *packages* them and *adds* premium content.
- **Manual entitlement for the pilot** — no billing yet; you grant access by hand.

## How exclusivity works
Premium content lives only in Supabase, never in the public `web/` site (`build_web.py`
copies named files, not `data/*.json`, so `data/course_content.json` is never published).
Row-Level Security on `course_content` serves rows **only to entitled users**, so a
signed-out or non-entitled caller gets nothing. This is the real control — the client-side
sign-in/paywall is just UX.

## Setup

### 1. Apply the migration
Run `supabase/migrations/0002_course_entitlements.sql` (SQL editor or `supabase db push`).
It creates `entitlements` and `course_content` with the RLS above.

### 2. Seed the premium content
With the **service_role** key (Project Settings → API → `service_role`; keep it secret):

```sh
SUPABASE_URL=https://<ref>.supabase.co \
SUPABASE_SERVICE_ROLE=<service_role key> \
python scripts/seed_course_content.py
```

Re-run any time you edit `data/course_content.json` — it clears and re-inserts the
course's rows.

### 3. Grant a user access (manual, pilot)
Insert an entitlement row (service_role — SQL editor or Table editor):

```sql
insert into entitlements (user_id, course)
values ('<the user's auth uid>', 'mri-core');
```

Find the uid in Authentication → Users. The user now passes `Accounts.isEntitled('mri-core')`
and can read the premium content.

## Content
`data/course_content.json` — `{ course, items: [{ topic, kind: education|quiz, ord, body }] }`.
- **education** body: `{ title, html, keypoints[] }` — exam-focused overviews.
- **quiz** body: `{ prompt, options[4], answer, explain }` (text) — same shape as
  `web/quiz.json`; an optional `setup` can render an engine image (render-verify it, as in
  [the content bar](../docs)).
Topics use stable keys (`safety`, `patient-care`, `image-quality`, `contrast-weighting`);
the course page maps its left-rail modules to these.

## Later
Server-validated **completion certificate / CE credit**, **Stripe** self-serve billing, and
instructor-grants-access are deferred phases.
