# Instructor backend — formative MVP

An **optional** accounts layer that lets an instructor run a class on top of the
free MRISim simulator: create a class, have students join with a code, and see who
has done what. It is deliberately *formative* — it tracks practice, not trusted
grades — and it never gets in the way of the open, no-account experience that is
the project's adoption funnel.

Status: **Phase 1 (data model + access policies)** landed here as
[`supabase/migrations/0001_instructor_formative.sql`](../supabase/migrations/0001_instructor_formative.sql).
Phase 2 (front-end auth + progress sync + instructor dashboard) is next and needs a
live Supabase project to build against.

## Principles

- **The free app is untouched.** No account is required; progress still lives in
  `localStorage` exactly as today. The accounts features are additive and
  *config-gated* — absent config ⇒ they don't render, and nothing regresses.
- **No app server.** The browser talks to Supabase directly with the public
  *anon* key; **Row-Level Security** is the entire authorization model. Less code,
  less to run, less to break.
- **Formative, and honest about it.** Quiz answers ship to the client in
  `web/quiz.json` (`quiz.js` reads `q.answer`), so a browser-reported score is
  practice signal, not an exam grade — and a server *re-grade* can't fix that
  because the answer key is public. Trustworthy grades require a **server-held
  question bank**, which is a later phase, not this one.

## Architecture

```
Browser (unchanged engine, Pyodide)
  │  supabase-js (anon key)
  ▼
Supabase
  ├─ Auth (email magic-link)
  ├─ Postgres + RLS   ← profiles, classes, enrollments, activity
  └─ (later) Edge Functions for server-side grading
```

## Data model

| table | holds | key access rule (RLS) |
|-------|-------|-----------------------|
| `profiles` | one row per user; `role` (instructor/student), name, institution | read/update self; instructor may read the profiles of students in classes they own |
| `classes` | instructor-owned class + unique `join_code` | instructor: full CRUD on own; student: read classes they're in |
| `enrollments` | student ↔ class membership | student: read/leave own; instructor: read/remove for own classes |
| `activity` | append-only formative events (`quiz_attempt`, `lesson_complete`) | student: read/write own; instructor: read events stamped to a class they own |

Two `SECURITY DEFINER` functions carry the flows that a plain policy can't do
safely: `handle_new_user()` (auto-creates a profile on sign-up, role from sign-up
metadata) and `join_class(code)` (enrol by code without exposing a "look up any
class by code" policy).

## Setup — what you provide

Phase 2 can't be built or tested without these:

1. **Create a Supabase project** (free tier is plenty for a pilot).
2. **Apply the migration** — `supabase db push`, or paste
   `0001_instructor_formative.sql` into the SQL editor.
3. **Enable Email auth** (magic link) in Auth settings.
4. **Config** — drop the project URL + anon key into `web/config.js` (Phase 2 adds
   a `config.example.js`). No config ⇒ accounts UI stays hidden.
5. **FERPA posture** — storing student name + email + activity makes these
   education records. For a pilot, a signed data-use agreement + a stated
   retention window is enough; a real deployment needs a considered posture. This
   is a product/legal decision, not a code one.

## Beyond the MVP (not in this phase)

- **Graded exams** — a server-held question bank (answers never sent to the
  client) graded by an Edge Function, with attempt limits.
- **LTI 1.3** — grade passback into Canvas / Blackboard / Moodle.
- **CE credit** — completion certificates for continuing-education hours.
